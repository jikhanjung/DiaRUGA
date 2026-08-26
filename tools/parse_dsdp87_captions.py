#!/usr/bin/env python3
"""1985 Akiba & Yanagisawa(DSDP Leg 87) 도판 캡션에서 그림 번호 ↔ 종을 뽑는다.

    python tools/parse_dsdp87_captions.py            # 뽑아서 검산하고 낸다
    python tools/parse_dsdp87_captions.py --dry-run  # 아무것도 안 쓰고 수만 센다

## 왜 이 논문만 프로그램으로 뽑나

1936·1992·1993 은 사람이 도판을 눈으로 읽어 `plate_figs.py` 에 손으로
적었다(캡션 79~80줄). **이 논문은 도판이 52장·그림 600개 안팎**이라 손으로
옮기면 옮기다 텔린다. 대신 이 논문은 **텍스트 레이어에 "Explanation of
Plates" 절 전체가 있다** — `Plate N. 1-2. Crucidenticula ikebei …, Sample
JDS-5675 …. 3-4, 6-8. Crucidenticula kanayae …` 처럼 그림 구간과 종을
문장으로 다 적어 놨다. 그래서 정규식으로 뽑는다.

## 부록(APPENDIX)이 검산표다

논문 끝의 "List of Diatoms Treated in This Chapter" 가 **38종**을 못 박고
있다(초록의 "38 species are described" 와 일치 — 직접 세어서 확인했다).
이 도구는 뽑은 이름을 전부 그 38종과 대조한다. **속명 목록(`GENERA`)도
거기서 왔다** — "Enlarged view"·"Oblique view" 처럼 대문자로 시작하는
그림 설명 문구를 종명으로 오인하지 않으려면 "새 종의 시작" 을 아무
대문자 단어가 아니라 **이 11개 속으로만** 인정해야 한다. 안 그러면 그
뒤 그림 전부가 "Enlarged view" 라는 가짜 종을 이어받는다 — 실제로 한 번
그렇게 됐다가 잡았다.

## 도판 하나가 한 종일 수 있다

`Plate 6. Denticula norwegica Schrader, Sample JDS-11171 …. 1. Oblique
external …` 처럼 **번호 없이 종명부터 나오고 그 뒤 숫자는 그림 설명일
뿐인** 도판이 있다. 그 종을 그 도판의 기본값으로 두고, 새 종(위 11개 속
중 하나)이 다시 나오기 전까지는 뒤따르는 숫자를 전부 그 기본값에 붙인다.

## 텍스트 레이어가 흘린 것 다섯

`pdftotext` 가 이탤릭 속명 셋을 다른 글자로 냈다 — 폰트 글리프 매핑
문제라 **PDF 화면은 멀쩡한데 뽑힌 글자만 다르다**(`Crucidenficula` ·
`Denticulòpsis` · `Thαlαssiosirα`, 도판마다 한 번씩). 그리고 원문 자체의
문제가 둘 — 속명·종소명 사이 공백이 조판에서 빠진 것(`Rhizosoleniapraebarboi`)과
종소명 자리에 지명이 온 오식(`Rouxia California` → 부록의 `R. californica`).
전부 `FIXUPS` 에 있다. **일부러 흔한 문자열은 안 썼다** — 도판 하나에만
나오는 자리라 통짜 치환이 안전하다.

## 종의 철자가 부록과 도판에서 다를 수 있다

`Denticulopsis miocenica`(부록 철자)가 도판에는 전부 `miocaenica` 로
나온다(-caen- / -cen- 은 둘 다 쓰이는 라틴어 표기다). **고쳐 쓰지 않는다** —
도판 캡션은 그대로 두고, 검산에서는 부록의 38종에 "안 나온 종 없음" 이
되도록 그 철자 차이를 `ALIASES` 로만 흡수한다.

## 자리

| | |
|---|---|
| 읽는 것 | `papers/1985_akiba_yanagisawa_dsdp87_zonal_markers.pdf` 텍스트 레이어 |
| 반입용 | `tools/data/ak85_captions.json` — `plate_figs.py` 가 그대로 읽는다 |
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402

PDF = DIADICTION / "papers/1985_akiba_yanagisawa_dsdp87_zonal_markers.pdf"
OUT = Path(__file__).resolve().parent / "data/ak85_captions.json"

# 부록 "List of Diatoms Treated in This Chapter" 38종 — 검산 · 속명 판별의 기준
APPENDIX = {
    ("Crucidenticula", "ikebei"), ("Crucidenticula", "kanayae"),
    ("Crucidenticula", "nicobarica"), ("Crucidenticula", "paranicobarica"),
    ("Crucidenticula", "punctata"), ("Denticula", "norwegica"),
    ("Denticulopsis", "dimorpha"), ("Denticulopsis", "hustedtii"),
    ("Denticulopsis", "hyalina"), ("Denticulopsis", "katayamae"),
    ("Denticulopsis", "miocenica"), ("Denticulopsis", "praedimorpha"),
    ("Denticulopsis", "praelauta"), ("Neodenticula", "kamtschatica"),
    ("Neodenticula", "koizumii"), ("Neodenticula", "seminae"),
    ("Neodenticula", "sp"),
    ("Thalassiosira", "brunii"), ("Thalassiosira", "grunowii"),
    ("Thalassiosira", "temperei"), ("Thalassiosira", "yabei"),
    ("Actinocyclus", "ingens"), ("Actinocyclus", "oculatus"),
    ("Kisseleviella", "carina"), ("Kisseleviella", "ezoensis"),
    ("Kisseleviella", "magnaareolata"), ("Nitzschia", "jouseae"),
    ("Nitzschia", "miocenica"), ("Nitzschia", "pliocena"),
    ("Nitzschia", "reinholdii"), ("Rhizosolenia", "barboi"),
    ("Rhizosolenia", "curvirostris"), ("Rhizosolenia", "praebarboi"),
    ("Rouxia", "californica"), ("Thalassionema", "hirosakiensis"),
    ("Thalassionema", "schraderi"), ("Thalassiosira", "antiqua"),
    ("Thalassiosira", "fraga"),
}
assert len(APPENDIX) == 38, "부록은 38종이어야 한다 — 초록의 숫자와 다르면 멈춘다"

GENERA = tuple(sorted({g for g, _ in APPENDIX}))

# 도판 철자 → 부록 철자. **고쳐 쓰지 않는다** — 검산에서만 이 표로 맞춰 본다
ALIASES = {("Denticulopsis", "miocaenica"): ("Denticulopsis", "miocenica")}

# pdftotext 가 이탤릭 속명 셋을 다른 글자로 냈다(폰트 글리프 문제 — PDF 화면은
# 멀쩡하다) + 원문 자체의 공백 누락·오식 둘. 도판 하나에만 나오는 자리라
# 통짜 치환이 안전하다
FIXUPS = [
    ("Crucidenficula", "Crucidenticula"),
    ("Denticulòpsis", "Denticulopsis"),
    ("Thαlαssiosirα", "Thalassiosira"),
    ("Rhizosoleniapraebarboi", "Rhizosolenia praebarboi"),
    ("Rouxia California", "Rouxia californica"),
]

RANGE = re.compile(
    r'(?:(?<=^)|(?<=[.;] ))'
    r'((?:\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)(?:\s*,\s*\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)*)'
    r'\.\s+(?=[A-Z])')
CUTMARK = re.compile(r',?\s+Sample\b')
GS = re.compile(r'^(?:' + '|'.join(GENERA) + r')\.?\s+(?:cf\.\s+)?[a-z][a-z]+')


def dehyphenate(s: str) -> str:
    return re.sub(r'(\w)-\s+(\w)', r'\1\2', s)


def read_text() -> str:
    out = subprocess.run(["pdftotext", "-layout", str(PDF), "-"],
                         capture_output=True, text=True, check=True).stdout
    for bad, good in FIXUPS:
        out = out.replace(bad, good)
    # **"1A-B." 는 두 번째 번호를 생략한 표기다**(20번 나온다 — 흔한 관용
    # 표기이지 오식이 아니다). `RANGE` 는 대시 뒤에도 숫자를 요구하므로
    # 생략된 숫자를 되살려 "1A-1B." 로 만든다 — `expand_range` 가 그 모양을
    # 이미 "한 그림의 부분 라벨" 로 처리한다
    out = re.sub(r'(\d+)([A-Z])-([A-Z])\.', r'\1\2-\1\3.', out)
    # 원문 자체가 마침표를 빠뜨린 자리 — 도판 하나에만 나온다
    out = out.replace("5 Internal view of valve.", "5. Internal view of valve.")
    return out


def split_plates(text: str) -> dict[int, str]:
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if re.match(r'^Plate \d+\.', l)]
    plates = {}
    for k, i in enumerate(starts):
        j = starts[k + 1] if k + 1 < len(starts) else min(i + 40, len(lines))
        chunk = lines[i:j]
        # 다음 도판 시작 전 빈 줄이 두 개 이어지면 그 사이가 캡션의 끝이다
        stop, blanks = len(chunk), 0
        for idx, l in enumerate(chunk):
            if idx == 0:
                continue
            if not l.strip():
                blanks += 1
                if blanks >= 2:
                    stop = idx
                    break
            else:
                blanks = 0
        para = dehyphenate(" ".join(l.strip() for l in chunk[:stop] if l.strip()))
        num = int(re.match(r'^Plate (\d+)\.', para).group(1))
        plates[num] = para
    return plates


def strip_lead(p: str, num: int) -> str:
    p = re.sub(rf'^Plate {num}\.\s*', '', p)
    while True:
        m = re.match(r'^\(([^()]|\([^()]*\))*\)\.?\s*', p)
        if not m:
            break
        p = p[m.end():]
    return p.strip()


def extract_name(seg: str) -> str:
    """종명+저자 인용까지만 자른다. **`Sample` 앞에서 끊는다** — 그 뒤는
    산지·시료 설명이라 이름이 아니다. 그 앞의 `, (10)` 같은 그림별 주석도 뗀다."""
    m = CUTMARK.search(seg)
    name = (seg[:m.start()] if m else seg).strip()
    name = re.sub(r',?\s*\([^()]*\)\s*$', '', name).strip()
    return name.rstrip('.').strip()


def split_segments(body: str) -> list[tuple[str, str]]:
    matches = list(RANGE.finditer(body))
    segs = []
    for idx, m in enumerate(matches):
        seg_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        segs.append((m.group(1), body[m.end():seg_end].strip()))
    return segs


def expand_range(rng: str) -> list[str]:
    figs = []
    for part in rng.split(','):
        m = re.match(r'^(\d+)([A-Za-z]?)(?:-(\d+)([A-Za-z]?))?$', part.strip())
        if not m:
            continue
        a, al, b, bl = m.groups()
        a, b = int(a), int(b) if b else int(a)
        if al and bl and a == b:
            figs += [f"{a}{al}", f"{a}{bl}"]        # "5A-B" — 한 그림의 부분 라벨
        elif al and not b:
            figs.append(f"{a}{al}")
        else:
            figs += [str(n) for n in range(a, b + 1)]
    return figs


def parse() -> tuple[dict, list]:
    plates = split_plates(read_text())
    out, warn = {}, []
    for num, para in plates.items():
        body = strip_lead(para, num)
        matches = list(RANGE.finditer(body))
        lead = body[:matches[0].start()] if matches else body
        # 도판 전체가 한 종일 수 있다(Plate 6 형) — 번호 없이 종명부터 나온다
        prev = extract_name(lead) if GS.match(lead.strip()) else None
        d = {}
        for rng, seg in split_segments(body):
            name = extract_name(seg)
            if name and GS.match(name):
                prev = name
            elif prev is None:
                warn.append((num, rng, seg[:60]))
                continue
            else:
                name = prev
            for f in expand_range(rng):
                d[f] = name
        out[num] = d
    return out, warn


def gs_key(name: str) -> tuple[str, str] | None:
    m = re.match(r'^([A-Za-z]+)\.?\s+(?:cf\.\s+)?([a-z]+)', name)
    if not m:
        return None
    return ALIASES.get(m.groups(), m.groups())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out, warn = parse()
    total = sum(len(d) for d in out.values())
    print(f"도판 {len(out)}개(52 기대) · 그림 {total}개 · 이름 못 뽑은 자리 {len(warn)}")
    for w in warn:
        print("   ", w)

    found = {k for d in out.values() for n in d.values() if (k := gs_key(n))}
    missing = APPENDIX - found
    unknown = found - APPENDIX
    print(f"부록 38종 중 도판에 나온 것 {len(found & APPENDIX)} · "
          f"안 나온 것 {len(missing)} · 부록에 없는 이름 {len(unknown)}")
    if missing:
        print("   안 나온 것:", sorted(missing))
    if unknown:
        print("   부록에 없다(비교종·미기재 가능):", sorted(unknown))
    if warn:
        print("\n**이름 못 뽑은 자리가 있다 — 반입하지 않는다.**")
        return 1

    if args.dry_run:
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n→ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
