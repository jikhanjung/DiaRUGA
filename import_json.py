#!/usr/bin/env python3
"""지금까지의 JSON 산출물을 DB 로 옮긴다. 설계는 devlog/20260730_P02_db-schema.md.

    python import_json.py            # 전부
    python import_json.py --slide rs23
    python import_json.py --skip-xml # XML 345개 읽기를 건너뛴다 (빠르다)

**멱등이다** — 다시 돌려도 같은 결과가 된다(mask_key·이름·idx 로 맞춘다). JSON 은
지우지 않는다. 이전이 맞았는지 `verify_db.py` 로 대조한 뒤에야 다음 단계로 간다.

읽는 것:
    groups_*.json               -> Slide, Viewpoint, Frame
    <사진>.jpg_metadata.xml     -> Frame.um_per_pixel, acquired_at
    stacked/*_scale.json        -> Stack (배율)
    stacked/stack_report.json   -> Stack (합성 품질)
    out/*_candidates.json       -> ThresholdSet, Detection, Candidate
    review/*_review.json        -> ViewpointReview, ObjectReview
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import django

# 이 스크립트는 저장소 밖(/srv/DiaRUGA/scripts)에 복사해 두고 컨테이너 안에서
# 돌릴 수도 있다. 그때 Django 코드가 어디 있는지는 DIARUGA_APP 이 알려 준다 —
# 이미지 안의 /app 이고, 뷰어 컨테이너가 쓰는 바로 그 코드다. 저장소에서 그냥
# 돌리면 예전처럼 자기 옆의 web/ 을 본다.
APP = Path(os.environ.get("DIARUGA_APP") or Path(__file__).resolve().parent)
sys.path.insert(0, str(APP / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.conf import settings                                    # noqa: E402
from django.db import transaction                                   # noqa: E402
from django.utils import timezone                                   # noqa: E402

from viewer.images import (ensure_frame_image, ensure_image,
                          ensure_stack_images)
from viewer.models import (Candidate, ClassDef, Core, Detection,     # noqa: E402
                           Frame, ObjectReview, Run, Setting, Site,
                           Slide, Stack, ThresholdSet, Viewpoint,
                           ViewpointReview)

sys.path.insert(0, str(APP))
import zen_meta                                                     # noqa: E402

ROOT = Path(settings.DATA_ROOT)

# 지금 data.py 에 하드코딩된 분류 정의. 색은 base.html 에 흩어져 있던 값이다.
CLASS_SEED = [
    ("round", "원형", "on", "60,220,120", False),
    ("round_frag", "원형 파편", "frag", "60,205,205", False),
    ("rod", "봉상", "rod", "70,140,255", False),
    ("rod_frag", "봉상 파편", "frag", "160,120,255", False),
    ("eucampia", "Eucampia", "euc", "255,110,190", True),
]


def rel(p) -> str:
    """DATA_ROOT 기준 상대경로. JSON 에 절대경로가 적혀 있어도 맞춘다."""
    p = Path(p)
    if not p.is_absolute():
        return str(p)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# "RS23-GC03 71cm" -> 지역 RS23 · 코어 GC03 · 깊이 71cm
SAMPLE_NAME = re.compile(
    r"^\s*(?P<site>[A-Za-z]+\d*)-(?P<core>[A-Za-z]+\d*)"
    r"(?:\s+(?P<depth>[\d.]+)\s*cm)?", re.I)


def parse_sample_name(name: str):
    """폴더명에서 지역·코어·깊이를 뽑는다. 못 읽으면 (None, None, None).

    통짜 문자열로 두면 깊이순 정렬도 지역별 묶음도 안 된다 — 같은 코어의 깊이
    변화와 지역별 차이가 이 시료의 분석 목적이다.
    """
    m = SAMPLE_NAME.match(name or "")
    if not m:
        return None, None, None
    depth = m.group("depth")
    return (m.group("site").upper(), m.group("core").upper(),
            float(depth) if depth else None)


# 관찰 접미사 `(1)`·`(2)`. **정본은 `group_focus_series.parse_obs_no` 다** —
# 고칠 때 둘을 함께 본다. 여기서 임포트하지 않는 이유는 그 모듈이 cv2 를 끌고
# 오기 때문이다(이 스크립트는 그것 없이 도는 자리에서도 불린다). `parse_sample_name`
# 이 이미 같은 이유로 두 벌이다.
OBS_SUFFIX = re.compile(r"\s*\((\d+)\)\s*$")


def parse_obs_no(folder: str) -> int:
    m = OBS_SUFFIX.search(folder or "")
    return int(m.group(1)) if m else 0


def mask_key(bbox) -> str:
    """review/*.json 과 뷰어 keyOf() 가 쓰는 규칙과 같아야 한다."""
    return "_".join(str(int(v)) for v in bbox)


def new_run(kind, **params):
    return Run.objects.create(
        kind=kind, status="running", params=params,
        host=socket.gethostname(),
        code_version=git_version(),
    )


def git_version():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# --- 설정 -----------------------------------------------------------------
def seed_settings():
    for i, (key, label, badge, color, taxon) in enumerate(CLASS_SEED):
        ClassDef.objects.update_or_create(
            key=key,
            defaults=dict(label=label, badge=badge, color=color,
                          is_taxon=taxon, sort_order=i, active=True))
    Setting.objects.update_or_create(
        key="upright_min_ratio",
        defaults={"value": 1.15})
    Setting.objects.update_or_create(
        key="crops_per_page",
        defaults={"value": 500})
    print(f"  분류 정의 {ClassDef.objects.count()}개 · 설정 {Setting.objects.count()}개")


def threshold_set_for(th: dict) -> ThresholdSet:
    """같은 문턱 조합이면 한 행을 공유한다 — 결과마다 복사되던 것을 모은다."""
    fields = {f: th.get(f) for f in ThresholdSet.FIELDS if th.get(f) is not None}
    found = ThresholdSet.objects.filter(**fields).first()
    if found:
        return found
    name = f"areolae {fields.get('round_texture_min', '-')}"
    return ThresholdSet.objects.create(name=name, note="import_json 이 만들었다",
                                       **fields)


# --- 1) groups_*.json -----------------------------------------------------
def import_slides(only=None, read_xml=True):
    run = new_run("ingest", part="slides", read_xml=read_xml)
    n_sl = n_vp = n_fr = n_xml = 0
    for path in sorted(ROOT.glob("groups_*.json")):
        slug = path.stem.removeprefix("groups_").lower()
        if only and slug != only:
            continue
        meta = json.loads(path.read_text(encoding="utf-8"))
        image_dir = meta["dir"]
        folder = Path(image_dir).name
        site_code, core_code, depth = parse_sample_name(folder)
        core = None
        if site_code and core_code:
            site, _ = Site.objects.get_or_create(code=site_code)
            core, _ = Core.objects.get_or_create(site=site, code=core_code)
        slide, _ = Slide.objects.update_or_create(
            slug=slug,
            defaults=dict(name=folder, image_dir=image_dir, core=core,
                          depth_cm=depth, obs_no=parse_obs_no(folder),
                          corr_thresh=meta.get("corr_thresh"), state="done"))
        n_sl += 1

        seq = 0
        for g in meta["groups"]:
            images = g["images"]
            tag = f"g{g['id']:03d}_{images[0]}-{images[-1].split('-')[-1]}"
            vp, _ = Viewpoint.objects.update_or_create(
                slide=slide, idx=g["id"],
                defaults=dict(tag=tag, n_frames=g["n"],
                              span_sec=g.get("span_sec"), grouping_run=run))
            n_vp += 1
            sharp = g.get("sharpness") or {}
            for name in images:
                jpg = ROOT / image_dir / f"{name}.jpg"
                fr, _ = Frame.objects.update_or_create(
                    slide=slide, name=name,
                    defaults=dict(viewpoint=vp, path=rel(jpg), seq=seq,
                                  sharpness=sharp.get(name),
                                  is_sharpest=(name == g.get("sharpest"))))
                ensure_frame_image(fr)
                seq += 1
                n_fr += 1
                if read_xml and jpg.exists():
                    sc = zen_meta.scaling_for(jpg)
                    ts = zen_meta.read_timestamp(jpg)
                    if sc["source"] != "default" or ts:
                        fr.um_per_pixel = sc["um_per_pixel"]
                        fr.um_per_pixel_source = sc["source"]
                        fr.acquired_at = ts
                        fr.save(update_fields=["um_per_pixel",
                                               "um_per_pixel_source",
                                               "acquired_at"])
                        n_xml += 1
            if g.get("sharpest"):
                vp.sharpest_frame = Frame.objects.filter(
                    slide=slide, name=g["sharpest"]).first()
                vp.save(update_fields=["sharpest_frame"])

    run.status = "done"
    run.finished_at = timezone.now()
    run.counts = {"slides": n_sl, "viewpoints": n_vp, "frames": n_fr, "xml": n_xml}
    run.save()
    print(f"  슬라이드 {n_sl} · 시야 {n_vp} · 프레임 {n_fr} (XML 읽음 {n_xml})")
    for c in Core.objects.select_related("site"):
        depths = sorted(d for d in c.slides.values_list("depth_cm", flat=True) if d)
        print(f"  {c.site.code} · 코어 {c.code} · 깊이 "
              f"{', '.join(f'{d:g}cm' for d in depths) or '-'}")


# --- 2) stacked/ ----------------------------------------------------------
def import_stacks():
    run = new_run("ingest", part="stacks")
    report = {}
    rp = ROOT / settings.STACK_DIR / "stack_report.json"
    if rp.exists():
        for row in json.loads(rp.read_text(encoding="utf-8")):
            report[row["tag"]] = row

    n = 0
    for vp in Viewpoint.objects.select_related("slide"):
        focused = ROOT / settings.STACK_DIR / f"{vp.tag}_focused.jpg"
        if not focused.exists():
            continue
        depth = ROOT / settings.STACK_DIR / f"{vp.tag}_depth.jpg"
        npz = ROOT / settings.STACK_DIR / f"{vp.tag}_depth.npz"
        side = zen_meta.scale_sidecar(focused)
        sc = {}
        if side.exists():
            sc = json.loads(side.read_text(encoding="utf-8"))
        r = report.get(vp.tag, {})
        ref = (Frame.objects.filter(slide=vp.slide, name=r["ref"]).first()
               if r.get("ref") else None)
        st, _ = Stack.objects.update_or_create(
            viewpoint=vp,
            defaults=dict(
                focused_path=rel(focused),
                depth_path=rel(depth) if depth.exists() else "",
                depth_npz_path=rel(npz) if npz.exists() else "",
                um_per_pixel=sc.get("um_per_pixel"),
                native_um_per_pixel=sc.get("native_um_per_pixel"),
                resize_scale=sc.get("resize_scale") or 1.0,
                um_per_pixel_source=sc.get("source") or "",
                ref_frame=ref,
                align_failed=r.get("align_failed") or 0,
                object_px_frac=r.get("object_px_frac"),
                sharpness_best_single=r.get("sharpness_best_single"),
                sharpness_fused=r.get("sharpness_fused"),
                gain=r.get("gain"),
                run=run))
        ensure_stack_images(st)
        n += 1
    run.status = "done"
    run.finished_at = timezone.now()
    run.counts = {"stacks": n, "report_rows": len(report)}
    run.save()
    print(f"  합성본 {n}개 (stack_report 항목 {len(report)}개 — "
          f"덮어써져 일부만 남아 있다)")


# --- 3) out/*_candidates.json --------------------------------------------
NUM = ("area_um2", "major_um", "minor_um", "long_side_um", "short_side_um",
       "aspect_ratio", "fill_ratio", "circularity", "convexity", "solidity",
       "elongation", "ellipse_iou", "texture", "predicted_iou",
       "stability_score")


def find_viewpoint(stem: str):
    """검출 JSON 의 stem 으로 시야를 찾는다.

    합성본은 `<tag>_focused`, 싱글턴은 프레임 이름(`Snap-21171`)이다.
    """
    if stem.endswith("_focused"):
        tag = stem[: -len("_focused")]
        vp = Viewpoint.objects.filter(tag=tag).first()
        return vp, "stack", None
    fr = Frame.objects.filter(name=stem).select_related("viewpoint").first()
    if fr and fr.viewpoint:
        return fr.viewpoint, "frame", fr
    return None, None, None


def import_detections():
    run = new_run("ingest", part="detections")
    n_det = n_cand = 0
    missing = []
    for path in sorted((ROOT / "out").glob("*_candidates.json")):
        stem = path.name[: -len("_candidates.json")]
        vp, target, frame = find_viewpoint(stem)
        if vp is None:
            missing.append(stem)
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        ts = threshold_set_for(d.get("thresholds") or {})

        image = ensure_image(rel(d.get("image") or ""),
                             "frame" if target == "frame" else "stack",
                             viewpoint=vp, frame=frame,
                             stack=getattr(vp, "stack", None) if target == "stack" else None)
        det, _ = Detection.objects.update_or_create(
            viewpoint=vp, image=image,
            defaults=dict(
                image_path=rel(d.get("image") or ""),
                width=(d.get("size") or [None, None])[0],
                height=(d.get("size") or [None, None])[1],
                scale=d.get("scale") or 1.0,
                um_per_pixel=d.get("um_per_pixel"),
                um_per_pixel_native=d.get("um_per_pixel_native"),
                um_per_pixel_source=d.get("um_per_pixel_source") or "",
                um_per_pixel_backfilled=bool(d.get("um_per_pixel_backfilled")),
                n_raw_masks=d.get("n_raw_masks") or 0,
                n_sized=d.get("n_sized") or 0,
                thresholds=ts, run=run, is_current=True))
        n_det += 1

        # 멱등: 이 검출의 후보를 다시 만든다. 교정은 mask_key 로 붙으므로
        # 후보를 지워도 사람의 판단은 사라지지 않는다.
        det.candidates.all().delete()
        rows = []
        for passed, pool in ((True, d.get("candidates") or []),
                             (False, d.get("rejected") or [])):
            for c in pool:
                b = c["bbox_xywh"]
                ctr = c.get("center_xy") or [None, None]
                rows.append(Candidate(
                    detection=det, mask_key=mask_key(b), raw_id=c.get("id"),
                    bbox_x=int(b[0]), bbox_y=int(b[1]),
                    bbox_w=int(b[2]), bbox_h=int(b[3]),
                    center_x=ctr[0], center_y=ctr[1],
                    area_px=c.get("area_px") or 0,
                    shape_ok=bool(c.get("shape_ok")),
                    polygon=c.get("polygon") or [],
                    passed=passed,
                    # 중첩정리로 떨어진 것은 탈락분인데도 cls 를 갖고 있다 —
                    # 판정을 통과한 뒤 정리됐기 때문이다. 그대로 담는다.
                    cls=c.get("cls") or "",
                    reject=(c.get("reject") or "") if not passed else "",
                    **{f: c.get(f) for f in NUM}))
        # 같은 bbox 가 두 번 나오면(중복 마스크) unique 에 걸린다 — 첫 것만 둔다
        seen, uniq = set(), []
        for r in rows:
            if r.mask_key in seen:
                continue
            seen.add(r.mask_key)
            uniq.append(r)
        Candidate.objects.bulk_create(uniq, batch_size=2000)
        n_cand += len(uniq)
        if len(uniq) != len(rows):
            print(f"    {stem}: 같은 bbox 중복 {len(rows) - len(uniq)}개를 합쳤다")

    run.status = "done"
    run.finished_at = timezone.now()
    run.counts = {"detections": n_det, "candidates": n_cand}
    run.save()
    print(f"  검출 {n_det}개 · 개체 {n_cand}개 · 문턱 조합 {ThresholdSet.objects.count()}개")
    if missing:
        print(f"  [확인필요] 시야를 찾지 못한 검출 {len(missing)}개: {missing[:5]}")


# --- 4) review/*_review.json ---------------------------------------------
def import_reviews():
    run = new_run("ingest", part="reviews")
    n_vp = n_obj = 0
    bind = {"exact": 0, "orphan": 0}
    missing = []
    for path in sorted((Path(settings.REVIEW_ROOT) / settings.REVIEW_DIR).glob("*_review.json")):
        stem = path.name[: -len("_review.json")]
        vp, _, _ = find_viewpoint(stem)
        if vp is None:
            missing.append(stem)
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        ViewpointReview.objects.update_or_create(
            viewpoint=vp,
            defaults=dict(done=bool(d.get("done")),
                          note=(d.get("note") or "").strip()))
        n_vp += 1

        # 이 시야의 현재 검출에서 mask_key -> Candidate 를 미리 뽑아 둔다
        det = vp.detections.filter(is_current=True).first()
        by_key = ({c.mask_key: c for c in det.candidates.all()} if det else {})

        keys = set(d.get("removed") or []) | set(d.get("accepted") or [])
        keys |= set((d.get("labels") or {}))
        keys |= set((d.get("notes") or {}))
        for key in sorted(keys):
            cand = by_key.get(key)
            geom = {}
            if cand:
                geom = {"bbox": cand.bbox_xywh, "polygon": cand.polygon}
            method = "exact" if cand else "orphan"
            bind[method] += 1
            ObjectReview.objects.update_or_create(
                viewpoint=vp, mask_key=key,
                defaults=dict(
                    candidate=cand, bind_method=method,
                    bind_score=1.0 if cand else None, geom=geom,
                    removed=key in set(d.get("removed") or []),
                    accepted=key in set(d.get("accepted") or []),
                    label=(d.get("labels") or {}).get(key, ""),
                    note=(d.get("notes") or {}).get(key, "")))
            n_obj += 1

    run.status = "done"
    run.finished_at = timezone.now()
    run.counts = {"viewpoint_reviews": n_vp, "object_reviews": n_obj, **bind}
    run.save()
    print(f"  시야 교정 {n_vp}개 · 개체 교정 {n_obj}개 "
          f"(exact {bind['exact']} · orphan {bind['orphan']})")
    if bind["orphan"]:
        print("  [주의] orphan 이 있다. 이전 직후에는 전부 exact 여야 한다 (P02 §5-3)")
    if missing:
        print(f"  [확인필요] 시야를 찾지 못한 교정 {len(missing)}개: {missing[:5]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slide", help="이 슬러그만")
    ap.add_argument("--skip-xml", action="store_true",
                    help="XML 345개 읽기를 건너뛴다")
    args = ap.parse_args()

    print(f"DB: {settings.DIARUGA_DB}")
    with transaction.atomic():
        print("설정")
        seed_settings()
        print("1) groups_*.json")
        import_slides(args.slide, read_xml=not args.skip_xml)
        print("2) stacked/")
        import_stacks()
        print("3) out/*_candidates.json")
        import_detections()
        print("4) review/*_review.json")
        import_reviews()
    print("\n끝났다. 이어서 대조한다: python verify_db.py")


if __name__ == "__main__":
    main()
