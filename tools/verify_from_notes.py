#!/usr/bin/env python3
"""손봐야 할 색인 항목을 Schmidt 해설 원문에서 확인한다 (121 §9).

**107쪽을 다 렌더하기 전에 원문 문맥으로 거른다.** 색인을 만든 것이 그 OCR 이라,
그 낱말이 원문에서 **어느 자리에 있었는지**를 보면 대부분 렌더 없이 갈린다.
`genus_screen.py` 가 속명에 썼던 판별식과 같은 것이다 — 자리가 가른다.

```
학명 자리   9—11. Jedo (Brun), A. clavatus Brun.          ← 멀쩡한 항목이다
산문 자리   … die an Actinoptychus erinnernde …           ← 독일어 분사다
산문 자리   … Randmaschen der Hauptfelder eine feine …    ← 관사다
괄호 안     … Raphoneis nodulifera A. S. (Cocconeis nodulifer Grove.)
```

**괄호 안은 Tafel 57 과 같은 고장이다** — 이명이 괄호에 적힌 것을 항목으로 집었다.

## 갈래

| 판정 | 뜻 | 다음 |
|---|---|---|
| `원문에 학명으로 있다` | 항목 자리에 그대로 있다 | 색인이 맞다. WoRMS 에 없을 뿐 |
| `괄호 안 이명이다` | 괄호에 적힌 이름을 집었다 | 항목이 아니다 — 뺀다 |
| `원문이 산문이다` | 독일어 낱말·지명이 종소명 자리에 왔다 | 뺀다 |
| `원문 철자가 그대로다` | OCR 이 흘린 철자를 색인이 그대로 받았다 | 렌더해서 바른 철자를 읽는다 |
| `줄바꿈으로 잘렸다` | 원문이 `ventri- cosa` 로 끊겨 앞동강만 집었다 | 이어 붙이면 답이다 |
| `산문에 나온 실재 이름` | 학명이지만 그 쪽의 항목이 아니다 | 다른 쪽 것이다 |
| `원문에 없다` | 그 쪽에 그 낱말이 없다 | 렌더한다 (쪽이 어긋났을 수도) |

## 함정

- **`오타교정 제안` 은 여기서 안 끝난다.** 원문 철자가 색인과 같으면 **OCR 이
  흘린 것**이라 원문을 눈으로 봐야 바른 철자가 나온다 — WoRMS 가 준 후보가
  맞는지는 쪽을 열어야 안다
- **독일어 낱말 목록으로 가르지 않는다.** 목록은 늘 모자란다 — **자리**로 가른다
- **앞만 봐서는 안 된다 — 뒤도 봐야 한다.** `wäre Syndetocystis eine richtige
  Biddulphie` 는 속명이 바로 앞에 있지만 독일어 문장의 주어다. 인용이면
  **저자명이나 구두점**이 따라오는데(`A. clavatus Brun.`) 여기는 소문자
  형용사가 온다
- **아무 속 뒤나 보면 안 된다 — 색인이 말하는 그 속이어야 한다.** `eine`·`der`
  같은 낱말은 원문 곳곳에 있어서, 속을 안 따지면 어딘가의 `<속> eine` 이 걸려
  "학명으로 있다" 가 된다. `Syndetocystis eine` 이 그렇게 통과할 뻔했다

**`원문에 없다` 셋은 제목 줄 조각이었다** — `Diatoma cull`·`Diatoma kund` 는
쪽 제목 `Atlas der Diatomaceenkunde` 의 OCR 부스러기다(Tafel 43 을 렌더해 확인).

사용:

    python tools/verify_from_notes.py            # 가르고 md 로 낸다
    python tools/verify_from_notes.py --apply    # 대조표에 `원문확인` 칸을 채운다
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402
from genus_screen import (ASIDE, genus_vocab, match_genus,  # noqa: E402
                          read_index, read_notes)

MASTER = DIADICTION / "names/worms/worms_master_20260814.tsv"
OUT = DIADICTION / "names/worms/notes_verify_20260814.md"
SUSPECT = {"색인 쓰레기", "오타교정 제안", "사람이 본다"}

# 종소명 바로 앞의 낱말. 속명이 온전하거나(`Coscinodiscus`) 줄어 있다(`C.`)
BEFORE = re.compile(r"(\b[A-Z][a-zé]{4,}|\b[A-Z]{1,2})\.?\s*$")


def look(text: str, genus: str, ep: str, vocab: set, loose: dict) -> tuple[str, str]:
    """종소명이 원문 어디에 있었는지 본다. (판정, 문맥)

    **앞 낱말이 대문자라고 속명인 것이 아니다** — 독일어는 명사를 다 대문자로
    쓴다(`Hauptfelder eine feine`). 그리고 속명이 앞에 있어도 그 속명이 산문
    안이면 학명 자리가 아니다(`die an Actinoptychus erinnernde`).
    **둘 다 봐야 한다** — `genus_screen` 이 속명에서 겪은 것과 같은 자리다.
    """
    best = None
    for m in re.finditer(r"\b" + re.escape(ep[:6]) + r"[a-zé]*", text, re.I):
        word = m.group(0)
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 30]
        ctx = " ".join((before[-45:] + "«" + word + "»" + after[:35]).split())
        mb = BEFORE.search(before.rstrip())
        named = False
        if mb:
            tok = mb.group(1)
            # 줄인 속명(`C.`)이거나, 어휘에 있는 온전한 속명이어야 한다
            # **색인이 말하는 그 속이어야 한다** (온전하거나 머리글자로)
            same = (tok == genus[0]) if len(tok) <= 2 \
                else (match_genus(tok, vocab, loose) == genus)
            if same:
                # 그 속명 자체가 산문 안이면 학명 자리가 아니다
                lead = before.rstrip()[:mb.start()]
                named = not ASIDE.search(lead[-14:])
                # **뒤가 인용의 모양이어야 한다** — 저자명(대문자)이나 구두점.
                # 소문자 낱말이 이어지면 독일어 문장이다
                if named and not re.match(r"\s*(?:[A-Z(]|[.,;:?!)]|nov|n\.|var|$)",
                                          after):
                    named = False
        # 괄호 안인가 — 여는 괄호가 닫는 것보다 가까이 있으면
        seg = text[max(0, m.start() - 160):m.start()]
        inparen = seg.rfind("(") > seg.rfind(")")
        exact = word.lower() == ep.lower()
        score = (named, exact, not inparen)
        if best is None or score > best[0]:
            best = (score, ctx, named, inparen, exact, word)
    if best is None:
        # Tafel 43 을 렌더해 보니 셋 다 쪽 제목 `Atlas der Diatomaceenkunde` 의
        # OCR 부스러기였다 — 본문에 없는 것이 그래서다
        return "원문에 없다 (제목 줄 조각)", ""
    _, ctx, named, inparen, exact, word = best
    # **줄바꿈으로 잘린 것**은 뒤에 `- ` 와 이어질 조각이 온다 (`ventri- cosa`)
    tail = re.search(r"«" + re.escape(word) + r"»\s*-\s*([a-zé]{3,})", ctx)
    if tail:
        return f"줄바꿈으로 잘렸다 → {word}{tail.group(1)}", ctx
    if named and inparen:
        return "괄호 안 이명이다", ctx
    if named and exact:
        return "원문에 학명으로 있다", ctx
    if named and not exact:
        return f"원문 철자는 {word}", ctx
    return "원문이 산문이다", ctx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--apply", action="store_true", help="대조표에 칸을 채운다")
    args = ap.parse_args()

    notes, index = read_notes(), read_index()
    vocab = genus_vocab()
    loose = {g[:6]: g for g in vocab if len(g) >= 8}
    rows = {r["이름"]: r for r in
            csv.DictReader(MASTER.open(encoding="utf-8"), delimiter="\t")}

    out = []
    for t, items in sorted(index.items()):
        text = notes.get(t)
        if text is None:
            continue
        for genus, ep in items:
            r = rows.get(f"{genus} {ep}")
            if not r or r["재판정"] not in SUSPECT:
                continue
            verdict, ctx = look(text, genus, ep, vocab, loose)
            # 산문 자리인데 WoRMS 가 가까운 이름을 아는 것은 **실재하는 학명**이
            # 스쳐 지나간 것이다 — 독일어 낱말과 갈라 놓는다
            if verdict == "원문이 산문이다" and r["재판정"] != "색인 쓰레기":
                verdict = "산문에 나온 실재 이름"
            out.append({"tafel": t, "이름": f"{genus} {ep}", "재판정": r["재판정"],
                        "판정": verdict, "문맥": ctx,
                        "AlgaeBase": r.get("AlgaeBase", "")})

    tally = collections.Counter(o["판정"] for o in out)
    print(f"Schmidt 에서 손봐야 할 것 {len(out)}건 · Tafel "
          f"{len({o['tafel'] for o in out})}쪽\n")
    for k, n in tally.most_common():
        print(f"   {k:20s} {n}")
    render = sorted({o["tafel"] for o in out
                     if o["판정"].startswith("원문 철자는") or o["판정"].startswith("원문에 없다")})
    print(f"\n**렌더가 필요한 쪽 {len(render)}개** (107쪽에서 줄었다)")
    print("   " + " ".join(str(t) for t in render[:40]))

    L = ["# Schmidt 색인 — 손봐야 할 항목을 원문에서 확인 (2026-08-14)", "",
         f"손봐야 할 {len(out)}건을 **해설 원문의 어느 자리에 있었는지**로 갈랐습니다.",
         "`genus_screen.py` 가 속명에 썼던 판별식과 같습니다 — 자리가 가릅니다.", "",
         "| 판정 | 수 | 다음 |", "|---|---|---|"]
    nextstep = {"원문에 학명으로 있다": "색인이 맞습니다. WoRMS 에 없을 뿐입니다",
                "산문에 나온 실재 이름": "학명이지만 그 쪽의 항목이 아닙니다 — 다른 쪽 것입니다",
                "괄호 안 이명이다": "항목이 아닙니다 — 뺍니다 (Tafel 57 과 같은 고장)",
                "원문이 산문이다": "독일어 낱말·지명입니다 — 뺍니다",
                "원문에 없다 (제목 줄 조각)": "쪽 제목의 OCR 부스러기입니다 — 뺍니다"}
    for k, n in tally.most_common():
        L.append(f"| {k} | {n} | "
                 f"{nextstep.get(k, '**렌더해서 바른 철자를 읽습니다**')} |")
    L += ["", f"**렌더가 필요한 쪽은 {len(render)}개**입니다: "
          + ", ".join(str(t) for t in render), "",
          "| Tafel | 색인의 이름 | 대조 판정 | 원문에서 | 문맥 | AlgaeBase |",
          "|---|---|---|---|---|---|"]
    for o in sorted(out, key=lambda o: (o["판정"], o["tafel"])):
        L.append(f"| {o['tafel']} | *{o['이름']}* | {o['재판정']} | **{o['판정']}** | "
                 f"`{o['문맥'][:90]}` | {o['AlgaeBase']} |")
    args.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n→ {args.out}")

    if args.apply:
        by = {o["이름"]: o for o in out}
        lines = MASTER.read_text(encoding="utf-8").splitlines()
        head = lines[0].split("\t")
        if "원문확인" not in head:
            head.append("원문확인")
        at = head.index("원문확인")
        rows2, filled = [], 0
        for line in lines[1:]:
            if not line.strip():
                continue
            cells = line.split("\t")
            cells += [""] * (len(head) - len(cells))
            o = by.get(cells[0])
            if o:
                filled += 1
                cells[at] = f"T{o['tafel']} · {o['판정']}"
            rows2.append(cells)
        MASTER.write_text("\t".join(head) + "\n"
                          + "".join("\t".join(c) + "\n" for c in rows2),
                          encoding="utf-8")
        print(f"대조표 {filled}줄에 `원문확인` 을 채웠다 → {MASTER.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
