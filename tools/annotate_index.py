#!/usr/bin/env python3
"""도감 색인의 항목마다 학명 대조 결과를 붙인다 (P15).

**지우거나 갈아치우지 않는다 — 붙이기만 한다.** 이유가 셋이다.

- `Diadiction/README.md` 가 **색인 텍스트를 그대로 인용하지 말라**고 못 박고
  있다. OCR 산물이라 철자가 흔들린다 — 그런 자리를 기계가 고쳐 쓰면 안 된다
- 이 파일은 **119 에서 속명 복원 버그가 나온 파일이다**(Tafel 26 의
  `Amphiprora` 13건이 `Amphora` 였다). 아직 후보가 33개 더 있다
- 지우는 것은 되돌릴 수 없다. 오늘 `index_remove` 의 규칙 둘이 넓어 **진짜
  학명 7건을 지울 뻔했다** — 붙여 놓으면 사람이 보고 고를 수 있다

그래서 항목 줄 끝에 **표시 한 덩이**를 단다. 다시 돌리면 갈아 끼우고,
`--strip` 이면 통째로 걷는다 — **색인은 언제든 원래 모양으로 돌아간다.**

    - ***Achnanthes amoena*** — Tafel 420 (…)  〔WoRMS 20260814 · 이명 → Karayevia amoena〕

## 함정

- **색인 표제어가 곧 이명법이 아니다.** 한국 도감은 저자까지 달고 대문자로
  적는다(`Melosira ambigua (GRUN.) O. F. MÜLLER`). 이름을 뽑는 규칙은
  `harvest_worms.read_names` 하나뿐이라 **거기서 가져다 쓴다** — 두 벌이 되면
  붙는 자리가 어긋난다
- **`name_validity_log.md` 에는 쏟아붓지 않는다.** 거긴 AlgaeBase 를 주
  출처로 **사람이 적는** 자리다. WoRMS 1,600건이 들어가면 그 규칙이 무너진다

사용:

    python tools/annotate_index.py                 # 붙인다 (다시 돌려도 된다)
    python tools/annotate_index.py --dry-run       # 무엇이 붙는지만 본다
    python tools/annotate_index.py --strip         # 표시를 통째로 걷는다
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION, GENUS_FIX, INDEXES  # noqa: E402

MASTER = DIADICTION / "names/worms/worms_master_20260814.tsv"
DUMP = DIADICTION / "names/db/worms_diatoms_20260701.db"
STAMP = "20260814"
# **내가 붙인 것만 정확히 걷는다.** `\s*` 로 잡으면 한국 색인이 줄바꿈으로
# 쓰는 줄 끝 공백 두 칸까지 함께 사라져 원본으로 안 돌아간다.
# **`$` 로 고정하면 안 된다** — 다른 도구가 뒤에 표시를 하나 더 달면
# (`tafel_numbering.py` 의 `〔Tafel 아님 …〕`) 내 것이 줄 끝이 아니게 되어
# 안 걷히고, 다시 돌릴 때마다 표시가 하나씩 늘어난다. 실제로 21줄이 그랬다
MARK = re.compile(r"  〔WoRMS [^〕]*〕")
# 머리말 블록. **넣을 때와 뺄 때가 같은 모양이어야 왕복한다**
BLOCK = re.compile(r"\n<!-- WoRMS-표시 -->.*?<!-- /WoRMS-표시 -->\n", re.S)

STATUS_KR = {"accepted": "유효", "unaccepted": "이명", "unassessed": "미평가",
             "uncertain": "불확실", "nomen nudum": "나명",
             "alternative representation": "대체 표기",
             "junior objective synonym": "이명(객관)",
             "junior subjective synonym": "이명(주관)",
             "misspelling - incorrect subsequent spelling": "오철자"}


def binomial(title: str) -> str | None:
    """색인 표제어 → 이명법. **`harvest_worms.read_names` 와 같은 규칙이다.**"""
    words = title.replace("*", "").split()
    if len(words) < 2:
        return None
    genus, epithet = words[0].capitalize(), words[1].lower()
    if not re.fullmatch(r"[a-zöäüéë\-]+", epithet):
        return None
    return f"{GENUS_FIX.get(genus, genus)} {epithet}"


def unmatched(title: str, db: sqlite3.Connection | None) -> str:
    """이명법이 안 나오는 표제어에도 표시를 단다.

    **조용히 건너뛰지 않는다.** 여기 걸리는 것이 둘인데 성격이 아주 다르다 —
    도판집의 **속 수준 동정**(`Delphineis`)은 정상이고, `Synedra cyclopиm` 처럼
    **키릴 문자가 섞인 것**은 OCR 손상이라 고쳐야 할 자리다. 표시가 없으면
    둘 다 "그냥 안 붙은 줄" 로 보인다.
    """
    words = title.replace("*", "").split()
    if len(words) == 1:
        g = words[0].capitalize()
        note = "속 수준 동정 — 종까지 안 내려간 항목이다"
        if db is not None:
            r = db.execute("SELECT scientificName, taxonomicStatus FROM taxon "
                           "WHERE genus_fold=? AND taxonRank='Genus' LIMIT 1",
                           (g.lower(),)).fetchone()
            if r:
                note += f" · 속 {r[0]} ({STATUS_KR.get(r[1], r[1])}) 는 있다"
        return note
    ep = words[1]
    odd = [c for c in ep
           if unicodedata.category(c)[0] == "L" and "LATIN" not in unicodedata.name(c, "")]
    if odd:
        return (f"표제어가 손상됐다 — 종소명에 라틴 문자가 아닌 것이 섞였다 "
                f"({''.join(odd)!r} in {ep!r})")
    return "대조표에 없다 — 이름을 뽑는 규칙에 안 걸린 표제어다"


def algaebase(r: dict) -> str | None:
    """AlgaeBase 판정을 앞세운다. **쓸 이름은 AlgaeBase 를 따른다**(방침 08-12).

    다만 **엇갈렸다는 사실은 지우지 않는다** — WoRMS 가 다른 이름을 주면 그것도
    함께 적는다. 색인을 보는 사람이 "왜 저 이름인가" 를 여기서 알 수 있어야 한다.
    """
    ab = (r.get("AlgaeBase") or "").strip()
    if not ab:
        return None
    worms = r.get("유효명") or ""
    if re.fullmatch(r"[A-Z][a-zë\-]+ [a-zë\- .]+", ab):      # 이름이 왔다
        note = f"AlgaeBase 이명 → {ab}"
        if worms and worms not in (ab, r["이름"]):
            note += f" · WoRMS 는 {worms} (엇갈림)"
        return note
    if ab == "그대로 유효":
        note = "AlgaeBase 그대로 유효"
        if worms and worms != r["이름"]:
            note += f" · WoRMS 는 {worms} (엇갈림)"
        return note
    # `AlgaeBase 에 없다`·`확인 필요`·`미확인`·`아직 안 찾았다`
    return f"AlgaeBase {ab}"


# 원문에서 확인한 것이 등록부 대조보다 앞서는 판정들.
#
# 처음에는 **이름이 아니라는** 것 넷뿐이었다 — 학명이 아닌 것을 등록부에 물어
# 봐야 "없다" 만 나오기 때문이다. 08-18 에 `렌더 확인` 을 더했다
# (`render_verify.py`). **근거의 무게가 달라서 낱말로 갈랐다** — 앞엣것들은
# 해설 OCR 로 본 것이고, 뒤엣것은 **사람이 PDF 쪽을 열어 본 것**이다. 뒤엣것은
# 판정이 무엇이든(철자·Verzeichnis·속명·오식) 등록부보다 앞선다. 실제로
# `Cymbella amphi` 는 등록부만 보면 "철자 의심" 인데 원문은
# `Cymbella amphi- / cephala` 로 줄바꿈에 잘려 있었다.
#
# **해설 OCR 쪽에 낱말을 더 붙이지 말 것** — 그쪽 `원문에 학명으로 있다` 91건은
# Tafel 번호가 어긋난 본문에서 나온 것이라(126) 등록부를 밀어낼 무게가 아니다
RENDER = "렌더 확인 — "
SRC_WINS = ("산문", "괄호 안", "줄바꿈", "원문에 없다", RENDER)


def verdict(r: dict) -> str:
    """한 줄로 줄인 판정. **길면 색인이 안 읽힌다.**"""
    src = (r.get("원문확인") or "").split(" · ")[-1] if r.get("원문확인") else ""
    ab = algaebase(r)
    if src and any(k in src for k in SRC_WINS):
        # **AlgaeBase 를 버리지 않고 뒤에 붙인다.** 원문은 그 쪽에 무엇이 찍혀
        # 있는지를 말하고 AlgaeBase 는 지금 통용되는 이름을 말한다 — 다른 물음이다
        head = ("원문 렌더 확인: " + src[len(RENDER):]) if src.startswith(RENDER) \
            else f"원문 확인: {src}"
        return head + (f" · {ab}" if ab else "")
    if ab:
        return ab
    v, why = r["재판정"], r["근거"]
    if v == "확정":
        s = STATUS_KR.get(r["상태"], r["상태"] or "?")
        if r["유효명"] and r["유효명"] != r["이름"]:
            return f"{s} → {r['유효명']}"
        # **"이명" 만 적으면 뭘로 갈아타라는 것인지가 없다.** WoRMS 가
        # unaccepted 로 두면서 유효명을 자기 자신으로 주는 자리가 있다 (4건)
        if r["상태"] in ("unaccepted", "junior objective synonym",
                         "junior subjective synonym"):
            return f"{s} — WoRMS 가 갈아탈 이름을 안 준다"
        if not r["유효명"]:
            return f"{s} · 유효명 칸이 비었다"
        return s
    if v == "오타교정 제안":
        return f"철자 의심 → {r['WoRMS표제']} [{r['매칭유형']}]"
    if v == "되살린다":
        return f"WoRMS 에 있다 — 지우지 말 것 ({STATUS_KR.get(r['상태'], r['상태'])})"
    if v == "격리":
        return "WoRMS 격리 레코드 — 대조할 표제가 없다"
    if v in ("속 다름", "비규조"):
        return why
    if src:
        return f"원문에 학명으로 있다 (WoRMS 에만 없다) · {v}"
    if v == "색인 쓰레기":
        return f"색인 부스러기로 봤다 — {why}"
    # 사람이 본다
    return f"사람이 본다 — {r['왜없나'] or why}"


def annotate(strip: bool, dry: bool) -> int:
    rows = {r["이름"]: r for r in
            csv.DictReader(MASTER.open(encoding="utf-8"), delimiter="\t")}
    print(f"대조표 {len(rows):,}줄")
    dump = sqlite3.connect(DUMP) if DUMP.exists() else None
    total = collections.Counter()

    for atlas, rel, pat, section in INDEXES:
        path = DIADICTION / rel
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        # 절이 있는 색인은 그 범위 밖을 안 건드린다 (동남극은 원문이 뒤에 또 있다)
        lo, hi = 0, len(lines)
        if section:
            for i, ln in enumerate(lines):
                if ln.startswith(section[0]):
                    lo = i
                if ln.startswith(section[1]):
                    hi = i
                    break

        hit = miss = 0
        for i in range(lo, hi):
            m = re.match(pat, lines[i])
            if not m:
                continue
            base = MARK.sub("", lines[i])
            if strip:
                lines[i] = base
                hit += 1
                continue
            name = binomial(m.group(1))
            r = rows.get(name) if name else None
            if not r:
                # **표시 없이 넘기지 않는다** — 왜 안 붙었는지를 적는다
                lines[i] = f"{base}  〔WoRMS {STAMP} · {unmatched(m.group(1), dump)}〕"
                miss += 1
                total["대조 못 함"] += 1
                continue
            note = verdict(r)
            if r["덤프(20260701)"]:
                note += " · 덤프 확인"
            lines[i] = f"{base}  〔WoRMS {STAMP} · {note}〕"
            hit += 1
            total[r["재판정"]] += 1

        out = "\n".join(lines)
        if not strip:
            out = header(out, atlas)
        else:
            out = BLOCK.sub("", out)
        print(f"  {atlas:8s} {'걷었다' if strip else '붙였다'} {hit:4d}"
              + (f" · 이명법이 안 나온 표제어 {miss} (그것도 표시했다)" if miss else ""))
        if not dry:
            path.write_text(out, encoding="utf-8")

    if total:
        print("\n붙은 판정:")
        for k, n in total.most_common():
            print(f"  {k:14s} {n:,}")
    if dry:
        print("\n(--dry-run 이라 파일은 안 썼다)")
    return 0


def header(text: str, atlas: str) -> str:
    """표시가 무엇인지 색인 머리에 적는다. 이미 있으면 갈아 끼운다."""
    block = f"""<!-- WoRMS-표시 -->
> **항목 끝의 〔WoRMS {STAMP} …〕는 학명 대조 결과입니다** — 원문은 그대로 두고
> 붙이기만 한 것입니다. `tools/annotate_index.py --strip` 으로 통째로 걷힙니다.
> 근거는 `names/worms/worms_master_{STAMP}.tsv` 이고, **판정의 원본은
> `md/name_validity_log.md`** 입니다(AlgaeBase 가 주 출처).
>
> **표시가 곧 판정은 아닙니다.** `색인 부스러기로 봤다`·`철자 의심` 은 기계가
> 근거를 들어 세운 것이고, 지우거나 고치는 것은 사람이 정합니다 — 08-14 에
> 같은 규칙이 진짜 학명 7건을 지울 뻔했습니다. `사람이 본다` 는 WoRMS 가
> 답을 못 준 자리인데, **내려받은 사본에는 AlgaeBase 출처가 라이선스 때문에
> 빠져 있어**(`names/db/`) 그쪽에서도 안 갈립니다.
<!-- /WoRMS-표시 -->
"""
    text = BLOCK.sub("", text)
    # 첫 `---` 앞(머리말 끝)에 넣는다. 없으면 첫 제목 다음 줄
    at = text.find("\n---\n")
    if at < 0:
        at = text.find("\n", text.find("#"))
    return text[:at + 1] + "\n" + block + text[at + 1:]  # BLOCK 과 짝이다


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strip", action="store_true", help="표시를 통째로 걷는다")
    ap.add_argument("--dry-run", action="store_true", help="파일을 안 쓴다")
    args = ap.parse_args()
    if not MASTER.exists():
        print(f"대조표를 못 찾는다: {MASTER}", file=sys.stderr)
        return 2
    return annotate(args.strip, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
