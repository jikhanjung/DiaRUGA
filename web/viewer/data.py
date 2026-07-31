"""DB 에서 읽어 뷰가 쓰기 좋은 형태로 만든다.

전에는 JSON 을 직접 읽었다(슬라이드 3장에 첫 화면이 251개 파일을 열었다).
설계와 이전 과정은 devlog/20260730_P02_db-schema.md.

**함수 이름과 반환 형태는 JSON 시절과 같게 유지한다** — 템플릿과 뷰를 건드리지
않고 갈아 끼울 수 있어야 하고, 그래야 같은 화면이 나오는지 대조할 수 있다.
그래서 여기서 만드는 것은 모델 인스턴스가 아니라 예전 그대로의 dict 다.

기하 계산(주축·스케일바)은 DB 와 무관하므로 그대로 두었다.
"""
import math
import re
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Q

from .models import (Candidate, ClassDef, Detection, Frame, ObjectReview,
                     Slide, Stack, Viewpoint, ViewpointReview)

# --- 분류 정의 -------------------------------------------------------------
# ClassDef 테이블이 원본이다. 다만 매 요청마다 읽을 값이 아니라(거의 바뀌지 않고
# 템플릿·클라이언트가 여러 번 묻는다) 프로세스 수명 동안 캐시한다.
_classes = None


def _class_rows():
    global _classes
    if _classes is None:
        _classes = list(ClassDef.objects.filter(active=True)
                        .values("key", "label", "badge", "color",
                                "is_taxon", "sort_order"))
    return _classes


def invalidate_classes():
    """분류 정의를 고쳤을 때 부른다."""
    global _classes
    _classes = None


def class_list() -> list[dict]:
    """분류 목록. 템플릿·클라이언트가 메뉴를 만들 때 쓴다."""
    return [{"key": r["key"], "label": r["label"], "badge": r["badge"],
             "color": r["color"], "taxon": r["is_taxon"]}
            for r in _class_rows()]


class _LabelMap(dict):
    """없는 키를 물어도 빈 문자열 — 템플릿에서 쓰기 편하게."""

    def __missing__(self, key):
        return ""


def _labels():
    return _LabelMap((r["key"], r["label"]) for r in _class_rows())


def _badges():
    return _LabelMap((r["key"], r["badge"]) for r in _class_rows())


def __getattr__(name):
    """CLASS_LABELS 같은 모듈 수준 이름을 유지한다(템플릿태그가 그렇게 쓴다)."""
    if name == "CLASS_LABELS":
        return _labels()
    if name == "CLASS_BADGE":
        return _badges()
    if name == "CLASSES":
        return tuple(r["key"] for r in _class_rows())
    if name == "TAXON_CLASSES":
        return tuple(r["key"] for r in _class_rows() if r["is_taxon"])
    raise AttributeError(name)


# bbox 로 만든 개체 키. 뷰어의 keyOf() 와 같은 규칙을 쓴다.
CAND_KEY = re.compile(r"^-?\d+_-?\d+_-?\d+_-?\d+$")


def cand_key(c) -> str:
    """마스크의 안정적인 식별자. dict 와 Candidate 둘 다 받는다."""
    b = (c.get("bbox_xywh") or [0, 0, 0, 0]) if isinstance(c, dict) else c.bbox_xywh
    return "_".join(str(int(v)) for v in b)


def _rel(path) -> str:
    return str(Path(path).relative_to(settings.DATA_ROOT))


def stamp(rel: str) -> int:
    """이미지의 mtime. URL 에 넣어 "내용이 바뀌면 주소도 바뀌게" 만든다."""
    try:
        return int((Path(settings.DATA_ROOT) / rel).stat().st_mtime)
    except (OSError, TypeError, ValueError):
        return 0


# --- 개체 dict --------------------------------------------------------------
NUM_FIELDS = ("area_um2", "major_um", "minor_um", "long_side_um",
              "short_side_um", "aspect_ratio", "fill_ratio", "circularity",
              "convexity", "solidity", "elongation", "ellipse_iou",
              "texture", "predicted_iou", "stability_score")


def _cand_dict(c: Candidate) -> dict:
    """Candidate -> 예전 JSON 과 같은 모양의 dict.

    통과분의 id 는 아래에서 면적 순으로 다시 매기고, 탈락분은 원시 순번(raw_id)을
    그대로 쓴다 — 예전 JSON 이 그랬고, 내보내기로 되돌릴 수 있어야 한다.
    """
    d = {
        "bbox_xywh": [c.bbox_x, c.bbox_y, c.bbox_w, c.bbox_h],
        "center_xy": [c.center_x, c.center_y],
        "area_px": c.area_px,
        "shape_ok": c.shape_ok,
        "polygon": c.polygon,
    }
    for f in NUM_FIELDS:
        d[f] = getattr(c, f)
    if c.passed:
        d["cls"] = c.cls or None
    elif c.cls:
        # 중첩정리로 떨어진 것은 판정을 통과한 뒤 정리됐으므로 cls 가 있다
        d["cls"] = c.cls
    # 파일에 적혀 있던 id 를 그대로 낸다. 통과분은 아래에서 면적 순으로 다시
    # 매기지만, 유령(지운 것)은 이 값을 유지해야 예전과 같다.
    if c.raw_id is not None:
        d["id"] = c.raw_id
    if c.reject:
        d["reject"] = c.reject
    return d


def _guess_cls(c: dict) -> str | None:
    """수동으로 되살린 개체의 표시용 분류."""
    e = c.get("elongation")
    if e is None:
        return None
    if e < 1.4:
        return "round"
    return "rod" if 2.0 <= e <= 20.0 else None


def mask_class(c: dict) -> str:
    """마스크를 그릴 때 쓰는 클래스. 뷰어의 addPolygon() 과 같은 규칙이어야 한다.

    사람이 지정한 분류가 가장 먼저다 — 되살린 개체(manual)에 Eucampia 를
    지정했으면 Eucampia 색으로 보여야 한다.
    """
    if c.get("cls_user") and c.get("cls"):
        return c["cls"]
    if c.get("manual"):
        return "manual"
    return c.get("cls") or "none"


def mask_points(c: dict) -> str | None:
    """폴리곤을 SVG points 문자열로."""
    p = c.get("polygon") or []
    if len(p) < 6:
        return None
    return " ".join(f"{p[i]},{p[i + 1]}" for i in range(0, len(p) - 1, 2))


# --- 검출 + 교정 ------------------------------------------------------------
def _apply_review(det: Detection, reviews: dict, vr) -> dict:
    """검출 결과에 교정을 얹어 예전 detection_for() 와 같은 dict 를 만든다.

    규칙은 JSON 시절과 같다 — **사람이 지웠다가 이긴다.** 문턱을 바꿔 개체가
    탈락분으로 옮겨가도 지운 것이 조용히 되살아나지 않아야 한다.
    """
    removed = {k for k, o in reviews.items() if o.removed}
    accepted = {k for k, o in reviews.items() if o.accepted}

    kept, gone, rejected = [], [], []
    n_auto = 0
    for c in det.candidates.all():
        key = c.mask_key
        d = _cand_dict(c)
        if c.passed:
            n_auto += 1
            (gone if key in removed else kept).append(d)
            continue
        # 탈락분: 지운 것은 유령으로, 되살린 것은 통과분으로. 나머지는 후보 풀.
        if key in removed:
            d["from_reject"] = True
            gone.append(d)
        elif key in accepted:
            d["manual"] = True
            d["from_reject"] = True
            d["cls"] = _guess_cls(d)
            kept.append(d)
        else:
            rejected.append(d)

    # 사람이 지정한 분류·메모를 얹는다. 원래 값은 cls_auto 로 남긴다.
    for d in kept + gone:
        o = reviews.get(cand_key(d))
        if not o:
            continue
        if o.label:
            if d.get("cls") != o.label:
                d["cls_auto"] = d.get("cls")
            d["cls"] = o.label
            d["cls_user"] = True
        if o.note:
            d["note"] = o.note

    kept.sort(key=lambda r: -(r.get("area_px") or 0))
    for i, d in enumerate(kept):
        d["id"] = i
    for d in gone:
        d["removed"] = True

    counts = {r["key"]: 0 for r in _class_rows()}
    for d in kept:
        if d.get("cls") in counts:
            counts[d["cls"]] += 1
    counts["manual"] = sum(1 for d in kept if d.get("manual"))
    counts["labeled"] = sum(1 for d in kept if d.get("cls_user"))

    stem = Path(det.image_path).stem
    overlay = Path(settings.DATA_ROOT) / "out" / f"{stem}_overlay.jpg"
    return {
        "image": det.image_path,
        "stem": stem,
        "size": [det.width, det.height],
        "scale": det.scale,
        "um_per_pixel": det.um_per_pixel,
        "um_per_pixel_native": det.um_per_pixel_native,
        "um_per_pixel_source": det.um_per_pixel_source or None,
        "um_per_pixel_backfilled": det.um_per_pixel_backfilled or None,
        "n_raw_masks": det.n_raw_masks,
        "n_sized": det.n_sized,
        "n_auto": n_auto,
        "n_candidates": len(kept),
        "counts": counts,
        "thresholds": det.thresholds.as_dict() if det.thresholds else {},
        "candidates": kept,
        "removed_candidates": gone,
        "rejected": rejected,
        "n_removed": len(removed),
        "accepted_keys": sorted(accepted),
        "labels": {k: o.label for k, o in reviews.items() if o.label},
        "notes": {k: o.note for k, o in reviews.items() if o.note},
        "review_done": bool(vr and vr.done),
        "review_note": (vr.note if vr else ""),
        "overlay_rel": _rel(overlay) if overlay.exists() else None,
        "source_dir": "out",
    }


def scales_by_slide() -> dict:
    """슬라이드마다의 µm/px. 대물렌즈를 바꿔 찍으면 슬라이드마다 다르다.

    배율에 딸려가는 지표(texture)는 문턱을 슬라이드마다 따로 잡아야 한다 —
    같은 시료를 40x 와 100x 로 찍으면 texture 중앙값이 1,903 대 109 다(devlog 013).
    크기(µm)와 비율 지표는 배율과 무관하다.
    """
    out = {}
    for d in (Detection.objects.filter(is_current=True,
                                       um_per_pixel__isnull=False)
              .select_related("viewpoint__slide")):
        out.setdefault(d.viewpoint.slide.slug, round(d.um_per_pixel, 9))
    return out


def preview_detection(vp: Viewpoint) -> dict | None:
    """검출 전에도 같은 화면을 쓰려고 만드는 빈 검출.

    자동 처리가 도는 동안에도 사람은 "무엇이 찍혔나" 를 봐야 한다. 그렇다고 화면을
    따로 만들 이유는 없다 — 캐러셀(합성본·깊이 맵·프레임)은 `_shots.html` 이
    `stack`·`frames` 로 그리고 검출과 무관하다. 개체가 0개인 검출을 넘겨 주면
    같은 화면이 그대로 돌고, 검토 도구만 CSS 로 잠그면 된다.

    크기는 합성본에서 읽는다. `Frame.width/height` 는 아직 비어 있고, 겹쳐 그릴
    개체가 없으므로 못 읽어도 화면은 멀쩡하다.
    """
    st = getattr(vp, "stack", None)
    if st is None or not st.focused_path:
        return None

    w = h = None
    try:
        from PIL import Image                                 # noqa: PLC0415
        with Image.open(Path(settings.DATA_ROOT) / st.focused_path) as im:
            w, h = im.size          # 헤더만 읽는다 — 픽셀을 디코딩하지 않는다
    except (OSError, ValueError):
        pass

    vr = next(iter(ViewpointReview.objects.filter(viewpoint=vp)), None)
    return {
        "image": st.focused_path,
        "stem": Path(st.focused_path).stem,
        "size": [w, h],
        "scale": st.resize_scale or 1.0,
        "um_per_pixel": st.um_per_pixel,
        "um_per_pixel_native": st.native_um_per_pixel,
        "um_per_pixel_source": st.um_per_pixel_source or None,
        "um_per_pixel_backfilled": None,
        "n_raw_masks": 0, "n_sized": 0, "n_auto": 0, "n_candidates": 0,
        "counts": {}, "thresholds": {},
        "candidates": [], "removed_candidates": [], "rejected": [],
        "n_removed": 0, "accepted_keys": [], "labels": {}, "notes": {},
        "review_done": bool(vr and vr.done),
        "review_note": (vr.note if vr else ""),
        "overlay_rel": None, "source_dir": "out",
        # 이 화면은 아직 검출이 없다 — 템플릿이 도구를 감추는 데 쓴다
        "preview_only": True,
    }


def detection_for_viewpoint(vp: Viewpoint) -> dict | None:
    """시야에 붙은 현재 검출 결과 (교정 반영)."""
    det = next((d for d in vp.detections.all() if d.is_current), None)
    if det is None:
        return None
    reviews = {o.mask_key: o for o in vp.object_reviews.all()}
    vr = next(iter(ViewpointReview.objects.filter(viewpoint=vp)), None)
    return _apply_review(det, reviews, vr)


def review_blocked(stem_or_slide) -> str:
    """검토를 막아야 하면 그 이유를, 아니면 빈 문자열을 돌려준다.

    슬라이드(최상위 폴더) 하나를 단위로 연다. 자동으로 할 수 있는 처리 — 그룹핑,
    합성, 검출, 문턱 적용 — 이 다 끝나야 `state="done"` 이 되고, 그때 검토가 열린다
    (P01 §1, `segment_diatoms.mark_done_if_complete`).

    반쯤 처리된 슬라이드를 검토하면 아직 안 돌아간 시야의 검출이 뒤늦게 들어오면서
    이미 본 화면이 바뀐다. 사람의 판단이 재생성 불가라 그 상황을 만들면 안 된다.
    """
    slide = stem_or_slide
    if isinstance(stem_or_slide, str):
        vp = _viewpoint_of(stem_or_slide)
        if vp is None:
            return ""
        slide = vp.slide
    if slide is None or slide.state == "done":
        return ""
    if slide.state == "failed":
        why = slide.state_note or "원인을 확인해야 합니다"
        return (f"자동 처리 중에 확인이 필요한 문제가 생겼습니다 — {why}. "
                f"확인하신 뒤에 검토를 열 수 있습니다.")
    note = f" ({slide.state_note})" if slide.state_note else ""
    return (f"자동 처리가 아직 끝나지 않았습니다{note}. "
            f"끝나는 대로 검토를 열겠습니다.")


def _viewpoint_of(stem: str) -> Viewpoint | None:
    """검출·교정의 stem 으로 시야를 찾는다.

    합성본은 `<tag>_focused`, 싱글턴은 프레임 이름(`Snap-21171`)이다.
    """
    qs = (Viewpoint.objects
          .prefetch_related("detections__candidates", "object_reviews"))
    if stem.endswith("_focused"):
        return qs.filter(tag=stem[: -len("_focused")]).first()
    fr = Frame.objects.filter(name=stem).values_list("viewpoint_id", flat=True).first()
    return qs.filter(id=fr).first() if fr else None


def detection_for(stem: str) -> dict | None:
    """stem 으로 찾는다. 예전 시그니처를 유지하려고 남겨 둔 경로다."""
    vp = _viewpoint_of(stem)
    return detection_for_viewpoint(vp) if vp else None


def _stack_dict(st: Stack, det: dict | None) -> dict:
    return {
        "focused_rel": st.focused_path,
        "depth_rel": st.depth_path or None,
        "stem": Path(st.focused_path).stem,
        "detection": det,
    }


def stack_for(tag: str) -> dict | None:
    st = (Stack.objects.filter(viewpoint__tag=tag)
          .select_related("viewpoint")
          .prefetch_related("viewpoint__detections__candidates",
                            "viewpoint__object_reviews").first())
    if st is None:
        return None
    return _stack_dict(st, detection_for_viewpoint(st.viewpoint))


# --- 집계 -------------------------------------------------------------------
def _slide_summary(slide: Slide, details: list | None = None) -> dict:
    """목록 화면의 집계.

    details 를 넘기면 그것을 쓴다 — dataset_detail 이 이미 시야를 다 훑었으므로
    두 번 계산하지 않는다.
    """
    vps = Viewpoint.objects.filter(slide=slide)
    n_groups = vps.count()
    sizes = list(vps.values_list("n_frames", flat=True))
    n_img = sum(sizes)

    if details is None:
        details = []
        for vp in vps.prefetch_related("detections__candidates",
                                       "object_reviews"):
            det = detection_for_viewpoint(vp)
            if det:
                details.append(det)

    per_cls = {r["key"]: 0 for r in _class_rows()}
    counts, n_auto, n_detected, n_labeled = [], 0, 0, 0
    for det in details:
        counts.append(det["n_candidates"])
        n_detected += det["n_candidates"]
        n_auto += det["n_auto"]
        # 분류 지정은 **통과분만** 센다 — 탭 머리의 "사람지정" 과 같은 정의여야
        # 화면끼리 어긋나지 않는다(지웠다가 분류가 남은 개체가 있다).
        n_labeled += det["counts"].get("labeled", 0)
        for k in per_cls:
            per_cls[k] += det["counts"].get(k, 0)

    rv = ObjectReview.objects.filter(viewpoint__slide=slide)
    agg = rv.aggregate(
        removed=Count("id", filter=Q(removed=True)),
        accepted=Count("id", filter=Q(accepted=True)),
        noted=Count("id", filter=~Q(note="")),
    )
    vrs = ViewpointReview.objects.filter(viewpoint__slide=slide)

    class_counts = [{"key": k, "label": _labels()[k], "n": v}
                    for k, v in per_cls.items() if v]
    return {
        "n_groups": n_groups,
        "n_images": n_img,
        "mean_size": round(n_img / n_groups, 1) if n_groups else 0,
        "singletons": sum(1 for s in sizes if s == 1),
        "max_size": max(sizes) if sizes else 0,
        "detected_groups": len(counts),
        "n_auto": n_auto,
        "n_detected": n_detected,
        "mean_detected": (round(n_detected / len(counts), 1) if counts else None),
        "n_rod": per_cls.get("rod", 0),
        "n_round": per_cls.get("round", 0),
        "class_counts": class_counts,
        "n_removed": agg["removed"],
        "n_accepted": agg["accepted"],
        "n_labeled": n_labeled,
        "n_noted": agg["noted"],
        "n_group_notes": vrs.exclude(note="").count(),
        "reviewed_groups": vrs.filter(done=True).count(),
    }


def datasets() -> list[dict]:
    # groups_*.json 은 파이프라인에서 빠졌다(P02 7단계). 목록에 파일 이름 대신
    # 시료가 무엇인지와 어떤 배율로 찍혔는지를 보인다 — 그쪽이 화면에서 쓸모 있다.
    scales = scales_by_slide()
    out = []
    for slide in Slide.objects.select_related("core", "core__site"):
        core = slide.core
        site = core.site if core else None
        out.append({
            "slug": slide.slug,
            "label": slide.name,
            "image_dir": slide.image_dir,
            "corr_thresh": slide.corr_thresh,
            "site": (site.region or site.name or site.code) if site else "",
            "core": core.code if core else "",
            "depth_cm": slide.depth_cm,
            "description": slide.description,
            "um_per_pixel": scales.get(slide.slug),
            "state": slide.state,
            "state_note": slide.state_note,
            "missing_dir": not (Path(settings.DATA_ROOT)
                                / slide.image_dir).is_dir(),
            **_slide_summary(slide),
        })
    return out


def _viewpoints_of(slide: Slide):
    return (Viewpoint.objects.filter(slide=slide)
            .select_related("sharpest_frame", "stack")
            .prefetch_related("frames", "detections__candidates",
                              "object_reviews"))


def dataset_detail(slug: str) -> dict | None:
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return None

    groups, details = [], []
    for vp in _viewpoints_of(slide):
        det = detection_for_viewpoint(vp)
        if det:
            details.append(det)
        st = getattr(vp, "stack", None)

        # 목록의 대표 그림은 합성본이 원칙이다 — 그룹을 대표하는 그림이 검출을
        # 돌린 그림과 같아야 목록과 상세가 어긋나지 않는다. 합성본이 없으면
        # 싱글턴이거나 아직 합성하지 않은 시야이므로 프레임을 쓴다.
        cover_rel = st.focused_path if st else None
        if cover_rel is None:
            fr = vp.sharpest_frame or next(iter(vp.frames.all()), None)
            if fr and (Path(settings.DATA_ROOT) / fr.path).exists():
                cover_rel = fr.path

        # 표지에 검출 마스크를 얹는다. 검출을 돌린 이미지와 표지가 같을 때만 —
        # 다른 이미지의 좌표를 얹으면 조용히 어긋난 그림이 된다.
        masks, size = [], None
        if det and cover_rel and det.get("stem") == Path(cover_rel).stem:
            size = det.get("size")
            for c in det.get("candidates") or []:
                pts = mask_points(c)
                if pts:
                    masks.append({"points": pts, "cls": mask_class(c)})

        groups.append({
            "id": vp.idx,
            "n": vp.n_frames,
            "tag": vp.tag,
            "span_sec": round(vp.span_sec or 0, 1),
            "sharpest": vp.sharpest_frame.name if vp.sharpest_frame else None,
            "cover_rel": cover_rel,
            "cover_size": size,
            "masks": masks,
            "has_stack": st is not None,
            "n_detected": (det or {}).get("n_candidates"),
            "reviewed": bool((det or {}).get("review_done")),
        })

    return {
        "slug": slug,
        "label": slide.name,
        "json_name": f"groups_{slide.slug}.json",
        "corr_thresh": slide.corr_thresh,
        "groups": groups,
        **_slide_summary(slide, details),
    }


def _frames(vp: Viewpoint, det: dict | None, frame_det_id) -> list[dict]:
    frames = list(vp.frames.all())
    values = [f.sharpness for f in frames if f.sharpness is not None]
    top = max(values) if values else 0
    out = []
    for f in frames:
        out.append({
            "name": f.name,
            "sharpness": f.sharpness,
            # 그룹 내 최고 선명도 대비 비율 — 막대 길이로 쓴다.
            "sharp_pct": (round(100 * f.sharpness / top)
                          if f.sharpness and top else 0),
            "is_sharpest": f.is_sharpest,
            "rel": f.path,
            "exists": (Path(settings.DATA_ROOT) / f.path).exists(),
            # 싱글턴 시야는 합성본이 없어 프레임에 검출이 붙는다
            "detection": det if f.id == frame_det_id else None,
        })
    return out


def group_detail(slug: str, gid: int) -> dict | None:
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return None
    vp = _viewpoints_of(slide).filter(idx=gid).first()
    if vp is None:
        return None

    ids = list(Viewpoint.objects.filter(slide=slide)
               .order_by("idx").values_list("idx", flat=True))
    pos = ids.index(gid)

    cur = next((d for d in vp.detections.all() if d.is_current), None)
    det = detection_for_viewpoint(vp)
    st = getattr(vp, "stack", None)
    return {
        "slug": slug,
        "label": slide.name,
        "id": gid,
        "n": vp.n_frames,
        "tag": vp.tag,
        "span_sec": round(vp.span_sec or 0, 1),
        "sharpest": vp.sharpest_frame.name if vp.sharpest_frame else None,
        "frames": _frames(vp, det,
                          cur.frame_id if cur and cur.target == "frame" else None),
        # 검출이 아직 없으면 빈 검출을 넘겨 같은 화면을 쓴다 (도구만 잠근다)
        "stack": (_stack_dict(st, (det if cur and cur.target == "stack"
                                   else preview_detection(vp)))
                  if st else None),
        "prev_id": ids[pos - 1] if pos > 0 else None,
        "next_id": ids[pos + 1] if pos < len(ids) - 1 else None,
        # 자동 처리가 안 끝났으면 검토를 막는다 (P01 §1). 저장도 서버에서 거절한다.
        "review_blocked": review_blocked(slide),
    }


# --- 교정 저장 --------------------------------------------------------------
def save_review(stem: str, done: bool, note: str, removed, accepted,
                labels: dict, notes: dict) -> dict | None:
    """뷰어가 보낸 교정을 DB 에 쓴다. 예전에는 review/<stem>_review.json 이었다.

    키(mask_key)마다 한 행이고, 아무 표시도 남지 않은 행은 지운다 — 그래야
    "교정 전체 초기화" 가 예전처럼 깨끗하게 동작한다.
    """
    vp = _viewpoint_of(stem)
    if vp is None:
        return None

    ViewpointReview.objects.update_or_create(
        viewpoint=vp, defaults={"done": done, "note": note})

    removed, accepted = set(removed), set(accepted)
    keys = removed | accepted | set(labels) | set(notes)
    by_key = {c.mask_key: c for c in
              Candidate.objects.filter(detection__viewpoint=vp,
                                       detection__is_current=True)}
    for key in keys:
        cand = by_key.get(key)
        obj, _ = ObjectReview.objects.get_or_create(
            viewpoint=vp, mask_key=key,
            defaults={"candidate": cand,
                      "bind_method": "exact" if cand else "orphan",
                      "bind_score": 1.0 if cand else None})
        obj.removed = key in removed
        obj.accepted = key in accepted
        obj.label = labels.get(key, "")
        obj.note = notes.get(key, "")
        if cand and obj.candidate_id != cand.id:
            obj.candidate = cand
            obj.bind_method = "exact"
            obj.bind_score = 1.0
        # 기하는 모든 교정 행이 들고 있는다 — 검출기가 바뀌어도 읽혀야 하고,
        # 지운 것도 학습의 음성 표본이다 (P02 §2.7)
        if cand and not obj.geom:
            obj.geom = {"bbox": cand.bbox_xywh, "polygon": cand.polygon}
        obj.save()

    # 표시가 사라진 행은 지운다
    ObjectReview.objects.filter(viewpoint=vp).exclude(mask_key__in=keys).delete()
    return {"removed": len(removed), "accepted": len(accepted),
            "labels": len(labels), "notes": len(notes)}


# --- 기하 (DB 와 무관, 예전 그대로) -----------------------------------------
def polygon_axis(poly) -> tuple[float, float] | None:
    """마스크의 주축 각도(도)와 축 비율. 폴리곤의 면적 모멘트로 정확히 구한다.

    꼭짓점만 PCA 하면 approxPolyDP 로 단순화된 점 간격이 고르지 않아 결과가
    치우친다. 다항식 닫힌 해로 채워진 영역의 2차 모멘트를 직접 구한다.
    """
    if not poly or len(poly) < 6:
        return None
    xs = [float(v) for v in poly[0::2]]
    ys = [float(v) for v in poly[1::2]]
    n = len(xs)

    a2 = sxx = syy = sxy = 0.0
    cx = cy = 0.0
    for i in range(n):
        j = (i + 1) % n
        x0, y0, x1, y1 = xs[i], ys[i], xs[j], ys[j]
        cross = x0 * y1 - x1 * y0
        a2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
        sxx += cross * (x0 * x0 + x0 * x1 + x1 * x1)
        syy += cross * (y0 * y0 + y0 * y1 + y1 * y1)
        sxy += cross * (2 * x0 * y0 + x0 * y1 + x1 * y0 + 2 * x1 * y1)
    area = a2 / 2.0
    if abs(area) < 1e-9:
        return None
    cx /= 6.0 * area
    cy /= 6.0 * area
    m20 = sxx / (12.0 * area) - cx * cx
    m02 = syy / (12.0 * area) - cy * cy
    m11 = sxy / (24.0 * area) - cx * cy

    ang = 0.5 * math.atan2(2.0 * m11, m20 - m02)
    diff = math.hypot(m20 - m02, 2.0 * m11)
    l1 = (m20 + m02 + diff) / 2.0
    l2 = (m20 + m02 - diff) / 2.0
    ratio = math.sqrt(l1 / l2) if l2 > 1e-9 else 999.0
    return math.degrees(ang), ratio


def rotated_extent(poly, deg: float) -> tuple[int, int]:
    """폴리곤을 deg 만큼 돌렸을 때의 가로·세로 크기(px)."""
    r = math.radians(deg)
    cos, sin = math.cos(r), math.sin(r)
    xs = [float(v) for v in poly[0::2]]
    ys = [float(v) for v in poly[1::2]]
    rx = [x * cos - y * sin for x, y in zip(xs, ys)]
    ry = [x * sin + y * cos for x, y in zip(xs, ys)]
    return (max(1, int(round(max(rx) - min(rx)))),
            max(1, int(round(max(ry) - min(ry)))))


# 이 비율 아래면 방향을 정할 수 없다 — 원형을 굳이 돌려 보간으로 흐리지 않는다.
UPRIGHT_MIN_RATIO = 1.15


def crop_geometry(c: dict, rotate: bool = True) -> dict | None:
    """갤러리 크롭의 회전량과 정확한 결과 크기(px).

    주축을 세로로 세운다(장축이 위아래) — 방향이 통일되면 형태를 나란히 비교할
    수 있다. 크기를 여백까지 포함해 여기서 확정하는 이유: **스케일바 길이를
    계산해야 한다.** 자르는 쪽에서 여백을 따로 더하면 몇 µm 폭인지 알 수 없다.
    """
    poly = c.get("polygon")
    if not poly or len(poly) < 6:
        return None
    deg = 0.0
    if rotate:
        axis = polygon_axis(poly)
        if axis and axis[1] >= UPRIGHT_MIN_RATIO:
            deg = 90.0 - axis[0]
            # -90~90 로 접는다. 180도 뒤집는 것은 형태 비교에 뜻이 없다.
            while deg > 90:
                deg -= 180
            while deg < -90:
                deg += 180
    w, h = rotated_extent(poly, deg)
    m = max(3, round(0.08 * max(w, h)))     # 테두리에 딱 붙으면 형태를 보기 어렵다
    ow, oh = w + 2 * m, h + 2 * m
    return {"rot": round(deg, 2), "out": f"{ow},{oh}", "out_w": ow, "out_h": oh}


def nice_length(v: float) -> float:
    """1·2·5 계열로 떨어뜨린다 — 눈금은 읽기 좋은 값이어야 한다."""
    if v <= 0:
        return 0.0
    e = 10.0 ** math.floor(math.log10(v))
    m = v / e
    return (1 if m < 1.5 else 2 if m < 3.5 else 5 if m < 7.5 else 10) * e


def scalebar_for(out_w: int, um_per_px: float, frac: float = 0.4) -> dict | None:
    """크롭 썸네일에 얹을 스케일바. 이미지 폭에 대한 백분율로 준다."""
    if not out_w or not um_per_px:
        return None
    um_w = out_w * um_per_px
    # 목표 길이를 **넘지 않는** 1·2·5 눈금을 고른다(내림). 올림으로 잡으면 바가
    # 이미지 폭의 절반을 넘어 개체를 가린다.
    target = um_w * frac
    if target <= 0:
        return None
    e = 10.0 ** math.floor(math.log10(target))
    m = target / e
    bar = (5 if m >= 5 else 2 if m >= 2 else 1) * e
    if bar <= 0:
        return None
    label = f"{bar:g} µm" if bar >= 1 else f"{bar:.1f} µm"
    return {"pct": round(100.0 * bar / um_w, 2), "um": bar, "label": label}


# --- 파일 접근 --------------------------------------------------------------
def safe_image_path(rel: str) -> Path | None:
    """p= 로 들어온 상대경로를 실제 파일로 바꾼다.

    IMAGE_DIRS 안에 실제로 들어 있는 파일만 허용한다. symlink 까지 풀어서
    비교하므로 ../ 나 링크로 바깥을 가리키는 경로는 통과하지 못한다.
    """
    if not rel:
        return None
    root = Path(settings.DATA_ROOT).resolve()
    try:
        target = (root / rel).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not target.is_file():
        return None
    for allowed in settings.IMAGE_DIRS:
        base = (root / allowed).resolve()
        if target.is_relative_to(base):
            return target
    return None
