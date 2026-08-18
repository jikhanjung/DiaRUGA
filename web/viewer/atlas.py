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


def vol_code(volume: str | None) -> str:
    """색인이 적은 권 표기를 **경로용 코드**로 (129).

        "Band4" → "band4"       None · "" → "main"

    **이 변환은 여기 하나뿐이다.** 색인 자료(`AtlasPlacement.volume`)는
    원문 표기(`Band4`)를 그대로 들고 있어야 한다 — 인용에 쓰이는 값이라
    화면의 경로 규칙을 알 이유가 없다(옆 세션과 합의, 2026-08-18). 그러면
    맞추는 일이 화면 몫이 되는데, **세 화면과 링크 만드는 자리가 각자
    `.lower()` 하면 넷째 도감에서 갈린다.** `naming.py` 가 폴더 이름 규칙을
    한 자리로 모은 것과 같은 이유다.
    """
    v = (volume or "").strip().lower()
    return v or "main"


def page_url(atlas: str, volume: str | None, pdf_page) -> str:
    """색인 항목 하나가 짚는 쪽으로 가는 주소. 못 만들면 빈 문자열.

    **여기서 파일이 있는지 안 본다.** 링크 하나마다 디스크를 짚으면 검색 결과
    한 판에 수백 번이 된다(105 의 "카드마다 되묻기"). 안 구운 쪽이면 그 화면이
    **404 로 정직하게 말한다** — 빈 그림을 내지 않는다. 링크를 흐리게 할 자리는
    `has_page()` 로 따로 묻는다.
    """
    from django.urls import reverse

    try:
        n = int(pdf_page)
    except (TypeError, ValueError):
        return ""
    vol = vol_code(volume)
    if n < 1 or not _ok(atlas, vol):
        return ""
    return reverse("atlas_page", args=[atlas, vol, n])


def has_page(atlas: str, volume: str | None, pdf_page) -> bool:
    """그 쪽이 실제로 떠 있는가. **디스크를 짚는다** — 자주 부르지 말 것."""
    try:
        n = int(pdf_page)
    except (TypeError, ValueError):
        return False
    return n in _pages_on_disk(atlas, vol_code(volume))


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


def left_parity(atlas_code: str) -> str:
    """펼침에서 **왼쪽에 놓이는 쪽 번호의 홀짝**. `"even"` 또는 `"odd"`.

    도감마다 다르다 — 굽는 스크립트의 `LEFT_PARITY` 가 원본이고 목록 파일에
    실려 온다. 자료로 갈랐다(131): Schmidt 는 도판면(홀수)의 Tafel 번호가
    **우상단**이라 홀수가 오른쪽이고, 한국·동남극은 색인의 `책 p.` ↔ `PDF p.`
    대응이 그 반대를 말한다.

    **모르면 `"odd"` 로 본다** — 첫 쪽이 표지로 혼자 오른쪽에 서는 흔한 모양이
    아니라, 1·2 가 나란히 서는 쪽이다. 다만 굽는 스크립트가 표에 없는 도감을
    아예 거절하므로 여기까지 오는 일은 목록이 낡았을 때뿐이다.
    """
    at = (_manifest().get("atlases") or {}).get(atlas_code) or {}
    return "even" if at.get("left_parity") == "even" else "odd"


def spread(atlas: str, vol: str, n: int) -> dict | None:
    """`n` 이 든 펼침 하나 — 원래 책처럼 두 쪽 (131).

    **번호가 바깥 모서리로 간다.** 왼쪽 쪽 번호는 좌상단, 오른쪽은 우상단이다
    (사용자 2026-08-18) — 책이 그렇게 찍혀 있고, 화면의 표시가 그것과 어긋나면
    어느 쪽을 보고 있는지 매번 되짚게 된다.

    **한쪽이 없을 수 있다.** 첫 쪽이 표지로 혼자 서거나(짝수-왼쪽 도감의 p.1)
    마지막 쪽이 짝을 못 만나는 자리다. 그때는 있는 쪽만 낸다 — 없는 자리에 빈
    칸을 그리면 사람이 **안 구운 쪽**으로 읽는다.
    """
    if not _ok(atlas, vol):
        return None
    nums = _pages_on_disk(atlas, vol)
    if not nums or n not in nums:
        return None

    want_even = left_parity(atlas) == "even"
    left = n if ((n % 2 == 0) == want_even) else n - 1
    right = left + 1
    lo, hi = nums[0], nums[-1]

    def side(num, where):
        if num < lo or num > hi or num not in nums:
            return None
        return {"n": num, "rel": rel_of(atlas, vol, num), "side": where}

    l, r = side(left, "left"), side(right, "right")
    if l is None and r is None:
        return None

    at = next((a for a in atlases() if a["code"] == atlas), None)
    v = next((x for x in (at or {}).get("volumes", []) if x["code"] == vol), None)
    first = (l or r)["n"]
    last = (r or l)["n"]
    # 앞뒤로 **펼침 단위**로 옮긴다. 한 쪽씩 가면 같은 펼침을 두 번 본다.
    prev_n = first - 1 if first - 1 >= lo else None
    next_n = last + 1 if last + 1 <= hi else None
    return {
        "atlas": at, "volume": v, "left": l, "right": r, "n": n,
        "prev": prev_n, "next": next_n,
        "pos": nums.index(first) + 1, "total": len(nums),
        "grid_offset": (nums.index(first) // PER_PAGE) * PER_PAGE,
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
