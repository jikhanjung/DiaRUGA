"""
groups_*.json 과 검출 산출물을 읽어 뷰가 쓰기 좋은 형태로 만든다.

DB 를 두지 않는 이유: 원본이 이미 JSON 이고, 스크립트를 다시 돌리면 그대로
덮어써진다. 동기화 문제를 만들 바에 매번 읽는 편이 낫다. 파일 mtime 을 보고
캐시하므로 스크립트를 재실행하면 새로고침만으로 반영된다.
"""
import json
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


def review_path(stem: str) -> Path:
    return Path(settings.DATA_ROOT) / settings.REVIEW_DIR / f"{stem}_review.json"


def load_review(stem: str) -> dict:
    data = _load_json(review_path(stem)) or {}
    return {
        "removed": set(data.get("removed") or []),
        "accepted": set(data.get("accepted") or []),
    }


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

        # 오검출로 표시된 것은 빼고, 되살린 것은 넣는다.
        # 뺀 것도 버리지 않고 따로 넘긴다 — 뷰어가 흔적으로 그려 되살릴 수 있게.
        kept, gone = [], []
        for c in data.get("candidates") or []:
            (gone if cand_key(c) in review["removed"] else kept).append(c)
        for c in rejected:
            key = cand_key(c)
            if key not in review["accepted"]:
                continue
            c = dict(c)
            c["manual"] = True
            c["cls"] = _guess_cls(c)
            kept.append(c)
        # 수동 복구했다가 다시 지운 것도 흔적으로 남는다.
        for c in rejected:
            key = cand_key(c)
            if key in review["removed"] and key not in review["accepted"]:
                c = dict(c)
                c["manual"] = True
                gone.append(c)

        kept.sort(key=lambda r: -r.get("area_px", 0))
        for i, c in enumerate(kept):
            c["id"] = i
        for c in gone:
            c["removed"] = True
        data["candidates"] = kept
        data["removed_candidates"] = gone
        data["n_candidates"] = len(kept)
        data["counts"] = {
            "rod": sum(1 for c in kept if c.get("cls") == "rod"),
            "round": sum(1 for c in kept if c.get("cls") == "round"),
            "manual": sum(1 for c in kept if c.get("manual")),
        }
        data["n_removed"] = len(review["removed"])
        # 되살리기 후보 — 아직 채택되지 않은 탈락분만 넘긴다.
        data["rejected"] = [c for c in rejected
                            if cand_key(c) not in review["accepted"]]
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
        cover = image_dir / f"{g.get('sharpest', g['images'][0])}.jpg"
        stack = stack_for(tag)
        groups.append(
            {
                "id": g["id"],
                "n": g["n"],
                "tag": tag,
                "span_sec": round(g.get("span_sec", 0), 1),
                "sharpest": g.get("sharpest"),
                "cover_rel": _rel(cover) if cover.exists() else None,
                "has_stack": stack is not None,
                # 대표 1장이든 합성본이든 검출 결과가 하나라도 붙어 있으면 표시
                "n_detected": (
                    (stack or {}).get("detection", {}) or {}
                ).get("n_candidates")
                or (detection_for(g.get("sharpest", "")) or {}).get("n_candidates"),
            }
        )
    return {
        "slug": slug,
        "label": image_dir.name,
        "json_name": path.name,
        "corr_thresh": meta.get("corr_thresh"),
        "groups": groups,
        **_stats(meta["groups"]),
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
