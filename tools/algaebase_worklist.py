#!/usr/bin/env python3
"""AlgaeBase 에서 물어봐야 할 것을 추린다 (121 §10).

**사람이 브라우저로 여는 자리라 목록이 짧아야 한다.** 300종씩 들어오고 있고
(사용자 2026-08-14), 남은 것이 1,545개다. 그중 **AlgaeBase 가 답할 수 있는 것**
만 골라 순서를 매긴다.

## 물어봐야 소용없는 것을 먼저 뺀다

08-14 에 Schmidt 해설 원문으로 154건을 확인했다(`verify_from_notes.py`).
거기서 **학명이 아니라고 밝혀진 것은 뺀다** — 등록부에 물어야 "없다" 만 나온다.

| 뺀 것 | 왜 |
|---|---|
| `원문이 산문이다` | 독일어 낱말이다 (`gerechnet`·`erinnernde`) |
| `원문에 없다 (제목 줄 조각)` | 쪽 제목 `Atlas der Diatomaceenkunde` 의 부스러기 |
| `괄호 안 이명이다` | 그 쪽 항목이 아니다 |
| `줄바꿈으로 잘렸다` | **이미 풀렸다** — 이어 붙인 이름을 WoRMS 가 확인해 줬다 |
| `Tafel 아님 (Verzeichnis)` | 권 뒤 색인 줄이다 |

## 남은 것을 순서대로

| 순위 | 무엇 | 왜 AlgaeBase 여야 하나 |
|---|---|---|
| 1 | **원문에는 학명으로 있는데 WoRMS 에 없다** | 원문이 실재를 보증한다. 등록부에서 확인할 곳이 AlgaeBase 뿐이다 |
| 2 | 속 표기가 어긋난다/의심한다 | 속을 고쳐야 하는데 WoRMS 로는 안 갈렸다 |
| 3 | WoRMS 격리 레코드 | WoRMS 가 답을 안 준다 |
| 4 | 철자 의심 | 바른 철자를 AlgaeBase 가 알 수 있다 |
| 5 | 그 밖 WoRMS 에 없는 이름 | |

**동남극 도감 것은 앞으로 당긴다** — 도감 셋 중 **RS23 시추코어와 직접 겹치는
것이 그것뿐이다**(`Diadiction/README.md`).

**나오는 것이 둘이다.** 하나는 근거가 붙은 목록(`names/algaebase/`), 하나는
**조회해 올 사람이 그대로 채울 작업지**(`temp/`)다. 작업지는 `ingest_algaebase.py`
가 읽는 표 모양 그대로라 **채워서 돌려주면 바로 먹는다** — 형식이 어긋나면
번호 검산에서 멈춘다.

사용:

    python tools/algaebase_worklist.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402

MASTER = DIADICTION / "names/worms/worms_master_20260814.tsv"
SPECIES = DIADICTION / "names/worms/species_1845.tsv"
OUT = DIADICTION / "names/algaebase/algaebase_worklist_20260814.md"

# 원문에서 **학명이 아니라고** 밝혀진 것들 — 물어봐야 소용없다
NOT_A_NAME = ("산문", "제목 줄 조각", "괄호 안", "줄바꿈으로 잘렸다")


def tier(r: dict) -> tuple[int, str] | None:
    src = (r.get("원문확인") or "").split(" · ")[-1]
    if src and any(k in src for k in NOT_A_NAME):
        return None
    if src.startswith("원문에 학명으로 있다"):
        return 1, "원문에는 학명으로 있는데 WoRMS 에 없다"
    why, v = r.get("왜없나", ""), r["재판정"]
    if why in ("속 표기가 어긋난다", "속 표기를 의심한다"):
        return 2, why
    if v == "격리":
        return 3, "WoRMS 격리 레코드 — 답이 없다"
    if v == "오타교정 제안":
        return 4, f"철자 의심 → {r['WoRMS표제']}"
    if v == "사람이 본다":
        return 5, why or "WoRMS 에 없다"
    if v == "색인 쓰레기":
        return 5, "색인 부스러기로 봤다 — 지우기 전 확인"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    order = {n: i + 1 for i, n in enumerate(
        l.split("\t")[0] for l in
        SPECIES.read_text(encoding="utf-8").splitlines()[1:] if l.strip())}
    rows = list(csv.DictReader(MASTER.open(encoding="utf-8"), delimiter="\t"))

    done = sum(1 for r in rows if r["AlgaeBase"])
    todo = []
    for r in rows:
        if r["이름"] not in order or r["AlgaeBase"]:
            continue
        t = tier(r)
        if t:
            todo.append({"번호": order[r["이름"]], "이름": r["이름"], "순위": t[0],
                         "왜": t[1], "도감": r["도감"],
                         "원문확인": (r.get("원문확인") or "").split(" · ")[-1],
                         "덤프": r.get("덤프(20260701)", "")})

    left = sum(1 for r in rows if r["이름"] in order and not r["AlgaeBase"])
    print(f"색인 이름 {len(order):,} · 조회 끝 {done} · 남은 것 {left:,}")
    print(f"**물어볼 것 {len(todo)}건** (나머지 {left - len(todo):,}건은 순번대로 오면 된다)\n")
    for k, n in sorted(collections.Counter(t["순위"] for t in todo).items()):
        one = next(t for t in todo if t["순위"] == k)
        print(f"   {k}순위 {n:4d}  {one['왜'][:44]}")

    ant = [t for t in todo if "동남극" in (t["도감"] or "")]
    print(f"\n   그중 동남극 도감 {len(ant)}건 — **RS23 과 겹치는 도감이다**")

    todo.sort(key=lambda t: (t["순위"], t["번호"]))
    L = ["# AlgaeBase 에서 물어볼 것 (2026-08-14 · 다시 추림)", "",
         f"색인 이름 {len(order):,}개 중 **{done}개는 조회가 끝났고**(1~300번),",
         f"남은 {left:,}개 가운데 **{len(todo)}건**이 AlgaeBase 가 답할 수 있는 자리입니다.", "",
         "**앞선 목록에서 뺀 것이 있습니다.** 08-14 에 Schmidt 해설 원문으로 확인해",
         "**학명이 아니라고 밝혀진 것들**입니다 — 독일어 낱말(`erinnernde`)·쪽 제목",
         "부스러기(`Diatoma cull`)·괄호 안 이명·줄바꿈으로 잘린 것(이미 풀렸습니다).",
         "물어봐야 \"없다\" 만 나오는 것들이라 뺐습니다.", ""]
    if ant:
        L += ["## 먼저 봐 주셨으면 하는 것 — 동남극 도감", "",
              "도감 셋 중 **RS23 시추코어와 직접 겹치는 것이 이 도감뿐입니다.**", "",
              "| # | 학명 | 왜 |", "|---|---|---|"]
        for t in sorted(ant, key=lambda t: t["번호"]):
            L.append(f"| {t['번호']} | *{t['이름']}* | {t['왜']} |")
        L.append("")
    L += ["## 순위별", "",
          "순위 안에서는 `species_1845.tsv` 번호순입니다 — **지금 하시는 순번 그대로",
          "훑으시면 걸립니다.** 번호가 300 이하인 것은 이미 조회하셨는데도 안 풀린 것입니다.", "",
          "| 순위 | # | 학명 | 도감 | 왜 물어야 하나 | 원문 확인 |",
          "|---|---|---|---|---|---|"]
    for t in todo:
        L.append(f"| {t['순위']} | {t['번호']} | *{t['이름']}* | {t['도감'] or '-'} | "
                 f"{t['왜']} | {t['원문확인']} |")
    args.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {args.out}")

    sheet = DIADICTION / "temp/algaebase_ask_20260814.md"
    W = [f"# AlgaeBase 조회 부탁 — {len(todo)}건 (2026-08-14)", "",
         "**이 표의 `AlgaeBase 현재 통용명` 칸만 채워서 돌려주시면 됩니다.**",
         "번호와 학명은 건드리지 마세요 — 번호가 `species_1845.tsv` 의 줄과",
         "맞는지 검산하고, 어긋나면 반입이 멈춥니다.", "",
         "## 채우는 법", "",
         "| 이런 경우 | 이렇게 적습니다 |", "|---|---|",
         "| 다른 이름으로 바뀌었다 | `**Karayevia amoena**` (학명만) |",
         "| 그대로 쓴다 | `(그대로 유효)` |",
         "| AlgaeBase 에 없다 | `AlgaeBase에 없음` |",
         "| 애매하다 | `확인 필요` — **비고에 왜 그런지 적어 주세요** |",
         "| 못 찾았다 | `미확인` |", "",
         "꼬리를 붙여도 됩니다(`(그대로 유효, 저자 W.Smith)`) — 낱말로 가릅니다.", "",
         "**함정 셋** (`names/algaebase/algaebase_worklist.md` 에서 옮깁니다)", "",
         "1. **Turnstile 에 걸린 화면을 결과로 읽지 마세요.** 걸리면 페이지 제목이",
         "   `Verify you are human :: AlgaeBase` 가 되고 **HTTP 는 200 입니다.**",
         "2. **`Status of Name` 이 최종 판정입니다** — 검색 결과 목록이 아니라",
         "   상세 페이지의 그 줄입니다.",
         "3. **그 레코드의 갱신 시점을 비고에 함께 적어 주세요.** WoRMS 와 엇갈릴 때",
         "   판단 재료가 됩니다.", "",
         "---", "",
         "**왜 이 종들인가** — WoRMS 로는 안 풀린 것들입니다. Schmidt 해설 원문으로",
         "먼저 걸러서 **학명이 아닌 것(독일어 낱말·쪽 제목 부스러기·괄호 안 이명)은",
         "뺐습니다.** 여기 있는 것은 전부 진짜 이름으로 볼 만한 것들입니다.", ""]
    if ant:
        W += [f"**{len(ant)}건은 동남극 도감 것이라 먼저 봐 주시면 좋겠습니다** — "
              "도감 셋 중 남극 시추코어와 직접 겹치는 것이 그것뿐입니다.", ""]
    W += ["## 표", "",
          "| # | 학명 (도감 표기) | AlgaeBase 현재 통용명 | 비고 |",
          "|---|---|---|---|"]
    for t in todo:
        tag = []
        if "동남극" in (t["도감"] or ""):
            tag.append("동남극")
        tag.append(t["왜"][:34])
        W.append(f"| {t['번호']} | {t['이름']} |  | ({' · '.join(tag)}) |")
    sheet.write_text("\n".join(W) + "\n", encoding="utf-8")
    print(f"→ {sheet}  ← **이걸 넘기시면 됩니다**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
