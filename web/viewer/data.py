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
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.urls import reverse
from django.db.models import (Case, CharField, Count, Exists, F, OuterRef,
                              Q, Subquery, Value, When)

from . import antarctica, korea
from .models import (Candidate, ClassDef, Detection, Frame, ObjectReview, Run,
                     Site, Slide, Stack, Viewpoint, ViewpointReview)

# --- 분류 정의 -------------------------------------------------------------
# ClassDef 테이블이 원본이다. 다만 매 요청마다 읽을 값이 아니라(거의 바뀌지 않고
# 템플릿·클라이언트가 여러 번 묻는다) 프로세스 수명 동안 캐시한다.
_classes = None


def _class_rows():
    global _classes
    if _classes is None:
        _classes = list(ClassDef.objects.filter(active=True)
                        .values("key", "label", "short", "badge", "color",
                                "hotkey", "is_taxon", "counted", "sort_order"))
        # 약칭이 비면 전체 이름으로 메운다. **읽는 쪽마다 이 판단을 되풀이하지
        # 않게 여기서 한 번만 한다** — 한 곳이라도 빠뜨리면 그 화면만 빈칸이 된다.
        for r in _classes:
            r["short"] = r["short"] or r["label"]
    return _classes


def invalidate_classes():
    """분류 정의를 고쳤을 때 부른다."""
    global _classes
    _classes = None


def class_list() -> list[dict]:
    """분류 목록. 템플릿·클라이언트가 메뉴를 만들 때 쓴다."""
    return [{"key": r["key"], "label": r["label"], "short": r["short"],
             "badge": r["badge"], "color": r["color"], "taxon": r["is_taxon"],
             "hotkey": r["hotkey"]}
            for r in _class_rows()]


def hotkey_groups() -> dict:
    """단축키 하나가 도는 분류들. 검토 화면의 안내 한 줄이 이것으로 그려진다.

    같은 키를 나눠 가진 분류는 누를 때마다 차례로 돈다(표 순서). 그래서 묶음의
    첫 분류가 "한 번 누르면 되는 것" 이고 나머지가 "더 누르면 나오는 것" 이다.

    **안내를 손으로 적지 않는 이유.** 분류를 더하면서 안내만 옛 목록으로 남는
    일이 이미 두 번 있었다(038 의 개수 줄, 목록의 분류 열). 키를 안 준 분류는
    안내에도 안 나온다 — 그것이 곧 "아직 안 배정했다" 는 표시다.
    """
    order, groups = [], {}
    for r in _class_rows():
        hot = (r["hotkey"] or "").strip()
        if not hot:
            continue
        if hot not in groups:
            order.append(hot)
            groups[hot] = []
        groups[hot].append({"key": r["key"], "label": r["label"],
                            "short": r["short"]})
    rows = [{"hotkey": h, "classes": groups[h]} for h in order]
    # `cycles` 는 "다시 누르면 넘어간다" 는 설명을 낼지 정한다. 도는 묶음이
    # 하나도 없으면 그 설명은 가리킬 것이 없다.
    return {"groups": rows, "cycles": any(len(g["classes"]) > 1 for g in rows)}


def counted_classes() -> list[dict]:
    """개체 수로 세는 분류. 목록 화면의 "검출" 칸이 더하는 것이 이것이다.

    **여기 없는 것은 파편과 미분류다.** 파편은 `ClassDef.counted=False` 로 꺼져
    있고, 미분류는 분류가 없어 애초에 어느 칸에도 들어가지 않는다. 둘 다 개체
    하나로 세면 밀도가 부풀기 때문에 뺀다.

    목록 표의 **열 머리**도 이 목록으로 만든다 — 슬라이드마다 0인 분류를 빼면
    줄마다 열 수가 달라져 세로로 안 맞는다. 비교하려고 표로 만든 화면이다.
    """
    return [{"key": r["key"], "label": r["label"], "short": r["short"]}
            for r in _class_rows() if r["counted"]]


class _LabelMap(dict):
    """없는 키를 물어도 빈 문자열 — 템플릿에서 쓰기 편하게."""

    def __missing__(self, key):
        return ""


def _labels():
    return _LabelMap((r["key"], r["label"]) for r in _class_rows())


def _shorts():
    return _LabelMap((r["key"], r["short"]) for r in _class_rows())


def _badges():
    return _LabelMap((r["key"], r["badge"]) for r in _class_rows())


def __getattr__(name):
    """CLASS_LABELS 같은 모듈 수준 이름을 유지한다(템플릿태그가 그렇게 쓴다)."""
    if name == "CLASS_LABELS":
        return _labels()
    if name == "CLASS_SHORT":
        return _shorts()
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

    # 검출 화면 머리의 "(봉상 12, 원형 3, …)". 분류 이름이 템플릿에 박혀 있었다 —
    # 그래서 Chaetoceros 를 표에 넣어도 이 줄에만 안 나왔다. 표가 정하게 바꾼다.
    # 0 인 분류는 뺀다. 여기는 표가 아니라 한 줄이라 자리를 맞출 것이 없고,
    # 짧을수록 읽힌다.
    order = ([(r["key"], r["short"]) for r in _class_rows()]
             + [("manual", "수동"), ("labeled", "사람지정")])
    counts_list = [{"key": k, "label": lb, "n": counts[k]}
                   for k, lb in order if counts.get(k)]

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
        "counts_list": counts_list,
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


def map_points(area: str | None = None) -> list[dict]:
    """지도에 찍을 지역별 묶음. 슬라이드가 아니라 **지역 단위**다.

    같은 코어의 깊이별 슬라이드는 좌표가 같으므로 겹쳐 찍으면 하나로 보인다.
    지역으로 묶고 그 안에 슬라이드를 세는 편이 지도에서 읽힌다.

    좌표는 `Site.lat/lon` 이 원칙이고, 비어 있으면 해역 대략값으로 물러난다.
    **어느 쪽인지 반드시 함께 낸다** — 대략값을 실측처럼 보이게 두면 안 된다.

    **권역마다 투영이 다르다.** 남극은 EPSG:3031(극구면), 한국은 EPSG:5179
    (횡메르카토르)다. 마커를 엉뚱한 투영으로 찍으면 지도와 어긋나므로 권역에
    맞는 것을 고른다 — 그래서 `area` 는 거르기용이 아니라 **투영을 정하는 값**이다.
    """
    area = area or "ant"
    if area == "kr":
        approx_sites, project = korea.APPROX_SITES, _korea_xy
    else:
        approx_sites, project = antarctica.APPROX_SITES, _polar_xy

    sites = Site.objects.filter(area=area).prefetch_related("cores__slides")
    out = []
    for site in sites:
        slides = [sl for c in site.cores.all() for sl in c.slides.all()]
        if not slides:
            continue
        # 코드는 <지역><연도> 꼴이다 (RS23 · WAP13 · AM22). 뒤의 숫자를 떼고 찾는다.
        base = re.sub(r"\d+$", "", site.code).upper()
        approx = approx_sites.get(base)
        if site.lat is not None and site.lon is not None:
            lat, lon, exact, note = site.lat, site.lon, True, ""
        elif approx:
            lat, lon, exact, note = approx[0], approx[1], False, approx[2]
        else:
            continue                    # 어디인지 짐작할 수도 없으면 안 찍는다
        x, y = project(lat, lon)

        # 코어 아래에 슬라이드를 매단다. 깊이순이다 — 같은 코어에서 깊이에 따른
        # 변화를 보는 것이 이 시료의 목적이라 그 순서로 읽혀야 한다.
        cores = []
        for core in sorted(site.cores.all(), key=lambda c: c.code):
            rows = sorted(core.slides.all(),
                          key=lambda sl: (sl.depth_cm is None, sl.depth_cm or 0))
            if not rows:
                continue
            cores.append({
                "code": core.code,
                "n_slides": len(rows),
                "slides": [{
                    "slug": sl.slug,
                    "label": sl.name,
                    "depth_cm": sl.depth_cm,
                    "state": sl.state,
                    "n_viewpoints": sl.viewpoints.count(),
                    "reviewed": ViewpointReview.objects.filter(
                        viewpoint__slide=sl, done=True).count(),
                } for sl in rows],
            })

        out.append({
            "code": site.code,
            "label": site.region or site.name or site.code,
            "x": round(x, 1), "y": round(y, 1),
            "exact": exact, "approx_note": note,
            "n_slides": len(slides),
            "n_viewpoints": sum(s.viewpoints.count() for s in slides),
            "cores": cores,
            "core_codes": [c["code"] for c in cores],
            "slugs": [s.slug for s in slides],
        })
    return out


def _polar_xy(lat: float, lon: float) -> tuple[float, float]:
    """EPSG:3031 로 투영해 SVG 좌표(km)로. antarctica.py 와 같은 식이어야 한다.

    거기서는 굽는 시점에 계산했고 여기서는 요청마다 계산한다 — 점 몇 개뿐이라
    미리 굽는 값어치가 없다. 대신 **식이 갈라지면 지도와 마커가 어긋나므로**
    상수를 여기 한 번 더 적지 않고 antarctica 에서 가져온다.
    """
    import math

    a, e = antarctica.WGS84_A, antarctica.WGS84_E

    def t(phi):
        s = e * math.sin(phi)
        return math.tan(math.pi / 4 + phi / 2) / (((1 + s) / (1 - s)) ** (e / 2))

    phi_c = math.radians(-71.0)
    mc = math.cos(phi_c) / math.sqrt(1 - e * e * math.sin(phi_c) ** 2)
    rho = a * mc * t(math.radians(lat)) / t(phi_c)
    lam = math.radians(lon)
    return rho * math.sin(lam) / 1000, -rho * math.cos(lam) / 1000


def _korea_xy(lat: float, lon: float) -> tuple[float, float]:
    """EPSG:5179 로 투영해 SVG 좌표(m)로. korea.py 를 구운 식과 같아야 한다.

    `tools/proj_kr.py` 의 `fwd()` 를 그대로 옮긴 것이다. 원본은 거기이고
    검산(`python3 tools/proj_kr.py`)도 거기 있다 — **고칠 일이 생기면 두 곳을
    함께 고쳐야 한다.** 지도는 굽는 시점에, 마커는 요청마다 계산하므로 식이
    갈라지면 마커가 육지를 벗어난다.

    단위가 남극(km)과 다르게 m 인 것은 `korea.py` 의 viewBox 가 m 이라서다.
    """
    import math

    a, f = 6378137.0, 1 / 298.257222101
    e2 = 2 * f - f * f
    ep2 = e2 / (1 - e2)
    lat0, lon0, k0 = math.radians(38.0), math.radians(127.5), 0.9996
    fe, fn = 1_000_000.0, 2_000_000.0

    def arc(phi):
        return a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
                    - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024)
                    * math.sin(2 * phi)
                    + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * phi)
                    - (35 * e2**3 / 3072) * math.sin(6 * phi))

    phi, lam = math.radians(lat), math.radians(lon)
    sp, cp, tp = math.sin(phi), math.cos(phi), math.tan(phi)
    n = a / math.sqrt(1 - e2 * sp * sp)
    t_, c = tp * tp, ep2 * cp * cp
    aa = (lam - lon0) * cp

    x = fe + k0 * n * (aa + (1 - t_ + c) * aa**3 / 6
                       + (5 - 18 * t_ + t_ * t_ + 72 * c - 58 * ep2)
                       * aa**5 / 120)
    y = fn + k0 * (arc(phi) - arc(lat0) + n * tp
                   * (aa**2 / 2 + (5 - t_ + 9 * c + 4 * c * c) * aa**4 / 24
                      + (61 - 58 * t_ + t_ * t_ + 600 * c - 330 * ep2)
                      * aa**6 / 720))
    return x, -y                    # SVG 는 y 가 아래로 자란다


def slide_label(slug: str) -> str | None:
    """머리글에 쓸 이름만. 없으면 None.

    `dataset_detail()` 은 시야를 전부 훑어 0.45초가 든다 — 이름 한 줄 때문에
    그것을 부르면 안 된다. 실제로 계측 표와 크롭 화면이 그러고 있었다.
    """
    return Slide.objects.filter(slug=slug).values_list("name", flat=True).first()


def candidate_rows(slug: str) -> list[dict]:
    """데이터셋 전체의 검출 개체를 한 목록으로. **시야를 한 번만 훑는다.**

    예전에는 뷰가 `dataset_detail()` 로 시야 74개를 훑은 뒤, 그룹마다 다시
    `group_detail()` 을 불러 같은 것을 또 만들었다 — 0.45초 + 0.67초. 뒤의 것이
    통째로 군더더기였다.

    `image_rel` 은 검출에 적힌 경로가 아니라 뷰어가 실제로 찾아낸 파일의
    상대경로다 — 크롭 요청이 그 경로로 이미지를 다시 열기 때문에, 검출 기록이
    절대경로인 경우에도 어긋나지 않아야 한다.
    """
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return []

    rows = []
    for vp in _viewpoints_of(slide):
        cur = next((d for d in vp.detections.all() if d.is_current), None)
        det = detection_for_viewpoint(vp)
        if det is None:
            continue
        st = getattr(vp, "stack", None)
        # 합성본 검출이 있으면 그쪽을, 없으면 각 프레임 검출을 훑는다.
        if st and cur and cur.target == "stack":
            sources = [(Path(st.focused_path).stem, det, st.focused_path)]
        else:
            sources = [(f["name"], det, f["rel"])
                       for f in _frames(vp, det,
                                        cur.frame_id if cur else None)
                       if f["detection"]]
        for stem, d, image_rel in sources:
            for c in d["candidates"]:
                rows.append({
                    "group_id": vp.idx,
                    "stem": stem,
                    "overlay_rel": d.get("overlay_rel"),
                    "image_rel": image_rel,
                    "reviewed": d.get("review_done"),
                    "um_per_pixel": d.get("um_per_pixel"),
                    **c,
                })
    return rows


def scales_by_slide() -> dict:
    """슬라이드마다의 µm/px. 대물렌즈를 바꿔 찍으면 슬라이드마다 다르다.

    배율에 딸려가는 지표(texture)는 문턱을 슬라이드마다 따로 잡아야 한다 —
    같은 시료를 40x 와 100x 로 찍으면 texture 중앙값이 1,903 대 109 다(devlog 013).
    크기(µm)와 비율 지표는 배율과 무관하다.
    """
    # 재검출이 도는 중에는 한 슬라이드 안에 옛 값과 새 값이 섞인다. 처음 만난
    # 것을 집으면 진행 상황에 따라 표시가 널뛴다 — 가장 많은 쪽을 쓴다.
    # 한 슬라이드 안이 갈라진 것 자체는 check_db 가 따로 잡는다.
    per = defaultdict(Counter)
    for d in (Detection.objects.filter(is_current=True,
                                       um_per_pixel__isnull=False)
              .select_related("viewpoint__slide")):
        per[d.viewpoint.slide.slug][round(d.um_per_pixel, 9)] += 1
    return {slug: c.most_common(1)[0][0] for slug, c in per.items()}


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
def _summary_by_sql(slide: Slide) -> dict:
    """집계를 SQL 로 낸다. 개체 dict 를 만들지 않는다.

    **왜 따로 두는가.** 목록 화면은 개수 열 몇 개만 쓰는데, 예전에는 슬라이드마다
    모든 시야의 검출 dict 를 통째로 만들었다 — 개체 34,219개를 폴리곤(9 MB)까지
    파이썬으로 올렸다. 목록 한 장에 1.2초가 걸렸고 슬라이드가 늘면 선형으로 는다.

    **판정 규칙은 `_apply_review` 와 같아야 한다.** 다르면 목록과 상세 화면의
    숫자가 어긋나고, 그 숫자가 보고서에 실린다. 아래 세 줄이 그 규칙이다:

      통과분 중 사람이 지운 것을 뺀다 + 탈락분 중 사람이 되살린 것을 더한다
      분류는 사람이 지정한 것이 먼저, 되살린 것은 신장비로 짐작, 나머지는 자동 판정
      "사람지정" 은 통과분만 센다
    """
    reviews = ObjectReview.objects.filter(
        viewpoint=OuterRef("detection__viewpoint"), mask_key=OuterRef("mask_key"))
    cands = (Candidate.objects
             .filter(detection__viewpoint__slide=slide, detection__is_current=True)
             .annotate(
                 gone=Exists(reviews.filter(removed=True)),
                 back=Exists(reviews.filter(accepted=True)),
                 user_cls=Subquery(reviews.exclude(label="").values("label")[:1]),
             ))
    # 화면에 남는 개체: 통과분에서 지운 것을 빼고, 탈락분에서 되살린 것을 더한다
    kept = Q(passed=True, gone=False) | Q(passed=False, back=True)

    # 표시 분류. _guess_cls 와 같은 경계값이어야 한다.
    guess = Case(When(elongation__lt=1.4, then=Value("round")),
                 When(elongation__gte=2.0, elongation__lte=20.0, then=Value("rod")),
                 default=Value(""), output_field=CharField())
    eff = Case(
        When(~Q(user_cls=None) & ~Q(user_cls=""), then=F("user_cls")),
        When(passed=False, then=guess),          # 되살린 것 = 수동
        default=F("cls"), output_field=CharField())

    per_cls = {r["key"]: 0 for r in _class_rows()}
    agg = {k: Count("id", filter=kept & Q(eff_cls=k)) for k in per_cls}
    row = cands.annotate(eff_cls=eff).aggregate(
        n_detected=Count("id", filter=kept),
        n_auto=Count("id", filter=Q(passed=True)),
        n_labeled=Count("id", filter=kept & ~Q(user_cls=None) & ~Q(user_cls="")),
        **agg)
    per_cls = {k: row[k] for k in per_cls}

    # 검출이 돈 시야 수 — 평균의 분모다
    detected_groups = (Detection.objects
                       .filter(viewpoint__slide=slide, is_current=True).count())
    return {"per_cls": per_cls, "n_detected": row["n_detected"],
            "n_auto": row["n_auto"], "n_labeled": row["n_labeled"],
            "detected_groups": detected_groups}


def _slide_summary(slide: Slide, details: list | None = None) -> dict:
    """목록 화면의 집계.

    details 를 넘기면 그것을 쓴다 — dataset_detail 이 이미 시야를 다 훑었으므로
    두 번 계산하지 않는다. 없으면 SQL 로 센다(`_summary_by_sql`).
    """
    vps = Viewpoint.objects.filter(slide=slide)
    n_groups = vps.count()
    sizes = list(vps.values_list("n_frames", flat=True))
    n_img = sum(sizes)

    if details is None:
        r = _summary_by_sql(slide)
        per_cls = r["per_cls"]
        n_detected, n_auto = r["n_detected"], r["n_auto"]
        n_labeled, n_counts = r["n_labeled"], r["detected_groups"]
    else:
        per_cls = {k["key"]: 0 for k in _class_rows()}
        n_detected = n_auto = n_labeled = 0
        for det in details:
            n_detected += det["n_candidates"]
            n_auto += det["n_auto"]
            # 분류 지정은 **통과분만** 센다 — 탭 머리의 "사람지정" 과 같은 정의여야
            # 화면끼리 어긋나지 않는다(지웠다가 분류가 남은 개체가 있다).
            n_labeled += det["counts"].get("labeled", 0)
            for k in per_cls:
                per_cls[k] += det["counts"].get(k, 0)
        n_counts = len(details)
    counts = [None] * n_counts     # 개수만 쓴다

    rv = ObjectReview.objects.filter(viewpoint__slide=slide)
    agg = rv.aggregate(
        removed=Count("id", filter=Q(removed=True)),
        accepted=Count("id", filter=Q(accepted=True)),
        noted=Count("id", filter=~Q(note="")),
    )
    vrs = ViewpointReview.objects.filter(viewpoint__slide=slide)

    class_counts = [{"key": k, "label": _labels()[k], "n": v}
                    for k, v in per_cls.items() if v]
    # 세는 분류만 더한 값. 파편·미분류가 빠진다 (counted_classes 머리말).
    # 0 인 분류도 자리를 남긴다 — 목록 표의 열이 줄마다 같아야 세로로 맞는다.
    counted = [{**c, "n": per_cls.get(c["key"], 0)} for c in counted_classes()]
    n_counted = sum(c["n"] for c in counted)
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
        # 목록 화면이 쓰는 값. 시야당도 같은 분자로 낸다 — 분자가 다르면
        # "검출 ÷ 시야" 가 "시야당" 과 안 맞아 어느 쪽이 틀렸는지 알 수 없다.
        "n_counted": n_counted,
        "mean_counted": (round(n_counted / len(counts), 1) if counts else None),
        "counted": counted,
        "class_counts": class_counts,
        "n_removed": agg["removed"],
        "n_accepted": agg["accepted"],
        "n_labeled": n_labeled,
        "n_noted": agg["noted"],
        "n_group_notes": vrs.exclude(note="").count(),
        "reviewed_groups": vrs.filter(done=True).count(),
    }


def datasets(area: str | None = None) -> list[dict]:
    # groups_*.json 은 파이프라인에서 빠졌다(P02 7단계). 목록에 파일 이름 대신
    # 시료가 무엇인지와 어떤 배율로 찍혔는지를 보인다 — 그쪽이 화면에서 쓸모 있다.
    scales = scales_by_slide()
    out = []
    # 지역 → 코어 → 깊이 순. 들어온 순서(id)로 두면 같은 코어의 깊이들이 표에서
    # 떨어져 놓인다 — 깊이에 따른 변화를 보는 것이 분석 목적이라 그게 제일 아프다.
    # 지역·코어가 아직 안 붙은 슬라이드도 있어서 빈 값이 섞여도 죽지 않게 둔다.
    slides = (Slide.objects.select_related("core", "core__site")
              .order_by("core__site__code", "core__code", "depth_cm", "name"))
    # "전체" 는 거르지 않는다 — 지역이 안 붙은 슬라이드도 여기서는 보여야 한다.
    if area and area != AREA_ALL:
        slides = slides.filter(core__site__area=area)
    for slide in slides:
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


# "전체" 는 권역이 아니라 **거르지 않는다**는 뜻이다. `Site.area` 에 넣지 않는
# 이유가 그것이다 — 슬라이드가 "전체 권역" 에 속할 수는 없다.
AREA_ALL = "all"


def area_tabs(selected: str | None = None) -> dict:
    """목록 위의 [한국|남극|전체] 갈래. 각 권역의 슬라이드 수와 고른 것을 낸다.

    **고른 값을 여기서 정한다.** 화면이 `?area=` 를 그대로 믿으면 없는 값이
    들어왔을 때 빈 목록이 나오고, 왜 비었는지가 화면에 안 보인다.

    **아무것도 주지 않으면 `전체` 다.** 한때는 "자료가 있는 첫 권역" 이었는데,
    그러면 맨 처음 열리는 화면이 이미 한 번 걸러진 것이 된다 — 무엇이 빠졌는지
    모른 채 본다. 특히 지역이 안 붙은 슬라이드는 어느 권역에도 없어서, 새로
    반입된 것이 첫 화면에서 통째로 안 보였다.

    **`전체` 는 지역(Site)이 안 붙은 슬라이드까지 담는다.** 그것이 이 탭이
    있어야 하는 이유다 — 새로 반입된 슬라이드는 지역이 정해지기 전까지 한국에도
    남극에도 없어서, 있다는 것만 알리고 열어 볼 길이 없었다.
    """
    counts = dict(Slide.objects.filter(core__site__isnull=False)
                  .values_list("core__site__area")
                  .annotate(n=Count("id")))
    tabs = [{"key": k, "label": v, "n": counts.get(k, 0)} for k, v in Site.AREA]
    tabs.append({"key": AREA_ALL, "label": "전체",
                 "n": Slide.objects.count()})
    keys = [t["key"] for t in tabs]
    if selected not in keys:
        selected = AREA_ALL
    for t in tabs:
        t["on"] = t["key"] == selected
    return {
        "tabs": tabs,
        "selected": selected,
        "is_all": selected == AREA_ALL,
        # 권역을 물을 곳이 없는 슬라이드. 한국·남극 어느 탭에도 안 나오므로
        # 세어서 알리고 **전체 탭으로 가는 길을 함께 준다** — 알리기만 하고
        # 갈 곳이 없으면 안내가 아니라 막다른 길이다.
        "orphans": Slide.objects.filter(core__site__isnull=True).count(),
    }


def datasets_total(rows: list[dict]) -> dict:
    """목록 표의 합계 줄.

    합칠 수 있는 것만 합친다. 평균(`mean_size`·`mean_counted`)은 분모가 슬라이드마다
    달라서 다시 더할 수 없고, 배율은 슬라이드마다 다를 수 있다(devlog 015·017) —
    합계 칸을 비워 두는 편이 그럴듯한 숫자를 놓는 것보다 낫다.
    """
    keys = ("n_images", "n_groups", "n_detected", "n_counted",
            "reviewed_groups")
    total = {k: sum(r.get(k) or 0 for r in rows) for k in keys}
    # 분류별 합계도 열 순서 그대로 — 표의 열과 하나씩 맞아야 한다.
    per = {c["key"]: 0 for c in counted_classes()}
    for r in rows:
        for c in r.get("counted") or []:
            if c["key"] in per:
                per[c["key"]] += c["n"]
    total["counted"] = [{**c, "n": per[c["key"]]} for c in counted_classes()]
    return total


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
        # groups_*.json 은 파이프라인에서 빠졌다(P02 7단계). 파일 이름 대신
        # 시료가 무엇이고 어떤 배율로 찍혔는지를 보인다.
        "corr_thresh": slide.corr_thresh,
        "site": (slide.core.site.region or slide.core.site.name
                 or slide.core.site.code) if slide.core else "",
        "core": slide.core.code if slide.core else "",
        "depth_cm": slide.depth_cm,
        "um_per_pixel": scales_by_slide().get(slide.slug),
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
            # 촬영 시각은 사진에 딸린 XML 이, 반입 시각은 우리 시스템이 안다.
            # 둘은 다른 것이고 되짚을 때 둘 다 필요하다.
            "acquired_at": f.acquired_at,
            "created_at": f.created_at,
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
        "prev_url": (reverse("group", args=[slug, ids[pos - 1]])
                     if pos > 0 else None),
        "next_url": (reverse("group", args=[slug, ids[pos + 1]])
                     if pos < len(ids) - 1 else None),
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

    removed, accepted = set(removed), set(accepted)
    keys = removed | accepted | set(labels) | set(notes)
    by_key = {c.mask_key: c for c in
              Candidate.objects.filter(detection__viewpoint=vp,
                                       detection__is_current=True)}

    # **현재 검출에 없는 키는 받지 않는다.** 사람은 화면에 있는 것만 표시할 수
    # 있고, 화면은 현재 검출을 그린다. 그 밖의 키가 섞여 오면 다른 검출을 보고
    # 보낸 것이다 — 아래에서 `keys` 에 없는 행을 전부 지우므로, 그대로 두면
    # **엉뚱한 화면의 클릭 한 번이 그 시야의 교정을 통째로 갈아치운다.**
    #
    # 실제로 그렇게 잃었다: 시험용 화면(/engine/)이 YOLO 검출을 그리고 있었는데
    # 마스크를 클릭하자 그 키 하나만 담긴 POST 가 나갔고, 369cm g32 의 교정
    # 37건이 지워졌다. CSS 로 도구를 감춘 것으로는 못 막는다.
    #
    # 이미 교정 행이 있는 키는 통과시킨다 — 재바인딩에서 고아가 된 것들이
    # 그렇고, 그것들은 사람이 화면에서 지울 수 있어야 한다.
    known = set(by_key) | set(ObjectReview.objects.filter(viewpoint=vp)
                              .values_list("mask_key", flat=True))
    unknown = keys - known
    if unknown:
        raise ValueError(
            f"현재 검출에 없는 개체 {len(unknown)}개가 섞여 있다 — 저장하지 "
            f"않았다. 다른 검출을 보고 있지 않은지 확인할 것 "
            f"(예: {sorted(unknown)[:3]})")

    ViewpointReview.objects.update_or_create(
        viewpoint=vp, defaults={"done": done, "note": note})
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


# --- 다른 엔진 결과 보기 (시험용) ---------------------------------------------
def _engine_pick(dets):
    """한 시야에 쌓인 검출들 중 **화면이 그릴 것 하나씩** 고른다.

    같은 자리에 검출이 여럿 남을 수 있다. 두 가지 경로로 그렇게 된다:

    - 빠진 프레임만 다시 돌려도 `--keep-current` 는 이미 있는 것 위에 또 쌓는다
    - 첫 시도가 실패해 다시 돌린 것이 그대로 남아 있다 (SAM2 #37 → #39)

    **현재로 올라간 것, 그 다음 나중 것**을 고른다. 아무 것이나 고르면 화면과
    묶음 칸의 개수가 어긋나고 — 실제로 그렇게 어긋났다 — 첫 시도의 죽은 결과가
    그 묶음의 성적표인 것처럼 보인다.
    """
    by_frame, stack_det = {}, None
    for d in sorted(dets, key=lambda d: (d.is_current, d.pk)):
        if d.target == "frame":
            by_frame[d.frame_id] = d
        elif d.target == "stack":
            stack_det = d
    return by_frame, stack_det


def engine_runs() -> list[dict]:
    """검출을 **묶음 단위로** 낸다.

    검토 화면은 `is_current=True` 인 것만 본다. 나란히 쌓아 둔 다른 엔진의
    결과는 **어디에도 안 보인다** — 그것을 보려고 만든 목록이다.

    파이프라인이 슬라이드마다 도는 탓에 한 번의 작업이 실행 여럿으로 흩어진다.
    묶음(`RunBatch`)이 있으면 그것으로 묶고, 없으면 실행 하나를 묶음처럼 낸다.

    **묶음이 낸 것 전부를 센다.** 한때는 쌓인 것만 셌다 — 현재 검출은 검토
    화면에서 본다는 뜻이었는데, SAM2 묶음은 대부분이 현재로 올라가 있어서 그
    묶음이 거의 빈 것처럼 보였다. 현재로 올라간 수는 `n_current` 로 따로 낸다.
    """
    stacked = (Detection.objects.filter(run__kind="detect")
               .select_related("run__batch", "viewpoint__slide"))
    groups = {}
    for d in stacked:
        r = d.run
        key = ("b", r.batch_id) if r.batch_id else ("r", r.pk)
        g = groups.setdefault(key, {
            "is_batch": bool(r.batch_id),
            "label": r.batch.label if r.batch_id else f"실행 #{r.pk}",
            "note": r.batch.note if r.batch_id else "",
            "backend": (r.params or {}).get("backend", "?"),
            "params": r.params or {},
            "link_run": r.pk,
            "n_detections": 0, "slides": set(), "run_ids": set(),
        })
        g["n_detections"] += 1
        g["run_ids"].add(r.pk)
        if d.viewpoint:
            g["slides"].add(d.viewpoint.slide.slug)

    out = []
    for (kind, ident), g in groups.items():
        # **실행 수는 묶음 전체로 센다.** 쌓인 검출이 있는 실행만 세면 묶음이
        # 실제보다 작아 보인다 (SAM2 묶음은 11건 중 6건에만 쌓인 것이 있다).
        if g["is_batch"]:
            runs = Run.objects.filter(batch_id=ident)
            g["n_runs"] = runs.count()
            all_ids = list(runs.values_list("pk", flat=True))
            g["started_at"] = runs.order_by("started_at").first().started_at
        else:
            g["n_runs"] = 1
            all_ids = [ident]
            g["started_at"] = Run.objects.get(pk=ident).started_at
        g["n_current"] = Detection.objects.filter(
            run_id__in=all_ids, is_current=True).count()
        g["n_candidates"] = Candidate.objects.filter(
            detection__run_id__in=all_ids).count()
        g["slides"] = sorted(g["slides"])
        g["n_slides"] = len(g["slides"])
        g["run_ids"] = sorted(g["run_ids"])
        g["status"] = ", ".join(sorted(set(
            Run.objects.filter(pk__in=all_ids).values_list("status", flat=True))))
        out.append(g)
    out.sort(key=lambda g: g["started_at"], reverse=True)
    return out


def engine_detection(det: Detection) -> dict:
    """`is_current` 가 아닌 검출 하나를 화면이 쓰는 dict 로.

    **교정을 얹지 않는다.** 교정은 `mask_key`(bbox 문자열)로 붙는데 엔진이 다르면
    거의 전부 어긋난다. 억지로 얹으면 "사람이 지운 것" 이 엉뚱한 개체에 붙어
    보이게 된다. 이 화면의 목적은 **엔진이 무엇을 냈는가** 를 그대로 보는 것이다.

    `_apply_review` 에 빈 교정을 넘겨 같은 dict 모양을 얻는다 — 모양을 여기서
    다시 만들면 `_detection.html` 이 기대하는 칸이 하나라도 빠질 때 조용히
    깨진다.
    """
    return _apply_review(det, {}, None)


def engine_viewpoint(slug: str, gid: int, run_id: int) -> dict | None:
    """시험 화면 한 장. `group_detail` 과 같은 모양이되 검출만 갈아 끼운다.

    YOLO 는 **프레임마다** 검출을 낸다(합성본이 아니라 원본을 본다). 그래서
    프레임 하나하나에 각자의 검출이 붙는다 — `group_detail` 이 싱글턴에 쓰던
    길과 같다.
    """
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return None
    vp = _viewpoints_of(slide).filter(idx=gid).first()
    if vp is None:
        return None

    # 묶음이면 형제 실행까지 본다 — 한 슬라이드가 한 실행이라 시야를 열면
    # 그 시야를 만든 실행은 하나뿐이지만, 주소의 실행 번호가 다른 슬라이드
    # 것일 수 있다.
    # **현재 검출도 함께 본다.** 예전에는 쌓아 둔 것만 봤다 — 검토 화면과
    # 겹치지 않게 하려는 뜻이었다. 그런데 SAM2 묶음은 결과의 대부분이 현재로
    # 올라가 있어서, 묶음을 고를 수 있게 되자 "SAM2 칸을 눌렀는데 아무것도
    # 없다" 가 됐다. 견주려면 그 묶음이 **실제로 낸 것**을 봐야 한다.
    # 이 화면은 읽기 전용이고 교정을 얹지 않으므로 검토 화면을 건드리지 않는다.
    ids = set(engine_run_ids(run_id))
    by_frame, stack_det = _engine_pick(
        [d for d in vp.detections.all() if d.run_id in ids])

    # **엔진마다 검출을 다는 자리가 다르다.** SAM2 는 합성본 한 장에만 달고,
    # YOLO 는 프레임마다 + 합성본에도 단다. 프레임만 보면 SAM2 묶음은 통째로
    # 빈 화면이 된다 — 묶음을 고를 수 있게 된 뒤로는 사람이 그 빈 화면을 직접
    # 누르게 된다.

    frames = []
    for f in vp.frames.all():
        d = by_frame.get(f.id)
        frames.append({
            "name": f.name,
            "acquired_at": f.acquired_at,
            "created_at": f.created_at,
            "sharpness": f.sharpness,
            "is_sharpest": f.is_sharpest,
            "rel": f.path,
            "exists": (Path(settings.DATA_ROOT) / f.path).exists(),
            "detection": engine_detection(d) if d else None,
        })

    ids = list(Viewpoint.objects.filter(slide=slide)
               .order_by("idx").values_list("idx", flat=True))
    pos = ids.index(gid)
    st = getattr(vp, "stack", None)

    # **한 화면에서 캐러셀로 갈아 본다.** 프레임마다 화면을 따로 그리면 세로로
    # 늘어서서 견줄 수가 없다 — 같은 자리에서 프레임만 바뀌어야 "이 규조각이
    # 어느 초점면에서 잡혔나" 가 보인다. 판 하나를 그리고 나머지는 캐러셀이
    # 갈아 끼울 자료로 넘긴다.
    def _shot(d):
        c = d["counts"]
        parts = [f"{k} {c[k]}" for k in ("rod", "round", "rod_frag",
                                         "round_frag", "eucampia") if c.get(k)]
        return {
            "candidates": d["candidates"],
            "rejected": d["rejected"],
            "summary": (f"후보 {d['n_candidates']}개"
                        + (f" ({', '.join(parts)})" if parts else "")
                        + f" · 원시 {d['n_raw_masks']}"
                        + (f" → 크기통과 {d['n_sized']}" if d['n_sized'] else "")
                        + f" · 탈락 {len(d['rejected'])}개"),
        }

    stack = (_stack_dict(st, engine_detection(stack_det))
             if st and stack_det else None)
    if stack:
        stack["detkey"] = STACK_KEY

    # 캐러셀이 갈아 끼울 판들. 합성본도 프레임과 같은 자격으로 넣는다.
    pool = [{"key": f["name"], "rel": f["rel"], "det": f["detection"]}
            for f in frames if f["detection"]]
    if stack:
        pool.append({"key": STACK_KEY, "rel": stack["focused_rel"],
                     "det": stack["detection"]})

    shots = {p["key"]: _shot(p["det"]) for p in pool}
    # 개체가 가장 많은 판에서 시작한다 — 빈 프레임이 먼저 열리면 검출이
    # 아무것도 없는 줄 알게 된다.
    best = max(pool, key=lambda p: len(p["det"]["candidates"]), default=None)
    return {
        "slug": slug, "label": slide.name, "id": gid, "tag": vp.tag,
        "run_id": run_id,
        "frames": frames,
        "stack": stack,
        "base_rel": best["rel"] if best else None,
        "base_det": best["det"] if best else None,
        "base_name": (("합성본" if best["key"] == STACK_KEY else best["key"])
                      if best else None),
        "shot_dets": shots,
        "n_objects": sum(len(p["det"]["candidates"]) for p in pool),
        "n_frames_with_det": sum(1 for p in pool if p["key"] != STACK_KEY),
        "has_stack_det": stack is not None,
        "prev_id": ids[pos - 1] if pos > 0 else None,
        "next_id": ids[pos + 1] if pos < len(ids) - 1 else None,
        # **이 화면 안에 머문다.** 사진 띠의 시야 이동 단추가 검토 화면 주소를
        # 박아 두고 있어서, 여기서 "다음 시야" 를 누르면 /d/ 로 튀어나갔다.
        "prev_url": (reverse("engine_view", args=[run_id, slug, ids[pos - 1]])
                     if pos > 0 else None),
        "next_url": (reverse("engine_view", args=[run_id, slug, ids[pos + 1]])
                     if pos < len(ids) - 1 else None),
    }


# 캐러셀에서 합성본을 가리키는 열쇠. 프레임 이름(`Snap-…`)과 겹칠 수 없어야
# 한다 — 겹치면 프레임을 눌렀는데 합성본 검출이 얹힌다.
STACK_KEY = "__stack__"


def engine_run_ids(run_id: int) -> list[int]:
    """실행 하나가 묶음에 속하면 그 묶음의 실행 전부를, 아니면 자기만.

    화면은 묶음을 하나처럼 다룬다. 주소에는 실행 번호가 들어가지만, 그 실행이
    묶여 있으면 형제들까지 함께 보여야 "전체를 한 번 훑은 것" 이 한 화면에 온다.
    """
    r = Run.objects.filter(pk=run_id).select_related("batch").first()
    if r is None:
        return []
    if r.batch_id:
        return list(Run.objects.filter(batch_id=r.batch_id)
                    .values_list("pk", flat=True))
    return [r.pk]


def engine_viewpoints(run_id: int) -> list[dict]:
    """실행(또는 그 묶음)이 건드린 시야 목록. 어디부터 볼지 고르는 화면에 쓴다.

    수는 `_engine_pick` 으로 고른 것만 센다 — 같은 자리에 쌓인 것을 다 더하면
    목록이 시야 화면보다 커 보인다.
    """
    ids = engine_run_ids(run_id)
    per = defaultdict(list)
    for d in (Detection.objects.filter(run_id__in=ids, viewpoint__isnull=False)
              .select_related("viewpoint__slide")
              .annotate(n=Count("candidates", filter=Q(candidates__passed=True)))):
        per[d.viewpoint].append(d)

    rows = []
    for vp, dets in per.items():
        by_frame, stack_det = _engine_pick(dets)
        picked = list(by_frame.values()) + ([stack_det] if stack_det else [])
        rows.append({"slug": vp.slide.slug, "label": vp.slide.name,
                     "idx": vp.idx, "tag": vp.tag,
                     "n_detections": len(picked),
                     "n_objects": sum(d.n for d in picked)})
    return sorted(rows, key=lambda r: (r["slug"], r["idx"]))


def batches_for_viewpoint(slug: str, gid: int,
                          run_id: int | None = None) -> list[dict]:
    """이 시야에 쌓여 있는 묶음들. 검출 화면에서 갈아 끼우는 데 쓴다.

    **같은 시야를 보면서 엔진을 바꿀 수 있어야 한다.** 목록으로 나갔다가 다른
    묶음으로 들어오면 어느 시야를 보고 있었는지 잃는다 — 견주기는 같은 자리를
    번갈아 보는 일이다.

    주소에는 실행 번호가 들어가지만 화면은 묶음 단위로 다루므로, 각 묶음에서
    **아무 실행 하나**를 대표로 준다(`engine_run_ids` 가 형제까지 편다).

    칸마다 개체 합계를 함께 준다. 눌러 보기 전에 "여기서는 몇 개를 잡았나" 를
    견주는 것이 이 화면의 목적이고, 그 수가 묶음을 고르는 근거이기 때문이다.
    """
    vp = (Viewpoint.objects.filter(slide__slug=slug, idx=gid)
          .prefetch_related("detections__run__batch").first())
    if vp is None:
        return []
    # 검토 화면에서 부를 때는 "지금 보고 있는 묶음" 이 없다 — 그때는 아무것도
    # 켜지지 않는다.
    here = set(engine_run_ids(run_id)) if run_id else set()

    per = defaultdict(list)
    for d in vp.detections.all():
        if d.run_id is None:
            continue
        r = d.run
        per[("b", r.batch_id) if r.batch_id else ("r", r.pk)].append(d)

    # **화면이 세는 것과 같은 것을 센다.** 화면은 문턱을 통과한 것만 그리므로
    # 칸이 원시 개수를 보이면 눌러 보고 "아까 그 수가 아닌데" 가 된다. 교정은
    # 얹지 않는 화면이라 `passed` 하나로 갈린다(`_apply_review`).
    out = []
    for key, dets in per.items():
        by_frame, stack_det = _engine_pick(dets)
        picked = list(by_frame.values()) + ([stack_det] if stack_det else [])
        rep = next((d for d in picked if d.run_id in here), picked[0])
        out.append({
            "label": (rep.run.batch.label if rep.run.batch_id
                      else f"실행 #{rep.run_id}"),
            "backend": (rep.run.params or {}).get("backend", "?"),
            "run_id": rep.run_id,
            "on": any(d.run_id in here for d in picked),
            # 검토 화면이 이미 보여 주는 것인가 — 거기서 길을 낼 때 쓴다
            "current": any(d.is_current for d in picked),
            "n": Candidate.objects.filter(
                detection__in=picked, passed=True).count(),
        })
    return sorted(out, key=lambda g: g["label"])
