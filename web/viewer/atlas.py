"""도감 도판 — 목록·쪽 넘기기. **DB 에 행이 없다** (P15 §6 · 129).

`outcrop.py` 와 같은 자리다 — **파일이 곧 자료다.** 도감 PDF 를 쪽마다 PNG 로
떠 둔 것(`tools/render_atlas_pages.py`)을 읽어 화면에 낸다. 모델도 마이그레이션도
없다.

## 왜 DB 를 안 쓰나

도판 이미지는 **재생성 가능한 것**이다 — 원본 PDF 가 NAS 에 있고 스크립트를
다시 돌리면 그대로 나온다. 재생성 가능한 것에 행을 만들면 그 행과 파일이
어긋나는 상태를 사람이 관리하게 된다. `AtlasEntry`(글자 자료)는 옆 세션이
DB 로 넣는 중이고 **이 모듈은 거기 안 매달린다** — DB 가 비어 있어도 도판은
넘겨 볼 수 있다.

## 쪽 번호가 열쇠다

파일 이름이 **`PDF p.N` 그대로**다(`p0068.png`). 색인 셋이 전부 그 번호로 자리를
짚으므로(`Tafel 26 (Band1 PDF p.68/69)`) 색인에서 화면으로 가는 길이 계산 없이
선다. **번호를 옮겨 적는 자리를 안 만든다** — 옮겨 적으면 어긋난다.

## 목록은 스크립트가 만든 것을 읽는다

`atlas/atlases.json` 은 굽는 스크립트가 낸다. 여기서 폴더를 훑어 세지 않는다 —
**세는 자리가 둘이 되면 갈린다.** 다만 파일이 없으면 훑는 쪽으로 물러난다
(굽는 중이거나 옛 자료일 수 있다).

## 위험한 자리

- **코드에 경로가 못 들어가게 못 박는다.** `[a-z0-9-]` 만 받는다 — 주소에서 온
  값으로 디렉토리를 만들기 때문이다
- **자리가 없어도 죽지 않는다.** `/data3` 가 안 붙은 날에 화면이 500 이 되면
  안 된다 — `outcrop.py` 와 같은 규칙이다
- **확장자를 못 박는다.** 굽다 만 부스러기나 `.json` 을 쪽으로 세지 않는다
"""
import json
import re
from pathlib import Path

from django.conf import settings

# 주소에서 오는 값이라 못 박는다.
CODE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
# 쪽 파일. 굽는 스크립트가 짓는 이름과 같아야 한다.
PAGE = re.compile(r"^p(\d{4,})\.png$")
EXT = ".png"
# 격자 한 판. 카탈로그(`CATALOG_PER_PAGE`)와 같은 성격이다.
PER_PAGE = 60


def _root() -> Path:
    """PNG 가 놓인 자리. **`DATA_ROOT` 아래여야 한다** — `/img` 가 거기만 연다."""
    return Path(settings.DATA_ROOT) / "atlas"


def rel_of(atlas: str, vol: str, page: int) -> str:
    """`/img?p=` 에 실을 상대경로. `DATA_ROOT` 기준이다."""
    return f"atlas/{atlas}/{vol}/p{page:04d}{EXT}"


def _ok(*codes: str) -> bool:
    return all(bool(c) and bool(CODE.match(c)) for c in codes)


def _manifest() -> dict:
    """굽는 스크립트가 낸 목록. 없으면 빈 dict."""
    try:
        return json.loads((_root() / "atlases.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _pages_on_disk(atlas: str, vol: str) -> list[int]:
    """그 권에 실제로 있는 쪽 번호. 번호순."""
    if not _ok(atlas, vol):
        return []
    out = []
    try:
        for f in (_root() / atlas / vol).iterdir():
            m = PAGE.match(f.name)
            if m:
                out.append(int(m.group(1)))
    except OSError:
        return []
    return sorted(out)


def atlases() -> list[dict]:
    """도감 목록. 표지는 그 도감 첫 권의 첫 쪽이다.

    **목록 파일이 없으면 폴더를 훑는다** — 굽는 중이거나 목록을 잃은 자리에서도
    화면이 서야 한다. 그때는 이름을 모르니 코드를 그대로 쓴다.
    """
    mf = _manifest().get("atlases") or {}
    codes = sorted(mf) if mf else sorted(
        p.name for p in _safe_iter(_root()) if p.is_dir() and _ok(p.name))

    out = []
    for code in codes:
        if not _ok(code):
            continue
        entry = mf.get(code) or {}
        vols = entry.get("volumes")
        if not vols:
            vols = [{"code": p.name, "label": p.name}
                    for p in _safe_iter(_root() / code)
                    if p.is_dir() and _ok(p.name)]
        vlist, total, have = [], 0, 0
        for v in vols:
            vcode = v.get("code") or ""
            if not _ok(vcode):
                continue
            on_disk = _pages_on_disk(code, vcode)
            vlist.append({
                "code": vcode,
                "label": v.get("label") or vcode,
                "source": v.get("source") or "",
                # **쪽 수 둘을 갈라 말한다.** 원본이 몇 쪽인지와 우리가 몇 쪽을
                # 떴는지는 다른 값이고, 굽다 만 상태를 화면이 감추면 안 된다.
                "pages": v.get("pages") or len(on_disk),
                "rendered": len(on_disk),
                "first": on_disk[0] if on_disk else None,
            })
            total += v.get("pages") or len(on_disk)
            have += len(on_disk)
        if not vlist:
            continue
        cover = next((v for v in vlist if v["first"]), None)
        out.append({
            "code": code,
            "label": entry.get("label") or code,
            "volumes": vlist,
            "pages": total,
            "rendered": have,
            "partial": have < total,
            "cover_rel": rel_of(code, cover["code"], cover["first"]) if cover else "",
        })
    return out


def _safe_iter(p: Path):
    try:
        return sorted(p.iterdir())
    except OSError:
        return []


def volume(atlas: str, vol: str, offset: int = 0) -> dict | None:
    """권 하나 — 쪽 격자 한 판."""
    if not _ok(atlas, vol):
        return None
    at = next((a for a in atlases() if a["code"] == atlas), None)
    if at is None:
        return None
    v = next((x for x in at["volumes"] if x["code"] == vol), None)
    if v is None:
        return None
    nums = _pages_on_disk(atlas, vol)
    offset = max(0, min(offset, max(0, len(nums) - 1)))
    page_nums = nums[offset:offset + PER_PAGE]
    return {
        "atlas": at, "volume": v, "total": len(nums), "offset": offset,
        "per_page": PER_PAGE,
        "pages": [{"n": n, "rel": rel_of(atlas, vol, n)} for n in page_nums],
        "prev_offset": offset - PER_PAGE if offset > 0 else None,
        "next_offset": (offset + PER_PAGE
                        if offset + PER_PAGE < len(nums) else None),
    }


def page(atlas: str, vol: str, n: int) -> dict | None:
    """쪽 하나 — 앞뒤로 넘길 자리까지.

    **없는 쪽은 `None` 이다.** 색인이 짚어 온 번호가 아직 안 구워졌을 수 있고,
    그때 화면은 "없다" 고 말해야 한다 — 빈 그림을 내면 사람이 원본에 그 쪽이
    없다고 읽는다.
    """
    if not _ok(atlas, vol):
        return None
    nums = _pages_on_disk(atlas, vol)
    if n not in nums:
        return None
    at = next((a for a in atlases() if a["code"] == atlas), None)
    if at is None:
        return None
    v = next((x for x in at["volumes"] if x["code"] == vol), None)
    i = nums.index(n)
    return {
        "atlas": at, "volume": v, "n": n, "rel": rel_of(atlas, vol, n),
        "prev": nums[i - 1] if i > 0 else None,
        "next": nums[i + 1] if i < len(nums) - 1 else None,
        "pos": i + 1, "total": len(nums),
        # 격자로 돌아갈 때 이 쪽이 보이는 자리에서 열리게 한다
        "grid_offset": (i // PER_PAGE) * PER_PAGE,
    }
