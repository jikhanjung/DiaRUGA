#!/usr/bin/env python3
"""도감의 분포 줄에서 **출현 기록**을 뽑는다 — 종 × 지역 × 문헌 (P20 1단계).

    python tools/parse_occurrence.py            # 뽑아서 md·json 을 낸다
    python tools/parse_occurrence.py --dry-run  # 아무것도 안 쓰고 수만 센다

## 왜 도감에서 시작하나

**논문을 넣으려고 만드는 층인데 첫 자료는 도감이다.** 한국 도감은 항목마다
`분포 : 경기도 행주(정 영호 외, 1965), 서해(이 민재 외, 1967) 등지에서
채집되었다.` 를 달고 있고, 이것이 **이미 종 × 지역 × 문헌**이다. 논문이
들어오면 `Reference` 가 하나 더 붙는 것이지 구조가 달라지지 않는다 —
층의 모양을 도감으로 먼저 확인하고 논문을 그 위에 얹는다.

## 자리

| | |
|---|---|
| 읽는 것 | `origin/korean_flora_diatom.pdf` 의 **텍스트 레이어** (`pdftotext -layout`) |
| 사람이 보는 원본 | `md/korean_flora_diatom_occurrence.md` (Diadiction) |
| 반입용 | `atlas/occurrence/korean.json` (저장소 — 이미지에 실려 간다) |

**색인 md 가 아니라 PDF 본문을 읽는다.** 분포는 색인에 없다(색인은 표제어와
도판 자리만 든다). 그래서 이 도구만 원본이 PDF 다.

## 덮이는 범위가 절반이다 — 그것을 수로 말한다

**텍스트 레이어는 PDF 46–190 쪽(항목 169–480)에만 있다.** 147 이 도판 캡션에서
찾은 것과 같은 경계다. 나머지 200 항목(#481–680)은 쪽을 렌더해 읽어야 하고
**이 도구는 그것을 안 한다.** 안 덮은 것을 덮은 것처럼 보이게 하지 않으려고
`--dry-run` 이 매번 범위를 함께 찍는다.

## 걸린 함정 넷 (전부 실제로 당했다)

1. **빈 줄에서 끊으면 안 된다.** OCR 이 분포 문장 한가운데에 빈 줄을 넣는다.
   문장의 끝은 `채집되었다` 다
2. **쪽 머리·꼬리가 문장 한가운데로 들어온다.** 분포가 쪽을 넘으면
   `경기도 청 황색편모조식물 문 259 평 저수지` 가 된다 — 걷지 않으면 그것이
   지역 이름이 된다
3. **도판 목록 쪽을 통째로 삼킬 수 있다.** 걷어도 남는 자리가 있어서
   **길이로 막고 실패로 센다**(`CAP`) — 조용히 지나가면 쓰레기가 기록이 된다
4. **생태 문장이 분포 줄로 흘러든다** (`분포 : 각 해양에 분포한다. 대한해협 …`).
   첫 괄호 앞의 마침표까지 버린다

## 이름은 원문 그대로 들고, 맞추는 값을 따로 둔다

`AtlasEntry` 와 같은 규칙이다 — `region_raw`·`ref_raw` 는 OCR 이 낸 그대로이고
`region`·`ref` 가 맞추는 값이다. **정규화가 모르는 것은 조용히 통과시키지 않고
멈춘다** — 새 지역·새 문헌이 나오면 사람이 표에 적어야 한다.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402

PDF = DIADICTION / "origin/korean_flora_diatom.pdf"
INDEX = Path(__file__).resolve().parent.parent / "atlas/korean.json"
OUT_MD = DIADICTION / "md/korean_flora_diatom_occurrence.md"
# **`atlas/*.json` 옆에 두면 안 된다** — `ops/import_atlas.py` 가 그 디렉토리를
# `glob("*.json")` 으로 훑으며 **모든 파일에 `atlas` 키가 있다고 믿는다.**
# 나란히 뒀다가 반입 시험이 `KeyError: 'atlas'` 로 깨졌다. 출현 기록은 색인이
# 아니므로 한 단 아래로 내린다 — 논문 것이 늘어도 같은 자리에 안 걸린다
OUT_JSON = Path(__file__).resolve().parent.parent / "atlas/occurrence/korean.json"

# 텍스트 레이어가 있는 범위. **147 이 도판 캡션에서 찾은 경계와 같다**
TEXT_LAYER = (1, 190)
CAP = 250          # 분포 문장이 이보다 길면 쪽을 삼킨 것이다

# --- 쪽 머리·꼬리 (자료가 아니다) -------------------------------------------
FURNITURE = [
    re.compile(r'^\s*\d*\s*황색편\s*모조?\s*식물\s*문\s*\d*\s*$'),
    re.compile(r'^\s*\d*\s*황색편모조식물\s*문\s*\d*\s*$'),
    re.compile(r'^\s*\d*\s*한국\s*동\s*식\s*물\s*도\s*감.*$'),
    re.compile(r'^\s*Plate\s+\d+\s*$'),
]

HEAD = re.compile(r'^\s*(\d{2,3})\.\s*p[l!][.,]?\s*(\d+)\s+(.*)$')
DIST = re.compile(r'[분문][포토]\s*[:：]')
END = re.compile(r'채\s*집\s*되\s*었\s*다|採集')
CITE = re.compile(r'\(([^()]*?)\)')

# --- 지역 ---------------------------------------------------------------------
#
# **열쇠는 공백을 걷은 것이다** — OCR 이 낱말 한가운데에 공백을 넣는다
# (`남 해안`·`강원 도 춘천 저수지`). 그리고 **도감이 한 줄 안에서 앞가지를
# 생략한다**(`경기도 청평 저수지, 양수리, 기두원`) — 그 셋을 여기서 되살린다.
REGION = {
    "대한해협": "대한해협", "서해": "서해", "남해": "남해",
    "동해안": "동해안", "남해안": "남해안", "서해안": "서해안",
    "난해안": "남해안",                      # OCR
    "대마도연안": "대마도 연안",
    "경기도행주": "경기도 행주", "우리나라에서는경기도행주": "경기도 행주",
    "경기도서호": "경기도 서호",
    "경기도팔당": "경기도 팔당", "팔당": "경기도 팔당",
    "경기도청평저수지": "경기도 청평 저수지", "청평저수지": "경기도 청평 저수지",
    "경기도청평": "경기도 청평 저수지", "경기도청평저수": "경기도 청평 저수지",
    "경기도양수리": "경기도 양수리", "양수리": "경기도 양수리",
    "경기도기두원": "경기도 기두원", "기두원": "경기도 기두원",
    "서울노량진": "서울 노량진", "서을노량진": "서울 노량진",   # OCR
    "서울청량리": "서울 청량리",
    "서울광장": "서울 광장", "광장": "서울 광장",
    "강원도춘천저수지": "강원도 춘천 저수지", "춘천저수지": "강원도 춘천 저수지",
    "강원도춘천": "강원도 춘천 저수지", "강원도천춘저수지": "강원도 춘천 저수지",
    "강원도소양강": "강원도 소양강", "소양강": "강원도 소양강",
    "강원도소양": "강원도 소양강", "소양": "강원도 소양강",
    "강원도신연": "강원도 신연", "신연": "강원도 신연",
    "충남대야도": "충남 대야도",
    "경남다대포": "경남 다대포", "경북다대포": "경남 다대포",   # OCR
    "경남밀양강": "경남 밀양강",
    "전남보성강": "전남 보성강", "전남섬진강": "전남 섬진강",
    "평남청천강": "평남 청천강", "청천강": "평남 청천강",
    "함남안변": "함남 안변", "함북청진": "함북 청진", "함북나남": "함북 나남",
    "오십천": "강원도 오십천",
    "부산": "부산",
    # **원문 그대로 둔다** — 어디인지 확정 못 했다(#399 의 하천 목록 안이다)
    "전두계": "전두계",
    # 도감이 한 번 `경북 다대포` 로 찍었다(#262) — 다대포는 경남이다
    "경북다대포": "경남 다대포",
}

# --- 문헌 ---------------------------------------------------------------------
#
# **저자 열이고 (저자, 연도) 열다섯이다.** 한자 이름 넷은 OCR 이 거의 못 읽어
# 쪽을 떠서 눈으로 확인했다(아래 `RENDERED` 와 같은 자리):
#
# | 원문 | OCR 이 낸 것 | 확인한 쪽 |
# |---|---|---|
# | `殖田三郎 외, 1935` | `三 외`·`로`·`國` | PDF p.159 (#399) |
# | `羽田良禾, 1936` | `日` | PDF p.139 (#356) |
# | `倉茂英次郎, 1943` | `英`·`校英X`·`法 水`·`白英`·`族 文` | PDF p.64 (#212) |
# | `奧野春雄, 1948` | `東野春`·`東野`·`無野進` | PDF p.159·139 |
#
# **연도만으로 맞추면 안 된다 — 1936 이 둘이다**(`Skvortzow` 와 `羽田良禾`).
# 한 번 그렇게 짤 뻔했고, 그러면 열세 번째 문헌이 조용히 사라진다.
REF = {
    "최상": "최 상", "최 상": "최 상",
    "정영호외": "정 영호 외", "정영호": "정 영호 외", "정영호의": "정 영호 외",
    "정영호와": "정 영호 외", "정·영호외": "정 영호 외",
    "이민재외": "이 민재 외", "이민재": "이 민재 외",
    "이재민외": "이 민재 외",   # **원문 오식이다**(#330 에 그렇게 찍혀 있다)
    "야민재외": "이 민재 외",   # OCR
    "엄규백외": "엄 규백 외", "엄규백": "엄 규백 외",
    "박태수": "박 태수",
    "skvortzow": "Skvortzow", "skvrotzow": "Skvortzow",  # 뒤엣것은 OCR 뒤집힘
    "정호영외": "정 영호 외",                              # OCR 뒤집힘
    "殖田三郎외": "殖田三郎 외", "羽田良禾": "羽田良禾",
    "倉茂英次郎": "倉茂英次郎", "奧野春雄": "奧野春雄",
}

# **있을 수 있는 (저자, 연도) 열다섯.** 여기 없는 조합이 나오면 멈춘다 —
# 연도가 한 자만 어긋나도 **없는 문헌이 조용히 하나 생긴다**(실제로 둘 났다).
KNOWN = {
    ("Skvortzow", "1929"), ("Skvortzow", "1931"), ("Skvortzow", "1932"),
    ("Skvortzow", "1936"), ("羽田良禾", "1936"), ("殖田三郎 외", "1935"),
    ("倉茂英次郎", "1943"), ("奧野春雄", "1948"), ("박 태수", "1956"),
    ("최 상", "1966"), ("최 상", "1967"), ("정 영호 외", "1965"),
    ("정 영호 외", "1967"), ("이 민재 외", "1967"), ("엄 규백 외", "1967"),
}

# **원문 오식이라고 쪽을 떠서 확인한 연도.** 고쳐 쓰는 것이 아니라
# `ref_raw` 는 그대로 두고 맞추는 값만 옮긴다 — 그 저자의 문헌이 하나뿐이라
# 안전한 자리에서만 한다
YEAR_TYPO = {("박 태수", "1965"): "1956"}   # #267 (PDF p.90) — 1956 의 뒤집힘

# **못 고치는 오식도 있다.** #293(PDF p.107)은 원문이 `SKVORTZOW, 1967` 이다.
# Skvortzow 의 한국 보고는 1929·31·32·36 넷이라 어느 것인지 원문으로는
# 못 가른다 — **짐작하지 않고 실패로 센다.**

# 한자 이름이 OCR 로 뭉개진 자리. **연도가 그 해에 하나뿐일 때만 쓴다** —
# 1936 은 둘이라 여기 없고, 못 읽으면 실패로 센다
HANJA_YEAR = {"1935": "殖田三郎 외", "1943": "倉茂英次郎", "1948": "奧野春雄"}


# --- 텍스트 레이어가 흘린 분포 문장 -------------------------------------------
#
# **쪽을 떠서 눈으로 읽은 것이다.** 텍스트 레이어가 문장을 통째로 잃거나
# (p.64), 낱말 순서를 뒤섞거나(p.66), 도판 목록 쪽을 삼킨(p.139) 자리다.
# `render_verify.py` 의 `VERIFIED` 와 같은 성격이라 **도구가 다시 계산하지
# 않고 값을 그대로 든다.**
RENDERED = {
    212: ("우리 나라에서는 부산, 남해안(SKVORTZOW, 1931), 충남 대야도, "
          "경남 다대포(倉茂英次郎, 1943), 경기도 행주(정 영호 외, 1965), "
          "대한해협(최 상, 1966; 엄 규백 외, 1967), 서해(이 민재 외, 1967), "
          "동해안, 남해안, 서해안(최 상, 1967)"),
    217: ("경기도 행주(정 영호 외, 1965), 서해(이 민재 외, 1967), "
          "동해안, 남해안, 서해안(최 상, 1967)"),
    # **원문이 저자를 빠뜨렸다** — `남해안(1967)` 이라고만 찍혀 있다.
    # 그 한 자리는 문헌을 못 달고 넘어간다(뒤의 `bad_ref` 에 걸린다)
    262: ("충남 대야도, 경북 다대포(倉茂英次郎, 1943), 대한해협(최 상, 1966), "
          "남해안(1967)"),
    # **원문이 여는 괄호를 빠뜨렸다** — `서해, SKVORTZOW, 1932) 서해` 다.
    # 뜻은 `서해(SKVORTZOW, 1932)` 이므로 그렇게 적고 근거를 여기 남긴다
    330: ("대한해협(SKVORTZOW, 1931; 엄 규백 외, 1967), 서해(SKVORTZOW, 1932), "
          "서해, 남해(이 재민 외, 1967), 동해안, 남해안, 서해안(최 상, 1967)"),
    356: ("서울 청량리(SKVORTZOW, 1929), 경기도 서호(SKVORTZOW, 1929; 羽田良禾, 1936), "
          "함남 안변(SKVORTZOW, 1936), 강원도 춘천 저수지, 신연, "
          "경기도 청평 저수지, 양수리, 기두원(정 영호 외, 1967)"),
}


def squash(s: str) -> str:
    return re.sub(r'\s', '', s)


def norm_region(raw: str) -> str | None:
    r = squash(raw)
    r = re.sub(r'^\d+\)', '', r)          # `1965)` 부스러기
    r = re.sub(r'^우리나라에서는', '', r)   # 문장 머리가 지역에 붙는다
    r = re.sub(r'\(.*$', '', r)           # 열린 괄호 뒤는 다음 문헌이다
    return REGION.get(r)


def norm_ref(raw: str) -> tuple[str, str] | None:
    """`(저자, 연도)` 로 가른다. **연도가 없으면 문헌이 아니다.**"""
    m = re.search(r'(1[89]\d\d)', raw)
    if not m:
        return None
    year = m.group(1)
    who = re.sub(r'[,.·]', '', squash(raw[:m.start()]))
    key = REF.get(who.lower()) or REF.get(who)
    if key:
        return key, year
    # 한자 이름이 뭉개진 자리. **그 해에 문헌이 하나뿐일 때만** 편다 —
    # OCR 이 다섯 자를 통째로 잃어 저자 자리가 비기도 한다(`, 1943`)
    if year in HANJA_YEAR:
        return HANJA_YEAR[year], year
    return None                           # `남해안(1967)` — 원문이 저자를 빠뜨렸다


def check_pair(ref: str, year: str) -> tuple[str, str, str] | None:
    """**있을 수 있는 조합인가.** 아니면 None — 부르는 쪽이 실패로 센다."""
    if (ref, year) in KNOWN:
        return ref, year, ""
    fixed = YEAR_TYPO.get((ref, year))
    if fixed:
        return ref, fixed, f"원문 오식 — {year} 로 찍혀 있다"
    return None


def read_text() -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(PDF), "-"],
                         capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines()
            if not any(f.match(ln) for f in FURNITURE)]


def sentence(body: list[str]) -> str:
    buf, grab = [], False
    for ln in body:
        if not grab:
            m = DIST.search(ln)
            if m:
                grab = True
                buf.append(ln[m.end():])
                if END.search(ln):
                    break
            continue
        if HEAD.match(ln) or "생태" in ln:
            break
        buf.append(ln)
        if END.search(ln):
            break
    s = re.sub(r'\s+', ' ', ' '.join(buf)).strip()
    head = s.split('(')[0]
    if '. ' in head:                       # 생태 문장이 흘러들었다
        s = s[head.rindex('. ') + 2:]
    return re.sub(r'\s*(등지에서|에서)?\s*채\s*집\s*되\s*었\s*다.*$', '', s).strip(' ,.')


def extract():
    lines = read_text()
    blocks, cur = [], None
    for ln in lines:
        m = HEAD.match(ln)
        if m and int(m.group(1)) >= 169:
            cur = {"no": int(m.group(1)), "body": []}
            blocks.append(cur)
        elif cur is not None:
            cur["body"].append(ln)

    seen, raws, recs = set(), {}, []
    swallowed, bad_region, bad_ref = [], [], []
    for b in blocks:
        if b["no"] in seen:
            continue
        s = RENDERED.get(b["no"]) or sentence(b["body"])
        if not s:
            continue
        seen.add(b["no"])
        if len(s) > CAP:                   # 쪽을 삼켰다 — 버리지 않고 센다
            swallowed.append((b["no"], s[:120]))
            continue
        raws[b["no"]] = s
        pos = 0
        for m in CITE.finditer(s):
            regions = [r.strip(' ,.') for r in s[pos:m.start()].split(',') if r.strip(' ,.')]
            cites = [c.strip() for c in m.group(1).split(';') if c.strip()]
            pos = m.end()
            for r in regions:
                rn = norm_region(r)
                if rn is None:
                    bad_region.append((b["no"], r))
                    continue
                for c in cites:
                    cn = norm_ref(c)
                    ok = check_pair(*cn) if cn else None
                    if ok is None:
                        bad_ref.append((b["no"], c))
                        continue
                    recs.append({"item_no": str(b["no"]), "region_raw": r,
                                 "region": rn, "ref_raw": c,
                                 "ref": ok[0], "year": ok[1], "note": ok[2]})
    return raws, recs, swallowed, bad_region, bad_ref


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="아무것도 안 쓴다")
    args = ap.parse_args()

    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    by_no = {e["item_no"]: e for e in idx["entries"] if e.get("item_no")}
    in_layer = {n for n, e in by_no.items()
                if e["placements"] and e["placements"][0].get("pdf_page")
                and TEXT_LAYER[0] <= e["placements"][0]["pdf_page"] <= TEXT_LAYER[1]}

    raws, recs, swallowed, bad_region, bad_ref = extract()

    # **색인에 없는 항목 번호가 나오면 멈춘다** — 머리를 잘못 읽은 것이다
    unknown = sorted(set(raws) - {int(n) for n in by_no})
    for r in recs:
        r["binomial"] = by_no[r["item_no"]].get("binomial") or by_no[r["item_no"]]["name"]

    print(f"분포 문장 {len(raws)} · 출현 기록 {len(recs)}")
    print(f"   텍스트 레이어 안의 항목 {len(in_layer)} 중 {len(raws)} 을 읽었다 "
          f"(색인 전체는 {len(by_no)} — **나머지 {len(by_no) - len(in_layer)} 는 "
          f"텍스트 레이어가 없어 이 도구가 안 본다**)")
    print(f"   서로 다른 지역 {len({r['region'] for r in recs})} · "
          f"문헌 {len({(r['ref'], r['year']) for r in recs})}")
    bad = len(swallowed) + len(bad_region) + len(bad_ref) + len(unknown)
    if swallowed:
        print(f"\n쪽을 삼킨 분포 문장 {len(swallowed)}: {[n for n, _ in swallowed]}")
    if bad_region:
        print(f"표에 없는 지역 {len(bad_region)}: "
              f"{sorted({r for _, r in bad_region})}")
    if bad_ref:
        print(f"표에 없는 문헌 {len(bad_ref)}: {sorted({c for _, c in bad_ref})}")
    if unknown:
        print(f"색인에 없는 항목 번호 {unknown}")
    if bad:
        print(f"\n**{bad} 자리를 못 읽었다 — 표를 채우거나 그 쪽을 렌더해 읽는다.**")

    if args.dry_run:
        return 0

    refs = collections.Counter((r["ref"], r["year"]) for r in recs)
    OUT_JSON.write_text(json.dumps({
        "source": {"atlas": "korean", "pdf": "origin/korean_flora_diatom.pdf",
                   "text_layer_pages": list(TEXT_LAYER)},
        "references": [{"ref": a, "year": y, "records": n}
                       for (a, y), n in sorted(refs.items(), key=lambda x: -x[1])],
        "occurrences": recs,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n→ {OUT_JSON}")

    L = [f"# 한국동식물도감 — 출현 기록 {len(recs)}건", "",
         f"`tools/parse_occurrence.py` 가 본문의 분포 줄에서 뽑았다.",
         f"**항목 {len(raws)}개**에서 나왔고, 텍스트 레이어가 있는 범위",
         f"(PDF {TEXT_LAYER[0]}–{TEXT_LAYER[1]} · 항목 {len(in_layer)}개)가 전부다 —",
         f"**나머지 {len(by_no) - len(in_layer)}개는 쪽을 렌더해야 읽힌다.**", "",
         "## 문헌", "", "| 문헌 | 기록 |", "|---|---|"]
    L += [f"| {a} {y} | {n} |" for (a, y), n in sorted(refs.items(), key=lambda x: -x[1])]
    L += ["", "## 기록", "",
          "| # | 종 | 지역 | 원문 지역 | 문헌 |", "|---|---|---|---|---|"]
    for r in sorted(recs, key=lambda r: (int(r["item_no"]), r["region"])):
        L.append(f"| {r['item_no']} | *{r['binomial']}* | {r['region']} | "
                 f"{r['region_raw']} | {r['ref']} {r['year']} |")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
