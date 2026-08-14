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

## 고칠 값은 두 쪽에서 세어 맞춰 본다

**되짚기만 쓰면 안 된다.** Band4 의 `Tafel 420` 묶음이 그랬다 — 다음이 433 이라
거꾸로 세면 431~432 가 나오는데, **421–432 는 미간행이라**(README) 그 구간에
번호를 줄 수가 없다. 실제로 p.174 는 419(p.172) 다음이라 **진짜 420 이다.**

**그리고 '이어지는 면' 이 늘 고장인 것도 아니다** — 한 Tafel 의 해설이 두 쪽에
걸치는 일이 실제로 있다(Band1 의 Tafel 48 이 그렇다: 앞이 47, 다음이 49).

그래서 **묶음이 담아야 할 Tafel 수**를 쪽수와 맞춰 본다.

    담아야 할 수 = (다음 Tafel) − (앞 Tafel) − 1

| 담아야 할 수 | 쪽수 | 읽는 법 |
|---|---|---|
| n | n | **쪽마다 한 Tafel** — 앞 Tafel+1 부터 차례로 준다 |
| 1 | n | 한 Tafel 이 여러 쪽에 걸친 것 — 정상이다 |
| 그 밖 | | 사이에 **미간행 Tafel** 이 있다 — 손대지 않는다 |

Band2 p.80(→183)·p.90(→188)을 렌더해 눈으로 확인했고 첫 갈래와 맞는다.
Band4 의 `420` 묶음은 셋째 갈래다 — 다음이 433 인데 쪽은 둘뿐이라 **421–432
미간행 구간**을 건넌다. 손대지 않는다.

## 함정

- **쪽은 안 고친다.** 색인의 `PDF p.N/N+1` 은 맞다 — 도판을 여는 것은 멀쩡하다.
  틀린 것은 **인용에 적힌 Tafel 번호**뿐이다
- **묶음 뒤에 Tafel 이 없으면 못 센다.** Band2 의 마지막 묶음(34쪽)이 그렇다 —
  권의 끝이라 기준이 없다. **계산하지 않고 그대로 둔다**
- **거꾸로 세는 것이 늘 되는 것은 아니다.** 간행 안 된 Tafel 이 사이에 있으면
  건너뛴 만큼 어긋난다 — `Tafel 421–432` 가 미간행이다(README). 계산값이 OCR 이
  읽은 번호보다 **커지면** 앞뒤가 안 맞는 것이라 `되짚음` 칸에 적어 둔다
- **눈으로 확인한 것은 세 장이다** — Band2 p.80(→183)·p.90(→188)·Band4
  p.74(→371). 셋 다 계산과 맞았다. 나머지는 같은 셈으로 낸 것이다

사용:

    python tools/tafel_numbering.py            # 고칠 값을 md 로 낸다
    python tools/tafel_numbering.py --apply    # 색인에 반영한다 (사본을 먼저 뜬다)
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
    """'이어지는 면(추정)' 묶음마다 참 Tafel 을 정한다.

    **앞의 Tafel 은 고쳐진 값을 쓴다** — 묶음이 잇달아 있으면 앞 묶음의 끝이
    다음 묶음의 기준이 되기 때문이다(Band1 의 131·138 이 그렇다).
    """
    out = []
    for b in (1, 2, 3, 4):
        path = DIADICTION / f"md/schmidt_atlas_band{b}_notes_ocr.md"
        secs = [(int(m[1]), bool(m[2]), int(m[3]))
                for m in SECTION.finditer(path.read_text(encoding="utf-8"))]
        i, prev_true = 0, None
        while i < len(secs):
            t, cont, p = secs[i]
            if cont:
                i += 1
                continue
            j = i + 1
            while j < len(secs) and secs[j][1]:
                j += 1
            n = j - i
            nxt = secs[j][0] if j < len(secs) else None
            if n == 1:
                prev_true = t
                i = j
                continue
            need = (nxt - prev_true - 1) if (nxt is not None and prev_true is not None) \
                else None
            per_page = need == n              # 쪽마다 한 Tafel
            one_tafel = need == 1             # 한 Tafel 이 여러 쪽에
            first = (prev_true + 1) if (per_page or one_tafel) else None
            out.append({"band": b, "ocr": t, "첫쪽": p, "쪽수": n,
                        "앞": prev_true, "다음": nxt, "담을수": need,
                        "쪽마다": per_page, "한Tafel": one_tafel, "참첫": first,
                        "쪽들": [p + 2 * k for k in range(n)]})
            if first is not None:
                prev_true = first + (n - 1) if per_page else first
            elif nxt is not None:
                prev_true = nxt - 1
            i = j
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--apply", action="store_true", help="색인의 Tafel 번호를 고친다")
    args = ap.parse_args()

    rs = runs()
    bypage = {}
    for r in rs:
        if r["참첫"] is None:
            continue
        for k, p in enumerate(r["쪽들"]):
            # 한 Tafel 이 여러 쪽에 걸친 것이면 쪽마다 올리지 않는다
            bypage[(r["band"], p)] = (r["참첫"] + (k if r["쪽마다"] else 0), r)

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

    print("\n고칠 묶음:")
    for (b, t), n in per.most_common():
        r = next(x for x in rs if x["band"] == b and x["ocr"] == t)
        print(f"   Band{b} 색인이 적은 Tafel {t:3d} → 참 {r['참첫']}~{r['참첫'] + r['쪽수'] - 1}"
              f"  ({n}건, 해설면 {r['쪽수']}쪽)")
    for r in rs:
        if r["참첫"] is None:
            print(f"   손대지 않는다 — Band{r['band']} OCR:{r['ocr']} p.{r['첫쪽']} "
                  f"({r['쪽수']}쪽) · 앞 {r['앞']} · 다음 {r['다음']} · "
                  f"담아야 할 Tafel {r['담을수']}개인데 쪽은 {r['쪽수']}장")

    L = ["# Schmidt 색인 — Tafel 번호 고칠 값 (2026-08-14)", "",
         "**쪽은 맞고 번호가 틀린 것입니다.** 색인의 `PDF p.N/N+1` 은 정확하니",
         "**도판을 여는 것은 멀쩡합니다** — 틀린 것은 인용에 적힌 Tafel 번호뿐입니다.", "",
         "해설 OCR 이 Tafel 머리 숫자 하나를 잘못 읽으면, 그다음 쪽들이 머리를 못 찾아",
         "**같은 번호의 '이어지는 면(추정)'** 이 됩니다. 한 글자가 여러 쪽으로 번집니다.",
         "고칠 값은 묶음 **다음의 확인된 Tafel 에서 거꾸로 세어** 얻습니다.", "",
         "**Band2 p.80 을 실제로 렌더해 Tafel 183 임을 눈으로 확인했고, 계산과 맞습니다.**",
         "나머지는 같은 방법으로 계산한 것이라 **후보입니다.**", "",
         f"| Band | 색인이 적은 Tafel | 참 Tafel | 해설면 | 고칠 인용 |",
         "|---|---|---|---|---|"]
    for (b, t), n in per.most_common():
        r = next(x for x in rs if x["band"] == b and x["ocr"] == t)
        L.append(f"| {b} | {t} | **{r['참첫']}~{r['참첫'] + r['쪽수'] - 1}** | "
                 f"{r['쪽수']}쪽 | {n}건 |")
    skipped = [r for r in rs if r["참첫"] is None]
    if skipped:
        L += ["", "## 손대지 않은 묶음 (두 셈이 어긋난다)", "",
              "담아야 할 Tafel 수가 쪽수와 안 맞습니다 — 사이에 **미간행 Tafel**이",
              "있다는 뜻이라 번호를 줄 수 없습니다.", "",
              "| Band | OCR 이 읽은 것 | 첫 쪽 | 쪽수 | 앞 Tafel | 다음 Tafel | 담아야 할 수 |",
              "|---|---|---|---|---|---|---|"]
        for r in skipped:
            L.append(f"| {r['band']} | {r['ocr']} | {r['첫쪽']} | {r['쪽수']} | "
                     f"{r['앞']} | {r['다음']} | {r['담을수']} |")
    L += ["", "## 인용마다", "",
          "| 학명 | Band | PDF 쪽 | 색인의 Tafel | 참 Tafel |", "|---|---|---|---|---|"]
    for f in sorted(fixes, key=lambda f: (f["band"], f["쪽"], f["이름"])):
        L.append(f"| *{f['이름']}* | {f['band']} | {f['쪽']} | {f['색인']} | **{f['참']}** |")
    args.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n→ {args.out}")

    if args.apply:
        apply_fixes(bypage)
    return 0


def apply_fixes(bypage: dict) -> None:
    """색인의 인용에서 **Tafel 번호만** 고친다. 쪽은 손대지 않는다.

    한 줄에 인용이 여럿이고 쪽이 서로 다를 수 있어(`Tafel 417 (…p.168); Tafel
    418 (…p.170)`) **인용마다 그 쪽으로 짚어** 바꾼다. 줄을 통째로 다시 쓰면
    다른 인용까지 물든다.
    """
    backup = DIADICTION / "names/index_backup_20260814/schmidt_atlas_name_index.pre-tafelfix.md"
    text = INDEX.read_text(encoding="utf-8")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
        print(f"사본 → {backup}")

    changed = [0]

    def fix(m: re.Match) -> str:
        t, mid, b, p = m.group(1), m.group(2), m.group(3), m.group(4)
        real = bypage.get((int(b), int(p)))
        if real and real[0] != int(t):
            changed[0] += 1
            return f"Tafel {real[0]}{mid}(Band{b} PDF p.{p}/"
        return m.group(0)

    out = []
    for line in text.split("\n"):
        out.append(CITE.sub(fix, line) if ENTRY.match(line) else line)
    text = "\n".join(out)

    note = f"""<!-- Tafel-번호-고침 -->
> **Tafel 번호 {changed[0]}건을 고쳤습니다** (2026-08-14, `tools/tafel_numbering.py`).
> 해설 OCR 이 Tafel 머리 숫자를 잘못 읽으면 그다음 쪽들이 머리를 못 찾아 **같은
> 번호의 '이어지는 면'** 이 되고, 한 글자가 여러 쪽으로 번집니다.
> **쪽(`PDF p.N/N+1`)은 원래 맞았고 손대지 않았습니다** — 도판을 여는 것은
> 그대로입니다. 고친 것은 인용에 적힌 Tafel 번호뿐입니다.
>
> 고친 묶음과 인용 목록은 `names/worms/tafel_numbering_20260814.md` 에 있고,
> 고치기 전 사본은 `names/index_backup_20260814/` 에 있습니다.
> **수가 안 맞아 손대지 않은 묶음 셋**도 그 문서에 적어 두었습니다.
<!-- /Tafel-번호-고침 -->
"""
    text = re.sub(r"<!-- Tafel-번호-고침 -->.*?<!-- /Tafel-번호-고침 -->\n", "",
                  text, flags=re.S)
    at = text.find("\n---\n")
    text = text[:at + 1] + "\n" + note + text[at + 1:]
    INDEX.write_text(text, encoding="utf-8")
    print(f"색인에 반영했다 — 인용 {changed[0]}건")


if __name__ == "__main__":
    raise SystemExit(main())
