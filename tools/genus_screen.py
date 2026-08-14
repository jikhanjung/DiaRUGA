#!/usr/bin/env python3
"""Schmidt 해설 원문으로 속명 복원 고장을 전수 검사한다 (119·121 §7).

**왜 이 방법인가.** 119 는 WoRMS 로 후보를 냈고(같은 Tafel 의 다른 속으로
종소명이 존재하는가), 그것으로 세 쪽을 잡았다. 그런데 Tafel 259 를 열어 보니
**정상인데 후보가 6건 붙어 있었다** — 그 쪽은 속명을 줄이지 않고 다 쓰는데,
`Navicula`↔`Pinnularia` 는 종소명이 원래 많이 겹쳐서 WoRMS 만으로는 잡음이 난다.

**고장은 원문이 속명을 줄인 쪽에서만 난다.** 그리고 고장의 모양은 하나다 —
색인이 말하는 속이 그 쪽에서 **표제 자리에 한 번도 안 나온다.**

**표제 자리는 지명 뒤 쉼표다.** 확인된 셋을 나란히 놓으면 바로 보인다.

```
참    1. Barbadoes, Springf.,  Coscinodiscus griseus Grev.
참    1. Silldorf b, Magdeburg, Amphora lyrata Gregory
틀린  … die Aehnlichkeit mit  Craspedodiscus ist eine nur scheinbare
틀린  … Coscinodiscus armatus Grev. var. (= Cosmiodiscus armatus Grev. 1866.)
틀린  … Stauroneis amphoroides Grunow, 0. E. soll = Amphiprora constricta E. sein
```

**두 번 헛짚고 왔다.** 처음엔 "`속명 + 종소명` 꼴로 안 나온다" 로 잡으려 했는데
**지나가는 언급도 종소명을 달고 온다.** 다음엔 횟수로 갈랐는데 **참인 속도 한
번만 나온다** — 첫 항목에서 펴 놓고 그다음은 전부 줄이기 때문이다.
**자기검사가 두 번 다 잡아 줬다** — 확인된 셋이 안 걸리면 판별식이 틀린 것이다.

| Tafel | 색인이 말하는 속 | 원문에서 그 속이 나온 자리 |
|---|---|---|
| 26 | *Amphiprora* | fig 37–39 해설의 **비교 문장** |
| 57 | *Cosmiodiscus* | fig 4 의 **괄호 안 이명** |
| 58 | *Craspedodiscus* | fig 15 의 **부정하는 문장** ("닮은 것은 겉보기일 뿐") |

세 가지 방식이 다 다른데 **"표제로 안 나온다" 는 하나로 잡힌다.** 그래서 이쪽을
근거로 삼는다 — 원문을 읽는 것이라 조회가 필요 없고, 369쪽 전부를 본다.

## 함정

- **독일어는 명사를 다 대문자로 쓴다.** 대문자 낱말을 세면 `Ansicht`·`Abbildung`
  이 속명 자리에 앉고, 지명(`Sumbawa`·`Celebes`)과 저자명(`Arnott`)도 섞인다 —
  **속명 어휘를 WoRMS 에서 가져와 거른다**(로컬 덤프의 속 555개 + 확정 목록의 속)
- **OCR 이라 철자가 흔들린다.** `Coscinodiscus` 가 `Cosecinodiscus` 로도 나온다.
  그렇다고 **앞 6글자로만 맞추면 안 된다** — 저자명 `Grunow` 가 속 `Grunowia` 와
  충돌해 Tafel 26 에서 13번 나오는 주인이 되어 버렸다. **온전한 이름으로 맞추고,
  여유는 여덟 글자 이상인 이름에만 준다**
- **줄인 속명은 머리글자만 남는다**(`C. nitidus`). 그 머리글자로 시작하는 속이
  그 쪽에 여럿이면 어느 것인지 원문만으로는 못 가른다 — **후보를 나열한다**
- **이것도 후보다.** 고치는 것은 사람이 쪽을 보고 한다 (119 §7)

사용:

    python tools/genus_screen.py                 # 전수 검사
    python tools/genus_screen.py --tafel 58      # 한 쪽만 들여다본다
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION, GENUS_FIX  # noqa: E402

INDEX = DIADICTION / "md/schmidt_atlas_name_index.md"
NOTES = [DIADICTION / f"md/schmidt_atlas_band{b}_notes_ocr.md" for b in (1, 2, 3, 4)]
OUT = DIADICTION / "names/worms/genus_screen_20260814.md"

ENTRY = re.compile(r"^- \*\*\*(.+?)\*\*\*(.*)$")
TAFEL_IN_LINE = re.compile(r"Tafel (\d+)")
SECTION = re.compile(r"^## Tafel (\d+)\b")


def read_notes() -> dict[int, str]:
    """해설 OCR 을 Tafel 마다 자른다.

    **같은 번호가 여러 번 나오면 이어 붙인다.** '이어지는 면(추정)' 은 같은
    번호를 달고 오므로 덮어쓰면 마지막 한 쪽만 남는다 — Tafel 240 이 34쪽인데
    그렇게 잘려서 색인 11건이 "원문에 없다" 로 나왔다.
    """
    out: dict[int, str] = {}
    for path in NOTES:
        if not path.exists():
            continue
        cur = None
        buf: list[str] = []
        for line in path.read_text(encoding="utf-8").split("\n"):
            m = SECTION.match(line)
            if m:
                if cur is not None:
                    out[cur] = out.get(cur, "") + "\n" + "\n".join(buf)
                cur, buf = int(m.group(1)), []
            elif cur is not None:
                buf.append(line)
        if cur is not None:
            out[cur] = out.get(cur, "") + "\n" + "\n".join(buf)
    return out


def read_index() -> dict[int, list[tuple[str, str]]]:
    """Tafel 마다 색인이 올려 둔 (속, 종소명)."""
    out: dict[int, list[tuple[str, str]]] = collections.defaultdict(list)
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
        for t in {int(x) for x in TAFEL_IN_LINE.findall(m.group(2))}:
            out[t].append((GENUS_FIX.get(genus, genus), ep))
    return out


def genus_vocab() -> set[str]:
    """규조 속명 어휘 (온전한 이름). **독일어 명사를 거르는 유일한 방법이다.**"""
    vocab: set[str] = set()
    db = DIADICTION / "names/db/worms_diatoms_20260701.db"
    if db.exists():
        import sqlite3
        con = sqlite3.connect(db)
        vocab |= {r[0] for r in con.execute(
            "SELECT DISTINCT genus FROM taxon WHERE genus IS NOT NULL AND genus<>''")}
    # **WoRMS 가 확인해 준 이름의 속만 쓴다.** 대조표의 모든 줄에서 첫 낱말을
    # 가져왔더니 `Grunow`·`Celebes`·`Donkin` 이 속명으로 들어왔다 — 색인
    # 부스러기의 저자명·지명이다. 그것들이 Tafel 26 에서 13번 나와 주인 자리를
    # 차지했다
    master = DIADICTION / "names/worms/worms_master_20260814.tsv"
    if master.exists():
        lines = master.read_text(encoding="utf-8").splitlines()
        head = lines[0].split("\t")
        i왜, i유효 = head.index("재판정"), head.index("유효명")
        for line in lines[1:]:
            cells = line.split("\t")
            if len(cells) <= max(i왜, i유효) or cells[i왜] != "확정":
                continue
            for v in (cells[0], cells[i유효]):
                if v and " " in v:
                    vocab.add(v.split()[0])
    return {v for v in vocab if len(v) >= 5}


def match_genus(token: str, vocab: set[str], loose: dict[str, str]) -> str | None:
    """낱말이 속명인가. **온전히 맞거나, 여덟 글자 이상일 때만 앞자리로 맞춘다.**"""
    if token in vocab:
        return token
    if len(token) >= 8:
        return loose.get(token[:6])
    return None


# 스쳐 간 언급을 이끄는 말들. 이 뒤에 오는 속명은 표제가 아니다
ASIDE = re.compile(r"(?:mit|als|wie|an|auf|bei|zu|zum|zur|von|vergl\.?|siehe|gleich|aehnlich|ähnlich|=|\()\s*$", re.I)


def genera_in(text: str, vocab: set[str]) -> tuple[collections.Counter,
                                                   collections.Counter]:
    """속명을 **표제 자리**와 **스쳐 간 자리**로 갈라 센다.

    표제 자리는 지명 뒤 쉼표이거나 도판 번호 뒤다. 스쳐 간 자리는
    `mit`·`=`·괄호 뒤다 — 머리말의 다섯 줄이 그 근거다.
    """
    loose = {g[:6]: g for g in vocab if len(g) >= 8}
    head, aside = collections.Counter(), collections.Counter()
    for m in re.finditer(r"\b([A-Z][a-zA-Zé]{5,})\b", text):
        k = match_genus(m.group(1), vocab, loose)
        if not k:
            continue
        before = text[max(0, m.start() - 14):m.start()]
        (aside if ASIDE.search(before) else head)[k] += 1
    return head, aside


GERMAN = {"ist", "und", "der", "die", "das", "ein", "eine", "von", "mit", "nur",
          "sind", "wie", "aber", "kommt", "vor", "nicht", "auch", "sich", "oder",
          "des", "dem", "den", "zu", "im", "am", "an", "auf", "bei", "aus",
          "ils", "vergl", "siehe", "var", "forma", "sp", "vielleicht", "wohl"}


def initials_in(text: str) -> collections.Counter:
    """줄인 속명(`C. nitidus`)의 머리글자를 센다."""
    c = collections.Counter()
    for m in re.finditer(r"\b([A-Z])\.\s*([a-zé][a-zé\-]{3,})\b", text):
        if m.group(2).lower() not in GERMAN:
            c[m.group(1)] += 1
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tafel", type=int, help="한 쪽만 본다")
    args = ap.parse_args()

    notes, index = read_notes(), read_index()
    vocab = genus_vocab()
    print(f"속명 어휘 {len(vocab):,}개 (WoRMS 덤프 + 확정 목록)")
    print(f"해설 OCR {len(notes)}쪽 · 색인이 이름을 올린 Tafel {len(index)}쪽")
    both = sorted(set(notes) & set(index))
    print(f"둘 다 있는 쪽 {len(both)}")

    findings = []
    for t in both:
        if args.tafel and t != args.tafel:
            continue
        text = notes[t]
        heads, asides = genera_in(text, vocab)
        inits = initials_in(text)
        claimed = collections.Counter(g for g, _ in index[t])
        for genus, n in claimed.items():
            key = genus
            mine = heads.get(key, 0)
            # **표제 자리에 한 번도 안 나오는데** 같은 머리글자의 다른 속은 나온다
            rivals = sorted(((heads[g], g) for g in heads
                             if g[0] == genus[0] and g != key), reverse=True)
            best = rivals[0] if rivals else (0, "")
            if not (n >= 2 and mine == 0 and best[0] >= 1):
                continue
            findings.append({
                "tafel": t, "속": genus, "색인건수": n, "원문등장": mine,
                "스쳐감": asides.get(key, 0),
                "주인후보": best[1], "후보등장": best[0],
                "줄인머리글자": inits.get(genus[0], 0),
                "그쪽속": ", ".join(f"{g} {heads[g]}"
                                 for _, g in [(heads[g], g) for g in
                                              sorted(heads, key=lambda x: -heads[x])[:4]]),
            })

    # 확인된 셋이 어떻게 잡히는지 먼저 보여 준다
    known = {26: "Amphiprora", 57: "Cosmiodiscus", 58: "Craspedodiscus"}
    print("\n확인된 셋이 이 검사에 걸리는가 (걸려야 검사가 성립한다):")
    for t, g in known.items():
        hit = [f for f in findings if f["tafel"] == t and f["속"] == g]
        print(f"  Tafel {t:3d} {g:16s} {'걸린다 ✓' if hit else '**안 걸린다**'}")

    findings.sort(key=lambda f: (-(f["후보등장"] - f["원문등장"]), -f["색인건수"]))
    print(f"\n걸린 것 {len(findings)}건")

    L = ["# Schmidt 속명 복원 — 해설 원문 전수 검사 (2026-08-14)", "",
         "색인이 어떤 Tafel 에 올려 둔 속이, **그 쪽 해설 원문에 `속명 + 종소명` 꼴로",
         "한 번도 안 나오는** 경우를 모은 것입니다. 확인된 세 쪽이 전부 이 모양이었습니다.", "",
         "| Tafel | 색인이 말하는 속 | 원문에서 그 속이 나온 자리 |",
         "|---|---|---|",
         "| 26 | *Amphiprora* | fig 37–39 해설의 **비교 문장** |",
         "| 57 | *Cosmiodiscus* | fig 4 의 **괄호 안 이명** |",
         "| 58 | *Craspedodiscus* | fig 15 의 **부정하는 문장** |", "",
         "`문장에만` 이 **예**이면 그 속이 글자로는 나오는데 표제가 아니라는 뜻입니다 —",
         "확인된 셋과 같은 모양입니다. `아니오`이면 그 쪽에 아예 안 나오므로 **다른",
         "Tafel 에서 흘러온 것**이거나 색인 파싱이 다른 데서 틀린 것입니다.", "",
         "**OCR 이라 철자가 흔들립니다** — 속명은 앞 6글자로 맞췄고, 표제 판정도 그렇습니다.",
         "**후보입니다.** 고치는 것은 해당 쪽을 열어 사람이 합니다.", "",
         "| Tafel | 색인의 속 | 색인 건수 | 표제 자리 | 스쳐 간 자리 | 진짜 주인 후보 | 그 표제 | 줄인 머리글자 |",
         "|---|---|---|---|---|---|---|---|"]
    for f in findings:
        L.append(f"| {f['tafel']} | *{f['속']}* | {f['색인건수']} | **{f['원문등장']}** | "
                 f"{f['스쳐감']} | *{f['주인후보']}* | {f['후보등장']} | {f['줄인머리글자']} |")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {OUT}")

    print("\n차이가 큰 것부터:")
    for f in findings[:24]:
        mark = " ← 확인 끝" if known.get(f["tafel"]) == f["속"] else ""
        print(f"  Tafel {f['tafel']:4d} {f['속']:16s} 색인 {f['색인건수']:2d}건 · "
              f"표제 0 · 스쳐감 {f['스쳐감']}  →  {f['주인후보']} 표제 {f['후보등장']}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
