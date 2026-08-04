#!/usr/bin/env python3
"""같은 위치를 초점만 바꿔 찍은 사진들을 하나의 그룹으로 묶는다.

XML에 스테이지 XY/Z 좌표가 기록돼 있지 않으므로 이미지 내용으로 판단한다.
초점이 달라지면 고주파(선명도)는 크게 변하지만 입자들의 배치는 그대로이므로,
축소 + 가우시안 블러로 고주파를 죽인 뒤 정규화 상관계수를 비교하면
초점 변화에 둔감하고 시야 이동에는 민감한 지문이 된다.

촬영 시각 간격을 보조 신호로 함께 쓴다 (그룹 내부는 촘촘, 시야 이동 시 벌어짐).

사용 예:
    python group_focus_series.py "/data3/diatom/photos/260731/RS23-GC03 369cm" --dry-run
    python group_focus_series.py "/data3/diatom/photos/260731/RS23-GC03 369cm"

DB 로 옮기면서 달라진 것 (P02 6단계 마지막):

- `Slide`·`Viewpoint`·`Frame` 행을 직접 만든다. `groups_*.json` 은 내보내기로만 남는다
- **이미 검출하거나 교정한 슬라이드는 `--force` 없이 다시 묶지 않는다.** 재그룹핑은
  `Viewpoint` 를 재편하므로 그 아래 검출·교정이 통째로 어긋난다. 이 스크립트가
  6단계의 **마지막**인 이유가 그것이다
- **분포가 양분되지 않으면 사람을 부른다** (P01 §1). 그룹 안의 최소 상관과 경계의
  최대 상관 사이가 벌어져 있어야 임계값이 의미가 있다. 좁으면 `state="failed"` 로
  남기고 넘어가지 않는다 — 잘못 묶인 시야 위에 쌓은 검출과 교정은 되돌리기가 훨씬 비싸다
"""
import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import django

# 이 스크립트는 저장소 밖(/srv/diatom/scripts)에 복사해 두고 컨테이너 안에서
# 돌릴 수도 있다. 그때 Django 코드가 어디 있는지는 DIATOM_APP 이 알려 준다 —
# 이미지 안의 /app 이고, 뷰어 컨테이너가 쓰는 바로 그 코드다. 저장소에서 그냥
# 돌리면 예전처럼 자기 옆의 web/ 을 본다.
APP = Path(os.environ.get("DIATOM_APP") or Path(__file__).resolve().parent)
sys.path.insert(0, str(APP / "web"))
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diatomweb.settings")
django.setup()

from django.conf import settings                                    # noqa: E402
from django.db import transaction                                   # noqa: E402
from django.utils import timezone                                   # noqa: E402

import zen_meta                                                     # noqa: E402
import runlog                                                       # noqa: E402
from viewer.models import (Core, Frame, Site, Slide, Viewpoint)     # noqa: E402
# XML 을 찾는 규칙은 zen_meta 한 곳에만 둔다
from zen_meta import read_timestamp                                 # noqa: E402

THUMB_W = 256

# "RS23-GC03 71cm" -> 지역 RS23 · 코어 GC03 · 깊이 71cm (import_json.py 와 같다)
import re                                                           # noqa: E402
SAMPLE_NAME = re.compile(
    r"^(?P<site>[A-Za-z0-9]+)-(?P<core>[A-Za-z0-9]+)\s+(?P<depth>[\d.]+)\s*cm",
    re.IGNORECASE)


def parse_sample_name(folder: str):
    m = SAMPLE_NAME.match(folder)
    if not m:
        return None, None, None
    d = m.group("depth")
    return (m.group("site").upper(), m.group("core").upper(),
            float(d) if d else None)


def git_version():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=Path(__file__).resolve().parent)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def rel(p) -> str:
    """DATA_ROOT 기준 상대경로. DB 는 이 형태로만 경로를 담는다."""
    p = Path(p)
    if not p.is_absolute():
        return str(p)
    try:
        return str(p.relative_to(Path(settings.DATA_ROOT)))
    except ValueError:
        return str(p)


def separability(corrs, groups, thresh):
    """임계값이 이 슬라이드에서 의미가 있는가.

    "0.55 이상이면 같은 시야" 라는 규칙은 **그룹 안 상관과 경계 상관이 겹치지
    않을 때만** 성립한다. 겹치면 임계값을 어디에 두든 잘못 묶이는 쌍이 생긴다.

    처음에는 `min(그룹안) - max(경계)` 를 재고 그 값이 작으면 미심쩍다고 봤다.
    **틀린 기준이었다.** 최솟값·최댓값은 꼬리라서 표본이 많을수록 나빠진다 —
    실측에서 그룹 쌍이 1개뿐인 슬라이드가 만점(0.9957)을 받고, 34개인 슬라이드가
    최악 하나 때문에 걸렸다. 그런데 그 슬라이드는 사람이 확인하니 **정상이었다.**

        AM22 25cm 그룹 안 34쌍: 0.594 0.623 0.629 0.723 | 0.986 … 0.998
                   경계 25쌍:  … 0.475 0.494
                               └ 0.494~0.594 사이는 완전히 비어 있다

    겹치는 쌍이 하나도 없다. 분포는 깨끗하게 양분돼 있었고 내가 양 끝만 빼서
    "여유 0.1" 이라 부른 것이다.

    그래서 판정과 정보를 가른다.

    - **겹침**(`overlap`) — 경계 상관이 그룹 안 상관보다 높은 쌍이 실제로 있는가.
      있으면 임계값 문제가 맞다. 이것만 사람을 부른다
    - **여유**(`margin`) — 임계값에서 양쪽으로 얼마나 떨어져 있나. 좁아도 겹치지
      않으면 정상이다. 기록만 한다

    표본이 너무 적으면(`within_n` 이 한 자리) 어느 쪽도 말할 수 없다 — 그것도
    그대로 알린다. 모르는 것을 통과로 처리하지 않는다.
    """
    inner, edge = [], []
    for g in groups:
        for i in g[:-1]:
            if i < len(corrs):
                inner.append(corrs[i])
        last = g[-1]
        if last < len(corrs):          # 마지막 그룹의 끝은 경계가 아니다
            edge.append(corrs[last])

    out = {"within_n": len(inner), "between_n": len(edge)}
    if not inner or not edge:
        return {**out, "within_min": None, "between_max": None,
                "gap": None, "overlap": None, "margin": None}

    lo, hi = min(inner), max(edge)
    # 겹치는 쌍: 그룹 안인데 어떤 경계보다 낮은 것 + 경계인데 어떤 그룹 안보다 높은 것.
    # 0 이면 임계값을 두 무리 사이 어디에 둬도 결과가 같다.
    overlap = sum(1 for v in inner if v < hi) + sum(1 for v in edge if v > lo)
    return {
        **out,
        "within_min": round(lo, 4),
        "between_max": round(hi, 4),
        "gap": round(lo - hi, 4),          # 이력 비교용으로 계속 남긴다
        "overlap": overlap,
        # 임계값을 이만큼 움직여도 그룹이 안 바뀐다. 음수면 임계값이 무리 안을
        # 자르고 있다는 뜻이라 겹침이 없어도 위태롭다.
        "margin": round(min(thresh - hi, lo - thresh), 4),
    }


def fingerprint(jpg: Path, blur_sigma: float):
    """초점 변화에 둔감한 저주파 지문."""
    img = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise IOError(f"cannot read {jpg}")
    h = int(THUMB_W * img.shape[0] / img.shape[1])
    small = cv2.resize(img, (THUMB_W, h), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small.astype(np.float32), (0, 0), blur_sigma)
    small -= small.mean()
    s = small.std()
    return small / s if s > 1e-6 else small


def sharpness(jpg: Path):
    """Laplacian 분산 — 값이 클수록 초점이 잘 맞은 장."""
    img = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE)
    small = cv2.resize(img, (1024, int(1024 * img.shape[0] / img.shape[1])),
                       interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(small, cv2.CV_32F).var())


def ncc(a, b):
    return float((a * b).mean())


def slide_slug(slide_dir: Path) -> str:
    """`photos/<촬영일>/<슬라이드>/` 에서 슬러그를 만든다.

    촬영일을 함께 넣는다 — 같은 슬라이드를 다른 날 다시 촬영하면 이름이 부딪힌다.
    `ingest_nas.py` 도 이것을 쓴다. 규칙이 갈라지면 반입한 슬라이드를 그룹핑이
    새것으로 다시 만든다.
    """
    return f"{slide_dir.parent.name}_{slide_dir.name}".lower().replace(" ", "_")


def save_grouping(slide_dir: Path, files, groups, sharps, times, args, sep, run):
    """Slide·Viewpoint·Frame 을 만든다. 통째로 한 트랜잭션이다.

    중간에 끊기면 시야 절반만 있는 슬라이드가 남고, 그 위에 검출을 돌리면
    나머지 절반이 조용히 빠진다.
    """
    folder = slide_dir.name
    site_code, core_code, depth = parse_sample_name(folder)
    core = None
    if site_code and core_code:
        site, _ = Site.objects.get_or_create(code=site_code)
        core, _ = Core.objects.get_or_create(site=site, code=core_code)

    slug = slide_slug(slide_dir)

    with transaction.atomic():
        slide, _ = Slide.objects.update_or_create(
            slug=slug,
            defaults=dict(name=folder, image_dir=rel(slide_dir), core=core,
                          depth_cm=depth, corr_thresh=args.corr_thresh,
                          # 자동 처리가 다 끝나기 전에는 사람이 검토하면 안 된다.
                          # 뷰어가 이 값을 보고 막는다 (P01 §1)
                          state="processing",
                          state_note=f"그룹핑 완료 · 합성·검출 대기 "
                                     f"(경계 여유 {sep['gap']})",
                          discovered_at=timezone.now()))

        # 다시 묶으면 옛 시야는 지운다 — --force 로만 여기까지 온다
        slide.viewpoints.all().delete()

        seq = 0
        for gi, g in enumerate(groups):
            names = [files[i].stem for i in g]
            tag = f"g{gi:03d}_{names[0]}-{names[-1].split('-')[-1]}"
            span = ((times[g[-1]] - times[g[0]]).total_seconds()
                    if times[g[0]] and times[g[-1]] else None)
            vp = Viewpoint.objects.create(
                slide=slide, idx=gi, tag=tag, n_frames=len(g),
                span_sec=span, grouping_run=run)

            best_name = max((files[i].stem for i in g), key=lambda n: sharps[n])
            best_frame = None
            for i in g:
                jpg = files[i]
                name = jpg.stem
                sc = zen_meta.scaling_for(jpg)
                fr, _ = Frame.objects.update_or_create(
                    slide=slide, name=name,
                    defaults=dict(viewpoint=vp, path=rel(jpg), seq=seq,
                                  sharpness=sharps[name],
                                  is_sharpest=(name == best_name),
                                  um_per_pixel=sc["um_per_pixel"],
                                  um_per_pixel_source=sc["source"],
                                  acquired_at=times[i]))
                if name == best_name:
                    best_frame = fr
                seq += 1
            if best_frame:
                vp.sharpest_frame = best_frame
                vp.save(update_fields=["sharpest_frame"])
    return slide


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="이미지 디렉토리")
    ap.add_argument("-o", "--out", default=None,
                    help="groups.json 내보내기 경로 (기본: 안 쓴다)")
    ap.add_argument("--corr-thresh", type=float, default=0.55,
                    help="이 값 이상이면 같은 시야로 판단")
    ap.add_argument("--blur", type=float, default=2.0)
    ap.add_argument("--max-gap-sec", type=float, default=0.0,
                    help=">0 이면 이 시간 이상 벌어진 경우 상관계수와 무관하게 분리")
    # 여유(margin)로는 판정하지 않는다 — 좁아도 겹치지 않으면 정상이다.
    # 실측: 여유 0.05 짜리 슬라이드를 사람이 확인하니 그룹핑이 맞았다.
    ap.add_argument("--min-pairs", type=int, default=5,
                    help="그룹 안 쌍이 이보다 적으면 묶임을 검증할 수 없다고 본다")
    ap.add_argument("--force", action="store_true",
                    help="이미 검출·교정이 있는 슬라이드도 다시 묶는다 (아래를 읽을 것)")
    ap.add_argument("--dry-run", action="store_true",
                    help="묶어 보기만 한다. DB 도 파일도 건드리지 않는다")
    args = ap.parse_args()

    slide_dir = Path(args.input).resolve()
    files = sorted(slide_dir.glob("*.jpg"))
    if not files:
        raise SystemExit(f"jpg 가 없다: {slide_dir}")
    print(f"{len(files)} images")

    # 재그룹핑은 Viewpoint 를 재편하므로 그 아래 검출·교정이 통째로 어긋난다.
    # 이 스크립트가 6단계의 마지막인 이유다.
    existing = Slide.objects.filter(image_dir=rel(slide_dir)).first()
    if existing and not args.dry_run and not args.force:
        n_rev = sum(vp.object_reviews.count() for vp in existing.viewpoints.all())
        n_det = sum(vp.detections.count() for vp in existing.viewpoints.all())
        if n_rev or n_det:
            raise SystemExit(
                f"{existing.slug} 은 이미 검출 {n_det}건 · 교정 {n_rev}건이 있다.\n"
                f"  다시 묶으면 시야가 재편되어 그 아래가 통째로 어긋난다.\n"
                f"  정말 다시 묶으려면 --force (교정은 mask_key 로 남지만 고아가 된다).")

    # Run 을 계산 **전에** 연다. 끝난 뒤에 만들면 DB 쓰기 시간(2초)만 잡히고
    # 실제 소요(412장에 31초)가 기록되지 않는다.
    run = None
    if not args.dry_run:
        run = runlog.start(
            "group",
            params={"corr_thresh": args.corr_thresh, "blur": args.blur,
                    "max_gap_sec": args.max_gap_sec, "dir": rel(slide_dir),
                    "n_images": len(files)},
            host=socket.gethostname(), code_version=git_version())

    fps = [fingerprint(f, args.blur) for f in files]
    times = [read_timestamp(f) for f in files]

    corrs = [ncc(fps[i], fps[i + 1]) for i in range(len(files) - 1)]
    gaps = [
        (times[i + 1] - times[i]).total_seconds()
        if times[i] and times[i + 1] else float("nan")
        for i in range(len(files) - 1)
    ]

    groups, cur = [], [0]
    for i, c in enumerate(corrs):
        split = c < args.corr_thresh
        if args.max_gap_sec > 0 and gaps[i] == gaps[i] and gaps[i] > args.max_gap_sec:
            split = True
        if split:
            groups.append(cur)
            cur = []
        cur.append(i + 1)
    groups.append(cur)

    sharps = {f.stem: round(sharpness(f), 1) for f in files}
    out = {"dir": rel(slide_dir), "corr_thresh": args.corr_thresh, "groups": []}
    print(f"\n{len(groups)} groups")
    for gi, g in enumerate(groups):
        names = [files[i].stem for i in g]
        sharp = {n: sharps[n] for n in names}
        best = max(sharp, key=sharp.get)
        span = ((times[g[-1]] - times[g[0]]).total_seconds()
                if times[g[0]] and times[g[-1]] else None)
        out["groups"].append({
            "id": gi, "images": names, "n": len(g),
            "sharpest": best, "sharpness": sharp, "span_sec": span,
        })
        print(f"  [{gi:3d}] n={len(g):2d} {names[0]}..{names[-1]}  "
              f"best={best} span={span}s")

    # 임계값이 이 슬라이드에서 의미가 있는가 (P01 §1)
    sep = separability(corrs, groups, args.corr_thresh)
    singles = sum(1 for g in groups if len(g) == 1)
    print(f"\n상관계수 — 그룹 안 {sep['within_min']} 이상({sep['within_n']}쌍) · "
          f"경계 {sep['between_max']} 이하({sep['between_n']}쌍)")
    print(f"  겹치는 쌍 {sep['overlap']}개 · 임계값 여유 {sep['margin']} · "
          f"단독 그룹 {singles}/{len(groups)}개")

    why = []
    if sep["overlap"]:
        why.append(f"두 무리가 겹친다 (쌍 {sep['overlap']}개) — 임계값을 어디에 둬도 "
                   f"잘못 묶이는 쌍이 생긴다")
    elif sep["margin"] is not None and sep["margin"] < 0:
        why.append(f"임계값 {args.corr_thresh} 이 무리 안을 자르고 있다 "
                   f"(그룹 안 최소 {sep['within_min']} · 경계 최대 {sep['between_max']})")
    elif sep["within_n"] < args.min_pairs and sep["within_n"] > 0:
        why.append(f"판단할 표본이 모자란다 (그룹 안 쌍 {sep['within_n']}개) — "
                   f"대부분 단독 촬영이라 묶임을 검증할 수 없다")
    suspect = bool(why)
    if suspect:
        print("\n** 그룹핑을 사람이 확인해야 한다.", file=sys.stderr)
        for w in why:
            print(f"   - {w}", file=sys.stderr)
    elif sep["margin"] is not None and sep["margin"] < 0.05:
        # 겹치지 않으면 정상이다. 여유가 적은 것은 정보로만 알린다.
        print(f"\n(참고) 임계값 여유가 {sep['margin']} 로 좁다. "
              f"겹치는 쌍은 없어 결과는 정상이다.", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")

    if args.dry_run:
        print("\ndry-run — DB 에 쓰지 않았다.")
        return

    try:
        slide = save_grouping(slide_dir, files, groups, sharps, times,
                              args, sep, run)
        run.slide = slide
        if suspect:
            # 자동으로 넘기지 않는다. 잘못 묶인 시야 위에 쌓은 검출과 교정은
            # 나중에 되돌리기가 훨씬 비싸다 (P01 §1).
            slide.state = "failed"
            slide.state_note = ("그룹핑 확인 필요 — " + " · ".join(why) +
                                f" (단독 그룹 {singles}/{len(groups)})")
            slide.save(update_fields=["state", "state_note"])
    except Exception as e:
        run.status = "failed"
        run.error = f"{type(e).__name__}: {e}"
        run.finished_at = timezone.now()
        run.save()
        raise

    run.status = "done"
    run.finished_at = timezone.now()
    run.counts = {"viewpoints": len(groups), "frames": len(files),
                  "singletons": singles, **sep}
    run.save()
    print(f"\n{slide.slug} · 시야 {len(groups)}개 · 프레임 {len(files)}개 · "
          f"상태 {slide.state} · Run #{run.pk}")
    if slide.state != "done":
        print(f"  {slide.state_note}")


if __name__ == "__main__":
    main()
