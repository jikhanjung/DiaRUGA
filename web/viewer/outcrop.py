"""노두 지점의 현장 사진 — 목록·서빙·올리기·지우기.

**`data.py` 에서 떼어 냈다.** 그쪽은 읽기 전용이라는 약속이 있는데 여기는 NAS
공유에 파일을 쓴다. 한 파일에 섞으면 "이 함수가 쓰는가" 를 매번 확인해야 한다.

## 파일이 곧 자료다

사진은 NAS 공유(`settings.OUTCROP_DIR`)에 **파일로만** 산다. DB 에 행이 없다 —
이름이 `<지점코드> (n).jpg` 인 것이 지점과 사진을 잇는 유일한 근거다. 그래서:

- 사람이 탐색기로 직접 올려도 화면에 나타난다 (`N:\\DiaRUGA\\outcrop`)
- 새 노두 지점을 만들고 사진만 두면 저절로 붙는다
- 지점 코드를 바꾸면 사진이 떨어진다 — **그것이 이 방식의 값이다**(간단하다)
  는 것과 맞바꾼 대가다. 코드를 바꾸는 일이 드물어 지금은 그대로 둔다

## 왜 세 장인가

용량 관리다 (사용자 방침 2026-08-06). 원본이 장당 12 MB 짜리 5568x3712 로
올라오는데 NAS 공유는 여럿이 함께 쓰는 자리다. 그래서 **올릴 때 줄인다** —
긴 변 2400px · q85 면 1 MB 아래로 떨어지고 화면에서 확대해 보기에 넉넉하다
(실측 8%). 세 장이면 지점 하나에 3 MB 다.

## 위험한 자리

- **클라이언트가 준 파일 이름을 안 쓴다.** 이름은 우리가 짓는다
  (`<코드> (n).jpg`) — 경로 탈출이 애초에 불가능해진다
- **주소에도 이름이 없다.** 서빙·삭제는 `(지점, 순번)` 으로만 짚는다
- **`.part` 로 쓰고 검증한 뒤 제자리로 옮긴다.** 반쯤 쓴 파일이 제 이름을 달면
  화면이 깨진 그림을 낸다 (`backup_db.py` 와 같은 규칙)
- **NAS 가 없어도 죽지 않는다.** 읽기는 `OSError` 를 삼키고 빈 목록을 낸다 —
  공유가 안 붙은 날에 지점 페이지가 500 이 되면 안 된다
"""
import re
from pathlib import Path

from django.conf import settings

# 화면에서 받는 것. **못 박는다** — 그 폴더에는 윈도우가 남기는
# `…:Zone.Identifier` 같은 부스러기가 섞여 있고, 그것을 이미지로 열려 들면 매
# 요청마다 예외가 난다.
EXT = (".jpg", ".jpeg", ".png")
# 지점 하나에 몇 장까지. 용량 관리 (사용자 방침 2026-08-06).
MAX_PHOTOS = 3
# 올릴 때 줄이는 크기. `shrink_outcrop.py` 와 같은 값이어야 한다 — 갈라지면
# 사람이 직접 올린 것과 화면으로 올린 것의 크기가 달라진다.
MAX_SIDE = 2400
QUALITY = 85


def _root() -> Path:
    return Path(settings.OUTCROP_DIR)


def _entries(code: str):
    """`(번호, 파일)` 목록. 번호순. 못 읽으면 빈 목록."""
    code = (code or "").lower()
    if not code:
        return []
    found = []
    try:
        for f in _root().iterdir():
            if f.suffix.lower() not in EXT or not f.is_file():
                continue
            stem = f.stem.lower()
            if stem == code:
                found.append((0, f))
                continue
            m = re.fullmatch(rf"{re.escape(code)}\s*\((\d+)\)", stem)
            if m:
                found.append((int(m.group(1)), f))
    except OSError:
        return []
    found.sort(key=lambda t: (t[0], t[1].name))
    return found


def photos(loc) -> list[dict]:
    """노두 지점의 현장 사진. 시추코어 지점에는 안 붙인다 — 그 자리는 암상 띠다."""
    if getattr(loc, "kind", None) != "outcrop":
        return []
    out = []
    for i, (no, f) in enumerate(_entries(loc.code)):
        try:
            mb = round(f.stat().st_size / 1e6, 2)
        except OSError:
            continue
        out.append({"i": i, "no": no, "name": f.name, "mb": mb})
    return out


def photo_path(loc, index: int) -> Path | None:
    """`(지점, 순번)` → 실제 파일. **순번으로만 짚는 것이 요점이다.**

    파일 이름을 URL 로 받으면 `../` 를 막을 일이 생기는데, 여기서는 목록을 서버가
    만들고 그중 하나를 고를 뿐이라 바깥을 가리킬 방법이 없다.
    """
    items = photos(loc)
    if not (0 <= index < len(items)):
        return None
    p = _root() / items[index]["name"]
    return p if p.is_file() else None


def free_slot(code: str) -> int | None:
    """다음에 쓸 번호. 꽉 찼으면 `None`.

    **빈 자리를 메운다.** 2번을 지우고 새로 올리면 2번이 된다 — 늘 뒤에 붙이면
    3장 제한 안에서 자리가 남았는데도 못 올리게 된다.
    """
    used = {no for no, _ in _entries(code)}
    if len(used) >= MAX_PHOTOS:
        return None
    for n in range(1, MAX_PHOTOS + 1):
        if n not in used:
            return n
    return None


def save_upload(loc, fileobj) -> tuple[bool, str]:
    """올라온 파일 하나를 그 지점의 사진으로 저장한다. 줄여서 JPEG 으로.

    **이름은 우리가 짓는다.** 클라이언트가 준 이름은 확장자조차 안 쓴다 —
    경로 탈출도, 이상한 확장자도 애초에 들어올 수 없다.
    """
    from PIL import Image, UnidentifiedImageError

    if getattr(loc, "kind", None) != "outcrop":
        return False, "노두 지점에만 사진을 올릴 수 있습니다."
    slot = free_slot(loc.code)
    if slot is None:
        return False, (f"사진은 지점마다 {MAX_PHOTOS}장까지입니다 — "
                       f"먼저 하나를 지우세요.")

    try:
        with Image.open(fileobj) as im:
            im.load()                    # 여기서 깨진 파일이 걸린다
            w, h = im.size
            im = im.convert("RGB")
            if max(w, h) > MAX_SIDE:
                s = MAX_SIDE / max(w, h)
                im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
            out = im
    except (UnidentifiedImageError, OSError, ValueError):
        return False, "이미지로 읽지 못했습니다 (JPEG·PNG 만 받습니다)."

    root = _root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        dst = root / f"{loc.code} ({slot}).jpg"
        tmp = dst.with_suffix(".jpg.part")
        out.save(tmp, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        # 검증하고 나서 제 이름을 준다 — 반쯤 쓴 파일이 화면에 걸리면 안 된다
        with Image.open(tmp) as chk:
            chk.verify()
        tmp.replace(dst)
    except OSError as e:
        return False, f"저장하지 못했습니다: {e}"
    mb = dst.stat().st_size / 1e6
    return True, f"{dst.name} 을(를) 올렸습니다 ({mb:.2f} MB)."


def delete_photo(loc, index: int) -> tuple[bool, str]:
    """사진 하나를 지운다. **되돌릴 수 없다** — 화면이 먼저 묻는다."""
    p = photo_path(loc, index)
    if p is None:
        return False, "사진을 찾지 못했습니다."
    name = p.name
    try:
        p.unlink()
    except OSError as e:
        return False, f"지우지 못했습니다: {e}"
    return True, f"{name} 을(를) 지웠습니다."
