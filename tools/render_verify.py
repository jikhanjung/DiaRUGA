#!/usr/bin/env python3
"""해설 원문을 렌더해 눈으로 확인한 것을 대조표에 적는다 (P15 ⑦).

`verify_from_notes.py` 가 **해설 OCR 로** 154건을 갈랐고, 거기서 갈리지 않는
것만 남았다 — OCR 이 흘린 철자와, 해설 OCR 이 아예 없는 Tafel 이다.
그것을 **PDF 쪽을 렌더해 사람이 읽어** 닫은 결과가 이 파일이다.

**이 표는 조회 결과가 아니라 사람이 원문을 본 기록이다.** 그래서 도구가 다시
계산하지 않는다 — 값을 그대로 들고 있다가 대조표(`원문확인` 칸)에 적는다.
근거(쪽·그림 번호·원문 구절)는 보고서 md 로 낸다.

## 여기서 배운 것 — 해설 OCR 의 Tafel 번호를 열쇠로 쓰면 안 된다

`schmidt_atlas_band*_notes_ocr.md` 는 Tafel 머리 숫자를 못 읽은 쪽을
**`이어지는 면(추정)`** 으로 앞 번호에 붙인다. 그런데 그것이 묶음째로
어긋나 있다 — Band4 p.74–86 은 전부 `Tafel 377` 로 달려 있지만 실제로는
**371–377 일곱 쪽**이다. `genus_screen.read_notes` 가 같은 번호를 이어 붙이니
**다른 쪽 본문이 한 Tafel 아래로 들어간다.**

그래서 `Cymbella amphi` 가 *"원문 철자는 amphioxys"* 로 갈렸는데, 그
`Cymbella amphioxys` 는 **Tafel 373 fig 13** 의 것이다. 진짜 Tafel 377
fig 28–30 은 `Cymbella amphi- / cephala var. hercynica` 다 — 줄바꿈으로
잘린 것이었다. **쪽(`PDF p.N`)으로 짚으면 안 걸린다** — 색인은 항목마다
그 쪽을 이미 들고 있고, 렌더한 쪽의 머리에 Tafel 번호가 찍혀 있다.

053(프레임 이름) · 103(판이 여럿) · 119(속명 복원)와 같은 줄이다 — **번호가
겹치거나 어긋나는데 조회가 그것을 모른다.**

## 갈래

| 판정 | 뜻 | 색인은 |
|---|---|---|
| `줄바꿈으로 잘렸다` | 원문이 `lepto- / soma` 로 끊겨 앞동강만 집었다 | 이어 붙인 것이 이름이다 |
| `원문 철자는 …` | OCR 이 흘렸다. 원문은 멀쩡하다 | 원문 철자가 이름이다 |
| `원문 자체의 오식` | **원문이 그렇게 찍혀 있다** | 색인은 맞다. 이름은 따로 적는다 |
| `Verzeichnis 에 학명으로 있다` | 권 뒤 색인 쪽에서 온 항목이다 | 맞다 — 참조가 Tafel N fig M 이다 |
| `원문이 산문이다` | 독일어 낱말이 종소명 자리에 왔다 | 항목이 아니다 |

**원문 자체의 오식은 고쳐 쓰지 않는다.** `Triceratium venustun` 은 Tafel 110
fig 18 에 그대로 그렇게 찍혀 있다(같은 줄의 `ratium` 은 `m` 이 세 다리로
또렷하다). 색인은 원문을 옮긴 것이라 틀리지 않았고, **바른 이름은 표시가
말한다** — 여기를 고쳐 쓰면 인용이 원문과 어긋난다.

사용:

    python tools/render_verify.py             # 보고서 md 를 낸다
    python tools/render_verify.py --apply     # 대조표의 `원문확인` 칸을 채운다

`--apply` 뒤에는 `annotate_index.py` 를 돌려야 색인 표시가 이 판정으로 바뀐다.
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

MASTER = DIADICTION / "names/worms/worms_master_20260814.tsv"
INDEX = DIADICTION / "md/schmidt_atlas_name_index.md"
OUT = DIADICTION / "names/worms/render_verify_20260818.md"
STAMP = "20260818"

# 머리말 블록. **넣을 때와 뺄 때가 같은 모양이어야 왕복한다** (annotate_index 와 같은 규칙).
# 앵커는 그 앞 도구가 넣어 둔 Tafel 블록이다 — 그 뒤에 놓아야 순서가 읽힌다
BLOCK = re.compile(r"\n<!-- 원문-재판독 -->.*?<!-- /원문-재판독 -->\n", re.S)
ANCHOR = "<!-- /Tafel-번호-고침 -->\n"

# 이름 · Tafel · (Band, PDF 해설쪽) · 그림 · 판정 · 원문 구절
#
# **`판정` 에 ` · ` 를 넣지 않는다** — `annotate_index.verdict` 가 마지막
# 조각만 떼어 색인에 싣는다. 넣으면 앞이 잘려 뜻이 반대가 된다.
VERIFIED = [
    ("Triceratium venustun", 110, 1, 238, "18",
     "원문 자체의 오식 — 원문도 venustun 이다, 바른 이름은 Triceratium venustum",
     "18. Archangelsk, nach Witt Triceratium venustun Witt var."),
    ("Coscinodiscus agapetos", 113, 2, 204, "18",
     "Verzeichnis 에 학명으로 있다 — 참조는 Tafel 113 fig 18",
     "113, 18. Coscinodiscus agapetos Rattr."),
    ("Diploneis lineata", 70, 2, 204, "67",
     "Verzeichnis 에 학명으로 있다 — 참조는 Tafel 70 fig 67",
     "70, 67. Diploneis lineata Donk."),
    ("Triceratium campechianum", 78, 2, 204, "18—20",
     "Verzeichnis 에 학명으로 있다 — 참조는 Tafel 78 fig 18—20",
     "78, 18—20. Triceratium campechianum (Grun.?)."),
    ("Auliscus pauper", 125, 2, 204, "5",
     "Verzeichnis 에 학명으로 있다 — 참조는 Tafel 125 fig 5",
     "125, 5. Auliscus pauper Rattr."),
    ("Mastogloia bildet", 185, 2, 84, "",
     "원문이 산문이다 — 속 머리말의 독일어 동사다",
     "Mastogloia bildet dagegen ein streng abgeschlossenes Genus"),
    ("Mastogloia umfasst", 185, 2, 84, "",
     "원문이 산문이다 — 속 머리말의 독일어 동사다",
     "Das Genus Mastogloia umfasst diejenigen Diatomaceen"),
    ("Mastogloia cruclata", 187, 2, 88, "50",
     "원문 철자는 cruciata",
     "50. Cebu (Grove), M. cruciata Leuduger Fortm., nach Brun M. Jelineckiana var."),
    ("Cymbella micro", 373, 4, 78, "20—23",
     "줄바꿈으로 잘렸다 → Cymbella microcephala",
     "20—23. An Steinen im Untersee bei Lunz. Cymbella micro- / cephala Grun."),
    ("Cymbella amphi", 377, 4, 86, "28—30",
     "줄바꿈으로 잘렸다 → Cymbella amphicephala",
     "28—30. Saline Juliushall bei Harzburg. Cymbella amphi- / cephala var. hercynica (A. S.) Cl."),
    ("Gomphonema subclavaturh", 238, 2, 192, "1—11",
     "원문 철자는 subclavatum",
     "Gomphonema subclavatum v. montana Schum."),
    ("Navicula transit", 259, 3, 40, "14.15",
     "원문 철자는 transitans",
     "14. 15. Navicula transitans Cl."),
    ("Navicula peeudo-quatrathres", 259, 3, 40, "23",
     "원문 철자는 pseudo-quadratarea",
     "23. Eis an der Ostküste Grönlands: Navicula pseudo-quadratarea n. sp."),
    ("Pinnularia lepto", 385, 4, 104, "21—25",
     "줄바꿈으로 잘렸다 → Pinnularia leptosoma",
     "21—25. Wasserfall am Südufer des Bedalisees, Java. Pinnularia lepto- / soma Grun."),
    ("Pinnularia rivu", 392, 4, 118, "1",
     "줄바꿈으로 잘렸다 → Pinnularia rivularis",
     "1. Urwaldbach Ajer Upi am Ranausee, Sumatra. Pinnularia rivu- / laris nov. spec."),
    ("Hemidiscus cunei", 436, 4, 184, "5—9",
     "줄바꿈으로 잘렸다 → Hemidiscus cuneiformis",
     "5—9. Südl. Eismeer, Material der Gauß-Exped. Hemidiscus cunei- / formis f. ventricosa (Castr.) Hust."),
    ("Euodia ventri", 436, 4, 184, "1.2",
     "줄바꿈으로 잘렸다 → Euodia ventricosa — Castracane 인용이라 이 쪽의 항목이 아니다",
     "Übergangsformen nach Fig. 3, die von CASTRACANE als Euodia ventri- / cosa var. nov. abgebildet ist"),
    ("Stictodiscus kamische", 448, 4, 208, "1—4",
     "줄바꿈으로 잘렸다 → Stictodiscus kamischevensis",
     "1—4. Kamichew, Rußland. Stictodiscus kamische- / vensis Chen."),
    ("Stictodiscus japo", 452, 4, 216, "7",
     "줄바꿈으로 잘렸다 → Stictodiscus japonicus",
     "7. Ebenda. … mit Stictodiscus japo- / nicus Castr. verbinden"),
    ("Aulacodiscus gigan", 457, 4, 226, "1",
     "줄바꿈으로 잘렸다 → Aulacodiscus giganteus",
     "1. Sendai, Japan. Aulacodiscus gigan- / teus Temp. et Brun"),
    ("Triceratium subquadran", 480, 4, 272, "10",
     "줄바꿈으로 잘렸다 → Triceratium subquadrangulare",
     "10. Indischer Ozean. Triceratium subquadran- / gulare nov. spec."),

    # 아래 여덟은 **손봐야 할 목록에 없던 것들**이다. 쪽을 열러 갔다가 같은
    # 쪽에서 나왔거나(Tafel 149), AlgaeBase 쪽 세션이 넘겨 온 것이다.
    # **그중 셋은 "확정" 으로 통과해 있던 항목이라** 목록만 따라갔으면 못 봤다
    ("Actinoptychus ellipticus", 149, 2, 12, "4",
     "속명이 잘못 펴졌다 → Auliscus ellipticus",
     "4. Oamaru (Grunow), A. ellipticus A. S., verwandt mit A. ovalis Arnott, cf. 125, 3."),
    ("Actinoptychus erinnernde", 149, 2, 12, "2",
     "원문이 산문이다 — fig 2 의 비교 문장이다",
     "die an Actinoptychus erinnernde Abtheilung der Felder"),
    ("Biddulphia pedalis", 149, 2, 12, "18",
     "괄호 안 이명이다 — 원문 항목은 Grovea pedalis A. S. 다",
     "18. Oamaru (Weissfl.), Grovea pedalis A. S. (Biddulphia pedalis Gr. & St.)."),
    ("Achnanthes tenulstriata", 410, 4, 154, "8, 9",
     "원문 철자는 tenuistriata",
     "8, 9. Demerara River, r. S. Achnanthes tenuistriata nov. spec."),
    ("Achnanthes lata", 410, 4, 154, "15—20",
     "원문에 학명으로 있다 — Hustedt 가 이 쪽에서 세운 새 종이다",
     "15—20. Celebes, Wawontoasee. Achnanthes lata nov. spec."),
    ("Cocconeis glacialis", 189, 2, 92, "22",
     "원문에 학명으로 있다 — 저자가 A. S. 로 찍혀 있다",
     "22. Julianenhaab (Gründl.), C. glacialis A. S."),
    ("Cocconeis notabilis", 194, 2, 104, "13",
     "원문에 학명으로 있다 — 저자가 A. S. 로 찍혀 있다",
     "13. Monterey (Weissfl.), C. notabilis A. S., nach Grunow zwar verwandt mit C. pseudom."),
    ("Cocconeis citrina", 198, 2, 112, "28—30",
     "원문에 학명으로 있다 — 저자가 A. S. 로 찍혀 있다",
     "28—30. Cap d. g. H., C. citrina A. S."),
]

# 렌더한 쪽에 찍혀 있던 Tafel 번호와, 해설 OCR 이 그 쪽에 달아 놓은 번호.
# **다르면 OCR 이 틀린 것이다** — 쪽은 색인이 들고 있던 값이라 맞았다.
MISLABELED = [
    (1, 238, 110, "Tafel 109 — 이어지는 면(추정)"),
    (1, 244, 113, "Tafel 118"),
    (2, 84, 185, "Tafel 188 — 이어지는 면(추정)"),
    (2, 88, 187, "Tafel 188 — 이어지는 면(추정)"),
    (4, 78, 373, "Tafel 377 — 이어지는 면(추정)"),
]


def bucket(v: str) -> str:
    """판정을 갈래로 줄인다. **철자는 낱말마다 다르니 머리만 센다.**"""
    if v.startswith("원문 철자는"):
        return "원문 철자는 …"
    return v.split(" —")[0].split(" →")[0].strip()


def report() -> str:
    L = [f"# Schmidt 색인 — 해설 원문을 렌더해 확인 ({STAMP[:4]}-{STAMP[4:6]}-{STAMP[6:]})",
         "",
         f"해설 OCR 로는 갈리지 않던 **{len(VERIFIED)}건**을 PDF 쪽 "
         f"**{len({(b, p) for _, _, b, p, _, _, _ in VERIFIED})}개**를 렌더해 눈으로 확인했습니다.",
         "`verify_from_notes.py` 가 남긴 자리(원문 철자·해설 OCR 이 없는 Tafel)입니다.",
         ""]

    tally = collections.Counter(bucket(v) for *_, v, _ in VERIFIED)
    L += ["| 판정 | 수 |", "|---|---|"]
    L += [f"| {k} | {n} |" for k, n in tally.most_common()]
    L += ["",
          "| Tafel | 색인의 이름 | PDF | 그림 | 판정 | 원문 |",
          "|---|---|---|---|---|---|"]
    for name, t, band, page, fig, v, src in VERIFIED:
        L.append(f"| {t} | *{name}* | Band{band} p.{page} | {fig or '—'} | "
                 f"**{v}** | `{src}` |")

    L += ["", "## 해설 OCR 의 Tafel 번호가 묶음째로 어긋난다", "",
          "렌더한 쪽 머리에 찍힌 번호와, 해설 OCR 이 그 쪽에 달아 둔 번호입니다.",
          "**쪽 번호는 맞았습니다** — 색인이 항목마다 들고 있는 `PDF p.N` 이 그것입니다.", "",
          "| PDF | 원문에 찍힌 것 | 해설 OCR 이 달아 둔 것 |", "|---|---|---|"]
    for band, page, real, claimed in MISLABELED:
        L.append(f"| Band{band} p.{page} | **Tafel {real}** | {claimed} |")
    L += ["",
          "`read_notes` 가 같은 번호를 이어 붙이므로 **다른 쪽 본문이 한 Tafel 아래로**",
          "들어갑니다. `Cymbella amphi` 가 그래서 *Tafel 373* 의 `amphioxys` 로 갈렸습니다.",
          "**해설 OCR 로 낸 판정은 쪽으로 짚어 확인하고 쓰세요.**", ""]
    return "\n".join(L) + "\n"


def apply_master() -> int:
    lines = MASTER.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    if "원문확인" not in head:
        head.append("원문확인")
    at = head.index("원문확인")
    # **`렌더 확인` 을 값 안에 적는다.** 08-14 의 해설 OCR 판정과 같은 칸을 쓰는데,
    # 근거의 무게가 다르다 — 표시를 다는 쪽(`annotate_index`)이 그것을 보고 가른다
    by = {name: f"T{t} · 렌더 확인 — {v}" for name, t, _, _, _, v, _ in VERIFIED}

    rows, filled, changed = [], 0, []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        cells += [""] * (len(head) - len(cells))
        want = by.get(cells[0])
        if want:
            if cells[at] and cells[at] != want:
                changed.append((cells[0], cells[at], want))
            cells[at] = want
            filled += 1
        rows.append(cells)

    MASTER.write_text("\t".join(head) + "\n"
                      + "".join("\t".join(c) + "\n" for c in rows), encoding="utf-8")
    print(f"대조표 {filled}줄에 `원문확인` 을 적었다 → {MASTER.name}")
    if changed:
        # **해설 OCR 이 낸 판정을 덮은 자리다.** 조용히 덮으면 왜 바뀌었는지가 없다
        print(f"\n해설 OCR 판정을 덮은 것 {len(changed)}건:")
        for name, was, now in changed:
            print(f"  {name}\n     전 {was}\n     후 {now}")
    missing = [n for n in by if n not in {r[0] for r in rows}]
    if missing:
        print(f"\n대조표에 없는 이름 {len(missing)}: {missing}")
    return len(missing)


def apply_index(strip: bool) -> None:
    """색인 머리말에 이번 재판독을 적는다. **항목 줄은 안 건드린다** —
    항목에 붙는 표시는 `annotate_index.py` 하나가 담당한다(표시를 다는 도구가
    둘이 되면 서로의 것이 줄 끝이 아니게 되어 안 걷힌다 · 124)."""
    text = INDEX.read_text(encoding="utf-8")
    text = BLOCK.sub("", text)
    if not strip:
        mis = " · ".join(f"Band{b} p.{p}=Tafel {r}" for b, p, r, _ in MISLABELED)
        block = f"""
<!-- 원문-재판독 -->
> **원문을 렌더해 {len(VERIFIED)}건을 확인했습니다** (2026-08-18, `tools/render_verify.py`).
> 해설 OCR 로는 갈리지 않던 자리입니다 — 잘린 철자, 그리고 **해설 OCR 이 없는 Tafel**.
> 항목마다의 결과는 아래 〔WoRMS … 원문 확인: …〕 에 실려 있고, 근거(쪽·그림·원문
> 구절)는 `names/worms/render_verify_{STAMP}.md` 에 있습니다.
>
> ⚠️ **해설 OCR(`schmidt_atlas_band*_notes_ocr.md`)의 Tafel 번호를 열쇠로 쓰지
> 마세요.** 번호가 묶음째로 어긋나 있습니다 — 확인한 것: {mis}.
> 머리 숫자를 못 읽은 쪽이 `이어지는 면(추정)` 으로 **앞 번호에 붙어**, 다른 쪽
> 본문이 한 Tafel 아래로 들어갑니다. 이 색인의 `PDF p.N` 은 맞으니 **쪽으로
> 짚으세요** — 렌더한 쪽 머리에 Tafel 번호가 찍혀 있습니다.
<!-- /원문-재판독 -->
"""
        text = text.replace(ANCHOR, ANCHOR + block, 1)
    INDEX.write_text(text, encoding="utf-8")
    print(f"색인 머리말을 {'걷었다' if strip else '적었다'} → {INDEX.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--apply", action="store_true", help="대조표에 적는다")
    ap.add_argument("--strip", action="store_true", help="색인 머리말을 걷는다")
    args = ap.parse_args()

    if args.strip:
        apply_index(strip=True)
        return 0

    args.out.write_text(report(), encoding="utf-8")
    print(f"확인한 것 {len(VERIFIED)}건 · 렌더한 쪽 "
          f"{len({(b, p) for _, _, b, p, _, _, _ in VERIFIED})}개 → {args.out}")
    if not args.apply:
        return 0
    apply_index(strip=False)
    return apply_master()


if __name__ == "__main__":
    raise SystemExit(main())
