#!/usr/bin/env python3
"""Schmidt 색인의 Tafel 번호가 PDF 쪽과 어긋난 자리를 찾아 고칠 값을 낸다 (121 §8).

**속명 고장을 훑다가 다른 고장이 나왔다.** Tafel 188 의 `Melosira` 를 확인하려고
Band2 p.80 을 열었더니 **그 쪽은 Tafel 183 이었다.** 내용은 맞았다 — fig 1 이
`Melosira pontificalis Brun` 으로 색인과 같다. **쪽은 맞고 번호가 틀린 것이다.**

## 어쩌다 그랬나

해설 OCR 이 스스로 표시해 두고 있었다.

```
## Tafel 182  ·  PDF p.78
## Tafel 188  ·  PDF p.80              ← OCR 이 183 을 188 로 잘못 읽었다
## Tafel 188  — 이어지는 면(추정)  ·  p.82
## Tafel 188  — 이어지는 면(추정)  ·  p.84 … p.90
## Tafel 189  ·  PDF p.92
```

**숫자 하나를 잘못 읽자 그다음 다섯 쪽이 Tafel 머리를 못 찾아 전부 "188 이어지는
면" 이 됐다.** 한 글자가 여섯 쪽으로 번졌다.

## 고칠 값은 계산된다

묶음 다음의 확인된 Tafel 에서 거꾸로 센다 — `189 - 6 = 183`. Band2 p.80 을
실제로 렌더해 **Tafel 183 임을 눈으로 확인했고**, 계산과 맞는다.

## 함정

- **쪽은 안 고친다.** 색인의 `PDF p.N/N+1` 은 맞다 — 도판을 여는 것은 멀쩡하다.
  틀린 것은 **인용에 적힌 Tafel 번호**뿐이다
- **묶음 뒤에 Tafel 이 없으면 못 센다.** Band2 의 마지막 묶음(34쪽)이 그렇다 —
  권의 끝이라 기준이 없다. **계산하지 않고 그대로 둔다**
- **거꾸로 세는 것이 늘 되는 것은 아니다.** 간행 안 된 Tafel 이 사이에 있으면
  건너뛴 만큼 어긋난다 — `Tafel 421–432` 가 미간행이다(README). 계산값이 OCR 이
  읽은 번호보다 **커지면** 앞뒤가 안 맞는 것이라 `되짚음` 칸에 적어 둔다
- **이것도 후보다.** 여섯 쪽 중 한 쪽(p.80)만 눈으로 봤다

사용:

    python tools/tafel_numbering.py            # 고칠 값을 md 로 낸다
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402

INDEX = DIADICTION / "md/schmidt_atlas_name_index.md"
OUT = DIADICTION / "names/worms/tafel_numbering_20260814.md"
# **`re.M` 이 없으면 `^` 가 파일 첫 줄에만 걸려 아무것도 안 잡힌다**
SECTION = re.compile(r"^## Tafel (\d+)(\s*—\s*이어지는 면\(추정\))?\s*·\s*PDF p\.(\d+)",
                     re.M)
ENTRY = re.compile(r"^- \*\*\*(.+?)\*\*\*(.*)$")
CITE = re.compile(r"Tafel (\d+)([^()]*)\(Band(\d) PDF p\.(\d+)/")


def runs() -> list[dict]:
    """'이어지는 면(추정)' 묶음을 찾고, 다음 Tafel 에서 거꾸로 세어 참값을 낸다."""
    out = []
    for b in (1, 2, 3, 4):
        path = DIADICTION / f"md/schmidt_atlas_band{b}_notes_ocr.md"
        secs = [(int(m[1]), bool(m[2]), int(m[3]))
                for m in SECTION.finditer(path.read_text(encoding="utf-8"))]
        i = 0
        while i < len(secs):
            t, cont, p = secs[i]
            if cont:
                i += 1
                continue
            j = i + 1
            while j < len(secs) and secs[j][1]:
                j += 1
            n = j - i
            if n > 1:
                nxt = secs[j][0] if j < len(secs) else None
                # **권의 끝이면 기준이 없다 — 계산하지 않는다**
                first = (nxt - n) if nxt is not None else None
                out.append({"band": b, "ocr": t, "첫쪽": p, "쪽수": n,
                            "다음": nxt, "참첫": first,
                            "쪽들": [p + 2 * k for k in range(n)]})
            i = j
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    rs = runs()
    bypage = {}
    for r in rs:
        if r["참첫"] is None:
            continue
        for k, p in enumerate(r["쪽들"]):
            bypage[(r["band"], p)] = (r["참첫"] + k, r)

    fixes, unknown = [], collections.Counter()
    for line in INDEX.read_text(encoding="utf-8").split("\n"):
        m = ENTRY.match(line)
        if not m:
            continue
        name = m.group(1).replace("*", "")
        for t, mid, b, p in CITE.findall(m.group(2)):
            key = (int(b), int(p))
            if key in bypage:
                real, r = bypage[key]
                if real != int(t):
                    fixes.append({"이름": name, "band": int(b), "쪽": int(p),
                                  "색인": int(t), "참": real,
                                  "fig": mid.strip() or "", "묶음": r["ocr"]})
            else:
                for r in rs:
                    if r["band"] == int(b) and r["참첫"] is None \
                            and int(p) in r["쪽들"]:
                        unknown[(int(b), r["ocr"])] += 1

    print(f"'이어지는 면(추정)' 묶음 {len(rs)}개 · 해설면 {sum(r['쪽수'] for r in rs)}쪽")
    print(f"**고칠 인용 {len(fixes):,}건**")
    if unknown:
        print(f"기준이 없어 못 세는 것 {sum(unknown.values())}건 "
              f"({', '.join(f'Band{b} Tafel {t}' for b, t in unknown)})")

    per = collections.Counter((f["band"], f["색인"]) for f in fixes)

    def sane(r: dict) -> bool:
        """OCR 오독은 번호를 **키워** 읽는다 — 계산값이 더 크면 앞뒤가 안 맞는다."""
        return r["참첫"] is not None and r["참첫"] < r["ocr"]

    print("\n묶음별:")
    for (b, t), n in per.most_common():
        r = next(x for x in rs if x["band"] == b and x["ocr"] == t)
        print(f"   Band{b} 색인이 적은 Tafel {t:3d} → 참 {r['참첫']}~{r['참첫'] + r['쪽수'] - 1}"
              f"  ({n}건, 해설면 {r['쪽수']}쪽)"
              + ("" if sane(r) else "   ← **되짚음이 안 맞는다. 미간행 구간을 건넜을 수 있다**"))

    L = ["# Schmidt 색인 — Tafel 번호 고칠 값 (2026-08-14)", "",
         "**쪽은 맞고 번호가 틀린 것입니다.** 색인의 `PDF p.N/N+1` 은 정확하니",
         "**도판을 여는 것은 멀쩡합니다** — 틀린 것은 인용에 적힌 Tafel 번호뿐입니다.", "",
         "해설 OCR 이 Tafel 머리 숫자 하나를 잘못 읽으면, 그다음 쪽들이 머리를 못 찾아",
         "**같은 번호의 '이어지는 면(추정)'** 이 됩니다. 한 글자가 여러 쪽으로 번집니다.",
         "고칠 값은 묶음 **다음의 확인된 Tafel 에서 거꾸로 세어** 얻습니다.", "",
         "**Band2 p.80 을 실제로 렌더해 Tafel 183 임을 눈으로 확인했고, 계산과 맞습니다.**",
         "나머지는 같은 방법으로 계산한 것이라 **후보입니다.**", "",
         f"| Band | 색인이 적은 Tafel | 참 Tafel | 해설면 | 고칠 인용 | 되짚음 |",
         "|---|---|---|---|---|---|"]
    for (b, t), n in per.most_common():
        r = next(x for x in rs if x["band"] == b and x["ocr"] == t)
        L.append(f"| {b} | {t} | **{r['참첫']}~{r['참첫'] + r['쪽수'] - 1}** | "
                 f"{r['쪽수']}쪽 | {n}건 | "
                 f"{'맞는다' if sane(r) else '**안 맞는다 — 미간행 구간?**'} |")
    L += ["", "## 인용마다", "",
          "| 학명 | Band | PDF 쪽 | 색인의 Tafel | 참 Tafel |", "|---|---|---|---|---|"]
    for f in sorted(fixes, key=lambda f: (f["band"], f["쪽"], f["이름"])):
        L.append(f"| *{f['이름']}* | {f['band']} | {f['쪽']} | {f['색인']} | **{f['참']}** |")
    args.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
