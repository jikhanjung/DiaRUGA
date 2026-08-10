"""DB 에서 읽어 뷰가 쓰기 좋은 형태로 만든다.

전에는 JSON 을 직접 읽었다(슬라이드 3장에 첫 화면이 251개 파일을 열었다).
설계와 이전 과정은 devlog/20260730_P02_db-schema.md.

**함수 이름과 반환 형태는 JSON 시절과 같게 유지한다** — 템플릿과 뷰를 건드리지
않고 갈아 끼울 수 있어야 하고, 그래야 같은 화면이 나오는지 대조할 수 있다.
그래서 여기서 만드는 것은 모델 인스턴스가 아니라 예전 그대로의 dict 다.

기하 계산(주축·스케일바)은 DB 와 무관하므로 그대로 두었다.
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.urls import reverse
from django.db import connection, transaction
from django.db.models import Case, Count, Prefetch, Q, When
from django.utils import timezone

from . import antarctica, korea, outcrop
from . import shape
from .models import (Candidate, ClassDef, Detection, Frame, Locality,
                     ObjectLink, ObjectLinkMember, ObjectReview,
                     Run, RunBatch, Site, Slide, Stack, Viewpoint,
                     ViewpointReview)

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
    """마스크의 안정적인 식별자. dict 와 Candidate 둘 다 받는다.

    **dict 에 `key` 가 있으면 그것이 먼저다** (P09 2단계). 지금까지는 키가 곧
    bbox 문자열이라 기하에서 다시 만들어도 같았다. 그런데 **후보 없이 교정만
    남은 개체**는 그 등식이 깨질 수 있다 — 사람이 기하를 고치면(4단계) bbox 는
    바뀌고 키는 그대로여야 한다. 기하에서 키를 만들면 그 순간 **다른 개체가
    되어 옛 행이 지워진다.**

    화면의 `keyOf()` 도 같은 규칙이다. 둘이 갈라지면 화면이 보내는 키와 서버가
    아는 키가 어긋나고, `/review` 는 모르는 키를 지운다.
    """
    if isinstance(c, dict):
        if c.get("key"):
            return c["key"]
        b = c.get("bbox_xywh") or [0, 0, 0, 0]
    else:
        b = c.bbox_xywh
    return "_".join(str(int(v)) for v in b)


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
        # **키를 늘 실어 보낸다** (P09 4단계). 지금까지는 기하에서 다시 만들어도
        # 같았는데, 사람이 경계를 고치면 bbox 가 바뀌고 키는 그대로여야 한다 —
        # 기하에서 만들면 그 순간 **다른 개체가 되어 옛 행이 지워진다.**
        # 안 고친 개체에서도 값이 같으므로 늘 넣어 그 갈래를 아예 없앤다.
        "key": c.mask_key,
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


def _key_bbox(key: str):
    """`mask_key` 에서 bbox 를 되살린다. 키가 `x_y_w_h` 일 때만 된다.

    `rebind.key_to_bbox` 와 같은 규칙이다. 저쪽을 임포트하지 않는 것은 뷰어가
    저장소 뿌리의 스크립트에 매이지 않게 하려는 것이고(컨테이너 안에서 코드가
    `/app` 이다), 규칙이 **되살리기 전용의 보조**라 갈라져도 값이 안 틀린다 —
    맞으면 쓰고 아니면 `geom` 을 본다.
    """
    try:
        x, y, w, h = (int(v) for v in key.split("_"))
    except ValueError:
        return None
    return [x, y, w, h]


def _orphan_dict(key: str, o, um_per_px=None) -> dict | None:
    """**후보 없이 교정만 남은 개체**를 화면이 그릴 수 있는 모양으로 (P09 2단계).

    두 가지가 여기로 온다.

    - **고아**(`bind_method="orphan"`) — 재검출에서 대응 후보를 못 찾은 것.
      사람의 판단은 살아 있는데 엔진이 그 자리에 아무것도 안 냈다
    - **사람이 그린 개체**(`source="manual"`) — 3단계부터 생긴다

    **안 그리면 다음 저장에 지워진다.** 화면은 자기가 아는 키만 보내고
    `save_review` 의 마지막 줄은 payload 에 없는 키를 지운다 — 사람이 아무것도
    안 하고 "검토 완료" 만 눌러도 사라진다. 시험이 그것을 재현해 두었다.

    기하가 없으면 `None` 이다. 그릴 것이 없으면 화면에 낼 수 없고, 그 상태는
    `check_db.py` 의 "교정이 기하를 갖고 있다" 가 따로 센다.
    """
    geom = o.geom or {}
    bbox = geom.get("bbox") or _key_bbox(key)
    if not bbox or len(bbox) != 4:
        return None
    x, y, w, h = (int(v) for v in bbox)
    poly = geom.get("polygon") or []
    d = {
        # **키를 실어 보낸다.** 기하에서 다시 만들면 안 된다 — 4단계에서 사람이
        # 경계를 고치면 bbox 가 바뀌는데 키는 그대로여야 한다 (`cand_key`).
        "key": key,
        "bbox_xywh": [x, y, w, h],
        "center_xy": [x + w // 2, y + h // 2],
        "area_px": geom.get("area_px") or 0,
        "shape_ok": False,
        "polygon": list(poly),
        # **엔진이 낸 것이 아니라는 표시.** 화면이 이것으로 갈라 그린다 —
        # 지표가 비어 있는 이유이기도 하다(`Candidate` 가 없어 잰 적이 없다).
        "orphan": True,
        "source": o.source,
    }
    # **지표는 저장하지 않고 그때그때 잰다** (P09 3단계). 폴리곤이 원본이고
    # 지표는 거기서 나오는 값이라, 따로 넣어 두면 **기하를 고쳤을 때 낡는다**
    # (4단계에서 사람이 경계를 고친다). 개체 하나에 점 13~19개라 재는 값이
    # 싸고, 뷰어에 numpy·cv2 를 안 들이는 경계도 지킨다(`shape.py` 머리말).
    m = shape.measure(d["polygon"], um_per_px) if d["polygon"] else {}
    for f in NUM_FIELDS:
        d[f] = m.get(f)
    if m.get("area_px"):
        d["area_px"] = m["area_px"]
    if o.label:
        d["cls"] = o.label
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

    **부르는 자리는 없다.** 시야 목록이 이 규칙을 SQL 로 옮겨 갔다(`_COVER_SQL`,
    060). 규칙이 셋(여기 · SQL · 뷰어의 `addPolygon`)이 되면 어긋나므로, 다음에
    파이썬 쪽에서 마스크를 그릴 일이 생기면 **이것을 되쓰거나 함께 고친다.**
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
def _apply_review(det: Detection, reviews: dict, state) -> dict:
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

    # **후보가 없는 교정도 그린다** (P09 2단계). 재검출이 낳은 고아와, 3단계부터
    # 사람이 그린 개체가 여기로 온다.
    #
    # **안 그리면 다음 저장에 지워진다** — 화면은 자기가 아는 키만 보내고
    # `save_review` 는 payload 에 없는 키를 지운다. 사람이 아무것도 안 하고
    # "검토 완료" 만 눌러도 사라진다. 시험이 그 갈래를 재현해 둔다
    # (`OrphanReviewSurvivesTest`).
    seen = {c.mask_key for c in det.candidates.all()}
    for key, o in reviews.items():
        if key in seen:
            continue
        d = _orphan_dict(key, o, det.um_per_pixel)
        if d is None:
            continue
        (gone if o.removed else kept).append(d)

    # 사람이 지정한 분류·메모를 얹는다. 원래 값은 cls_auto 로 남긴다.
    for d in kept + gone:
        o = reviews.get(cand_key(d))
        if not o:
            continue
        # **사람이 고친 기하가 엔진 것을 덮는다** (P09 4단계). `geom` 이 원본이고
        # 엔진의 `Candidate` 는 그대로 둔다 — 검출 이력에서 엔진이 낸 것과 사람이
        # 손댄 것을 못 가르게 되면 회차 비교가 무의미해진다 (P09 5.6).
        if o.geom_edited and (o.geom or {}).get("polygon"):
            d["polygon"] = list(o.geom["polygon"])
            if o.geom.get("bbox"):
                d["bbox_xywh"] = list(o.geom["bbox"])
                bx, by, bw, bh = d["bbox_xywh"]
                d["center_xy"] = [bx + bw // 2, by + bh // 2]
            d["geom_edited"] = True
            # **기하가 바뀌었으면 지표도 다시 잰다.** 안 재면 화면이 옛 모양의
            # 면적·장축을 새 마스크 옆에 적는다 — 예외 없이 틀린 숫자다.
            #
            # `texture`·`predicted_iou`·`stability_score` 는 **그대로 둔다**:
            # 픽셀이 있어야 나오는 값이라 여기서 못 재고, 엔진이 잰 영역과 거의
            # 같은 자리다. 다시 잰 것과 아닌 것이 섞이므로 **화면이 고쳤다는
            # 사실을 적는다**(말풍선).
            m = shape.measure(d["polygon"], det.um_per_pixel)
            for f in NUM_FIELDS:
                if f in ("texture", "predicted_iou", "stability_score"):
                    continue
                d[f] = m.get(f)
            if m.get("area_px"):
                d["area_px"] = m["area_px"]
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
    # 그래서 Chaetoceros 를 테이블에 넣어도 이 줄에만 안 나왔다. 테이블이 정하게 바꾼다.
    # 0 인 분류는 뺀다. 여기는 표가 아니라 한 줄이라 자리를 맞출 것이 없고,
    # 짧을수록 읽힌다.
    order = ([(r["key"], r["short"]) for r in _class_rows()]
             + [("manual", "수동"), ("labeled", "사람지정")])
    counts_list = [{"key": k, "label": lb, "n": counts[k]}
                   for k, lb in order if counts.get(k)]

    stem = Path(det.image_path).stem
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
        # **사람이 그린 개체는 여기 안 담는다** (P09 3단계). 이 둘은 화면이 저장
        # payload 로 되돌려 보내는 지도인데, 그린 개체의 분류·코멘트는 `drawn`
        # 이 통째로 나른다 — 양쪽에 실으면 `save_review` 가 같은 키로 **엔진
        # 쪽 행을 하나 더 만든다**(`batch` 가 달라 유일 제약에 안 걸린다).
        #
        # 분류·코멘트 자체는 개체 dict 의 `cls`·`note` 로 이미 화면에 간다.
        "labels": {k: o.label for k, o in reviews.items()
                   if o.label and o.source != "manual"},
        "notes": {k: o.note for k, o in reviews.items()
                  if o.note and o.source != "manual"},
        "review_done": bool(state and state[0]),
        "review_note": (state[1] if state else ""),
        "source_dir": "out",
    }


def map_points(area: str | None = None,
               with_hidden: bool = False) -> list[dict]:
    """지도에 찍을 지역별 묶음. 슬라이드가 아니라 **지역 단위**다.

    같은 코어의 깊이별 슬라이드는 좌표가 같으므로 겹쳐 찍으면 하나로 보인다.
    지역으로 묶고 그 안에 슬라이드를 세는 편이 지도에서 읽힌다.

    좌표는 `Site.lat/lon` 이 원칙이고, 비어 있으면 해역 대략값으로 물러난다.
    **어느 쪽인지 반드시 함께 낸다** — 대략값을 실측처럼 보이게 두면 안 된다.

    **권역마다 투영이 다르다.** 남극은 EPSG:3031(극구면), 한국은 EPSG:5179
    (횡메르카토르)다. 마커를 엉뚱한 투영으로 찍으면 지도와 어긋나므로 권역에
    맞는 것을 고른다 — 그래서 `area` 는 거르기용이 아니라 **투영을 정하는 값**이다.

    **숨긴 슬라이드는 여기서도 뺀다** — 세 보기가 같은 것을 봐야 한다. 지도만
    남으면 마커의 "슬라이드 N장" 이 표의 장수와 안 맞는다.
    """
    area = area or "ant"
    if area == "kr":
        approx_sites, project = korea.APPROX_SITES, _korea_xy
    else:
        approx_sites, project = antarctica.APPROX_SITES, _polar_xy

    sites = (Site.objects.filter(area=area)
             .prefetch_related("localities__samples__slides"))

    def visible(qs):
        return [sl for sl in qs if with_hidden or not sl.hide_in_list]

    def slides_of(loc):
        """지점 아래의 관찰 전부. **시료를 한 겹 거친다** (P07)."""
        return [sl for sm in loc.samples.all() for sl in visible(sm.slides.all())]

    out = []
    for site in sites:
        slides = [sl for loc in site.localities.all() for sl in slides_of(loc)]
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

        # 지점 아래에 관찰을 매단다. 시료의 위치순이다 — 한 지점에서 위치에 따른
        # 변화를 보는 것이 이 시료의 목적이라 그 순서로 읽혀야 한다.
        # 시추코어는 깊이로, 노두는 단면상의 위치로 선다(`Sample.position`).
        cores = []
        for loc in sorted(site.localities.all(), key=lambda c: c.code):
            rows = sorted(slides_of(loc), key=_slide_order)
            if not rows:
                continue
            cores.append({
                "code": loc.code,
                "kind": loc.kind,
                "n_slides": len(rows),
                "slides": [{
                    "slug": sl.slug,
                    "label": sl.name,
                    "depth_cm": sl.depth_cm,
                    "sample_kind": sl.sample_kind,
                    "state": sl.state,
                    # 지도 목록은 깊이만 적는다 — 같은 깊이의 관찰 둘이 글자
                    # 그대로 같아 보인다. 배지가 그것을 가른다.
                    **_obs(sl),
                    "n_viewpoints": sl.viewpoints.count(),
                    # **고른 묶음의 완료만 센다** (073) — 묶음마다 따로다
                    "reviewed": len(done_viewpoints(slide=sl)),
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
    for vp in _viewpoints_of(slide, only_current=True):
        # **이미지마다 자기 검출을 만든다** (P09 1단계). 시야 하나에 현재 검출이
        # 여럿일 수 있고(합성본 하나 + 프레임마다 하나), `_frames` 는 그것을
        # 경로로 맞춘다 — 검토 화면(`viewpoint_detail`)과 같은 자료다.
        dets = current_detections(vp)
        if not dets:
            continue
        bmap = batch_ids_of(dets)
        by_path = {d.image.path: (d.image_id, _with_reviews(vp, d, bmap[d.pk]))
                   for d in dets if d.image_id}
        st = getattr(vp, "stack", None)
        # 합성본 검출이 있으면 그쪽을, 없으면 각 프레임 검출을 훑는다.
        stacked = by_path.get(st.focused_path) if st else None
        if stacked:
            sources = [(Path(st.focused_path).stem, stacked[1], st.focused_path)]
        else:
            # **프레임마다 자기 검출을 준다.** 예전에는 대표 검출 하나를 프레임
            # 수만큼 되돌려 같은 개체가 여러 줄로 나왔다.
            sources = [(f["name"], f["detection"], f["rel"])
                       for f in _frames(vp, by_path) if f["detection"]]
        for stem, d, image_rel in sources:
            for c in d["candidates"]:
                rows.append({
                    "group_id": vp.idx,
                    "stem": stem,
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
    for d in (Detection.objects.reviewing().filter(
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

    done, note = review_state(vp)
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
        "review_done": done,
        "review_note": note,
        "source_dir": "out",
        # 이 화면은 아직 검출이 없다 — 템플릿이 도구를 감추는 데 쓴다
        "preview_only": True,
    }


def batches_to_run() -> list[dict]:
    """새 자료가 들어왔을 때 **어떤 순서로 어느 묶음을 채우는가** (079).

    순서는 사람이 정했다(2026-08-07): **검토 중인 묶음이 먼저, 나머지는 최근
    것부터.** 이유가 있다 — 지금 사람이 보고 있는 화면이 가장 먼저 메워져야
    하고, 그 다음은 최근 회차일수록 다시 볼 일이 많다. GPU 는 한 번에 하나만
    도므로(잠금이 `segment_diatoms` 안에 있다) 이 순서가 곧 기다리는 순서다.

    **조리법이 없으면 안 돈다.** 끝난 회차를 그대로 두는 것이 기본이다.

    **가중치 파일이 없으면 못 돈다.** 그때는 목록에 남기되 `ready=False` 와
    이유를 함께 준다 — 조용히 빠지면 "왜 이 묶음만 비어 있나" 를 나중에 묻게
    된다. 가중치는 NAS 로 함께 백업한다(`sync_backup_nas.sync_models`).

    돌려주는 것: `[{"batch": RunBatch, "recipe": dict, "ready": bool,
                   "why": str}, …]`
    """
    root = Path(settings.DATA_ROOT)

    rows = []
    for b in RunBatch.objects.filter(kind="detect").exclude(recipe={}):
        r = dict(b.recipe)
        ready, why = True, ""
        w = r.get("weights")
        if r.get("backend") == "yolo":
            if not w:
                ready, why = False, "조리법에 가중치가 없다"
            else:
                path = Path(w) if Path(w).is_absolute() else root / w
                if not path.exists():
                    ready, why = False, f"가중치 파일이 없다: {path}"
        rows.append({"batch": b, "recipe": r, "ready": ready, "why": why})

    # 검토 중인 것 먼저, 그다음 최근 것부터. `started_at` 은 묶음이 생긴 때다.
    rows.sort(key=lambda x: (not x["batch"].for_review,
                             -x["batch"].started_at.timestamp()))
    return rows


def review_state(vp, batch_id=None):
    """그 시야의 `(검토 완료, 시야 코멘트)` — **완료는 묶음마다다** (073).

    `done` 은 "이 묶음이 낸 검출을 여기서 다 봤다" 이고, `note` 는 "이 시야가
    이러이러하다" 이다. 뒤엣것은 묶음을 갈아도 참이라 `batch=NULL` 줄에 산다
    (`ViewpointReview` 머리말).

    **읽는 자리를 하나로 모은다** — 흩어져 있으면 뜻이 바뀔 때 전부 틀리는데
    예외가 안 난다(P10 1단계에서 `is_current` 로 같은 일을 했다).
    """
    if batch_id is None:
        batch_id = review_batch_id()
    done, note = False, ""
    for r in ViewpointReview.objects.filter(viewpoint=vp):
        if r.batch_id is None:
            note = r.note
        elif r.batch_id == batch_id:
            done = r.done
    return done, note


def done_viewpoints(batch_id=None, *, slide=None, ids=None) -> set:
    """검토 완료로 표시된 시야 pk 들. **고른 묶음 것만 센다** (073)."""
    if batch_id is None:
        batch_id = review_batch_id()
    if batch_id is None:
        return set()
    qs = ViewpointReview.objects.filter(done=True, batch_id=batch_id)
    if slide is not None:
        qs = qs.filter(viewpoint__slide=slide)
    if ids is not None:
        qs = qs.filter(viewpoint_id__in=ids)
    return set(qs.values_list("viewpoint_id", flat=True))


def review_batch_label():
    """검토 대상 묶음의 이름. 없으면 빈 문자열 (P10 4단계).

    화면이 "무엇의 검출이 없다" 를 적으려면 이름이 필요하다.
    """
    return (RunBatch.objects.filter(for_review=True)
            .values_list("label", flat=True).first() or "")


def batches_elsewhere(slide=None, vp=None) -> dict:
    """시야 pk → **검토 대상이 아닌 묶음 중 검출이 있는 것**들의 이름 (P10 4단계).

    "이 시야가 빈 이유" 를 화면이 말하려면 이것이 있어야 한다. 검출이 아예 없는
    것과 **다른 묶음에는 있는 것**은 다른 말이고, 뒤엣것을 "검출은 아직입니다"
    라고 적으면 거짓말이다 — 사람이 돌리러 간다.
    """
    rb = review_batch_id()
    qs = Detection.objects.filter(is_current=True)
    if slide is not None:
        qs = qs.filter(viewpoint__slide=slide)
    if vp is not None:
        qs = qs.filter(viewpoint=vp)
    if rb is not None:
        qs = qs.exclude(run__batch_id=rb)
    out = defaultdict(list)
    for vp_id, label in (qs.values_list("viewpoint_id", "run__batch__label")
                         .distinct()):
        if label and label not in out[vp_id]:
            out[vp_id].append(label)
    return out


def review_batch_id():
    """검토 대상 묶음의 pk. 없으면 `None` (P10).

    **서버 설정이라 요청마다 한 번만 읽으면 된다.** 관리 화면이 바꾸면 다음
    요청부터 따른다 — 프로세스가 여럿이라 캐시하면 판이 갈린다.
    """
    return (RunBatch.objects.filter(for_review=True)
            .values_list("id", flat=True).first())


def pipeline_status() -> dict:
    """파이프라인이 지금 어떤 상태인가 — 시스템 설정 · 파이프라인 탭 (098).

    097 이 이 화면의 값을 증명했다: 폴러 3단계가 사흘을 조용히 죽어 있었는데
    (026 때는 4시간 반), **멈춘 것을 알려 주는 자리가 없어** 새 슬라이드가
    pending 에 걸리고서야 사람이 알았다. 뷰어는 늘 열려 있다 — 여기가 그 자리다.

    셋을 모은다:

    - **정찰** — `logs/last_scan.json` 의 mtime 과 내용. 폴러 1단계가 매분
      다시 쓰므로 이 파일의 나이가 곧 "폴러가 살아 있는가" 다
    - **실행** — `Run` 최근 것들. "마지막으로 언제 돌았는가" 는 여기 있다
    - **밀린 슬라이드** — `done` 이 아닌 것 전부와 각각의 진행(시야·합성·검출)

    파일이 없거나 못 읽으면 그렇게 말한다 — 개발 서버(`/data3` 밖)에서는
    정찰 파일이 없는 것이 정상이라, 없음을 고장처럼 그리지 않는 것은 화면 몫이다.
    """
    import json as _json
    now = timezone.now()

    scan = {"exists": False, "age_min": None, "slides": [], "error": ""}
    scan_path = Path(settings.DATA_ROOT) / "logs" / "last_scan.json"
    try:
        st = scan_path.stat()
        scan["exists"] = True
        scan["age_min"] = round((now.timestamp() - st.st_mtime) / 60, 1)
        d = _json.loads(scan_path.read_text(encoding="utf-8"))
        scan["slides"] = [{"rel": r.get("rel", ""), "state": r.get("state", ""),
                          "jpgs": r.get("jpgs", 0),
                          "stable_min": round(r.get("stable_min") or 0, 1)}
                         for r in d.get("slides", [])]
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        scan["error"] = f"{type(e).__name__}: {e}"

    runs = []
    for r in (Run.objects.select_related("slide", "batch")
              .order_by("-started_at")[:12]):
        dur = None
        if r.finished_at:
            dur = round((r.finished_at - r.started_at).total_seconds() / 60, 1)
        runs.append({
            "kind": r.kind, "status": r.status,
            "slide": r.slide.slug if r.slide else "",
            "batch": r.batch.label if r.batch else "",
            "started_at": r.started_at, "finished_at": r.finished_at,
            "minutes": dur,
            "error": (r.error or "")[:200],
        })

    # 밀린 슬라이드 — done 이 아닌 전부. 시야·합성·검출 수로 어디까지 왔는지
    # 함께 낸다 (state_note 는 파이프라인이 적는 문장 그대로).
    busy = []
    for sl in Slide.objects.exclude(state="done").order_by("pk"):
        vps = Viewpoint.objects.filter(slide=sl).count()
        stacks = Stack.objects.filter(viewpoint__slide=sl).count()
        dets = (Detection.objects.filter(viewpoint__slide=sl, is_current=True)
                .values("viewpoint_id").distinct().count())
        busy.append({
            "slug": sl.slug, "name": sl.name, "state": sl.state,
            "note": sl.state_note or "",
            "n_frames": Frame.objects.filter(slide=sl).count(),
            "n_vps": vps, "n_stacks": stacks, "n_det_vps": dets,
            "discovered_at": sl.discovered_at, "copied_at": sl.copied_at,
        })

    last_done = (Run.objects.exclude(finished_at=None)
                 .order_by("-finished_at").first())

    # 경고 — 사람이 각 값을 해석하게 두지 않고 화면이 먼저 말한다 (097).
    #
    # **긴 작업이 도는 중이면 정찰이 늙는 것이 정상이다.** 폴러는 flock 하나로
    # 돌아서, 한 주기가 합성·검출(몇 시간)을 쥐고 있으면 다음 정찰이 그만큼
    # 밀린다 — 실제로 이 화면을 처음 띄운 날 합성 도중이라 거짓 경고부터 냈다.
    # 도는 실행이 있으면 접는다.
    warnings = []
    running = [r for r in runs if r["status"] == "running"]
    if (scan["exists"] and scan["age_min"] is not None
            and scan["age_min"] > 5 and not running):
        warnings.append(f"정찰이 {scan['age_min']:.0f}분째 없다 — 폴러가 멈춰 "
                        "있을 수 있다 (cron 은 1분마다 돈다)")
    if busy and not running:
        newest = last_done.finished_at if last_done else None
        idle_min = ((now - newest).total_seconds() / 60) if newest else None
        if idle_min is None or idle_min > 15:
            warnings.append(
                f"끝나지 않은 슬라이드가 {len(busy)}개 있는데 도는 실행이 없다 — "
                "폴러가 데리러 오지 않는 상태일 수 있다 (097 이 그 모양이었다)")

    return {"scan": scan, "runs": runs, "busy": busy,
            "last_done": last_done, "warnings": warnings, "now": now}


def object_links_of(vp) -> list[dict]:
    """이 시야의 같은 개체 묶음 (P11). 화면이 그대로 쓰는 모양으로 낸다.

    멤버는 `(image, mask_key)` 로 화면의 마스크와 만난다 — 화면 쪽 `keyOf` 와
    같은 규칙이다. batch 는 안 낸다: 화면은 검토 대상 묶음 하나만 보고 있고,
    다른 묶음의 마스크는 애초에 안 그려진다.
    """
    out = []
    for l in (ObjectLink.objects.filter(viewpoint=vp)
              .prefetch_related("members")):
        out.append({
            "id": l.pk,
            "members": [{"image": m.image_id, "mask_key": m.mask_key,
                         "rep": m.is_rep} for m in l.members.all()],
        })
    return out


def current_detections(vp: Viewpoint) -> list:
    """그 시야의 현재 검출들. **여럿일 수 있다** (P09 1단계).

    합성본에 하나 + 프레임마다 하나가 된다 — YOLO 는 합성본이 아니라 원본
    프레임을 보므로 갈아타면 그 모양이다(실측: `yolo-3차` 는 시야 452개에 프레임
    검출 1,310개, 합성본 검출 314개).

    **이미지마다 하나라는 것이 불변식이다.** 0025 마이그레이션이 그것을 확인하고
    통과했다 — 어긋나면 어느 묶음의 판단인지 정할 수 없어 교정을 못 앉힌다.
    """
    dets = [d for d in vp.detections.all() if d.is_current]
    # **`is_current` 하나로는 모자란다** (P10). 그것은 "그 묶음 안에서 최신"
    # 이고, 어느 묶음을 볼지는 `RunBatch.for_review` 가 정한다 — 화면이 보는
    # 것은 **둘 다 켜진 검출**이다.
    #
    # 검토 대상이 없으면 **빈 목록**이다. 조용히 아무 묶음이나 보여주면 사람이
    # 무엇을 검토하고 있는지 모른 채 교정을 쌓는다 (P10 3.6). 그 상태는
    # `check_db.py` 가 센다.
    rb = review_batch_id()
    if rb is None:
        return []
    bmap = batch_ids_of(dets)
    return [d for d in dets if bmap.get(d.pk) == rb]


def representative_detection(vp: Viewpoint, dets=None):
    """집계가 세는 검출 하나 (P09 5.3).

    **검토는 모든 이미지에서 하되 집계는 시야마다 하나에서 낸다.** 합성본 1 +
    프레임 3.6 을 다 세면 같은 규조각이 4.6번 세어져 밀도가 그만큼 부푼다 —
    **학습 자료로는 맞고 계측 통계로는 틀리다.**

    합성본이 있으면 합성본이다. 없으면(싱글턴 시야 153개) 그 프레임이다.
    지금 `is_current` 가 시야당 하나인 것이 하던 역할 그대로다.
    """
    dets = current_detections(vp) if dets is None else dets
    return (next((d for d in dets if d.image and d.image.kind == "stack"), None)
            or next(iter(dets), None))


def batch_ids_of(dets) -> dict:
    """검출 pk → 묶음 pk. **조인을 한 번에 한다.**

    `Detection.batch` 는 `run` 을 타고 두 번 조인한다. 프레임마다 부르면 시야
    하나에 조인이 열 번씩 걸린다 — 개수를 세려고 자료를 물질화하지 말라는 것과
    같은 이야기다(CLAUDE.md).
    """
    run_ids = {d.run_id for d in dets if d.run_id}
    if not run_ids:
        return {d.pk: None for d in dets}
    by_run = dict(Run.objects.filter(id__in=run_ids)
                  .values_list("id", "batch_id"))
    return {d.pk: by_run.get(d.run_id) for d in dets}


def detection_for_viewpoint(vp: Viewpoint, image=None) -> dict | None:
    """시야에 붙은 현재 검출 결과 (교정 반영).

    **`image` 를 주면 그 이미지의 것을 낸다** (P09 1단계). 안 주면 대표 이미지의
    것이다 — 합성본이 있으면 합성본, 없으면 그 프레임.
    """
    dets = current_detections(vp)
    if image is not None:
        image_id = getattr(image, "pk", image)
        det = next((d for d in dets if d.image_id == image_id), None)
    else:
        det = representative_detection(vp, dets)
    if det is None:
        return None
    return _with_reviews(vp, det, batch_ids_of([det]).get(det.pk))


def _with_reviews(vp: Viewpoint, det, batch_id) -> dict:
    """검출 하나에 **그 검출의 교정만** 얹는다.

    **교정을 `(image, batch)` 로 거른다.** 안 거르면 두 가지가 화면에 새어 든다:

    - **다른 이미지의 교정** — 합성본에서 한 판단이 프레임 화면에 얹혀 보인다.
      같은 시야라 좌표계가 같아서 `mask_key` 가 실제로 맞는다
    - **다른 묶음의 교정** — SAM2 시절 "오검출" 이 YOLO 검출에 얹힌다. 사람은
      **자기가 지우지 않은 것이 지워져 있는 것**을 본다(실측 1,076건, P09 4.4)

    둘 다 예외가 안 나고 **그럴듯한 화면**이 나오는 종류다.
    """
    # **사람이 그린 개체는 묶음을 안 가린다** (P09 5.2). `batch=NULL` 은 어느
    # 회차에도 안 속한다 — 엔진에 대한 판단이 아니라 **이미지에 대한 사실**이라
    # 회차를 갈아타도 그 자리에 있어야 한다. 거르면 화면에서 사라지고, 사라지면
    # 다음 저장에 지워진다(2단계에서 본 그 길이다).
    reviews = {o.mask_key: o for o in vp.object_reviews.all()
               if o.image_id == det.image_id
               and (o.batch_id == batch_id or o.batch_id is None)}
    return _apply_review(det, reviews, review_state(vp))


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


def _viewpoints_by_stem(stem: str) -> list:
    """stem 이 가리키는 시야들. **여럿이면 여럿을 그대로 돌려준다.**

    합성본은 `<tag>_focused`, 싱글턴은 프레임 이름(`Snap-21171`)이다.

    **프레임 이름은 슬라이드끼리 겹친다** — 카메라 일련번호라 같은 날 이어 찍으면
    번호대가 이어진다(260803 두 슬라이드에서 143종). `Frame` 에 `(slide, name)`
    유일 제약이 있는 것이 곧 "이름만으로는 못 찾는다" 는 뜻인데, 여기가 그 제약을
    안 쓰고 `.first()` 로 아무거나 집고 있었다. 고르는 일은 부르는 쪽에 맡긴다.
    """
    qs = (Viewpoint.objects
          .prefetch_related("detections__candidates", "object_reviews"))
    if stem.endswith("_focused"):
        return list(qs.filter(tag=stem[: -len("_focused")]))
    ids = (Frame.objects.filter(name=stem)
           .values_list("viewpoint_id", flat=True).distinct())
    return list(qs.filter(id__in=list(ids)))


def _viewpoint_of(stem: str) -> Viewpoint | None:
    """stem 하나로 시야를 찾는다. **모호하면 None 이다.**

    이름이 겹쳐 둘 이상이 나오면 **아무것도 돌려주지 않는다.** 아무거나 집으면
    엉뚱한 시야가 열리고, 그 화면에서 저장하면 `save_review` 가 그 시야의 교정을
    통째로 갈아치운다 — 사본에서 재현했다: 싱글턴 시야 135개 중 12개가 자기
    stem 으로 자기를 못 찾았고, "검토 완료" 만 누른 빈 payload 하나가 남의 시야
    교정 7건을 지웠다(2026-08-05). 017·027 과 같은 계열이다.

    **부르는 쪽은 `find_viewpoint()` 를 쓴다** — 거기는 `(slug, gid)` 로 짚어서
    모호할 일이 없다.
    """
    vps = _viewpoints_by_stem(stem)
    return vps[0] if len(vps) == 1 else None


def find_viewpoint(stem: str = "", slug: str = "",
                   gid=None) -> tuple[Viewpoint | None, str]:
    """저장 요청이 가리키는 시야. `(시야, 오류)` 를 돌려준다.

    **`(slug, gid)` 가 있으면 그것이 정답이다.** stem 은 이름이라 겹칠 수 있지만
    슬라이드 슬러그와 시야 번호는 주소 그 자체다 — 화면이 이미 둘 다 알고 있으므로
    보내지 못할 이유가 없다.

    stem 은 그때 **검증용**으로만 쓴다: 그 시야의 현재 검출 이미지와 다르면
    "다른 화면을 보고 보낸 것" 이므로 받지 않는다. 화면과 저장 대상이 어긋난
    채로 통과하는 길을 하나도 남기지 않기 위해서다.

    `(slug, gid)` 가 없으면 stem 으로 찾되 **모호하면 거절한다.**
    """
    if slug and gid is not None:
        vp = (Viewpoint.objects
              .prefetch_related("detections__candidates", "object_reviews")
              .filter(slide__slug=slug, idx=gid).first())
        if vp is None:
            return None, f"모르는 시야다: {slug} g{gid}"
        if stem:
            # **시야의 현재 검출은 여럿이다** (P09 1단계 · 055). 이미지마다 하나씩
            # 있고, 화면은 캐러셀로 그중 하나를 띄운다. 그런데 여기서 `.first()`
            # 로 하나만 집어 견주고 있었다 — 053 과 같은 실수다.
            #
            # 그래서 **프레임을 보며 한 교정이 통째로 거절됐다**: 화면이 프레임
            # 판으로 렌더되면 `stem` 이 `Snap-22119` 인데 집힌 것은 합성본이라
            # 409 였다. 사람 쪽에서는 마스크가 지워진 채로 보이고 회색 글씨
            # 한 줄만 지나가서, 오검출 둘을 지운 것이 DB 에 하나도 안 남았다
            # (실사용 보고 2026-08-10 · am22-gc10b 25cm g0).
            #
            # 견줄 것은 **그 시야가 가진 판들**이다. 그중 하나면 "이 시야를 보고
            # 보낸 것" 이 맞고, 어느 판에 앉힐지는 `image` 가 따로 짚는다
            # (`save_review` 가 그 이미지에 현재 검출이 없으면 거절한다).
            stems = {Path(d.image_path).stem
                     for d in vp.detections.all() if d.is_current and d.image_path}
            # 검출이 아직 없는 시야(검토 준비 중)는 견줄 대상이 없다. 그쪽은
            # `review_blocked` 가 따로 막는다.
            if stems and stem not in stems:
                return None, (f"화면과 저장 대상이 어긋난다 — {slug} g{gid} 의 "
                              f"판은 {', '.join(sorted(stems))} 인데 "
                              f"{stem} 을 보냈다")
        return vp, ""

    vps = _viewpoints_by_stem(stem)
    if not vps:
        return None, f"모르는 이미지다: {stem}"
    if len(vps) > 1:
        where = ", ".join(f"{v.slide.slug} g{v.idx}" for v in vps[:4])
        return None, (f"이 이름의 시야가 {len(vps)}개다 — 어느 것인지 알 수 없어 "
                      f"저장하지 않았다 ({where}). 화면을 새로고침할 것")
    return vps[0], ""


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

    **교정은 `(image, mask_key)` 로 짚는다 — `viewpoint` 가 아니다.** 055 에서
    교정의 열쇠가 그리로 옮겨 갔는데 이 자리가 따라가지 않아 **인덱스가 발밑에서
    사라졌고** 목록 화면이 0.5 → 2.0초가 됐다(058). 그리고 **프레임별 검토
    (P06 5b)가 붙으면 `viewpoint` 는 값도 틀린다** — 한 시야에 이미지가 여럿이
    되는 순간 다른 이미지의 교정까지 끌어온다.

    세는 일은 `_summary_rows` 가 한다(원시 SQL 인 이유는 그쪽 머리말에).
    """
    per_cls = {r["key"]: 0 for r in _class_rows()}
    rows = _summary_rows("v.slide_id = %s", [slide.id])
    row = rows.get(slide.id) or {"per_cls": {}, "n_detected": 0,
                                 "n_auto": 0, "n_labeled": 0}
    per_cls.update({k: v for k, v in row["per_cls"].items() if k in per_cls})

    # 검출이 돈 **시야 수** — 평균의 분모다. **검출 수가 아니다**: 시야 하나에
    # 현재 검출이 여럿이면(합성본 + 프레임마다) 분모가 4.6배가 되어 시야당 평균이
    # 그만큼 작아진다. 분자는 대표 이미지 하나만 세므로 둘이 어긋난다 (P09 5.3).
    detected_groups = (Detection.objects
                       .filter(viewpoint__slide=slide).reviewing()
                       .values("viewpoint_id").distinct().count())
    return {"per_cls": per_cls, "n_detected": row["n_detected"],
            "n_auto": row["n_auto"], "n_labeled": row["n_labeled"],
            "detected_groups": detected_groups}


# 개체 하나하나를 파이썬으로 올리지 않고 세는 SQL. **원시 SQL 인 이유가 있다.**
#
# ORM 으로 쓰면 교정을 상관 서브질의로 찾게 되는데(`Exists`·`Subquery`), 그러면
# **후보마다 서너 번**의 인덱스 조회가 돈다 — 후보 97,299개에 400,000 번이다.
# 교정은 `(image, mask_key)` 가 유일하므로 **왼쪽 조인 한 번**이면 같은 값이
# 나오고 행도 안 불어난다: 실측 500 → 50 ms (058).
#
# Django ORM 은 이 조인을 낼 수 없다. 관계가 FK 가 아니라 `(image_id, mask_key)`
# 짝이기 때문이다 — `ObjectReview.candidate` FK 는 재검출에서 끊기라고 만든
# 것이라 조인 열쇠로 쓰면 안 된다(P02).
#
# **판정 규칙은 `_apply_review`·`_guess_cls` 와 같아야 한다.** 아래 CASE 두 개가
# 그 규칙이고, 경계값(1.4 · 2.0 · 20.0)까지 같아야 목록과 상세 화면의 숫자가
# 어긋나지 않는다.
#
# **시야마다 대표 이미지 하나만 센다** (P09 5.3). 예전에는 `d.is_current` 인 검출을
# 전부 세었는데, 시야마다 현재 검출이 하나일 때만 같은 뜻이다. 프레임별 검출이
# 올라오면 **같은 규조각이 합성본 1 + 프레임 3.6 장에서 4.6번 세어져** 밀도가 그만큼
# 부푼다 — 학습 자료로는 맞고 계측 통계로는 틀리다. 아래 `rep` 가 그 하나를 고르고,
# 규칙은 `representative_detection` 과 같다(합성본이 있으면 합성본).
#
# **교정을 묶음으로도 맞춘다.** `(image, mask_key)` 만으로 맺으면 묶음을 갈아탄 뒤
# 같은 이미지에 남아 있는 **옛 회차의 교정이 새 후보에 붙는다.** 키가 겹칠 확률은
# 낮지만(엔진이 다르면 `exact` 가 0%다) 겹치면 `LEFT JOIN` 이 행을 불려 개수가
# 조용히 는다. `IS` 로 비교하는 것은 사람이 그린 개체가 `batch IS NULL` 이라서다.
_SUMMARY_SQL = """
WITH rep AS (
    SELECT d.id AS det_id, d.viewpoint_id, d.image_id, run.batch_id,
           ROW_NUMBER() OVER (
               PARTITION BY d.viewpoint_id
               ORDER BY CASE i.kind WHEN 'stack' THEN 0 ELSE 1 END, d.id) AS rn
      FROM viewer_detection d
      JOIN viewer_image i ON i.id = d.image_id
      LEFT JOIN viewer_run run ON run.id = d.run_id
      LEFT JOIN viewer_runbatch rb ON rb.id = run.batch_id
     -- **검토 대상 묶음의 것만** (P10 1단계). `is_current` 만 보면 나란히 쌓아
     -- 둔 다른 엔진의 검출까지 세어 개수가 몇 배가 된다.
     WHERE d.is_current AND rb.for_review
)
SELECT v.slide_id AS slide_id,
       CASE WHEN r.label IS NOT NULL AND r.label <> '' THEN r.label
            WHEN NOT c.passed THEN CASE
                 WHEN c.elongation < 1.4 THEN 'round'
                 WHEN c.elongation >= 2.0 AND c.elongation <= 20.0 THEN 'rod'
                 ELSE '' END
            ELSE c.cls END                                          AS eff_cls,
       COUNT(*) FILTER (WHERE (c.passed AND NOT COALESCE(r.removed, 0))
                           OR (NOT c.passed AND COALESCE(r.accepted, 0)))   AS n_kept,
       COUNT(*) FILTER (WHERE c.passed)                                     AS n_auto,
       COUNT(*) FILTER (WHERE ((c.passed AND NOT COALESCE(r.removed, 0))
                            OR (NOT c.passed AND COALESCE(r.accepted, 0)))
                          AND r.label IS NOT NULL AND r.label <> '')        AS n_labeled
FROM viewer_candidate c
JOIN rep ON rep.det_id = c.detection_id AND rep.rn = 1
JOIN viewer_viewpoint v ON v.id = rep.viewpoint_id
LEFT JOIN viewer_objectreview r
       ON r.image_id = rep.image_id AND r.mask_key = c.mask_key
      AND r.batch_id IS rep.batch_id
WHERE {where}
GROUP BY v.slide_id, eff_cls

UNION ALL

-- **사람이 그린 개체** (P09 3단계). `Candidate` 가 없어 위 질의가 못 본다 —
-- 화면에는 보이는데 목록의 숫자에는 없는 상태가 된다.
--
-- 이것도 **대표 이미지에서만** 센다. 엔진 개체와 같은 규칙이어야 목록과 상세
-- 화면이 안 어긋난다 — 프레임에 그린 것은 안 세어진다는 뜻이고, 그것이 밀도의
-- 정의(시야 하나에 판 하나)와 맞는다.
--
-- `n_auto` 는 0 이다. 엔진이 낸 것이 아니라 사람이 만든 것이라, "자동 검출
-- 몇 개" 에 섞이면 엔진 성적을 잘못 읽는다.
SELECT v.slide_id AS slide_id,
       COALESCE(NULLIF(r.label, ''), '') AS eff_cls,
       COUNT(*)                                                  AS n_kept,
       0                                                         AS n_auto,
       COUNT(*) FILTER (WHERE r.label IS NOT NULL AND r.label <> '') AS n_labeled
FROM viewer_objectreview r
JOIN rep ON rep.image_id = r.image_id AND rep.rn = 1
JOIN viewer_viewpoint v ON v.id = rep.viewpoint_id
WHERE r.batch_id IS NULL AND r.source = 'manual' AND {where}
GROUP BY v.slide_id, eff_cls
"""


# 시야 목록의 표지에 얹을 마스크. **화면에 남는 개체만** 가져온다.
#
# 그리는 것은 시야당 다섯 남짓인데 예전에는 후보를 전부 dict 로 만들어(탈락분
# 8,586개까지) 그중에서 골랐다 — 폴리곤이 JSONField 라 만드는 값이 곧 파싱
# 비용이다(060). 남는 개체의 조건은 `_summary_rows` 와 같은 규칙이다.
#
# **표시 분류는 `mask_class` 와 같아야 한다** — 사람이 지정한 것이 먼저, 되살린
# 것은 `manual`(짐작한 분류가 아니라 되살렸다는 사실을 색으로 보인다), 나머지는
# 자동 판정. 순서도 같아야 한다: 넓은 것부터 그려야 작은 개체가 안 묻힌다.
# **여기도 대표 이미지 하나만 본다** (`_SUMMARY_SQL` 과 같은 `rep`). 표지에 얹는
# 마스크라 여럿을 그리면 같은 규조각이 겹쳐 그려지고, `n_kept` 도 함께 부푼다 —
# 그 수가 시야 목록의 "검토" 칸이다.
_COVER_SQL = """
WITH rep AS (
    SELECT d.id AS det_id, d.viewpoint_id, d.image_id, run.batch_id,
           ROW_NUMBER() OVER (
               PARTITION BY d.viewpoint_id
               ORDER BY CASE i.kind WHEN 'stack' THEN 0 ELSE 1 END, d.id) AS rn
      FROM viewer_detection d
      JOIN viewer_image i ON i.id = d.image_id
      LEFT JOIN viewer_run run ON run.id = d.run_id
      LEFT JOIN viewer_runbatch rb ON rb.id = run.batch_id
     -- **검토 대상 묶음의 것만** (P10 1단계). `is_current` 만 보면 나란히 쌓아
     -- 둔 다른 엔진의 검출까지 세어 개수가 몇 배가 된다.
     WHERE d.is_current AND rb.for_review
)
SELECT rep.viewpoint_id, c.polygon,
       CASE WHEN r.label IS NOT NULL AND r.label <> '' THEN r.label
            WHEN NOT c.passed THEN 'manual'
            ELSE COALESCE(NULLIF(c.cls, ''), 'none') END AS mask_cls
FROM viewer_candidate c
JOIN rep ON rep.det_id = c.detection_id AND rep.rn = 1
JOIN viewer_viewpoint v ON v.id = rep.viewpoint_id
LEFT JOIN viewer_objectreview r
       ON r.image_id = rep.image_id AND r.mask_key = c.mask_key
      AND r.batch_id IS rep.batch_id
WHERE v.slide_id = %s
  AND ((c.passed AND NOT COALESCE(r.removed, 0))
       OR (NOT c.passed AND COALESCE(r.accepted, 0)))
ORDER BY rep.viewpoint_id, c.area_px DESC
"""


def _kept_masks(slide: Slide) -> tuple[dict[int, list[dict]], dict[int, int]]:
    """시야 번호(pk) → (표지에 그릴 마스크, 남는 개체 수). 질의 하나.

    **개수는 마스크 수가 아니다.** 폴리곤이 점 셋 미만이면 그릴 수 없어 마스크를
    안 만드는데(`mask_points` 와 같은 문턱), 그 개체도 화면에는 세어져야 한다.
    """
    masks: dict[int, list[dict]] = {}
    n_kept: dict[int, int] = {}
    with connection.cursor() as cur:
        cur.execute(_COVER_SQL, [slide.id])
        for vp_id, poly, cls in cur.fetchall():
            n_kept[vp_id] = n_kept.get(vp_id, 0) + 1
            p = json.loads(poly) if poly else []
            if len(p) < 6:
                continue
            masks.setdefault(vp_id, []).append(
                {"points": " ".join(f"{p[i]},{p[i + 1]}"
                                    for i in range(0, len(p) - 1, 2)),
                 "cls": cls})
    return masks, n_kept


def _summary_rows(where: str, params: list) -> dict[int, dict]:
    """슬라이드 번호 → 집계. `eff_cls` 로 묶어 온 것을 파이썬에서 접는다.

    **분류 목록을 SQL 에 박지 않는다.** `ClassDef` 에 행을 더하면 저절로 따라온다
    (038~040 과 같은 방향). 모르는 분류로 나온 개체도 `n_detected` 에는 들어간다 —
    화면의 분류 열에만 안 보인다.
    """
    out: dict[int, dict] = {}
    with connection.cursor() as cur:
        # `{where}` 가 두 번 들어간다 (UNION 의 양쪽) — 파라미터도 두 벌이다.
        cur.execute(_SUMMARY_SQL.format(where=where), list(params) * 2)
        for slide_id, eff_cls, n_kept, n_auto, n_labeled in cur.fetchall():
            r = out.setdefault(slide_id, {"per_cls": {}, "n_detected": 0,
                                          "n_auto": 0, "n_labeled": 0})
            if n_kept:
                r["per_cls"][eff_cls] = r["per_cls"].get(eff_cls, 0) + n_kept
            r["n_detected"] += n_kept
            r["n_auto"] += n_auto
            r["n_labeled"] += n_labeled
    return out


def _slide_summary(slide: Slide) -> dict:
    """목록 화면의 집계.

    **세는 일은 `_summary_by_sql` 하나로 모았다.** 예전에는 `dataset_detail` 이
    이미 만든 개체 dict 를 넘겨 파이썬에서 더하는 갈래가 따로 있었는데, 그
    갈래가 있으려면 화면이 개체를 전부 물질화해야 했다 — 시야 목록이 후보
    11,048개를 만들어 그중 370개만 그리고 있었다(060). 두 길의 값이 슬라이드
    11개 전부에서 같은 것을 확인하고 SQL 쪽만 남겼다.
    """
    vps = Viewpoint.objects.filter(slide=slide)
    n_groups = vps.count()
    sizes = list(vps.values_list("n_frames", flat=True))
    n_img = sum(sizes)

    r = _summary_by_sql(slide)
    per_cls = r["per_cls"]
    n_detected, n_auto = r["n_detected"], r["n_auto"]
    n_labeled, n_counts = r["n_labeled"], r["detected_groups"]
    counts = [None] * n_counts     # 개수만 쓴다

    rv = ObjectReview.objects.filter(viewpoint__slide=slide)
    agg = rv.aggregate(
        removed=Count("id", filter=Q(removed=True)),
        accepted=Count("id", filter=Q(accepted=True)),
        noted=Count("id", filter=~Q(note="")),
    )
    # 코멘트는 시야의 것이라 묶음과 무관하고, 완료는 묶음마다다 (073)
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
        "reviewed_groups": len(done_viewpoints(slide=slide)),
    }


def _slide_order(sl):
    """관찰을 세우는 순서 — **시료의 위치, 그 다음 관찰 번호.**

    시추코어는 깊이(cm)로, 노두는 단면상의 위치로 선다 — 어느 칸을 볼지는
    `Sample.position` 이 정한다. 위치가 없는 것(소속을 잃었거나 아직 안 채운
    것)은 뒤로 보낸다: 축에 놓을 자리가 없다.

    **이름으로 가르지 않는다** — `(10)` 이 `(2)` 앞에 온다(문자열 정렬).
    `Slide.Meta.ordering` 과 같은 규칙이어야 한다.
    """
    pos = sl.sample.position if sl.sample_id else None
    return (pos is None, pos or 0, sl.obs_no, sl.name)


def _obs(slide) -> dict:
    """행에 싣는 관찰 정보. 목록·코어 페이지가 같은 열쇠를 쓴다.

    화면 셋(표·카드·지도)이 같은 값을 봐야 하므로 여기서 한 번만 만든다.
    """
    return {
        "obs_no": slide.obs_no,
        "obs_label": slide.obs_label,
        "obs_badge": slide.obs_badge,
        "hidden": slide.hide_in_list,
        "excluded": slide.exclude_from_totals,
    }


def datasets(area: str | None = None) -> list[dict]:
    """**숨긴 슬라이드도 담아 돌려준다.**

    거르는 자리는 `datasets_by_locality()` 다. 여기서 걸러 버리면 합계가 보기 토글을
    따라 흔들린다 — `숨김` 은 보기 상태이고 `집계 제외` 가 자료의 성질이다.
    """
    # groups_*.json 은 파이프라인에서 빠졌다(P02 7단계). 목록에 파일 이름 대신
    # 시료가 무엇인지와 어떤 배율로 찍혔는지를 보인다 — 그쪽이 화면에서 쓸모 있다.
    scales = scales_by_slide()
    out = []
    # 지역 → 지점 → 시료 위치 순. 들어온 순서(id)로 두면 같은 지점의 시료들이
    # 표에서 떨어져 놓인다 — 위치에 따른 변화를 보는 것이 분석 목적이라 그게 제일
    # 아프다. 소속이 아직 안 붙은 관찰도 있어서 빈 값이 섞여도 죽지 않게 둔다.
    # 같은 시료에 관찰이 여럿 서면 번호순이다 — 이름으로 가르면 `(10)` 이 `(2)`
    # 앞에 온다(문자열 정렬). `Slide.Meta.ordering` 과 같은 규칙이어야 한다.
    #
    # **`sample_no` 를 함께 태운다.** 노두는 깊이가 없어 그것만으로는 한 지점의
    # 시료들이 순서 없이 선다.
    slides = (Slide.objects.select_related("sample__locality__site")
              .order_by("sample__locality__site__code",
                        "sample__locality__code", "sample__depth_cm",
                        "sample__sample_no", "obs_no", "name"))
    # "전체" 는 거르지 않는다 — 지역이 안 붙은 관찰도 여기서는 보여야 한다.
    if area and area != AREA_ALL:
        slides = slides.filter(sample__locality__site__area=area)
    for slide in slides:
        sample = slide.sample
        loc = sample.locality if sample else None
        site = loc.site if loc else None
        out.append({
            "slug": slide.slug,
            "label": slide.name,
            "image_dir": slide.image_dir,
            "corr_thresh": slide.corr_thresh,
            "site": (site.region or site.name or site.code) if site else "",
            # 화면에 내는 이름(`site`)과 주소·열쇠에 쓰는 코드는 다르다 —
            # 지역 이름은 사람이 고칠 수 있고, 지점 페이지의 주소가 그때
            # 따라 바뀌면 적어 둔 링크가 깨진다.
            "site_code": site.code if site else "",
            "core": loc.code if loc else "",
            "sample_code": sample.code if sample else "",
            "depth_cm": sample.depth_cm if sample else None,
            "sample_no": sample.sample_no if sample else None,
            "sample_kind": loc.kind if loc else "core",
            "description": slide.description,
            "um_per_pixel": scales.get(slide.slug),
            "state": slide.state,
            "state_note": slide.state_note,
            "missing_dir": not (Path(settings.DATA_ROOT)
                                / slide.image_dir).is_dir(),
            **_obs(slide),
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
    counts = dict(Slide.objects.filter(sample__locality__site__isnull=False)
                  .values_list("sample__locality__site__area")
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
        "orphans": Slide.objects.filter(sample__isnull=True).count(),
    }


def datasets_total(rows: list[dict]) -> dict:
    """목록 표의 합계 줄.

    합칠 수 있는 것만 합친다. 평균(`mean_size`·`mean_counted`)은 분모가 슬라이드마다
    달라서 다시 더할 수 없고, 배율은 슬라이드마다 다를 수 있다(devlog 015·017) —
    합계 칸을 비워 두는 편이 그럴듯한 숫자를 놓는 것보다 낫다.

    **같은 시료의 관찰이 여럿이면 그냥 더한 값이 조용히 두 배가 된다.** 예외도
    경고도 안 난다 — 그럴듯한 숫자가 그냥 틀린다. 어느 관찰이 대표인지는 코드가
    정할 수 없으므로(처리 방법을 달리해 비교하려고 만든 것이다) **사람이 슬라이드
    속성에서 `집계 제외` 를 켜고, 여기는 그것만 읽는다.**

    **`숨김` 은 안 읽는다.** 읽으면 보기 토글 한 번에 같은 자료가 다른 숫자를
    낸다. 대신 숨긴 행이 합계에 들어 있으면 세어서 알린다(`n_hidden_in`) —
    그래야 "보이는 것의 합 ≠ 합계" 가 이유 없는 어긋남으로 안 보인다.
    """
    counted_rows = [r for r in rows if not r.get("excluded")]
    keys = ("n_images", "n_groups", "n_detected", "n_counted",
            "reviewed_groups")
    total = {k: sum(r.get(k) or 0 for r in counted_rows) for k in keys}
    # 분류별 합계도 열 순서 그대로 — 표의 열과 하나씩 맞아야 한다.
    per = {c["key"]: 0 for c in counted_classes()}
    for r in counted_rows:
        for c in r.get("counted") or []:
            if c["key"] in per:
                per[c["key"]] += c["n"]
    total["counted"] = [{**c, "n": per[c["key"]]} for c in counted_classes()]
    # 화면이 각주를 붙일 근거. **0 이면 아무것도 안 낸다** — 관찰이 하나뿐인
    # 지금까지의 자료는 화면이 그대로 남는다.
    total["n_excluded"] = len(rows) - len(counted_rows)
    total["n_hidden_in"] = sum(1 for r in counted_rows if r.get("hidden"))
    return total


def datasets_by_locality(rows: list[dict], with_hidden: bool = False) -> list[dict]:
    """목록을 지점으로 묶는다. 표·카드 둘 다 이것을 쓴다.

    **묶는 열쇠는 지역이 아니라 지점이다.** 지역은 머리줄에 함께 낸다. 지금은
    지역↔코어가 거의 1:1(5:5)이라 어느 쪽으로 묶어도 화면은 같지만, **먼저 오는
    것은 한 코어에서 슬라이드가 여럿이 되는 일이다** — 이미 RS23-GC03 이 셋이다.
    한 지역에 코어가 둘 되는 날은 그 다음이고, 그때는 층이 하나 더 생길 뿐 이
    묶음이 안 흔들린다.

    **줄 순서는 이미 지역→코어→깊이다**(`datasets()`). 그래서 같은 코어가 이어
    놓여 있고, 나온 순서대로 훑으며 묶기만 하면 된다 — 다시 정렬하지 않는다.

    **코어가 안 붙은 슬라이드가 있다**(`data.py` 가 빈 값을 허용한다). 그것만
    따로 "코어 미지정" 묶음이 된다 — 어디에도 안 들어가면 목록에서 사라진다.

    머리줄의 숫자는 `datasets_total()` 을 묶음마다 한 번 불러 낸다(지금도 전체
    합계를 그 함수 하나로 낸다). **평균은 넣지 않는다** — 분모가 슬라이드마다
    달라 다시 더할 수 없다(그 함수 머리말의 이유).

    **숨긴 슬라이드를 거르는 자리가 여기다.** 다만 **머리줄 숫자는 숨긴 것까지
    센 값이다** — 안 그러면 보기 토글 한 번에 합계가 바뀐다(`datasets_total()`
    머리말). 그래서 `rows` 는 걸러 내고 `totals` 는 전부로 낸다.

    **빈 묶음이 되어도 안 지운다.** 한 코어가 통째로 숨겨졌을 때 머리줄까지
    사라지면 그 코어가 이 권역에 없는 것이 되고, 묶음 숫자를 다 더해도 아래
    합계와 안 맞는다. 머리줄을 남기고 "숨긴 N장" 을 그 자리에 적는다.
    """
    out, at = [], {}
    for r in rows:
        # 같은 지점 코드가 지역마다 따로 있을 수 있다(Locality 의 unique 가
        # (site, code) 인 이유). 열쇠도 그 짝이어야 한다.
        # **이름이 아니라 코드로 묶는다.** 지역 이름은 사람이 고칠 수 있는데,
        # 그것을 열쇠로 삼으면 이름을 고치는 순간 접어 둔 것이 풀린다.
        key = (r.get("site_code") or "", r.get("core") or "")
        g = at.get(key)
        if g is None:
            g = at[key] = {
                # 화면이 여닫은 상태를 기억할 이름. **가름표를 넣는다** —
                # 그냥 이으면 ("RS2","3GC03")과 ("RS23","GC03")이 같아진다.
                "key": f"{key[0]}/{key[1]}",
                "site_code": key[0],
                "site": r.get("site") or "",
                "core": key[1],
                "no_core": not key[1],
                "all_rows": [],
            }
            out.append(g)
        g["all_rows"].append(r)
    for g in out:
        # 숫자는 전부로, 보이는 줄은 걸러서. 둘을 같은 목록에서 내면 토글이
        # 합계를 흔든다.
        g["totals"] = datasets_total(g["all_rows"])
        g["rows"] = [r for r in g["all_rows"]
                     if with_hidden or not r.get("hidden")]
        g["n"] = len(g["rows"])
        g["n_hidden"] = len(g["all_rows"]) - g["n"]
    return out


def _nice_step(span: float, want: int = 8) -> int:
    """깊이 축의 눈금 간격. 사람이 읽는 수(1·2·5 계열)로만 고른다.

    `span / want` 를 그대로 쓰면 137 cm 같은 간격이 나와 축이 안 읽힌다.
    """
    raw = max(span / want, 1)
    for m in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500):
        if raw <= m:
            return m
    return 5000


def _axis_marks(rows: list[dict], bottom: float) -> list[dict]:
    """깊이 축의 시료 표식. **같은 깊이에 여럿 서면 겹친다.**

    위치를 `depth_cm / bottom` 하나로만 내면 같은 깊이는 `pct` 가 글자 그대로
    같아져 **하나가 다른 하나를 완전히 가린다.** 한 시료를 처리 방법을 달리해
    여러 번 관찰하면 바로 그 상황이다 — 예외도 경고도 없이 관찰 하나가 화면에서
    사라진다.

    **점은 참 깊이에 그대로 두고 이름표만 아래로 밀어 쌓는다.** 점까지 밀면
    깊이 축이 거짓말을 한다. 그래서 점은 무리의 첫 줄만 찍고(`first`) 나머지는
    그 아래 들여 쓴다 — 같은 깊이라는 것이 모양으로 읽힌다.

    `nudge_px` 로 내는 이유는 `pct` 에 더할 수 없어서다. 축이 길든 짧든 글줄
    높이는 그대로라 % 로 밀면 짧은 축에서는 너무 많이, 긴 축에서는 안 밀린다.
    """
    placed = [r for r in rows if r["depth_cm"] is not None]
    at_depth: dict[float, int] = {}
    for r in placed:
        at_depth[r["depth_cm"]] = at_depth.get(r["depth_cm"], 0) + 1

    out, seen = [], {}
    for r in placed:
        d = r["depth_cm"]
        i = seen.get(d, 0)
        seen[d] = i + 1
        out.append({
            "row": r,
            "pct": round(d / bottom * 100, 3),
            "first": i == 0,
            "n_at_depth": at_depth[d],
            # 글줄 하나만큼. 첫 줄은 0 이라 지금까지의 화면이 그대로다.
            "nudge_px": i * 17,
        })
    return out


def locality_detail(site_code: str, loc_code: str,
                    with_hidden: bool = False) -> dict | None:
    """지점 하나 — 위치 방향으로 본 화면. 시추코어면 깊이, 노두면 단면상의 위치.

    **목록의 부분집합이 아니어야 이 화면이 값을 한다.** 목록은 관찰끼리
    비교하는 자리이고, 여기는 **위치 축**이 주인공이다 — 암상 기재가 들어올
    자리도 그 축 옆이다. 목록이 절대 못 보여주는 것이 그것이다.

    **암상은 아직 모델이 없다.** 구간 상·하한 · 암상 코드 · 색 · 조직 · 화석
    함량 같은 칸이 정해져야 표가 서는데 그 기재 규칙이 아직 없다. 지금 스키마를
    박으면 나중에 이미 붙은 자료를 옮겨야 한다 — **축과 자리만 잡고 띠는 비워
    둔다.** 깊이는 DB 에 이미 있으니 축 자체는 진짜다.

    **축은 시추코어에만 선다.** 노두 지점의 시료는 단면상의 위치로 정렬되지만
    그 값은 "몇 번째로 딴 것" 이지 거리가 아니다 — cm 축에 얹으면 없는 간격을
    지어내게 된다. 그쪽은 순서대로 나열만 한다.

    **속성을 여기서 고치지 않는다.** `/d/<slug>/edit/` 이 이미 관찰·지점·
    지역을 한 트랜잭션으로 저장한다. 여기에 폼을 하나 더 두면 같은 `Locality`·
    `Site` 행에 쓰는 문이 둘이 된다 — 이 저장소가 두 번 당한 종류다.

    **합계와 보이는 줄을 가르는 규칙은 목록과 같다** — 숫자는 숨긴 것까지,
    줄은 걸러서(`datasets_by_locality()` 머리말).
    """
    loc = (Locality.objects.select_related("site")
           .filter(site__code=site_code, code=loc_code).first())
    if loc is None:
        return None
    site = loc.site
    scales = scales_by_slide()

    # 위치순. 위치가 없는 것은 뒤로 — 축에 놓을 자리가 없다.
    # 같은 시료에 관찰이 여럿이면 번호순 (`Slide.Meta.ordering` 과 같은 규칙).
    slides = sorted(
        (sl for sm in loc.samples.select_related("locality").all()
         for sl in sm.slides.all()), key=_slide_order)
    all_rows = [{
        "slug": sl.slug,
        "label": sl.name,
        "sample_code": sl.sample.code if sl.sample_id else "",
        "depth_cm": sl.sample.depth_cm if sl.sample_id else None,
        "sample_no": sl.sample.sample_no if sl.sample_id else None,
        "sample_kind": loc.kind,
        "state": sl.state,
        "state_note": sl.state_note,
        "description": sl.description,
        "um_per_pixel": scales.get(sl.slug),
        **_obs(sl),
        **_slide_summary(sl),
    } for sl in slides]
    rows = [r for r in all_rows if with_hidden or not r["hidden"]]

    depths = [r["depth_cm"] for r in rows if r["depth_cm"] is not None]
    axis = None
    if depths:
        # **위가 얕고 아래로 깊어진다** — 코어 로그의 관례다. 축은 늘 0 에서
        # 시작한다. 가장 얕은 시료부터 그리면 그 위의 구간이 없는 것처럼 보인다.
        step = _nice_step(max(depths) or 1)
        # 가장 깊은 시료가 축 맨 끝에 붙으면 이름표가 잘린다. 한 칸 더 준다.
        bottom = (int(max(depths) // step) + 1) * step
        axis = {
            "top": 0, "bottom": bottom, "step": step,
            "ticks": [{"cm": t, "pct": round(t / bottom * 100, 3)}
                      for t in range(0, bottom + 1, step)],
            "marks": _axis_marks(rows, bottom),
        }
    return {
        "site_code": site.code,
        "site_label": site.region or site.name or site.code,
        "site": site,
        # 템플릿이 `core` 라는 이름으로 받는다 — 지점 하나를 가리키는 말이라
        # 뜻은 같다. 화면 글자는 "지점" 이다.
        "core": loc,
        "locality": loc,
        "is_outcrop": loc.kind == "outcrop",
        # 노두 현장 사진. 시추코어면 빈 목록이고, 그 자리는 암상 띠가 쓴다.
        "photos": outcrop.photos(loc),
        "rows": rows,
        "n": len(rows),
        # **켜 놓았을 때도 실제 숨김 수를 센다** — `len(all_rows) - len(rows)` 로
        # 내면 켠 순간 0 이 되어 몇 장이 숨겨진 것인지 화면에서 사라진다.
        "n_hidden": sum(1 for r in all_rows if r["hidden"]),
        # **숫자는 숨긴 것까지 센다.** 목록과 같은 규칙이라 두 화면의 합계가
        # 서로 맞는다.
        "totals": datasets_total(all_rows),
        "axis": axis,
        # 축에 못 놓는 것들. **버리지 않고 따로 낸다** — 안 보이면 이 코어에
        # 없는 시료가 된다.
        "unplaced": [r for r in rows if r["depth_cm"] is None],
        # 편집은 기존 화면으로 보낸다. 관찰 하나를 지나가야 하는데,
        # 그 화면의 지점·지역 칸은 어느 관찰에서 열어도 같은 행을 고친다.
        "edit_slug": rows[0]["slug"] if rows else "",
    }


def _viewpoints_of(slide: Slide, only_current: bool = False, light: bool = False):
    """시야와 그 아래를 한 번에 당겨 온다.

    **`light` 는 검출을 아예 안 당긴다.** 시야 목록은 개체를 SQL 로 세고 마스크만
    따로 받으므로(`_kept_masks`) 검출 행도 후보도 필요 없다(060).

    **`only_current` 를 켜면 현재 검출의 후보만 당긴다.** 켜지 않으면 쌓아 둔
    묶음(YOLO 등)의 후보까지 전부 올라온다 — `RS23-GC03 369cm` 에서 후보
    28,697개 중 **17,649개가 YOLO 것**이고, 시야 목록은 그것을 한 개도 안 쓴다.
    `Candidate.polygon` 이 JSONField 라 올리는 값이 파싱 비용으로 그대로 나온다
    (059 에서 이 화면의 `json.raw_decode` 31,563회가 그것이었다).

    **끄고 부르는 자리가 있다** — `engine_viewpoint` 는 `?batch=` 로 고른 묶음의
    검출을 봐야 하므로 현재 검출만 당기면 화면이 빈다. 그래서 기본을 켜지 않고
    부르는 쪽이 고르게 뒀다.
    """
    qs = (Viewpoint.objects.filter(slide=slide)
          .select_related("sharpest_frame", "stack"))
    if light:
        return qs.prefetch_related("frames")
    dets = Detection.objects.all()
    if only_current:
        # **검토 대상 묶음의 것만** (P10 1단계). `is_current` 만 걸면 나란히
        # 쌓아 둔 다른 엔진의 검출까지 딸려 와 화면이 섞인다.
        dets = dets.reviewing()
    # **`image` 를 함께 당긴다.** 부르는 쪽이 `d.image.path` 로 검출을 이미지에
    # 맞춘다(`by_path`) — 안 붙이면 검출마다 질의가 하나씩 붙고, 크롭 화면처럼
    # 시야를 전부 훑는 자리에서 그대로 백 번이 된다.
    return qs.prefetch_related(
        "frames",
        Prefetch("detections",
                 queryset=dets.select_related("image")
                              .prefetch_related("candidates")),
        "object_reviews")


def dataset_detail(slug: str) -> dict | None:
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return None

    # **개체를 dict 로 만들지 않는다** (060). 이 화면이 개체에서 쓰는 것은
    # 표지에 얹을 마스크와 그 수뿐인데, 예전에는 시야마다 `detection_for_viewpoint`
    # 로 후보를 전부 만들어(이 슬라이드 11,048개) 그중 370개를 그렸다.
    cover_masks, n_kept = _kept_masks(slide)
    # **검토 대상 묶음의 것만**, 그리고 시야마다 하나 (P10 1단계). 프레임별
    # 검출이 올라오면 한 시야에 여럿이라 dict 가 아무거나 집는다 — 합성본을
    # 먼저 놓아 `representative_detection` 과 같은 것을 고르게 한다.
    dets = {}
    for d in (Detection.objects.filter(viewpoint__slide=slide).reviewing()
              .select_related("image")
              .order_by("viewpoint_id",
                        Case(When(image__kind="stack", then=0), default=1),
                        "id")
              .values("viewpoint_id", "image_path", "width", "height")):
        dets.setdefault(d["viewpoint_id"], d)
    reviewed = done_viewpoints(slide=slide)
    # **이 묶음에 검출이 없는 시야** (P10 4단계). 목록에서도 세어 낸다 — 시야를
    # 하나씩 열어 보고서야 아는 것은 063 이 "소속을 잃은 행은 그냥 사라진다" 로
    # 배운 자리와 같다.
    elsewhere = batches_elsewhere(slide=slide)

    groups = []
    for vp in _viewpoints_of(slide, light=True):
        det = dets.get(vp.id)
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
        if det and cover_rel and Path(det["image_path"]).stem == Path(cover_rel).stem:
            size = [det["width"], det["height"]]
            masks = cover_masks.get(vp.id, [])

        groups.append({
            "id": vp.idx,
            "n": vp.n_frames,
            "tag": vp.tag,
            # 이 묶음에 검출이 없다. `elsewhere` 가 비어 있으면 아무 데도 없는
            # 것이고, 차 있으면 **다른 묶음에는 있다** — 화면이 갈라 적는다.
            "missing": det is None,
            "elsewhere": elsewhere.get(vp.id, []),
            "span_sec": round(vp.span_sec or 0, 1),
            "sharpest": vp.sharpest_frame.name if vp.sharpest_frame else None,
            "cover_rel": cover_rel,
            "cover_size": size,
            "masks": masks,
            "has_stack": st is not None,
            "n_detected": n_kept.get(vp.id, 0) if det else None,
            "reviewed": vp.id in reviewed,
        })

    return {
        "slug": slug,
        "label": slide.name,
        # **이 묶음에 검출이 없는 시야를 목록에서 센다** (P10 4단계). 시야를 하나씩
        # 열어 보고서야 아는 것은 늦다 — 063 의 "소속을 잃은 행은 그냥 사라진다"
        # 와 같은 자리다. 다른 묶음에는 있는 것을 따로 세어 **돌릴 것이 남았는가**
        # 와 **묶음을 잘못 골랐는가**를 가른다.
        "missing_groups": sum(1 for g in groups if g["missing"]),
        "missing_elsewhere": sum(1 for g in groups
                                 if g["missing"] and g["elsewhere"]),
        "review_batch": review_batch_label(),
        # groups_*.json 은 파이프라인에서 빠졌다(P02 7단계). 파일 이름 대신
        # 시료가 무엇이고 어떤 배율로 찍혔는지를 보인다.
        "corr_thresh": slide.corr_thresh,
        "site": (slide.site.region or slide.site.name
                 or slide.site.code) if slide.site else "",
        "core": slide.locality.code if slide.locality else "",
        "sample_code": slide.sample.code if slide.sample_id else "",
        "depth_cm": slide.depth_cm,
        "sample_kind": slide.sample_kind,
        "um_per_pixel": scales_by_slide().get(slide.slug),
        "groups": groups,
        **_slide_summary(slide),
    }


def _review_shot(d: dict, image_id: int, rel: str = "") -> dict:
    """캐러셀이 판을 바꿀 때 갈아 끼울 것 — **교정 상태까지 통째로**.

    읽기 전용 쪽(`engine_viewpoint._shot`)은 그릴 것만 넘기면 된다. 저장을 안 해
    사람이 표시할 것이 없어서다. 검토 화면은 **판마다 교정이 따로**이므로
    지운 것·되살린 것·분류·코멘트가 함께 가야 하고, 저장이 어느 이미지로 갈지도
    (`image`) 실려야 한다 (P09 1단계).

    `image` 가 빠지면 화면은 프레임을 보여 주면서 저장은 대표 이미지로 간다 —
    **예외도 경고도 없이** 사람이 보고 있던 것과 다른 자리에 판단이 쌓인다.
    """
    c = d["counts"]
    parts = [f"{k} {c[k]}" for k in ("rod", "round", "rod_frag",
                                     "round_frag", "eucampia") if c.get(k)]
    return {
        "image": image_id,
        # **원본 경로** (P11). 묶기 팝업이 다른 판의 크롭을 청할 때 쓴다 —
        # 화면의 크롭 요청(`/crop?p=…`)이 경로를 받기 때문이다.
        "rel": rel,
        "candidates": d["candidates"],
        "gone": d["removed_candidates"],
        "rejected": d["rejected"],
        "accepted": d["accepted_keys"],
        "labels": d["labels"],
        "notes": d["notes"],
        "summary": (f"후보 {d['n_candidates']}개"
                    + (f" ({', '.join(parts)})" if parts else "")
                    + f" · 원시 {d['n_raw_masks']}"
                    + (f" → 크기통과 {d['n_sized']}" if d["n_sized"] else "")
                    + f" · 탈락 {len(d['rejected'])}개"),
    }


def _frames(vp: Viewpoint, by_path: dict) -> list[dict]:
    """프레임 목록. `by_path` 는 이미지 경로 → `(이미지 pk, 검출 dict)`.

    **프레임마다 자기 검출을 담는다** (P09 1단계). 예전에는 현재 검출이 프레임에
    붙은 싱글턴 시야일 때만 한 장이 받았다 — 시야마다 검출이 하나라는 전제다.

    **경로로 맞춘다.** `Image.path` 가 유일 열쇠라 `Frame.path` 와 그대로 만난다 —
    프레임마다 `frame.image` 를 되짚으면 시야 하나에 질의가 프레임 수만큼 는다.
    """
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
            # 그 프레임 이미지에 붙은 현재 검출. 없으면 None 이고, 캐러셀에서
            # 그 판으로 가면 마스크가 비워진다(`swapDet`).
            "detection": (by_path.get(f.path) or (None, None))[1],
            "image_id": (by_path.get(f.path) or (None, None))[0],
        })
    return out


def group_detail(slug: str, gid: int, run_id: int | None = None) -> dict | None:
    """검토 화면 한 장.

    `run_id` 를 주면 **그 묶음이 낸 검출**을 대신 그린다(051). 엔진을 갈아 끼우는
    일이 검토 화면 안에서 되어야 한다 — 예전에는 `/engine/` 이라는 다른 화면으로
    나가야 했고, 나갔다 돌아오면 어느 시야를 보고 있었는지 잃었다.

    **그때는 읽기 전용이다.** 교정은 `mask_key`(bbox 문자열)로 붙는데 엔진이
    다르면 거의 전부 어긋난다. `readonly` 를 켜서 화면이 저장을 아예 보내지 않게
    하고(`_detection.html` 의 `ro-<uid>`), 서버는 `save_review` 가 현재 검출에
    없는 키를 거절해 한 겹 더 막는다. **화면에서 감추는 것은 막는 것이 아니다**
    — 027 이 정확히 그 자리에서 났다(교정 37건).
    """
    if run_id is not None:
        ctx = engine_viewpoint(
            slug, gid, run_id,
            # 옆 시야로 가도 **고른 엔진을 그대로 들고 간다.** 비교는 같은
            # 조건으로 여러 시야를 훑는 일이라, 한 칸 옮길 때마다 현재 검출로
            # 돌아가면 무엇을 보고 있었는지 잃는다.
            link=lambda i: (reverse("group", args=[slug, i])
                            + f"?batch={run_id}"))
        if ctx is None:
            return None
        slide = Slide.objects.filter(slug=slug).first()
        ctx["review_blocked"] = review_blocked(slide)
        ctx["readonly"] = True
        ctx["batch_run_id"] = run_id
        return ctx

    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return None
    # 묶음 갈래는 위에서 이미 돌아갔다 — 여기는 현재 검출만 본다
    vp = _viewpoints_of(slide, only_current=True).filter(idx=gid).first()
    if vp is None:
        return None

    ids = list(Viewpoint.objects.filter(slide=slide)
               .order_by("idx").values_list("idx", flat=True))
    pos = ids.index(gid)

    # **다음 미검토 시야.** 옆 시야로 한 칸씩 가는 것과 다른 일이다 — 검토가
    # 드문드문 남으면(`am22-gc10b_25cm` 이 22/30 이었다) 한 칸씩 눌러 이미 본
    # 것을 계속 지나야 한다.
    #
    # **뒤를 먼저 보고, 없으면 앞으로 돌아간다.** 뒤만 보면 뒤쪽을 다 본 순간
    # 버튼이 죽는데 앞쪽에 남은 것이 있다. 돌아갔다는 것은 화면이 말한다 —
    # 말없이 뒤로 보내면 같은 자리를 도는 것으로 읽힌다.
    # **고른 묶음에서 완료한 것만 건너뛴다** (073). 묶음을 갈면 그 묶음의
    # 검출은 아직 아무도 안 본 것이라 다시 돌아야 한다.
    done = set(ViewpointReview.objects
               .filter(viewpoint__slide=slide, done=True,
                       batch_id=review_batch_id())
               .values_list("viewpoint__idx", flat=True))
    todo = [i for i in ids if i not in done and i != gid]
    ahead = [i for i in todo if i > gid]
    todo_id = ahead[0] if ahead else (todo[0] if todo else None)

    # **이미지마다 자기 검출을 만든다** (P09 1단계). 시야 하나에 현재 검출이
    # 여럿일 수 있고(합성본 하나 + 프레임마다 하나) 캐러셀이 그 사이를 오간다.
    # 교정은 `_with_reviews` 가 `(image, batch)` 로 걸러 얹는다 — 안 거르면
    # 합성본에서 한 판단이 프레임 화면에 얹혀 보인다.
    dets = current_detections(vp)
    bmap = batch_ids_of(dets)
    by_path = {d.image.path: (d.image_id, _with_reviews(vp, d, bmap[d.pk]))
               for d in dets if d.image_id}

    st = getattr(vp, "stack", None)

    frames = _frames(vp, by_path)
    # 검출이 아직 없으면 빈 검출을 넘겨 같은 화면을 쓴다 (도구만 잠근다)
    stack = (_stack_dict(st, (by_path.get(st.focused_path) or (None, None))[1]
                             or preview_detection(vp))
             if st else None)

    # **캐러셀이 갈아 끼울 판들.** 읽기 전용 갈래와 같은 구조인데(`engine_viewpoint`)
    # 교정 상태와 저장 대상(`image`)까지 실린다 — 그 화면은 읽기 전용이라 그릴
    # 것만 넘기면 됐다.
    shots, pool = {}, []
    if stack and st and st.focused_path in by_path:
        stack["detkey"] = STACK_KEY
        iid, sd = by_path[st.focused_path]
        shots[STACK_KEY] = _review_shot(sd, iid, st.focused_path)
        pool.append({"key": STACK_KEY, "rel": st.focused_path, "det": sd,
                     "image": iid, "name": "합성본"})
    for f in frames:
        if f["detection"] and f["image_id"]:
            shots[f["name"]] = _review_shot(f["detection"], f["image_id"], f["rel"])
            pool.append({"key": f["name"], "rel": f["rel"],
                         "det": f["detection"], "image": f["image_id"],
                         "name": f["name"]})

    # **처음 열리는 판.** 집계가 세는 대표(`representative_detection`)와 **다른
    # 일이다** — 저쪽은 밀도를 위해 늘 합성본을 골라야 하고, 이쪽은 사람에게
    # 무엇을 먼저 보일지를 정한다.
    #
    # 합성본에 개체가 있으면 합성본이다. 아니면 **개체가 가장 많은 판**으로
    # 물러난다. `engine_viewpoint` 가 실측으로 정한 규칙 그대로다 — "합성본이
    # 있으면" 으로 하면 합성본만 비고 프레임에는 개체가 있는 시야에서 **빈 판이
    # 먼저 열려 검출이 아무것도 없는 줄 알게 된다.** YOLO 는 합성본 검출이
    # 314개로 시야 355개보다 적어 그 상태가 실제로 41개 난다.
    stack_p = next((p for p in pool if p["key"] == STACK_KEY
                    and p["det"]["candidates"]), None)
    best = stack_p or max(pool, key=lambda p: len(p["det"]["candidates"]),
                          default=None)
    # 검출이 아직 없는 시야 — 합성만 끝난 상태다. 빈 검출을 넘겨 **같은 화면을
    # 쓴다**(사진은 보이고 도구만 잠긴다). 저장 대상은 없다.
    if best is None and stack:
        best = {"key": STACK_KEY, "rel": st.focused_path,
                "det": stack["detection"], "image": None, "name": "합성본"}
    det = best["det"] if best else None

    return {
        "slug": slug,
        "label": slide.name,
        "id": gid,
        "n": vp.n_frames,
        "tag": vp.tag,
        "span_sec": round(vp.span_sec or 0, 1),
        "sharpest": vp.sharpest_frame.name if vp.sharpest_frame else None,
        "frames": frames,
        "stack": stack,
        # 캐러셀이 판을 바꿀 때 갈아 끼울 자료. 판이 하나뿐이면 안 넘긴다 —
        # `_detection.html` 의 `swapDet` 이 자료가 없으면 곧장 빠져나가므로
        # 지금까지와 똑같이 돈다.
        "shot_dets": shots if len(shots) > 1 else None,
        # 같은 개체 묶음 (P11). 판이 하나뿐이면 묶을 것이 없다 — 안 낸다.
        "links": object_links_of(vp) if len(shots) > 1 else [],
        # 처음 열리는 판. 캐러셀이 움직이면 JS 가 `image` 까지 따라 바꾼다.
        "base_rel": best["rel"] if best else None,
        "base_det": det,
        "base_name": best["name"] if best else None,
        "base_image": best["image"] if best else None,
        "prev_id": ids[pos - 1] if pos > 0 else None,
        "next_id": ids[pos + 1] if pos < len(ids) - 1 else None,
        "prev_url": (reverse("group", args=[slug, ids[pos - 1]])
                     if pos > 0 else None),
        "next_url": (reverse("group", args=[slug, ids[pos + 1]])
                     if pos < len(ids) - 1 else None),
        # 다음 미검토. `todo_left` 는 지금 시야를 뺀 수다 — 이 시야를 아직 안
        # 끝냈을 수도 있어서, "남은 것" 에 지금 보고 있는 것을 세면 눌러 갈 곳의
        # 수와 안 맞는다.
        "todo_id": todo_id,
        "todo_url": (reverse("group", args=[slug, todo_id])
                     if todo_id is not None else None),
        "todo_left": len(todo),
        "todo_back": todo_id is not None and todo_id < gid,
        # 자동 처리가 안 끝났으면 검토를 막는다 (P01 §1). 저장도 서버에서 거절한다.
        "review_blocked": review_blocked(slide),
        # **왜 비었는가** (P10 4단계). 검출이 아예 없는 것과 **다른 묶음에는
        # 있는 것**은 다른 말이다 — 뒤엣것을 "검출은 아직입니다" 라고 적으면
        # 사람이 돌리러 간다. 조용히 다른 묶음으로 물러나지도 않는다(P10 3.6).
        "review_batch": review_batch_label(),
        "elsewhere": batches_elsewhere(vp=vp).get(vp.id, []),
    }


def mark_all_reviewed(slug: str, done: bool) -> dict | None:
    """슬라이드의 시야 전체를 검토 완료로 / 미검토로 돌린다.

    **`done` 만 건드린다.** 같은 행의 `note`(시야 코멘트)도, `ObjectReview`
    (삭제·되살림·분류·코멘트)도 손대지 않는다 — 그쪽이 재생성 불가한 자료다.
    미검토로 돌릴 때 행을 지우면 적어 둔 시야 코멘트가 함께 날아간다. 그래서
    지우지 않고 깃발만 내린다 (`ClassDef` 를 지우지 않고 `active=False` 로
    끄는 것과 같은 결이다).

    돌려주는 것은 **실제로 바뀐 수**다. 이미 그 상태이던 것은 안 센다 — "30개를
    표시했습니다" 가 사실은 8개였다면 사람이 무엇을 한 것인지 알 수 없다.
    """
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return None
    # **고른 묶음에만 찍는다** (073). 묶음을 안 정하면 어느 검출을 다 봤다는
    # 말인지가 없다 — 조용히 아무 데나 찍는 대신 안 한다.
    batch_id = review_batch_id()
    if batch_id is None:
        return {"changed": 0, "total": 0, "no_batch": True}
    ids = list(Viewpoint.objects.filter(slide=slide)
               .values_list("id", flat=True))
    with transaction.atomic():
        # 검토로 표시할 때만 없는 행을 만든다. 미검토로 돌릴 때는 만들 것이
        # 없다 — 행이 없는 것이 곧 미검토다.
        made = 0
        if done:
            have = set(ViewpointReview.objects
                       .filter(viewpoint_id__in=ids, batch_id=batch_id)
                       .values_list("viewpoint_id", flat=True))
            missing = [i for i in ids if i not in have]
            ViewpointReview.objects.bulk_create(
                [ViewpointReview(viewpoint_id=i, batch_id=batch_id, done=True)
                 for i in missing])
            made = len(missing)
        # `.update()` 는 `auto_now` 를 안 태운다 — 손으로 찍는다. 언제 뒤집혔는지
        # 모르면 나중에 되짚을 수가 없다.
        changed = (ViewpointReview.objects
                   .filter(viewpoint_id__in=ids, batch_id=batch_id,
                           done=not done)
                   .update(done=done, updated_at=timezone.now()))
    return {"changed": changed + made, "total": len(ids)}


# --- 교정 저장 --------------------------------------------------------------
def save_review(vp: Viewpoint, done: bool, note: str, removed, accepted,
                labels: dict, notes: dict, image=None,
                drawn=None, edits=None) -> dict | None:
    """뷰어가 보낸 교정을 DB 에 쓴다. 예전에는 review/<stem>_review.json 이었다.

    키(mask_key)마다 한 행이고, 아무 표시도 남지 않은 행은 지운다 — 그래야
    "교정 전체 초기화" 가 예전처럼 깨끗하게 동작한다.

    **시야는 부르는 쪽이 짚어서 넘긴다** (`find_viewpoint`). 예전에는 여기서
    stem 으로 찾았는데, 프레임 이름이 슬라이드끼리 겹쳐 **엉뚱한 시야가 잡히는
    길**이 있었다 — 이 함수는 마지막에 그 시야의 교정을 통째로 갈아치우므로
    잘못 짚으면 남의 판단이 사라진다.

    **이미지도 부르는 쪽이 짚는다** (P09 1단계). 시야 하나에 현재 검출이 여럿일
    수 있는데(합성본 하나 + 프레임마다 하나) 예전에는 여기서 `.is_current` 인 것 중
    **아무거나** 집었다 — 시야마다 하나일 때만 맞는 코드다. 그대로 두고 YOLO 를
    프레임 검출로 올리면 **합성본에서 한 교정이 프레임 행으로 앉거나 그 반대가
    된다.** 053 과 같은 계열이고, 마지막 줄이 그 범위를 갈아치운다.

    `image` 를 안 주면 대표 이미지다 — 옛 화면(배포 중에 열려 있던 탭)이 그렇고,
    시야마다 이미지가 하나이던 시절과 결과가 같다.
    """
    if vp is None:
        return None

    # **어느 이미지·어느 묶음에 대한 교정인가** (P06 5a · P09 5.1). 열쇠가
    # `(image, batch, mask_key)` 라 이것이 없으면 행을 만들 수도, 지울 범위를
    # 정할 수도 없다.
    dets = current_detections(vp)
    if image is None:
        cur = representative_detection(vp, dets)
    else:
        image_id = getattr(image, "pk", image)
        cur = next((d for d in dets if d.image_id == image_id), None)
        if cur is None:
            # **남의 이미지를 짚었거나 그 이미지에 현재 검출이 없다.** 둘 다
            # 오류로 말한다 — 조용히 대표 이미지에 앉히면 사람이 보고 있던 것과
            # 다른 자리에 판단이 쌓인다.
            raise ValueError(
                "그 이미지에는 이 시야의 현재 검출이 없다 — 저장하지 않았다")
    if cur is None or cur.image_id is None:
        raise ValueError("이 시야에는 현재 검출이 없다 — 저장하지 않았다")
    image = cur.image
    batch = cur.batch
    # **묶음이 없으면 받지 않는다.** `batch=None` 은 **사람이 그린 개체의
    # 자리다**(P09 5.2) — 엔진 교정을 거기 앉히면 두 종류가 한 이름 아래 섞이고,
    # 아래 삭제 줄이 사람이 그린 것을 쓸어 간다. 지금 현재 검출은 전부 묶음에
    # 들어 있으므로 이 갈래는 안 밟히지만, 밟히면 **오류로 말한다** — 조용히
    # 저장한 척하는 갈래를 남기지 않는다.
    if batch is None:
        raise ValueError(
            "이 시야의 현재 검출이 묶음(batch)에 안 들어 있다 — 저장하지 "
            "않았다. batch_runs.py 로 묶은 뒤 다시 시도할 것")

    removed, accepted = set(removed), set(accepted)
    keys = removed | accepted | set(labels) | set(notes)

    # **없는 것과 빈 것이 다르다** (`_save_drawn` 과 같은 규칙). `edits` 가 아예
    # 없으면 **고치기를 모르는 옛 화면**이다 — 배포 중에 열려 있던 탭이 그렇고,
    # 그 저장 한 번이 사람이 고친 기하를 전부 지우면 안 된다. 그때는 이미 고쳐
    # 둔 행의 키를 `keys` 에 얹어 삭제 대상에서 뺀다.
    #
    # 있으면 **그것이 전부다** — 화면은 늘 전체를 보낸다(`drawn` 과 같다).
    # 거기 없는 키는 고친 적이 없다는 말이고, `keys` 에 안 들어가면 아래 삭제
    # 줄이 지운다.
    if edits is None:
        keys |= set(ObjectReview.objects
                    .filter(image=image, batch=batch, geom_edited=True)
                    .values_list("mask_key", flat=True))
    edits = {str(k): list(v or []) for k, v in (edits or {}).items()}
    for k, poly in edits.items():
        if poly:                       # 빈 것은 "엔진 것으로 되돌린다" 는 말이다
            check_polygon(poly, (cur.width, cur.height), k)
    # **고친 기하도 표시다.** `keys` 에 안 넣으면 같은 저장의 마지막 줄이
    # "표시가 사라진 행" 으로 보고 지운다.
    keys |= set(edits)
    # **그 검출의 개체만 본다.** 예전에는 시야의 현재 검출 전부를 훑었는데,
    # 시야마다 현재 검출이 하나일 때만 같은 뜻이다 — 여럿이면 **프레임 A 의 키가
    # 프레임 B 의 화면에서 통과한다.** `mask_key` 는 프레임끼리 45% 겹치므로
    # 우연이 아니라 흔하게 통과하고, 아래 삭제 줄은 이미지로 좁혀져 있어
    # **엉뚱한 이미지의 키로 만든 행이 남는다** (P09 1단계).
    by_key = {c.mask_key: c for c in cur.candidates.all()}

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
    known = set(by_key) | set(ObjectReview.objects
                              .filter(image=image, batch=batch)
                              .values_list("mask_key", flat=True))
    unknown = keys - known
    if unknown:
        raise ValueError(
            f"현재 검출에 없는 개체 {len(unknown)}개가 섞여 있다 — 저장하지 "
            f"않았다. 다른 검출을 보고 있지 않은지 확인할 것 "
            f"(예: {sorted(unknown)[:3]})")

    # **완료는 그 묶음에, 코멘트는 시야에** (073). 한 줄에 담아 두었더니
    # `sam2-전수` 에서 붙인 완료가 `yolo-3차` 화면에도 붙어 있었다 — 아직 아무도
    # 안 본 검출이 "검토 완료" 로 보이고, "다음 미검토" 가 그 시야를 건너뛴다.
    #
    # 코멘트는 묶음을 갈아도 참이고 **사람이 쓴 글이라 재생성 불가**다. 완료와
    # 함께 묶음에 매달면 묶음을 갈 때마다 사라진다.
    ViewpointReview.objects.update_or_create(
        viewpoint=vp, batch=batch, defaults={"done": done})
    if note:
        ViewpointReview.objects.update_or_create(
            viewpoint=vp, batch=None, defaults={"note": note})
    else:
        # 비웠으면 지운다 — 빈 줄을 남겨 두면 "코멘트가 있는 시야" 를 세는 자리가
        # 어긋난다. 완료 줄은 건드리지 않는다.
        ViewpointReview.objects.filter(viewpoint=vp, batch=None).delete()
    for key in keys:
        cand = by_key.get(key)
        obj, _ = ObjectReview.objects.get_or_create(
            image=image, batch=batch, mask_key=key,
            defaults={"viewpoint": vp, "candidate": cand,
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
        # **사람이 고친 기하** (P09 4단계). 빈 폴리곤은 "엔진 것으로 되돌린다" 는
        # 말이라 깃발을 내리고 엔진의 기하를 다시 넣는다.
        if key in edits:
            poly = edits[key]
            if poly:
                obj.geom = {"bbox": shape.bbox(shape.points(poly)),
                            "polygon": poly}
                obj.geom_edited = True
            elif cand:
                obj.geom = {"bbox": cand.bbox_xywh, "polygon": cand.polygon}
                obj.geom_edited = False
            else:
                # 되돌릴 엔진 개체가 없다(고아) — 기하를 지우면 못 그린다
                raise ValueError(
                    f"되돌릴 엔진 개체가 없다 — 이 개체는 검출에 대응이 없다 "
                    f"(키 {key})")
        obj.save()

    # 표시가 사라진 행은 지운다.
    #
    # **범위가 시야가 아니라 `(이미지, 묶음)` 이다** (P06 5a · P09 5.1). 시야로
    # 지우면 프레임별 검토를 붙이는 날 **그 시야의 다른 이미지 교정까지 쓸어
    # 간다** — 017·027·053 이 전부 이 줄에서 났다. 묶음까지 넣으면 **다른 엔진을
    # 보고 있는 화면의 payload 가 이 묶음의 교정에 닿을 수가 없다** — 027 이
    # 구조적으로 불가능해진다.
    #
    # **`batch=None` 인 행은 안 지운다.** 사람이 그린 개체이고, 그것은 어느
    # 묶음에도 속하지 않아 이 payload 가 대표하지 않는다 (P09 5.2). 지우는 것은
    # 3단계에서 `drawn` 목록이 맡는다.
    (ObjectReview.objects.filter(image=image, batch=batch)
     .exclude(mask_key__in=keys).delete())

    n_drawn = _save_drawn(vp, image, drawn, (cur.width, cur.height))

    # **묶인 개체는 분류를 함께 받는다** (P11 · 2026-08-10).
    #
    # 묶음은 "이 판들의 이것이 같은 개체다" 라는 말이므로, 그중 하나가 봉상이면
    # 나머지도 봉상이다. 사람이 판을 넘겨 다시 지정하게 두면 **틀릴 수 있는 일**
    # 이 되고(한 판만 다르게 지정된 묶음은 학습 자료에서 모순이다), 무엇보다
    # 같은 판단을 판 수만큼 되풀이하게 된다.
    wants = dict(labels)
    for it in (drawn or []):
        if it.get("key"):
            wants[str(it["key"])] = it.get("cls") or ""
    spread = _spread_link_labels(vp, image, batch, known, wants)

    out = {"removed": len(removed), "accepted": len(accepted),
           "labels": len(labels), "notes": len(notes)}
    if n_drawn is not None:
        out["drawn"] = n_drawn
    if spread:
        # **화면이 이것을 받아야 한다.** 다른 판의 상태는 화면이 열릴 때 받은
        # 것이라 지금 번진 분류를 모르고, 그 판에서 다음 저장이 나가면 "표시가
        # 사라진 행" 으로 보고 지운다 — 뷰어는 늘 전체를 보낸다.
        out["linked"] = spread
    return out


def _spread_link_labels(vp, image, batch, known, wants) -> dict:
    """이 이미지에서 정한 분류를 **같은 묶음의 다른 판**에 번지게 한다.

    돌려주는 것은 `{이미지 id: {mask_key: 분류}}` — 바뀐 것만 담는다.

    **이 payload 가 대표하는 개체만 본다** (`known`). 화면에 없던 키까지 훑으면
    다른 화면이 정한 것을 이쪽의 빈칸으로 덮는다.

    `""` 는 "분류 없음" 이고 그것도 번진다 — 지정을 물렀는데 다른 판에만 남아
    있으면 묶음 안에서 어긋난다. 다만 **분류 말고는 아무것도 안 건드린다**:
    삭제·되살림·코멘트·종명은 판마다 따로 하는 판단이다.
    """
    mine = list(ObjectLinkMember.objects
                .filter(link__viewpoint=vp, image=image,
                        mask_key__in=list(known))
                .select_related("link"))
    if not mine:
        return {}
    # 이 화면이 대표하지 않는 것은 뺀다 — 사람이 그린 개체(batch=None)는 자기
    # 묶음(batch)이 없고, 엔진 개체는 이 판의 묶음이라야 한다.
    mine = [m for m in mine if m.batch_id in (batch.pk, None)]
    if not mine:
        return {}

    out = {}
    sibs = (ObjectLinkMember.objects
            .filter(link_id__in={m.link_id for m in mine})
            .exclude(pk__in=[m.pk for m in mine])
            .select_related("image"))
    by_link = {}
    for s in sibs:
        by_link.setdefault(s.link_id, []).append(s)

    for m in mine:
        want = wants.get(m.mask_key, "")
        for s in by_link.get(m.link_id, []):
            row = ObjectReview.objects.filter(
                image_id=s.image_id, batch_id=s.batch_id,
                mask_key=s.mask_key).first()
            if row is None:
                if not want:
                    continue          # 없던 행을 빈 분류로 만들 이유가 없다
                row = ObjectReview(viewpoint=vp, image_id=s.image_id,
                                   batch_id=s.batch_id, mask_key=s.mask_key,
                                   bind_method="exact", geom=s.geom)
            elif row.label == want:
                continue              # 이미 같다 — 화면에 알릴 것도 없다
            row.label = want
            # **빈 껍데기는 안 남긴다.** 분류를 물렀는데 표시가 하나도 없는 행이
            # 남으면, 그 판의 다음 저장이 "표시가 사라진 행" 으로 보고 지운다 —
            # 결과는 같지만 그때까지 세는 자리마다 유령이 하나씩 는다.
            if (not want and row.pk and not row.removed and not row.accepted
                    and not row.note and not getattr(row, "species", "")
                    and not row.geom_edited):
                row.delete()
            else:
                row.save()
            out.setdefault(str(s.image_id), {})[s.mask_key] = want
    return out


# 사람이 그린 개체의 키. **불투명하다** — bbox 를 넣으면 "키가 곧 기하" 라는
# 죽은 규약이 이어져서, 사람이 경계를 고쳤을 때(4단계) 키를 파싱한 쪽이 실제
# 모양과 다른 값을 얻는다 (P09 5.4).
MANUAL_KEY = re.compile(r"^m[0-9a-f]{8}$")
# 폴리곤 점 수의 상한. 점 찍기로 만드는 것이라 수십을 넘을 이유가 없고(엔진이
# 내는 것도 중앙 13~19점이다), 상한이 없으면 한 번의 POST 로 DB 를 부풀릴 수 있다.
MAX_POINTS = 400


def check_polygon(poly, size, key=""):
    """사람이 보낸 폴리곤을 받을 수 있는지 본다. 돌려주는 것은 `[x, y, w, h]`.

    **그리기와 고치기가 같은 검사를 지난다** — 갈라지면 한쪽으로만 들어오는
    값이 생기고, 그 값은 화면·학습 자료 어디서 터질지 모른다.

    못 받을 것은 **오류로 말한다.** 조용히 고쳐 앉히면 사람이 보낸 것과 다른
    것이 저장되고, 화면은 "저장됨" 이라고 적는다.
    """
    where = f" (키 {key})" if key else ""
    if len(poly) < shape.MIN_POINTS * 2 or len(poly) > MAX_POINTS * 2:
        raise ValueError(
            f"폴리곤의 점 수가 {shape.MIN_POINTS}~{MAX_POINTS} 를 벗어난다 "
            f"({len(poly) // 2}점){where}")
    try:
        poly[:] = [float(v) for v in poly]
    except (TypeError, ValueError):
        raise ValueError(f"폴리곤에 숫자가 아닌 값이 있다{where}")
    box = shape.bbox(shape.points(poly))
    if box is None:
        raise ValueError(f"폴리곤에서 상자를 못 만든다{where}")
    # **이미지 밖은 안 받는다.** 밖에 있는 개체는 그릴 수도 잴 수도 없고,
    # 학습 자료로 나가면 좌표가 뒤집힌 라벨이 된다.
    w, h = size
    if w and h and (box[0] < 0 or box[1] < 0
                    or box[0] + box[2] > w or box[1] + box[3] > h):
        raise ValueError(f"폴리곤이 이미지 밖으로 나간다{where}")
    return box


def _save_drawn(vp: Viewpoint, image, drawn, size=(0, 0)) -> int | None:
    """사람이 그린 개체를 저장한다 (P09 3단계). 돌려주는 것은 남은 개수다.

    **`None` 이면 손대지 않는다.** payload 에 `drawn` 이 아예 없는 것과 빈
    목록인 것은 다르다 — 앞은 **그리기를 모르는 옛 화면**(배포 중에 열려 있던
    탭)이고 뒤는 "그린 것이 하나도 없다" 는 말이다. 둘을 같이 다루면 옛 탭의
    저장 한 번이 사람이 그린 개체를 전부 지운다.

    **`batch` 가 `None` 이다.** 엔진에 대한 판단이 아니라 이미지에 대한 사실이라
    어느 회차에도 안 속한다 — 그래서 묶음을 갈아타도 안 사라진다 (P09 5.2).

    **지우는 것은 행을 지우는 것이다.** 엔진이 낸 것은 `removed=True` 로 남겨
    음성 표본이 되지만, 사람이 그리다 만 것을 그렇게 남기면 **"여기 규조각
    없다" 를 다음 회차에 가르치게 된다** (P09 5.10).
    """
    if drawn is None:
        return None

    keep = []
    for item in drawn:
        key = str(item.get("key") or "")
        if not MANUAL_KEY.match(key):
            raise ValueError(f"사람이 그린 개체의 키가 규칙에 안 맞는다: {key!r}")
        poly = list(item.get("polygon") or [])
        # 크기는 **검출**에서 받는다 — `Image.width`·`height` 는 nullable 이라
        # 안 채워진 행이 있고(그러면 검사가 조용히 통과한다), 화면이 좌표를
        # 만드는 근거도 검출의 `size` 다.
        box = check_polygon(poly, size, key)

        keep.append((key, {"bbox": box, "polygon": poly},
                     item.get("cls") or "", item.get("note") or ""))

    for key, geom, cls, note in keep:
        obj, _ = ObjectReview.objects.get_or_create(
            image=image, batch=None, mask_key=key,
            defaults={"viewpoint": vp, "source": "manual",
                      "bind_method": "manual"})
        obj.source = "manual"
        obj.geom = geom
        obj.label = cls
        obj.note = note
        obj.save()

    (ObjectReview.objects.filter(image=image, batch__isnull=True)
     .exclude(mask_key__in=[k for k, *_ in keep]).delete())
    return len(keep)


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
        # 무엇에 붙은 검출인가는 `image.kind` 가 말한다 (P06 5a). 예전에는
        # `target` + nullable `frame` 이라는 다형 연관을 흉내 냈다.
        if d.image_id is None:
            continue
        if d.image.kind == "frame":
            by_frame[d.image.frame_id] = d
        elif d.image.kind == "stack":
            stack_det = d
    return by_frame, stack_det


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


def engine_viewpoint(slug: str, gid: int, run_id: int,
                     link=None) -> dict | None:
    """시험 화면 한 장. `group_detail` 과 같은 모양이되 검출만 갈아 끼운다.

    YOLO 는 **프레임마다** 검출을 낸다(합성본이 아니라 원본을 본다). 그래서
    프레임 하나하나에 각자의 검출이 붙는다 — `group_detail` 이 싱글턴에 쓰던
    길과 같다.

    `link` 는 이웃 시야의 주소를 만드는 함수다. **부르는 쪽이 준다** — 엔진을
    갈아 끼운 상태(`/d/…?batch=`)는 그 상태로 옆 시야로 가야 하기 때문이다.
    주소를 여기 박아 두면 "다음 시야" 를 누를 때마다 현재 검출로 튀어나간다
    (051 이전에 실제로 그랬다). 한때 `/engine/` 이라는 다른 화면도 이 함수를
    썼고 그쪽은 거기 머물러야 했다 — 그 화면은 075 에서 지웠다.
    """
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        return None
    vp = _viewpoints_of(slide).filter(idx=gid).first()
    if vp is None:
        return None
    if link is None:
        # **여기서 만드는 주소는 검토 화면의 `?batch=` 다** (075). 예전에는
        # `/engine/` 로 갔는데 그 화면을 지웠으므로, 남겨 두면 `NoReverseMatch`
        # 로 **화면이 통째로 500** 이 된다. 들어오는 값이 404 가 되는 것과
        # 나가는 값을 못 만드는 것은 고장의 크기가 다르다 (057).
        def link(i):
            return reverse("group", args=[slug, i]) + f"?batch={run_id}"

    # 묶음이면 형제 실행까지 본다 — 한 슬라이드가 한 실행이라 시야를 열면
    # 그 시야를 만든 실행은 하나뿐이지만, 주소의 실행 번호가 다른 슬라이드
    # 것일 수 있다.
    # **현재 검출도 함께 본다.** 예전에는 쌓아 둔 것만 봤다 — 검토 화면과
    # 겹치지 않게 하려는 뜻이었다. 그런데 SAM2 묶음은 결과의 대부분이 현재로
    # 올라가 있어서, 묶음을 고를 수 있게 되자 "SAM2 칸을 눌렀는데 아무것도
    # 없다" 가 됐다. 비교하려면 그 묶음이 **실제로 낸 것**을 봐야 한다.
    # 이 화면은 읽기 전용이고 교정을 얹지 않으므로 검토 화면을 건드리지 않는다.
    ids = set(engine_run_ids(run_id))
    by_frame, stack_det = _engine_pick(
        [d for d in vp.detections.all() if d.run_id in ids])

    # **엔진마다 검출을 다는 자리가 다르다.** SAM2 는 합성본 한 장에만 달고,
    # YOLO 는 프레임마다 + 합성본에도 단다. 프레임만 보면 SAM2 묶음은 통째로
    # 빈 화면이 된다 — 묶음을 고를 수 있게 된 뒤로는 사람이 그 빈 화면을 직접
    # 누르게 된다.

    frames = []
    all_frames = list(vp.frames.all())
    # 선명도 막대는 그룹 내 최고 대비 비율이다. 빠뜨리면 `_shots.html` 이
    # `width:%` 라는 값 없는 CSS 를 내고 막대가 통째로 사라진다.
    values = [f.sharpness for f in all_frames if f.sharpness is not None]
    top = max(values) if values else 0
    for f in all_frames:
        d = by_frame.get(f.id)
        frames.append({
            "name": f.name,
            "acquired_at": f.acquired_at,
            "created_at": f.created_at,
            "sharpness": f.sharpness,
            "sharp_pct": (round(100 * f.sharpness / top)
                          if f.sharpness and top else 0),
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
    # 늘어서서 비교할 수가 없다 — 같은 자리에서 프레임만 바뀌어야 "이 규조각이
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
    # **개체가 있는 합성본이면 거기서 시작한다.** 시야로 들어가면 그 시야를
    # 대표하는 한 장이 먼저 보여야 하고, 그게 합성본이다 — 검토 화면
    # (`group_detail`)도 같은 규칙이라 두 화면이 같은 자리에서 열린다.
    #
    # 아니면 **개체가 가장 많은 판**으로 물러난다. 그것이 원래 규칙이었고 이유가
    # 있다 — 빈 판이 먼저 열리면 검출이 아무것도 없는 줄 알게 된다.
    #
    # **"합성본이 있으면" 이 아니라 "개체가 있으면" 이다.** 처음엔 합성본을
    # 무조건 골랐는데, 합성본만 비고 프레임에는 개체가 있는 시야가 yolo-1차에서
    # 10개 나왔다 — 옛 규칙이 막으려던 바로 그 화면을 다시 만들 뻔했다.
    #
    # 실측: 이 규칙 전에는 YOLO 묶음의 여러장 시야 317개 중 **247개**가 합성본이
    # 아닌 프레임에서 열렸다. SAM2 는 합성본에만 검출이 있어 0개였고, 그래서
    # 엔진을 갈아 끼울 때마다 시작 판이 달라 보였다.
    stack_p = next((p for p in pool if p["key"] == STACK_KEY
                    and p["det"]["candidates"]), None)
    best = stack_p or max(pool, key=lambda p: len(p["det"]["candidates"]),
                          default=None)
    return {
        "slug": slug, "label": slide.name, "id": gid, "tag": vp.tag,
        "run_id": run_id,
        "n": vp.n_frames,
        "sharpest": vp.sharpest_frame.name if vp.sharpest_frame else None,
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
        "prev_url": link(ids[pos - 1]) if pos > 0 else None,
        "next_url": link(ids[pos + 1]) if pos < len(ids) - 1 else None,
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


def batches_for_viewpoint(slug: str, gid: int,
                          run_id: int | None = None) -> list[dict]:
    """이 시야에 쌓여 있는 묶음들. 검출 화면에서 갈아 끼우는 데 쓴다.

    **같은 시야를 보면서 엔진을 바꿀 수 있어야 한다.** 목록으로 나갔다가 다른
    묶음으로 들어오면 어느 시야를 보고 있었는지 잃는다 — 비교는 같은 자리를
    번갈아 보는 일이다.

    주소에는 실행 번호가 들어가지만 화면은 묶음 단위로 다루므로, 각 묶음에서
    **아무 실행 하나**를 대표로 준다(`engine_run_ids` 가 형제까지 편다).

    칸마다 개체 합계를 함께 준다. 눌러 보기 전에 "여기서는 몇 개를 잡았나" 를
    비교하는 것이 이 화면의 목적이고, 그 수가 묶음을 고르는 근거이기 때문이다.
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
            # **검토 대상 묶음인가** — 이 값이 읽기 전용을 가른다 (P10 1단계).
            # 예전에는 `any(d.is_current …)` 였는데, 정규화 뒤에는 모든 묶음의
            # 검출이 `is_current` 라 **전부 편집 가능해 보인다.** 어느 묶음을
            # 검토하는지는 `RunBatch.for_review` 하나가 정한다.
            "current": bool(rep.run and rep.run.batch_id
                            and rep.run.batch.for_review),
            "n": Candidate.objects.filter(
                detection__in=picked, passed=True).count(),
        })
    return sorted(out, key=lambda g: g["label"])


# 화면에 적을 엔진 이름. 백엔드 이름(`Run.params["backend"]`)은 모델 판까지
# 들어 있어서(`sam2`) 고르는 칸에는 길다. **여기 없는 것은 대문자로 그대로
# 낸다** — 새 백엔드(`sam3` 등)가 이름 없이 사라지지 않게.
ENGINE_LABELS = {"sam2": "SAM", "sam3": "SAM3", "yolo": "YOLO"}


def engines_from_batches(batches: list[dict]) -> list[dict]:
    """묶음 목록을 **엔진 단위로** 접는다 (051).

    고르는 사람이 재는 것은 엔진이지 묶음이 아니다 — `yolo-1차`·`yolo-3차` 가
    따로 서면 무엇을 눌러야 할지 알 수 없다. 한 엔진에 묶음이 여럿이면 하나를
    대표로 세운다:

        지금 보고 있는 것 → 현재 검출을 낸 것 → 실행 번호가 큰 것(나중 것)

    **묶음 이름은 버리지 않는다** (`batch_label`). 화면이 말풍선에 적어 어느
    묶음을 열었는지 되짚을 수 있어야 한다.

    개수는 대표 묶음의 것이다. 합치지 않는다 — 눌러서 가는 곳이 대표 하나라,
    합계를 보이면 눌러 보고 "아까 그 수가 아닌데" 가 된다.
    """
    per = defaultdict(list)
    for b in batches:
        per[b["backend"]].append(b)

    out = []
    for backend, group in per.items():
        rep = sorted(group, key=lambda b: (b["on"], b["current"], b["run_id"]))[-1]
        out.append({
            **rep,
            "key": backend,
            "label": ENGINE_LABELS.get(backend, (backend or "?").upper()),
            "batch_label": rep["label"],
            # 이 엔진이 이 시야에 낸 묶음이 여럿인가 — 말풍선이 적는다
            "n_batches": len(group),
        })
    # **교정이 되는 것을 맨 앞에 둔다.** 검토 화면의 기본 자리이고, 라디오는
    # 왼쪽부터 읽힌다.
    return sorted(out, key=lambda e: (not e["current"], e["label"]))
