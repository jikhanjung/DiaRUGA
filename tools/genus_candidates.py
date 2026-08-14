#!/usr/bin/env python3
"""Schmidt 색인의 속명이 잘못 펴진 후보를 다시 뽑는다 (119 재실행).

**119 가 무엇을 했나.** 복원 규칙이 "같은 Tafel 안에 글자로 나온 속명" 이면
무엇이든 근거로 삼아서, **지나가는 언급**(비교 문장)이나 **괄호 안의 이명**까지
집었다. 그래서 Tafel 26 의 `Amphiprora` 13건이 실은 `Amphora` 였고, Tafel 57 의
`Cosmiodiscus` 7건이 `Coscinodiscus` 였다. 찾는 법은 **같은 Tafel 의 다른 속으로
종소명을 되물어 보는 것**이다.

**왜 다시 뽑나.** 119 스스로 남긴 것이다 — `extant_only` 를 빠뜨린 채로 만들어
**화석 55개가 빠져 있었다.** Schmidt 는 화석 해양규조 비중이 큰 도감이라 그
한 글자가 결과를 크게 바꾼다(`harvest_worms.py` 머리말).

**그리고 근거를 하나 더 쓴다 — 119 는 원래 이름이 실재하는지를 안 봤다.**

| 원래 이름 | 다른 속의 이름 | 읽는 법 |
|---|---|---|
| 없다 | 있다 | **강하다** — 색인의 이름이 아예 성립하지 않는다 |
| 있다 | 있다 | 약하다 — 둘 다 실재하니 쪽을 봐야 안다 |

여기에 119 자신의 규칙을 겹친다 — **한 쪽에서 여럿이 같은 속으로 몰리는 것만
진짜다.** `Terpsinoe` 하나에 후보 속이 셋씩 붙는 것은 종소명이 흔해서 나는 잡음이다.

## 함정

- **한 이름이 Tafel 여럿에 나온다.** `Tafel 417 (…); Tafel 418 fig.1—8 (…)` 처럼
  한 줄에 여러 번 적힌다 — 전부 뽑아 각각의 쪽에서 따진다
- **묻는 조건을 `harvest_worms` 와 맞춘다** (`marine_only=false&extant_only=false`
  · `class == Bacillariophyceae`). 안 맞추면 119 와 같은 자리에서 또 샌다
- **후보는 후보다.** 이 스크립트는 **쪽을 열 순서**를 정해 줄 뿐이고, 고치는
  것은 해당 Tafel 해설면을 보고 사람이 한다 (119 §7)

사용:

    python tools/genus_candidates.py                # 뽑아서 md 로 낸다
    python tools/genus_candidates.py --no-ask       # 캐시에 있는 것만으로
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION, GENUS_FIX  # noqa: E402

INDEX = DIADICTION / "md/schmidt_atlas_name_index.md"
MASTER = DIADICTION / "names/worms/worms_master_20260814.tsv"
CACHE = DIADICTION / "names/worms/genus_candidates_cache_20260814.json"
OUT = DIADICTION / "names/worms/genus_candidates_20260814.md"
API = "https://www.marinespecies.org/rest/AphiaRecordsByNames"
DIATOM_CLASS = "Bacillariophyceae"
BATCH = 50

ENTRY = re.compile(r"^- \*\*\*(.+?)\*\*\*(.*)$")
TAFEL = re.compile(r"Tafel (\d+)")


def read_index() -> list[tuple[str, str, set[int]]]:
    """색인에서 (속, 종소명, 그 이름이 나온 Tafel 들) 을 뽑는다."""
    out = []
    for line in INDEX.read_text(encoding="utf-8").split("\n"):
        m = ENTRY.match(line)
        if not m:
            continue
        words = m.group(1).replace("*", "").split()
        if len(words) < 2:
            continue
        genus, ep = words[0].capitalize(), words[1].lower()
        if not re.fullmatch(r"[a-zöäüéë\-]+", ep):
            continue
        tafeln = {int(t) for t in TAFEL.findall(m.group(2))}
        if tafeln:
            out.append((GENUS_FIX.get(genus, genus), ep, tafeln))
    return out


def ask(names: list[str], cache: dict, sleep: float) -> dict:
    """**`harvest_worms` 와 같은 조건이다** — 화석을 빠뜨리면 119 를 되풀이한다."""
    todo = [n for n in names if n not in cache]
    print(f"물을 것 {len(todo):,}개 (이미 물어 둔 것 {len(cache):,})")
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        q = "&".join("scientificnames%5B%5D=" + urllib.parse.quote(n) for n in batch)
        url = f"{API}?{q}&marine_only=false&extant_only=false"
        got = [[] for _ in batch]
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    if r.status == 200:
                        got = [(x or []) for x in json.loads(r.read().decode())]
                break
            except Exception:
                if attempt == 2:
                    print(f"  ! {batch[0]}… 못 물었다", file=sys.stderr)
                time.sleep(2 ** attempt)
        for name, recs in zip(batch, got):
            keep = [r for r in recs if r.get("class") == DIATOM_CLASS]
            cache[name] = [{"status": r.get("status"), "AphiaID": r.get("AphiaID"),
                            "authority": r.get("authority"),
                            "isExtinct": r.get("isExtinct")} for r in keep]
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        if (i // BATCH) % 5 == 0:
            print(f"  {min(i + BATCH, len(todo)):,}/{len(todo):,}")
        time.sleep(sleep)
    return cache


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ask", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.4)
    args = ap.parse_args()

    entries = read_index()
    print(f"Schmidt 색인 항목 {len(entries):,}개 (Tafel 이 적힌 것)")

    # 쪽마다 어떤 속이 있나
    by_tafel: dict[int, set[str]] = collections.defaultdict(set)
    for genus, ep, tafeln in entries:
        for t in tafeln:
            by_tafel[t].add(genus)
    print(f"Tafel {len(by_tafel):,}쪽 · 한 쪽 평균 속 "
          f"{sum(len(v) for v in by_tafel.values()) / len(by_tafel):.1f}개")

    # 후보 조합: 같은 쪽의 **다른** 속 + 그 종소명
    combos: dict[str, list[tuple[str, str, int]]] = collections.defaultdict(list)
    for genus, ep, tafeln in entries:
        for t in tafeln:
            for other in by_tafel[t]:
                if other != genus:
                    combos[f"{other} {ep}"].append((genus, ep, t))
    print(f"물어볼 조합 {len(combos):,}개")

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if not args.no_ask:
        cache = ask(sorted(combos), cache, args.sleep)

    # 원래 이름이 실재하는가 — **119 가 안 본 근거다**
    master = {r["이름"]: r for r in
              csv.DictReader(MASTER.open(encoding="utf-8"), delimiter="\t")}

    def exists(name: str) -> bool:
        r = master.get(name)
        return bool(r and r["재판정"] == "확정")

    rows = []
    for cand, uses in combos.items():
        if not cache.get(cand):
            continue
        rec = cache[cand][0]
        other = cand.split()[0]
        for genus, ep, t in uses:
            orig = f"{genus} {ep}"
            rows.append({"tafel": t, "원래": orig, "후보": cand, "→속": other,
                         "원래있나": exists(orig), "상태": rec.get("status") or "",
                         "화석": "화석" if rec.get("isExtinct") else "",
                         "저자": rec.get("authority") or ""})

    # 119 의 규칙 — **한 쪽에서 여럿이 같은 속으로 몰리는 것만 진짜다**
    cluster = collections.Counter((r["tafel"], r["원래"].split()[0], r["→속"])
                                  for r in rows)
    # **경쟁 후보를 함께 본다.** 한 쪽의 모든 속과 짝지으므로 Tafel 26 은
    # `→Amphora` 18 옆에 `→Stauroneis` 9 · `→Eunotia` 6 이 같이 선다. 몰림 수만
    # 보면 셋 다 그럴듯한데, 실제 답은 하나다(119 가 PDF 로 확인했다)
    rival: dict[tuple, list] = collections.defaultdict(list)
    for (t, frm, to), n in cluster.items():
        rival[(t, frm)].append((n, to))
    for k in rival:
        rival[k].sort(reverse=True)
    # **큰 속은 우연히 걸린다.** 확정 목록에서 그 속의 종 수를 세어 함께 적는다
    size = collections.Counter(n.split()[0] for n, r in master.items()
                               if r["재판정"] == "확정")
    for r in rows:
        frm = r["원래"].split()[0]
        r["몰림"] = cluster[(r["tafel"], frm, r["→속"])]
        alts = rival[(r["tafel"], frm)]
        r["으뜸"] = alts[0][1] == r["→속"] and (len(alts) == 1 or alts[0][0] > alts[1][0])
        r["경쟁"] = ", ".join(f"{to} {n}" for n, to in alts[:3])
        r["속크기"] = size.get(r["→속"], 0)
        # **으뜸이 아니면 세기를 한 칸 내린다** — 같은 쪽에서 더 많이 몰린
        # 다른 속이 있으면 이쪽이 답일 가능성이 그만큼 낮다
        base = ("강함" if not r["원래있나"] and r["몰림"] >= 2 else
                "중간" if not r["원래있나"] or r["몰림"] >= 3 else "약함")
        r["세기"] = base if r["으뜸"] else {"강함": "중간", "중간": "약함"}.get(base, "약함")

    names = {r["원래"] for r in rows}
    strong = sorted({r["원래"] for r in rows if r["세기"] == "강함"})
    print(f"\n후보가 붙은 색인 이름 {len(names):,}개 "
          f"(119 는 33개였다 — extant_only 를 빠뜨려 화석이 빠져 있었다)")
    for k in ("강함", "중간", "약함"):
        print(f"  {k} {len({r['원래'] for r in rows if r['세기'] == k}):,}")

    rows.sort(key=lambda r: (-r["몰림"], r["tafel"], r["원래"]))
    L = ["# Schmidt 속명 복원 후보 — 다시 뽑음 (2026-08-14)", "",
         "119 의 후보 목록을 `extant_only=false` 로 다시 뽑은 것입니다.",
         f"후보가 붙은 이름 **{len(names):,}개** (119 때는 33개 — 화석이 빠져 있었습니다).", "",
         "**세기**는 셋으로 읽습니다.", "",
         "- **강함** — 색인의 이름이 WoRMS 에 없고, 같은 쪽에서 **둘 이상**이 같은 속으로 몰린다",
         "- **중간** — 둘 중 하나만 성립한다",
         "- **약함** — 둘 다 실재해서 쪽을 열기 전에는 못 가른다 (종소명이 흔해 나는 잡음)", "",
         "**후보는 후보입니다.** 고치는 것은 해당 Tafel 해설면을 열어 사람이 합니다 (119 §7).", "",
         "**같은 쪽의 모든 속과 짝지으므로 경쟁 후보가 함께 섭니다.** Tafel 26 은",
         "`→Amphora` 18 옆에 `→Stauroneis` 9 · `→Eunotia` 6 이 같이 서는데 실제 답은",
         "*Amphora* 하나입니다(119 가 PDF 로 확인). **그 쪽에서 으뜸이 아닌 후보는 세기를**",
         "**한 칸 내렸고**, `경쟁` 칸에 같은 쪽의 다른 후보를 함께 적었습니다.", "",
         "`속 크기` 는 그 속이 확정 목록에 가진 종 수입니다 — **큰 속일수록 우연히 걸립니다.**", "",
         "| Tafel | 색인의 이름 | 이렇게 읽힐 수 있다 | 세기 | 몰림 | 같은 쪽 경쟁 | 속 크기 | 원래 이름이 WoRMS 에 | 후보의 상태 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['tafel']} | *{r['원래']}* | *{r['후보']}* {r['화석']} | "
                 f"**{r['세기']}** | {r['몰림']}{' 으뜸' if r['으뜸'] else ''} | "
                 f"{r['경쟁']} | {r['속크기']} | "
                 f"{'있다' if r['원래있나'] else '**없다**'} | {r['상태']} |")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n→ {OUT}")

    print("\n한 쪽에서 같은 속으로 몰리는 것 (119 가 진짜라고 한 모양):")
    for (t, frm, to), n in cluster.most_common(12):
        if n >= 2:
            print(f"   Tafel {t:4d}  {frm} → {to}  {n}건")
    if strong:
        print(f"\n**강함 {len(strong)}개**: {', '.join(strong[:14])}"
              + (" …" if len(strong) > 14 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
