"""
groups_*.json 과 검출 산출물을 읽어 뷰가 쓰기 좋은 형태로 만든다.

DB 를 두지 않는 이유: 원본이 이미 JSON 이고, 스크립트를 다시 돌리면 그대로
덮어써진다. 동기화 문제를 만들 바에 매번 읽는 편이 낫다. 파일 mtime 을 보고
캐시하므로 스크립트를 재실행하면 새로고침만으로 반영된다.
"""
import json
import math
import re
from pathlib import Path

from django.conf import settings

# {경로: (mtime, 파싱결과)}
_cache: dict[Path, tuple[float, object]] = {}


def _load_json(path: Path):
    """mtime 이 그대로면 캐시를 쓴다."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    _cache[path] = (mtime, data)
    return data


def group_files() -> list[Path]:
    return sorted(Path(settings.DATA_ROOT).glob("groups_*.json"))


def dataset_slug(path: Path) -> str:
    """groups_WAP13-GC47_116cm.json -> wap13-gc47_116cm"""
    return path.stem.removeprefix("groups_").lower()


def group_detection(group: dict) -> dict | None:
    """
    그룹 하나에 붙은 검출 결과.

    합성본이 원칙이고, 싱글턴 그룹(n=1)은 합성본이 없어 그 한 장으로 돌린다.
    run_batch.sh 의 대상 선정 규칙과 같아야 한다.
    """
    stack = stack_for(group_tag(group))
    if stack and stack.get("detection"):
        return stack["detection"]
    stem = group.get("sharpest") or group["images"][0]
    return detection_for(stem)


def _detect_stats(groups: list[dict]) -> dict:
    """검출·교정 통계를 데이터셋 단위로 모은다. 검출 안 돌린 그룹은 평균에서 뺀다.

    분류별 개수는 CLASSES 를 그대로 훑으므로 분류를 더해도 여기는 손댈 필요가 없다.
    """
    counts, reviewed = [], 0
    per_cls = {k: 0 for k in CLASSES}
    n_auto = n_removed = n_accepted = n_labeled = n_noted = n_group_notes = 0
    for g in groups:
        det = group_detection(g)
        if det is None:
            continue
        counts.append(det.get("n_candidates", 0))
        c = det.get("counts") or {}
        for k in CLASSES:
            per_cls[k] += c.get(k, 0)
        n_labeled += c.get("labeled", 0)
        n_auto += det.get("n_auto", 0)
        # 사람 손이 얼마나 들어갔는지 — 재현율·정밀도를 논할 때의 근거가 된다.
        n_removed += det.get("n_removed", 0)
        n_accepted += len(det.get("accepted_keys") or [])
        n_noted += len(det.get("notes") or {})
        if det.get("review_note"):
            n_group_notes += 1
        if det.get("review_done"):
            reviewed += 1

    class_counts = [{"key": k, "label": CLASS_LABELS[k], "n": per_cls[k]}
                    for k in CLASSES if per_cls[k]]
    common = {
        "n_auto": n_auto,
        "n_rod": per_cls["rod"],
        "n_round": per_cls["round"],
        "class_counts": class_counts,
        "n_removed": n_removed,
        "n_accepted": n_accepted,
        "n_labeled": n_labeled,
        "n_noted": n_noted,
        "n_group_notes": n_group_notes,
        # 검토를 마친 시야 수. 재현율 실측·학습 데이터 선별의 진척이다.
        "reviewed_groups": reviewed,
    }
    if not counts:
        return {"detected_groups": 0, "n_detected": 0, "mean_detected": None, **common}
    return {
        "detected_groups": len(counts),
        "n_detected": sum(counts),
        "mean_detected": round(sum(counts) / len(counts), 1),
        **common,
    }


def _stats(groups: list[dict]) -> dict:
    sizes = [g["n"] for g in groups]
    n_img = sum(sizes)
    return {
        "n_groups": len(groups),
        "n_images": n_img,
        "mean_size": round(n_img / len(groups), 1) if groups else 0,
        "singletons": sum(1 for s in sizes if s == 1),
        "max_size": max(sizes) if sizes else 0,
    }


def datasets() -> list[dict]:
    """모든 groups_*.json 을 요약해 돌려준다."""
    out = []
    for path in group_files():
        meta = _load_json(path)
        if not meta or "groups" not in meta:
            continue
        image_dir = Path(meta["dir"])
        out.append(
            {
                "slug": dataset_slug(path),
                "label": image_dir.name,
                "json_name": path.name,
                "image_dir": meta["dir"],
                "corr_thresh": meta.get("corr_thresh"),
                "missing_dir": not (Path(settings.DATA_ROOT) / image_dir).is_dir(),
                **_stats(meta["groups"]),
                **_detect_stats(meta["groups"]),
            }
        )
    return out


def _find_dataset_path(slug: str) -> Path | None:
    for path in group_files():
        if dataset_slug(path) == slug:
            return path
    return None


def group_tag(group: dict) -> str:
    """focus_stack.py 가 산출물 파일명에 쓰는 태그와 동일한 규칙."""
    images = group["images"]
    return f"g{group['id']:03d}_{images[0]}-{images[-1].split('-')[-1]}"


def _rel(path: Path) -> str:
    """DATA_ROOT 기준 상대경로 문자열. 이미지 URL 의 p= 값이 된다."""
    return str(path.relative_to(settings.DATA_ROOT))


def cand_key(c: dict) -> str:
    """
    마스크의 안정적인 식별자.

    id 는 필터를 다시 걸면 재부여되므로 못 쓴다. bbox 는 같은 마스크면
    그대로이므로 교정 기록(review)의 키로 삼는다. 클라이언트도 같은 규칙을
    쓴다 — 양쪽이 어긋나면 교정이 엉뚱한 개체에 붙는다.
    """
    b = c.get("bbox_xywh") or [0, 0, 0, 0]
    return "_".join(str(int(v)) for v in b)


# 사람이 지정할 수 있는 분류. **여기가 유일한 정의다** — 뷰어의 메뉴, 표의 배지,
# 크롭 갤러리의 필터가 모두 이것을 읽는다. 분류를 더할 때 한 줄만 고치면 된다.
#
# 자동 판정은 rod/round 둘뿐이다. 조각난 규조각을 그 둘로 밀어넣으면 계측·학습에서
# 온전한 개체와 섞이므로 파편을 따로 두고, 형태가 아니라 속(屬)으로 알아보는 것은
# 그 이름으로 둔다(Eucampia — 남극 시료의 지시종이라 형태 칸에 묶어 둘 수 없다).
CLASS_LABELS = {
    "round": "원형",
    "round_frag": "원형 파편",
    "rod": "봉상",
    "rod_frag": "봉상 파편",
    "eucampia": "Eucampia",
}
# 형태 칸과 분류학 칸은 성격이 다르다 — 메뉴에서 줄을 그어 나눈다.
TAXON_CLASSES = ("eucampia",)
CLASSES = tuple(CLASS_LABELS)
CLASS_BADGE = {"round": "on", "round_frag": "frag", "rod": "rod",
               "rod_frag": "frag", "eucampia": "euc"}


def class_list() -> list[dict]:
    """분류 정의를 템플릿·클라이언트가 쓰기 좋은 형태로."""
    return [{"key": k, "label": CLASS_LABELS[k],
             "badge": CLASS_BADGE.get(k, ""), "taxon": k in TAXON_CLASSES}
            for k in CLASSES]

# bbox 로 만든 개체 키. cand_key() 와 뷰어의 keyOf() 가 같은 규칙을 쓴다.
CAND_KEY = re.compile(r"^-?\d+_-?\d+_-?\d+_-?\d+$")


def review_path(stem: str) -> Path:
    return Path(settings.DATA_ROOT) / settings.REVIEW_DIR / f"{stem}_review.json"


def load_review(stem: str) -> dict:
    data = _load_json(review_path(stem)) or {}
    return {
        "removed": set(data.get("removed") or []),
        "accepted": set(data.get("accepted") or []),
        # 사람이 이 시야를 다 봤다고 표시했는가. 고칠 것이 없어 교정 기록이
        # 비어 있어도 검토는 끝났을 수 있으므로 따로 남긴다 — "검토한 시야"와
        # "아직 안 본 시야"를 가려야 재현율을 실측하고 학습 데이터를 고를 수 있다.
        "done": bool(data.get("done")),
        # 사람이 덮어쓴 분류. 자동 판정보다 늘 우선한다.
        "labels": {str(k): v for k, v in (data.get("labels") or {}).items()
                   if v in CLASSES},
        "notes": {str(k): str(v) for k, v in (data.get("notes") or {}).items()
                  if isinstance(v, str) and v.strip()},
        # 시야 전체에 대한 메모. 개체에 붙지 않는 이야기를 적는 곳이다.
        "note": (data.get("note") or "").strip() if isinstance(data.get("note"), str) else "",
    }


def polygon_axis(poly) -> tuple[float, float] | None:
    """마스크의 주축 각도(도)와 축 비율. 폴리곤의 **면적 모멘트**로 정확히 구한다.

    꼭짓점만 PCA 하면 approxPolyDP 로 단순화된 점 간격이 고르지 않아 결과가
    치우친다. 다항식 닫힌 해로 채워진 영역의 2차 모멘트를 직접 구한다.

    각도는 이미지 좌표계(y 아래로) 기준이고 +x 축에서 재며, 반환값은 (각도, 이심비).
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
    # 중심 기준 2차 모멘트
    m20 = sxx / (12.0 * area) - cx * cx
    m02 = syy / (12.0 * area) - cy * cy
    m11 = sxy / (24.0 * area) - cx * cy

    ang = 0.5 * math.atan2(2.0 * m11, m20 - m02)
    # 고유값 -> 축 길이 비. 원형(비 1)에서는 각도가 뜻이 없다.
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
    """갤러리 크롭의 회전량과 **정확한** 결과 크기(px).

    주축을 세로로 세운다(장축이 위아래) — 방향이 통일되면 형태를 나란히 비교할
    수 있다. 축 비율이 1에 가까운 것(원형)은 방향이 뜻 없으므로 돌리지 않는다.

    크기를 여백까지 포함해 여기서 확정하는 이유: **스케일바 길이를 계산해야
    한다.** 자르는 쪽에서 여백을 따로 더하면 결과가 몇 µm 폭인지 알 수 없다.
    회전을 하지 않을 때도 폴리곤 범위를 쓰므로, SAM 이 떠돌이 픽셀로 부풀려 놓은
    bbox 대신 본체에 맞춰 잘린다.
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
    """크롭 썸네일에 얹을 스케일바. 이미지 폭에 대한 백분율로 준다.

    백분율이라 화면에서 얼마로 그려지든 맞는다 — 다만 그리는 쪽에서 그 백분율의
    기준이 **이미지**여야 한다(칸이 아니라).
    """
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


def mask_class(c: dict) -> str:
    """마스크를 그릴 때 쓰는 클래스. **뷰어의 addPolygon() 과 같은 규칙이어야 한다.**

    사람이 지정한 분류가 가장 먼저다 — 되살린 개체(manual)에 Eucampia 를 지정했으면
    Eucampia 색으로 보여야 한다. 지정이 없으면 되살린 표시(주황), 그다음 자동 판정.
    """
    if c.get("cls_user") and c.get("cls"):
        return c["cls"]
    if c.get("manual"):
        return "manual"
    return c.get("cls") or "none"


def mask_points(c: dict) -> str | None:
    """폴리곤을 SVG points 문자열로. 목록 썸네일에 마스크를 얹는 데 쓴다."""
    p = c.get("polygon") or []
    if len(p) < 6:
        return None
    return " ".join(f"{p[i]},{p[i + 1]}" for i in range(0, len(p) - 1, 2))


def _guess_cls(c: dict) -> str | None:
    """수동으로 되살린 개체의 표시용 분류."""
    e = c.get("elongation")
    if e is None:
        return None
    if e < 1.4:
        return "round"
    return "rod" if 2.0 <= e <= 20.0 else None


def detection_for(stem: str) -> dict | None:
    """<stem>_candidates.json 을 DETECT_DIRS 순서로 찾고 교정 기록을 반영한다."""
    root = Path(settings.DATA_ROOT)
    for d in settings.DETECT_DIRS:
        path = root / d / f"{stem}_candidates.json"
        data = _load_json(path)
        if data is None:
            continue
        overlay = root / d / f"{stem}_overlay.jpg"
        data = dict(data)
        data["source_dir"] = d
        data["stem"] = stem
        data["overlay_rel"] = _rel(overlay) if overlay.exists() else None

        review = load_review(stem)
        rejected = list(data.get("rejected") or [])
        n_auto = len(data.get("candidates") or [])      # 교정 전 통과분 개수

        # 오검출로 표시된 것은 빼고, 되살린 것은 넣는다.
        # 뺀 것도 버리지 않고 따로 넘긴다 — 뷰어가 흔적으로 그려 되살릴 수 있게.
        #
        # 문턱을 바꿔 다시 거르면(refilter.py) 사람이 지워 둔 개체가 탈락분으로
        # 옮겨갈 수 있다. 그때도 **"사람이 지웠다"가 이긴다** — 지운 것이 조용히
        # 되살아나는 것이 가장 나쁜 결과다.
        kept, gone = [], []
        for c in data.get("candidates") or []:
            # **반드시 복사한다.** _load_json 이 파싱 결과를 mtime 캐시에 두므로,
            # 여기서 원본 dict 에 id·removed·cls·note 를 써 넣으면 그 값이 캐시에
            # 남는다. 그러면 교정을 되돌려도(되살리기, 분류 지정 해제, 메모 삭제)
            # 옛 상태가 계속 따라붙는다 — 조용히 틀린 화면이 된다.
            c = dict(c)
            (gone if cand_key(c) in review["removed"] else kept).append(c)
        for c in rejected:
            key = cand_key(c)
            # from_reject: 기록이 탈락분에서 왔다는 표시. 되살릴 때 accepted 에
            # 넣어야 한다는 뜻이며, manual(사람이 되살려 놓은 것)과는 다르다.
            if key in review["removed"]:
                c = dict(c)
                c["from_reject"] = True
                gone.append(c)
            elif key in review["accepted"]:
                c = dict(c)
                c["manual"] = True
                c["from_reject"] = True
                c["cls"] = _guess_cls(c)
                kept.append(c)

        # 사람이 지정한 분류·메모를 얹는다. 분류는 자동 판정을 덮어쓰되 원래
        # 값을 cls_auto 로 남긴다 — 나중에 "기계가 무엇이라고 했나" 를 봐야 한다.
        for c in kept + gone:
            key = cand_key(c)
            label = review["labels"].get(key)
            if label:
                if c.get("cls") != label:
                    c["cls_auto"] = c.get("cls")
                c["cls"] = label
                c["cls_user"] = True
            note = review["notes"].get(key)
            if note:
                c["note"] = note

        kept.sort(key=lambda r: -r.get("area_px", 0))
        for i, c in enumerate(kept):
            c["id"] = i
        for c in gone:
            c["removed"] = True
        data["candidates"] = kept
        data["removed_candidates"] = gone
        data["n_candidates"] = len(kept)
        data["counts"] = {
            **{k: sum(1 for c in kept if c.get("cls") == k) for k in CLASSES},
            "manual": sum(1 for c in kept if c.get("manual")),
            "labeled": sum(1 for c in kept if c.get("cls_user")),
        }
        # 자동 판정이 잡은 개수(교정 전). 화면의 "검출 N -> 남은 M" 이 여기서 온다.
        data["n_auto"] = n_auto
        data["n_removed"] = len(review["removed"])
        data["review_done"] = review["done"]
        # 분류·메모는 클라이언트가 그대로 이어받아 편집한다.
        data["labels"] = dict(review["labels"])
        data["notes"] = dict(review["notes"])
        data["review_note"] = review["note"]
        # 복구 목록을 그대로 넘긴다. 클라이언트가 manual 플래그로 되짚으면,
        # 지워 둔 탈락분(위의 from_reject)까지 "복구된 것"으로 잘못 세어
        # 다음 저장에서 지운 것이 되살아난다.
        data["accepted_keys"] = sorted(review["accepted"])
        # 되살리기 후보 — 이미 채택했거나 지워 둔 것은 뺀다. 지운 것은 유령으로
        # 이미 화면에 있으므로, 여기 남기면 같은 개체가 두 곳에 나온다.
        data["rejected"] = [c for c in rejected
                            if cand_key(c) not in review["accepted"]
                            and cand_key(c) not in review["removed"]]
        return data
    return None


def stack_for(tag: str) -> dict | None:
    """focus_stack.py 산출물이 있으면 경로를 모아 준다."""
    root = Path(settings.DATA_ROOT)
    focused = root / settings.STACK_DIR / f"{tag}_focused.jpg"
    if not focused.exists():
        return None
    depth = root / settings.STACK_DIR / f"{tag}_depth.jpg"
    return {
        "focused_rel": _rel(focused),
        "depth_rel": _rel(depth) if depth.exists() else None,
        "stem": f"{tag}_focused",
        "detection": detection_for(f"{tag}_focused"),
    }


def _frames(group: dict, image_dir: Path) -> list[dict]:
    sharp = group.get("sharpness") or {}
    values = [v for v in sharp.values() if isinstance(v, (int, float))]
    top = max(values) if values else 0
    frames = []
    for name in group["images"]:
        value = sharp.get(name)
        jpg = image_dir / f"{name}.jpg"
        frames.append(
            {
                "name": name,
                "sharpness": value,
                # 그룹 내 최고 선명도 대비 비율 — 막대 길이로 쓴다.
                "sharp_pct": round(100 * value / top) if value and top else 0,
                "is_sharpest": name == group.get("sharpest"),
                "rel": _rel(jpg),
                "exists": jpg.exists(),
                "detection": detection_for(name),
            }
        )
    return frames


def dataset_detail(slug: str) -> dict | None:
    path = _find_dataset_path(slug)
    if path is None:
        return None
    meta = _load_json(path)
    if not meta:
        return None
    image_dir = Path(settings.DATA_ROOT) / meta["dir"]
    groups = []
    for g in meta["groups"]:
        tag = group_tag(g)
        stack = stack_for(tag)
        det = group_detection(g)
        # 목록의 대표 그림은 합성본이 원칙이다 — 그룹을 대표하는 그림이 검출을
        # 돌린 그림과 같아야 목록과 상세가 어긋나지 않는다. 합성본이 없으면
        # 싱글턴(한 장뿐)이거나 아직 합성하지 않은 그룹이므로 프레임을 쓴다.
        cover_rel = stack["focused_rel"] if stack else None
        if cover_rel is None:
            cover = image_dir / f"{g.get('sharpest', g['images'][0])}.jpg"
            cover_rel = _rel(cover) if cover.exists() else None

        # 표지에 검출 마스크를 얹는다. 검출을 돌린 이미지와 표지가 같을 때만 —
        # 다른 이미지의 좌표를 얹으면 조용히 어긋난 그림이 된다.
        masks, size = [], None
        if det and cover_rel and det.get("stem") == Path(cover_rel).stem:
            size = det.get("size")
            for c in det.get("candidates") or []:
                pts = mask_points(c)
                if pts:
                    masks.append({"points": pts, "cls": mask_class(c)})
        groups.append(
            {
                "id": g["id"],
                "n": g["n"],
                "tag": tag,
                "span_sec": round(g.get("span_sec", 0), 1),
                "sharpest": g.get("sharpest"),
                "cover_rel": cover_rel,
                "cover_size": size,
                "masks": masks,
                "has_stack": stack is not None,
                "n_detected": (det or {}).get("n_candidates"),
                "reviewed": bool((det or {}).get("review_done")),
            }
        )
    return {
        "slug": slug,
        "label": image_dir.name,
        "json_name": path.name,
        "corr_thresh": meta.get("corr_thresh"),
        "groups": groups,
        **_stats(meta["groups"]),
        **_detect_stats(meta["groups"]),
    }


def group_detail(slug: str, gid: int) -> dict | None:
    path = _find_dataset_path(slug)
    if path is None:
        return None
    meta = _load_json(path)
    if not meta:
        return None
    group = next((g for g in meta["groups"] if g["id"] == gid), None)
    if group is None:
        return None
    image_dir = Path(settings.DATA_ROOT) / meta["dir"]
    ids = [g["id"] for g in meta["groups"]]
    pos = ids.index(gid)
    tag = group_tag(group)
    return {
        "slug": slug,
        "label": image_dir.name,
        "id": gid,
        "n": group["n"],
        "tag": tag,
        "span_sec": round(group.get("span_sec", 0), 1),
        "sharpest": group.get("sharpest"),
        "frames": _frames(group, image_dir),
        "stack": stack_for(tag),
        "prev_id": ids[pos - 1] if pos > 0 else None,
        "next_id": ids[pos + 1] if pos < len(ids) - 1 else None,
    }


def stamp(rel: str) -> int:
    """이미지의 mtime. URL 에 넣어 "내용이 바뀌면 주소도 바뀌게" 만든다.

    주소가 그대로면 브라우저는 합성본을 다시 만들어도 옛 그림을 계속 쓴다.
    반대로 주소에 mtime 이 있으면 마음껏 캐시해도 늘 맞는다.
    """
    try:
        return int((Path(settings.DATA_ROOT) / rel).stat().st_mtime)
    except (OSError, TypeError, ValueError):
        return 0


def safe_image_path(rel: str) -> Path | None:
    """
    p= 로 들어온 상대경로를 실제 파일로 바꾼다.

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
