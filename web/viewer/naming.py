"""폴더 이름에서 층을 읽는 규칙 — **여기 하나뿐이다.**

예전에는 `group_focus_series.py` 와 `import_json.py` 에 같은 정규식이 두 벌
있었다(그쪽이 cv2 를 끌고 와서 뷰어가 임포트할 수 없었기 때문이다). 이 모듈은
Django 도 cv2 도 안 부르는 순수 문자열 규칙이라 **뷰어·파이프라인·마이그레이션이
전부 같은 것을 본다.** 규칙이 갈라지면 같은 폴더가 두 자리에 다르게 앉는다.

## 층

    권역   한국 · 남극                       Site.area
     └ 지역   BP(북평분지) · RS23            Site
        └ 지점   BP09(노두) · GC03(시추코어)  Locality
           └ 시료   0901 · 71cm              Sample
              └ 관찰   (1) · (2)             Slide

## 두 체계의 폴더 규칙이 다르다

    남극   RS23-GC03 71cm    <지역>-<지점> <깊이>cm    지역이 폴더에 있다
    육상   BP09-0901         <지점>-<시료>            지역이 폴더에 없다

**가르는 표시는 `cm` 이 있느냐다.** 있으면 앞 토막이 지역, 없으면 앞 토막이
지점이다.

**육상의 지역은 지점 코드에서 숫자를 떼어 얻는다** (`BP09` → `BP`). 노두 코드가
`<지역문자><번호>` 꼴이라는 전제이고, 어긋나면 없는 지역이 만들어진다 — 그래서
관리 화면에서 사람이 고칠 수 있어야 한다. 비워 두는 쪽이 더 나쁘다: 지역이 없는
슬라이드는 어느 권역 탭에도 안 나와 화면에서 사라진다(실제로 `BP09-0901 (1)` 이
그랬다).

**시료 번호는 되풀이되는 자리를 떼서 얻는다.** `BP09-0901` 에서 지점 `BP09` 의
숫자 `09` 를 앞에서 떼면 `01` 이 남고 그것이 그 노두의 첫 시료다.
"""
import re

# 남극 규칙. `re.match` 라 뒤에 관찰 접미사가 붙어도 앞쪽을 그대로 뽑는다.
SAMPLE_NAME = re.compile(
    r"^(?P<site>[A-Za-z0-9]+)-(?P<loc>[A-Za-z0-9]+)\s+(?P<depth>[\d.]+)\s*cm",
    re.IGNORECASE)

# 육상 규칙. `<지점>-<시료>` 이고 둘 다 숫자를 품는다.
OUTCROP_NAME = re.compile(r"^(?P<loc>[A-Za-z]+\d+)\s*-\s*(?P<sample>\d+)")

# 관찰 접미사 — 시료 하나를 처리 방법이나 회차를 달리해 여러 번 관찰한 것.
# **폴더에는 숫자만 받는다** (사용자 방침 2026-08-05). 글자를 받으면 슬러그가
# 뭉개져 서로 다른 관찰이 같은 슬러그로 부딪히고, `update_or_create(slug=…)` 라
# 한쪽이 다른 쪽을 덮어쓴다. 뜻은 사람이 `obs_label` 에 적는다.
OBS_SUFFIX = re.compile(r"\s*\((\d+)\)\s*$")


def parse_obs_no(folder: str) -> int:
    """폴더명 끝의 `(1)`·`(2)` 를 읽는다. 없으면 `0`.

    **`0` 을 저장하고 화면에서만 감춘다.** 비워 두면 "아직 안 읽은 것" 과
    "접미사가 없던 것" 이 구별되지 않는다.
    """
    m = OBS_SUFFIX.search(folder or "")
    return int(m.group(1)) if m else 0


def base_name(folder: str) -> str:
    """관찰 접미사를 뗀 이름 — 같은 시료의 관찰들이 공유하는 것이다.

    **슬러그가 아니라 폴더 이름으로 짚는다.** 슬러그에는 촬영일이 붙어
    (`slide_slug`) 같은 시료를 다른 날 올린 관찰끼리 안 맞는다.
    """
    return OBS_SUFFIX.sub("", folder or "").strip()


def sample_no_from(loc_code: str, sample_code: str) -> int | None:
    """노두 시료 코드에서 단면상의 위치를 뽑는다. `BP09` + `0901` → `1`.

    지점 코드의 숫자(`09`)가 시료 코드 앞에 되풀이되므로 그것을 떼면 남는 것이
    그 노두에서 몇 번째로 딴 시료인가다. 되풀이가 없으면(규칙을 벗어난 이름)
    시료 코드 전체를 숫자로 읽는다 — 정렬은 되어야 한다.
    """
    if not sample_code or not sample_code.isdigit():
        return None
    head = "".join(c for c in (loc_code or "") if c.isdigit())
    rest = (sample_code[len(head):]
            if head and sample_code.startswith(head) else sample_code)
    return int(rest) if rest.isdigit() and rest else int(sample_code)


def parse_folder(folder: str) -> dict:
    """폴더 이름 하나를 층으로 가른다.

    돌려주는 것(모르는 자리는 `None`):

        site_code · loc_code · loc_kind · sample_code · depth_cm · sample_no · obs_no

    아무 규칙에도 안 맞으면 `site_code`·`loc_code` 가 `None` 이다. **그때는
    부르는 쪽이 아무것도 쓰지 않는다** — 사람이 채운 것을 자동값이 지우면 안 된다
    (`group_focus_series.sample_fields`).
    """
    folder = folder or ""
    base = base_name(folder)
    out = {"site_code": None, "loc_code": None, "loc_kind": None,
           "sample_code": None, "depth_cm": None, "sample_no": None,
           "obs_no": parse_obs_no(folder)}

    m = SAMPLE_NAME.match(base)
    if m:
        d = m.group("depth")
        out.update(site_code=m.group("site").upper(),
                   loc_code=m.group("loc").upper(),
                   loc_kind="core",
                   # 화면에 그대로 쓰는 시료 이름. `71.0cm` 이 아니라 `71cm` 다
                   sample_code=f"{float(d):g}cm" if d else None,
                   depth_cm=float(d) if d else None)
        return out

    m = OUTCROP_NAME.match(base)
    if m:
        loc = m.group("loc").upper()
        sample = m.group("sample")
        out.update(site_code=re.sub(r"\d+$", "", loc) or loc,
                   loc_code=loc,
                   loc_kind="outcrop",
                   sample_code=sample,
                   sample_no=sample_no_from(loc, sample))
        return out

    return out
