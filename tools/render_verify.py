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

# --- 2026-08-26 · 잔여 140건 중 "원문을 아직 안 봤다" 32건 -------------------
#
# **위 VERIFIED 와 성격이 같고 대상이 다르다.** 저기는 해설 OCR 로 안 갈리던
# 자리였고, 여기는 **AlgaeBase 에 물어도 안 나온 채 남은 것**이다
# (`algaebase_worklist.py --residual` 의 2층 31건 + 0층 #431).
#
# **도감이 셋이라 칸이 하나 늘었다** — `atlas` 가 `schmidt|korean|east-antarctic`.
# Schmidt 는 `Tafel`, 한국은 `항목 #`, 동남극은 `Plate` 를 `where` 에 적는다.
# 열쇠는 여전히 **쪽**이다(126) — `pdf` 가 색인이 들고 있던 해설 쪽이고,
# 렌더한 쪽 머리에 찍힌 번호로 매번 대조했다.
#
# 칸: 이름 · 도감 · 어디 · PDF쪽 · 그림 · 판정 · 원문 구절
RESIDUAL_VERIFIED = [
    # 속명 약자를 그 쪽에 나온 **다른 속**으로 폈다 (119·149 와 같은 고장).
    # 이것이 여덟으로 제일 많다 — 등록부에 물어서는 원리적으로 안 풀린다
    ("Amphiprora complanata", "schmidt", "Tafel 26", 68, "45",
     "속명이 잘못 펴졌다 → Amphora complanata Grunow",
     "45. Adria, A. complanata Grunow. O. E."),
    ("Amphiprora nana", "schmidt", "Tafel 26", 68, "67.68",
     "속명이 잘못 펴졌다 → Amphora nana Gregory",
     "67.68. Villesville, A. nana Gregory, forma parva."),
    ("Cosmiodiscus fasciculatus", "schmidt", "Tafel 57", 130, "9.10",
     "속명이 잘못 펴졌다 → Coscinodiscus fasciculatus A. S.",
     "9.10. Cuxhaven, C. fasciculatus A. S., nach Grunow = Heterostephania Rothi"),
    ("Cosmiodiscus marginulatus", "schmidt", "Tafel 57", 130, "5",
     "속명이 잘못 펴졌다 → Coscinodiscus marginulatus var. curvato-striata Grunow",
     "5. Camp. Bank, C. marginulatus var. curvato-striata Grunow."),
    ("Cosmiodiscus senarius", "schmidt", "Tafel 57", 130, "24",
     "속명이 잘못 펴졌다 → Coscinodiscus senarius A. S.",
     "24. Barbadoes, Springf., C. senarius A. S."),
    ("Cosmiodiscus subtilis", "schmidt", "Tafel 57", 130, "11.12",
     "속명이 잘못 펴졌다 → Coscinodiscus subtilis E.",
     "11. Yokohama … 13. Arica, 14. Peru Guano, C. subtilis E. / 12. Moron, C. subtilis ??"),
    ("Cosmiodiscus symmetricus", "schmidt", "Tafel 57", 130, "26",
     "속명이 잘못 펴졌다 → Coscinodiscus symmetricus Grev.",
     "26. Golf v. Mexico, 27. Singapore, C. symmetricus Grev. t. Weissfl."),
    ("Craspedodiscus minor", "schmidt", "Tafel 58", 132, "39",
     "속명이 잘못 펴졌다 → Coscinodiscus minor E.",
     "39. Tafelbai, C. minor E. / 40. … der echte C. minor E. Microg. XXII, 7, "
     "denn kein anderer Coscinodiscus dieses Materials"),
    ("Gomphonema herculeana", "schmidt", "Tafel 215", 146, "4·10·11·13",
     "속명이 잘못 펴졌다 → Gomphoneis herculeana (Ehr.)",
     "1. … Gomphoneis Mamilla (Ehr.) / 10. 12. … G. herculeana (Ehr.)"),

    # 괄호 안 이명이라 그 쪽의 항목이 아니다 — 그래도 학명이기는 하다
    ("Cosmiodiscus armatus", "schmidt", "Tafel 57", 130, "4",
     "괄호 안 이명이다 — 원문 항목은 Coscinodiscus armatus Grev. var. 다",
     "4. Richmond, Virgin. 990:1, Coscinodiscus armatus Grev. var. "
     "(= Cosmiodiscus armatus Grev. 1866.)"),

    # 학명이 아니다 — 물어봐야 "없다" 만 나온다
    ("Fragilaria spec", "schmidt", "Tafel 297", 118, "77—78",
     "원문이 산문이다 — 항목은 Navicula (Diadesmis) confervacea Kg. 이고 "
     "`Fragilaria spec.` 은 그 뒤 설명 문장이다",
     "77—78. Java, r. S. Navicula (Diadesmis) confervacea Kg. / "
     "Von E. Thum als Fragilaria spec. ausgegeben."),

    # 원문이 학명이라고 보증한다 — 등록부에만 없다.
    # **저자·간행 사정을 원문이 함께 말해 주는 자리가 있다**(MS 명·nov. comb.)
    ("Pseudauliscus udiensis", "schmidt", "Tafel 439", 190, "6",
     "원문에 학명으로 있다 — 다만 Debes 의 원고명(MS. 1923)이라 "
     "등록부에 없는 것이 맞다",
     "6. (1000/1). Udi, Gouv. Charkow, Rußland, f. m. Pseudauliscus udiensis Debes, MS. 1923."),
    ("Lepidodiscus sublimus", "schmidt", "Tafel 453", 218, "22, 23",
     "원문에 학명으로 있다 — 같은 Debes 원고명이고 여기서 nov. spec. 으로 냈다",
     "22, 23. Ananino, Simbirsk, f. m. Lepidodiscus sublimus Debes, nov. spec. (MS. 1923)."),
    ("Stictodiscus compar", "schmidt", "Tafel 447", 206, "6",
     "원문에 학명으로 있다 — Hustedt 가 이 쪽에서 낸 nov. comb. 다",
     "6. Tamatave, Madagascar, r. m. Stictodiscus compar (A. S.) nov. comb. Vgl. T. 81, F. 11"),
    ("Cyclotella hispalensis", "schmidt", "Tafel 222", 160, "33.34",
     "원문에 학명으로 있다 — 이 쪽에서 세운 새 종이다(n. sp.)",
     "33. 34. Sevilla, foss. S.: C. hispalensis n. sp."),
    ("Hemiaulus amplectens", "schmidt", "Tafel 143", 304, "1—3",
     "원문에 학명으로 있다 — 원문이 철자를 못 박는다(nicht amplectans!)",
     "1—3. Oamaru (Weissfl.), Hemiaulus amplectens Gr. & St., nicht amplectans!"),
    ("Asterolampra stellaris", "schmidt", "Tafel 202", 120, "13",
     "원문에 학명으로 있다 — 저자가 Br. & T. 로 찍혀 있다",
     "13. Sendai (Kinker), Asterolampra stellaris Br. & T."),
    ("Coscinodiscus pilosus", "schmidt", "Tafel 148", 10, "8",
     "원문에 학명으로 있다 — 저자가 A. S. 로 찍혀 있다",
     "8. S. Monica (Weissfl.), Coscinodiscus pilosus A. S."),
    ("Mastogloia bullata", "schmidt", "Tafel 186", 86, "36",
     "원문에 학명으로 있다 — 저자가 A. S. 로 찍혀 있다. "
     "색인의 그림 번호 86 은 36 의 오독이다(이 쪽은 44 에서 끝난다)",
     "36. (unde?), M. bullata A. S."),
    ("Mastogloia lineolata", "schmidt", "Tafel 186", 86, "33",
     "원문에 학명으로 있다 — 저자가 A. S. 이고 원문이 이명까지 말한다(M. acuta Grunow)",
     "33. Malabar (Weissfl.), M. lineolata A. S. Brun, Cleve und Grove ziehen diese Form "
     "zu M. acuta Grunow."),
    ("Navicula navigans", "schmidt", "Tafel 174", 62, "1",
     "원문에 학명으로 있다 — 저자가 Brun 이고 원문이 Cleve 의 자리도 말한다",
     "1. S. Monica, masse flottante (Brun), Navicula navigans Brun; "
     "nach Cleve Diploneis Pandura var."),
    ("Navicula rostochiensis", "schmidt", "Tafel 243", 8, "12",
     "원문에 학명으로 있다 — 저자가 Heiden 이다(이 Tafel 을 낸 사람이다)",
     "12. Rostock i. M., Moorerde: Navicula rostochiensis Heiden."),
    ("Navicula scutelliformis", "schmidt", "Tafel 192", 98, "57",
     "원문에 학명으로 있다 — Cleve 의 판정이고 원문은 f. minuta 까지 적는다",
     "57. Loka, nach Cleve Navicula scutelliformis f. minuta."),
    ("Rouxia leventerae", "east-antarctic", "Plate 8", 15, "6",
     "원문에 학명으로 있다 — 저자가 Bohaty 다. 화석 규조라 등록부가 성글다",
     "6. Rouxia leventerae Bohaty; sec.1-49, 54.9 cm / SEM 5. Rouxia leventerae Bohaty"),
    ("Asteromphalus hepaticus", "korean", "#238", 76, "",
     "원문에 학명으로 있다 — 저자가 (BRÉBISSON) RALFS 로 찍혀 있다",
     "238. pl. 31 Asteromphalus hepaticus (BRÉBISSON) RALFS"),
    ("Coscinodiscus anguste-lineatus", "korean", "#196", 56, "",
     "원문에 학명으로 있다 — 저자가 A. SCHMIDT 이고 하이픈이 원문에 있다",
     "196. pl. 26 Coscinodiscus anguste-lineatus A. SCHMIDT"),
    ("Pinnularia moralis", "korean", "#528", 210, "",
     "원문에 학명으로 있다 — 저자가 GRUNOW 로 찍혀 있다",
     "528. pl. 61 Pinnularia moralis GRUNOW"),
    ("Neidium preschevalski", "korean", "#493", 195, "",
     "원문에 학명으로 있다 — SKVORTZOW 의 1929 년 서울 채집종이고 "
     "원문은 var. koreana 까지다(색인이 변종을 흘렸다)",
     "493. pl. 58 Neidium Preschevalski SKVORTZOW var. koreana SKVORTZOW"),

    # 원문 자체의 오식 — 고쳐 쓰지 않는다. 바른 이름은 표시가 말한다
    ("Diploneis pandula", "korean", "#460", 184, "",
     "원문 자체의 오식 — 도감이 표제어와 이명 줄에 두 번 pandula 로 찍었다. "
     "바른 이름은 Diploneis pandura (Bréb.) Cleve 이고 "
     "Schmidt Tafel 174 fig 1 이 Diploneis Pandura 로 확인해 준다",
     "460. pl. 55 Diploneis pandula BRÉBISSON / Syn. Navicula pandula BRÉBISSON"),
    ("Frustulia rohmboides", "korean", "#464", 185, "",
     "원문 자체의 오식 — 바른 이름은 Frustulia rhomboides (Ehrenb.) De Toni 이고 "
     "바로 아래 465 번이 같은 쪽에서 rhomboides 로 찍혀 있다",
     "464. pl. 55 Frustulia rohmboides (EHRENB.) DE TONY / "
     "465. pl. 55 Frustulia rhomboides (EHRENB.) DE TONY var. saxonica"),

    # 색인이 원문 표기를 지켰는데 **열쇠를 만드는 자리가 속을 폈다**.
    # `harvest_worms.GENUS_FIX` 가 Chaetoceras→Chaetoceros 로 고치는데
    # 종소명은 원문 그대로라, 나온 열쇠가 **원문도 유효명도 아닌 것**이 된다
    ("Chaetoceros denticulatum", "korean", "#290", 103, "",
     "열쇠가 원문과 다르다 — 원문은 Chaetoceras denticulatum LAUDER 인데 속만 펴서 "
     "만든 열쇠라 등록부에 없다. 바른 이름은 Chaetoceros denticulatus Lauder",
     "290. pl. 38 Chaetoceras denticulatum LAUDER"),
    ("Chaetoceros paradoxum", "korean", "#306", 112, "",
     "열쇠가 원문과 다르다 — 원문은 Chaetoceras paradoxum PAVILLARD 다. 126 의 HOLD "
     "근거를 원본에서 다시 확인했다(새 사실은 없다). Pavillard 판으로 물어야 한다",
     "306. pl. 40 Chaetoceras paradoxum PAVILLARD"),
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


RESIDUAL_OUT = DIADICTION / "names/worms/render_verify_20260826.md"
RESIDUAL_STAMP = "20260826"

# 도감마다 원본 PDF 가 다르다. 쪽을 다시 뜰 때 쓰는 자리 (render_atlas_pages 와 같은 원본)
RESIDUAL_PDF = {"schmidt": "origin/Band{band}.pdf",
                "korean": "origin/korean_flora_diatom.pdf",
                "east-antarctic": "origin/pleistocene_east_antarctic_plates.pdf"}


def residual_report() -> str:
    pages = {(a, w.split()[0] if a == "schmidt" else a, pg)
             for _, a, w, pg, _, _, _ in RESIDUAL_VERIFIED}
    L = [f"# 잔여 32건 — 도감 원문을 렌더해 확인 "
         f"({RESIDUAL_STAMP[:4]}-{RESIDUAL_STAMP[4:6]}-{RESIDUAL_STAMP[6:]})", "",
         f"`algaebase_worklist.py --residual` 의 **2층 31건**(원문을 아직 안 봤다)과",
         f"**0층 #431**을 합한 32건입니다. 도감 원본 **27쪽**을 200 dpi 로 떠서",
         f"눈으로 읽었습니다 — 아래 표가 짚는 것은 {len(pages)}쪽이고, 나머지 둘은",
         "교차 확인만 한 쪽입니다(Band2 p.60 = Tafel 173 의 Hemiaulus 인용,",
         "동남극 p.19 = SEM 도판의 같은 이름).", "",
         "**등록부에 다시 묻는 것으로는 안 풀리는 자리가 절반이었습니다** — 아래 판정",
         "표의 첫 두 갈래가 그것입니다. 물어서 \"없다\" 가 나온 것이 맞았고, 이유가",
         "이름 쪽에 있었습니다.", ""]

    tally = collections.Counter(bucket(v) for *_, v, _ in RESIDUAL_VERIFIED)
    L += ["| 판정 | 수 |", "|---|---|"]
    L += [f"| {k} | {n} |" for k, n in tally.most_common()]
    L += ["", "| 도감 | 자리 | 색인의 이름 | PDF | 그림 | 판정 | 원문 |",
          "|---|---|---|---|---|---|---|"]
    for name, atlas, where, page, fig, v, src in RESIDUAL_VERIFIED:
        L.append(f"| {atlas} | {where} | *{name}* | p.{page} | {fig or '—'} | "
                 f"**{v}** | `{src}` |")
    L += ["", "## 다시 뜨려면", "",
          "```bash",
          "pdftoppm -f <쪽> -l <쪽> -r 200 -png -gray \\",
          "  \"$DIADICTION/origin/<원본>.pdf\" /tmp/p",
          "```", "",
          "`PDF` 칸이 색인이 들고 있던 **해설 쪽**입니다 — 렌더한 쪽 머리에 찍힌",
          "Tafel·항목 번호로 매번 대조했습니다(126 이 정한 대로 **번호가 아니라 쪽으로**",
          "짚습니다). 한국 도감은 PDF 190 쪽까지 텍스트 레이어가 있어 `pdftotext -layout`",
          "으로도 같은 값이 나옵니다 — 여섯은 그렇게 교차 확인했습니다.", ""]
    return "\n".join(L) + "\n"


def residual_check() -> int:
    """**작업지에 있던 32건과 같은가.** 이름이 하나라도 어긋나면 대조표에 못 적는다 —
    열쇠가 표제어라 철자가 한 글자만 달라도 조용히 안 붙는다."""
    import re
    sheet = DIADICTION / f"temp/algaebase_ask_{RESIDUAL_STAMP}.md"
    if not sheet.exists():
        print(f"작업지가 없다 — 검산을 건너뛴다 ({sheet.name})")
        return 0
    want = set()
    text = sheet.read_text(encoding="utf-8")
    for head in ("## 원문을 아직 안 봤다", "## 원문 재판독"):
        if head not in text:
            continue
        for line in text.split(head)[1].split("\n---\n")[0].splitlines():
            if re.match(r"\| \d+ \|", line):
                want.add(line.split("|")[2].strip())
    have = {n for n, *_ in RESIDUAL_VERIFIED}
    miss, extra = sorted(want - have), sorted(have - want)
    print(f"작업지 {len(want)}건 · 확인한 것 {len(have)}건")
    if miss:
        print(f"  아직 안 본 것 {len(miss)}: {miss}")
    if extra:
        print(f"  작업지에 없는 것 {len(extra)}: {extra}")
    return len(miss) + len(extra)


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
    ap.add_argument("--residual", action="store_true",
                    help="2026-08-26 잔여 32건 쪽 보고서를 낸다 (대조표는 안 만진다)")
    args = ap.parse_args()

    if args.strip:
        apply_index(strip=True)
        return 0

    if args.residual:
        RESIDUAL_OUT.write_text(residual_report(), encoding="utf-8")
        print(f"확인한 것 {len(RESIDUAL_VERIFIED)}건 → {RESIDUAL_OUT}")
        return residual_check()

    args.out.write_text(report(), encoding="utf-8")
    print(f"확인한 것 {len(VERIFIED)}건 · 렌더한 쪽 "
          f"{len({(b, p) for _, _, b, p, _, _, _ in VERIFIED})}개 → {args.out}")
    if not args.apply:
        return 0
    apply_index(strip=False)
    return apply_master()


if __name__ == "__main__":
    raise SystemExit(main())
