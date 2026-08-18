#!/usr/bin/env python3
"""parse_atlas 시험. **NAS 도 DB 도 없이 돈다** — 색인은 합성본으로 세운다.

    python3 tools/test_parse_atlas.py

시험 목록이 곧 **이 파서가 조용히 틀릴 수 있는 자리**다 (P08 의 기준).

1. 〔WoRMS …〕 는 걷고 **〔Tafel 아님 …〕 은 남긴다** — 색인에 `〔…〕` 가 두
   가지라, 아무 `〔…〕` 나 걷으면 색인의 자료가 조용히 사라진다
2. **표제어를 안 고친다** — 원문 오식(`venustun`)도 그대로 든다
3. `sp.` (속까지만 내려간 항목)과 **이름이 상해서 못 읽는 것**을 가른다
4. **빈 것을 안 채운다** — 도판 없는 항목·깊이 빠진 그림
5. **검산이 어긋나면 잡는다** — 실패할 수 없는 시험은 없는 것보다 나쁘다
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_atlas as pa

ok = fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"   ✓ {name}")
    else:
        fail += 1
        print(f"   ✗ {name}: {got!r} != {want!r}")


KOREAN = """# 시험용
수록 범위: **종 번호 169–170 (총 2항목)**

## 속(屬)별 빠른 색인

- **Melosira** (2) — #169, 170

## 종별 상세

### Order DISCALES · Fam. Coscinodiscaceae (체모양원반 과)

**169. *Melosira ambigua (GRUN.) O. F. MÜLLER***    〔WoRMS 20260814 · 미평가〕
<sub>pl. 21 · 책 p.145 · PDF p.46</sub>  
- 생태: 담수산 플랑크톤이다.
- 분포: 함남 안변.

**170. *Melosira distans KÜTZING var. ovata IWAHASHI***
<sub>책 p.370</sub>
"""

SCHMIDT = """# 시험용
**고유 학명 2개 / 출현 기록 3건**

## 속별 종 수

- **Achnanthes** — 1
- **Triceratium** — 1

## 학명 색인 (알파벳순)

### A

- ***Achnanthes lata*** *(속명 추정)* — Tafel 410 fig.15—20 (Band4 PDF p.154/155)  〔WoRMS 20260814 · 원문 렌더 확인: 원문에 학명으로 있다〕
- ***Triceratium venustun*** — Tafel 105 (Band1 PDF p.228/229); Tafel 240 fig.92, 12 (Band2 PDF p.204/205)  〔Tafel 아님 · 권 뒤 Verzeichnis(색인) 쪽에서 왔다〕  〔WoRMS 20260814 · 그대로 유효〕
"""

EAST = """# 시험용
**고유 학명 2개 / 속 2개 / 그림 4개**

## 속별 빠른 색인

- **Asteromphalus** (1) — parvulus
- **Denticulopsis** (1) — sp.

## 학명별 색인 (알파벳순)

***Asteromphalus parvulus*** Karsten  〔WoRMS 20260814 · 그대로 유효〕
<sub>pl. 5 fig.1–2 · PDF p.9/10 · SEM fig.6 · PDF p.19/20</sub>
- pl.5 — 1. sec.1-41, 45.8 cm · 2. sec.4-305, 345.7 cm
- SEM — 6. sec.2-119, 134.3 cm, ×1800, bar 10 μm
- 원문 표기: pl.5 fig.2 는 `parvulu`

***Denticulopsis*** sp.  〔WoRMS 20260814 · 속 수준 동정〕
<sub>pl. 8 fig.12 · PDF p.15/16</sub>
- 12. girdle view; sec.3-177, **깊이 빠짐** (원문 `sec.3-177, cm`)
- 크롭 있음: `plate/x.png`

## Plate 별 원문
"""

SPEC = {s["key"]: s for s in pa.ATLASES}

print("\n1. 한국 — 표제어·자리·본문")
kr, marked = pa.parse_korean(KOREAN)
check("항목 수", len(kr), 2)
check("표시를 걷었다", kr[0]["name"], "Melosira ambigua (GRUN.) O. F. MÜLLER")
check("표시를 세었다", marked, 1)
check("항목번호", kr[0]["item_no"], "169")
check("자리", [kr[0]["placements"][0][k] for k in ("plate", "book_page", "pdf_page")],
      [21, 145, 46])
check("생태", kr[0]["extra"]["ecology"], "담수산 플랑크톤이다.")
check("소속 절", kr[0]["extra"]["section"].startswith("Order DISCALES"), True)
check("이명법", kr[0]["binomial"], "Melosira ambigua")

print("\n2. 한국 — 빈 것을 안 채운다 (도판이 없는 항목)")
check("도판 없음", kr[1]["placements"][0]["plate"], None)
check("PDF 쪽 없음", kr[1]["placements"][0]["pdf_page"], None)
check("책 쪽은 있다", kr[1]["placements"][0]["book_page"], 370)
check("변종", kr[1]["rank"], "infraspecies")
check("변종 표기", kr[1]["infra"], "var. ovata IWAHASHI")

print("\n3. Schmidt — 〔…〕 가 둘이다. 하나만 걷는다")
sc, marked = pa.parse_schmidt(SCHMIDT)
check("항목 수", len(sc), 2)
check("속명 추정", sc[0]["genus_guess"], True)
check("표제어를 안 고쳤다", sc[1]["name"], "Triceratium venustun")
check("자리 둘", len(sc[1]["placements"]), 2)
check("Verzeichnis 주석이 남았다",
      sc[1]["placements"][1]["note"], "Tafel 아님 · 권 뒤 Verzeichnis(색인) 쪽에서 왔다")
check("주석이 든 자리도 값은 원문대로", sc[1]["placements"][1]["plate"], 240)
check("첫 자리에는 주석이 없다", sc[1]["placements"][0]["note"], None)
check("권", sc[1]["placements"][1]["volume"], "Band2")
check("해설면/도판면", [sc[0]["placements"][0]["pdf_page"],
                        sc[0]["placements"][0]["pdf_plate_page"]], [154, 155])
check("그림", sc[0]["placements"][0]["figures"], "15—20")

print("\n4. 동남극 — 자리 여럿·시료·비고")
ea, marked = pa.parse_east(EAST)
check("항목 수", len(ea), 2)
check("저자", ea[0]["authority"], "Karsten")
check("자리 둘", len(ea[0]["placements"]), 2)
check("SEM 자리", ea[0]["placements"][1]["plate_label"], "SEM")
check("시료 셋", len(ea[0]["extra"]["samples"]), 3)
check("깊이", ea[0]["extra"]["samples"][0]["depth_cm"], 45.8)
check("구간", ea[0]["extra"]["samples"][0]["section"], "1-41")
check("배율", ea[0]["extra"]["samples"][2]["magnification"], "1800")
check("원문 표기", ea[0]["extra"]["original_note"], "pl.5 fig.2 는 `parvulu`")

print("\n5. 동남극 — 속까지만 내려간 것과 깊이가 빠진 것")
check("속 수준 동정", ea[1]["rank"], "genus_only")
check("이명법이 없다", ea[1]["binomial"], None)
check("깊이를 안 채웠다", ea[1]["extra"]["samples"][0]["depth_cm"], None)
check("원문은 들고 있다", "깊이 빠짐" in ea[1]["extra"]["samples"][0]["raw"], True)
check("비고", ea[1]["extra"]["notes"], ["크롭 있음: `plate/x.png`"])

print("\n6. 이름이 상한 것은 속 수준 동정과 다르다")
check("키릴 и 가 섞인 종소명",
      pa.name_fields("Synedra cyclopиm BRUTSCHY")["rank"], "unreadable")
check("sp. 는 속 수준", pa.name_fields("Navicula sp.")["rank"], "genus_only")
check("group 도 속 수준", pa.name_fields("Rhizosolenia group")["rank"], "genus_only")

print("\n7. 검산 — 성한 것은 통과한다")
for key, text, entries in (("korean", KOREAN, kr),
                           ("schmidt", SCHMIDT, sc),
                           ("east-antarctic", EAST, ea)):
    spec = dict(SPEC[key])
    spec.pop("stated_override", None)   # 합성본은 머리말의 수가 맞다
    check(f"{spec['short']} 통과", pa.check(spec, text, entries), [])

print("\n8. 검산 — 어긋나면 잡는다 (되살려서 확인한다)")
spec = dict(SPEC["korean"])
check("항목을 빠뜨리면", bool(pa.check(spec, KOREAN, kr[:1])), True)
import copy
b = copy.deepcopy(kr)
b[0]["placements"] = []
check("자리를 빠뜨리면", bool(pa.check(spec, KOREAN, b)), True)
b = copy.deepcopy(kr)
b[0]["genus"] = "Zzz"
check("속을 잘못 읽으면", bool(pa.check(spec, KOREAN, b)), True)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
