# 잔여 32건을 원문으로 닫는다 — 등록부가 못 하는 자리였다 (2026-08-26)

`tools/render_verify.py --residual` · 근거는
`Diadiction/names/worms/render_verify_20260826.md`

## 무엇을 다시 봤나

[158](20260826_158_algaebase-residual-refresh.md) 이 낸 잔여 140건 중
**"원문을 아직 안 봤다" 31건과 "원문 재판독" 1건(#431)**, 모두 32건이다.
작업지가 그 자리에 **"등록부에서 안 나오면 그대로 두셔도 됩니다 — 나중에
원문 쪽을 렌더해서 확인할 자리입니다"** 라고 적어 두었고, 그 "나중" 을 지금 했다.

도감 원본 **27쪽**을 200 dpi 로 떠서 읽었다(Schmidt 17 · 한국 8 · 동남극 2).
쪽은 색인이 항목마다 들고 있는 `pdf_page` 를 그대로 썼고, 렌더한 쪽 머리에
찍힌 Tafel·항목 번호로 매번 대조했다 — **126 이 정한 대로 번호가 아니라 쪽으로
짚는다.** 한국 도감은 PDF 190쪽까지 텍스트 레이어가 있어 여섯은 `pdftotext
-layout` 으로 교차 확인했다.

## 판정 — 절반은 등록부에 물어서는 원리적으로 못 푼다

| 판정 | 수 |
|---|---|
| 원문에 학명으로 있다 | 17 |
| **속명이 잘못 펴졌다** | **9** |
| 원문 자체의 오식 | 2 |
| 열쇠가 원문과 다르다 | 2 |
| 괄호 안 이명이다 | 1 |
| 원문이 산문이다 | 1 |

**제일 큰 것이 속명 복원 고장이고 아홉이다** — 119·149 와 같은 줄이다.
해설이 `C. subtilis E.` 처럼 **속을 약자로** 쓰는데, 색인을 만들 때 그 약자를
**그 쪽에 등장한 다른 속**으로 폈다.

- **Tafel 57 하나에서 여섯**이 났다. 그 쪽의 속은 *Coscinodiscus* 인데
  (fig 31·33 이 `Actinocyclus curvatulus … zum Vergleich mit Coscinodiscus
  curvatulus`·`C. curvatulus Grunow` 로 짝을 지어 못 박는다), fig 4 의 괄호
  `(= Cosmiodiscus armatus Grev. 1866.)` 하나 때문에 **`C.` 가 전부
  *Cosmiodiscus* 로 펴졌다.** 그 괄호의 주인 `Cosmiodiscus armatus` 만 진짜다
- **Tafel 26 에서 둘** — 그 쪽은 *Amphora* 인데 fig 37—39 의 산문에 나온
  `Amphiprora constricta E.` 때문에 `A. complanata`·`A. nana` 가
  *Amphiprora* 가 됐다
- **Tafel 215 에서 하나** — `G. herculeana` 의 `G.` 는 *Gomphoneis* 다
  (fig 1 이 `Gomphoneis Mamilla (Ehr.)`). **종소명이 여성형인 것이 이미
  말하고 있었다** — *Gomphonema* 는 중성이라 `herculeanum` 이어야 한다

**갈래가 하나 더 있다 — 원문을 봐야 "없는 것이 맞다" 를 알 수 있는 자리다.**

- `Pseudauliscus udiensis`(T439)·`Lepidodiscus sublimus`(T453)는 둘 다
  **Debes 의 원고명(MS. 1923)** 이다. 등록부에 없는 것이 맞고, 아무리 다시
  물어도 안 나온다. **둘이 같은 자리에서 왔다는 것도 원문이 말해 준다**
- `Fragilaria spec`(T297)은 이름이 아니다 — 항목은
  `Navicula (Diadesmis) confervacea Kg.` 이고, `Von E. Thum als Fragilaria
  spec. ausgegeben.` 이 그 뒤 설명 문장이다. **`spec.` 이 종소명 자리에 온
  것**이라 148 이 걸러 낸 독일어 낱말과 같은 갈래다
- `Stictodiscus compar`(T447)는 Hustedt 가 그 쪽에서 낸 `nov. comb.`,
  `Cyclotella hispalensis`(T222)는 그 쪽에서 세운 `n. sp.` 다.
  **간행 자리가 곧 이 쪽이다**

## 도감이 스스로 검산해 준 자리 둘

**같은 쪽·다른 도감이 바른 철자를 들고 있었다.** 오식을 고쳐 쓰지 않는다는
규칙(126)이 성립하려면 바른 이름을 어디선가 가져와야 하는데, 둘 다 원문 안에
있었다.

- `Frustulia rohmboides`(한국 #464) — **바로 아래 #465 가 같은 쪽에서
  `Frustulia rhomboides (EHRENB.) DE TONY var. saxonica` 로 찍혀 있다**
- `Diploneis pandula`(한국 #460) — 도감이 표제어와 `Syn.` 줄에 **두 번**
  `pandula` 로 찍었다. 바른 이름 *Diploneis pandura* 는 **Schmidt Tafel 174
  fig 1** 이 준다: `Navicula navigans Brun; nach Cleve Diploneis Pandura var.`
  **그 fig 1 이 이번 32건 중 하나(#1262)였다** — 한 쪽을 읽으러 갔다가 다른
  도감의 항목이 닫혔다

## 색인이 흘린 것 셋

원문을 봐야 보이는 것들이라 여기 적어 둔다. **이번에 고치지는 않았다.**

- `Mastogloia bullata` 의 그림 번호가 색인에 **86** 인데 원문은 **36** 이다
  (Tafel 186 해설은 fig 44 에서 끝난다 — 86 은 없다). 자리는 맞아서 아무것도
  안 깨졌다
- `Neidium Preschevalski SKVORTZOW` 는 원문이 **`var. koreana SKVORTZOW`**
  까지다. 색인이 종까지만 집었다
- `Hemiaulus amplectens` 는 원문이 **`nicht amplectans!`** 라고 못 박는다.
  Tafel 173 fig 16 자리는 항목이 아니라 본문 인용이다

## 열쇠를 만드는 자리가 원문과 어긋난다 (둘)

`Chaetoceros denticulatum`·`Chaetoceros paradoxum` 은 **색인도 원문도 그렇게
안 적혀 있다.** 색인의 표제어는 `Chaetoceras denticulatum LAUDER` 로 원문
그대로인데, `harvest_worms.GENUS_FIX` 가 속만 `Chaetoceras → Chaetoceros` 로
펴고 종소명은 원문 그대로 둬서 **원문도 유효명도 아닌 열쇠**가 나왔다
(유효명은 `Chaetoceros denticulatus`). 등록부가 못 찾는 것이 당연하다.

`GENUS_FIX` 자체는 필요하다 — 없으면 홍조류 *Chaetoceras* 에 규조 55종이
붙는다(그 주석이 `harvest_worms.py` 19줄에 있다). **속만 펴고 종소명을 안
맞추는 것이 문제다.** #431 은 126 이 이미 HOLD 에 적어 둔 자리이고, 이번에는
원본에서 다시 확인만 했다 — **새 사실은 없다.**

## 낸 것 · 검산

- `tools/render_verify.py` 에 **`RESIDUAL_VERIFIED` 32줄**을 더했다.
  기존 `VERIFIED`(08-18)와 성격이 같고 **도감이 셋이라 칸이 하나 늘었다**
  (`atlas`). `--residual` 이 보고서를 내고, **대조표는 안 만진다**
- **검산이 붙어 있다** — `residual_check()` 가 작업지
  (`temp/algaebase_ask_20260826.md`)의 0·2층과 이름을 맞춘다.
  **32 = 32, 어긋남 0.** 이름이 한 글자만 달라도 대조표에 조용히 안 붙는 자리라
  여기서 잡는다

## 아직 안 한 것 — 대조표에 적는 것

`--apply` 는 **안 돌렸다.** 적는 순간 `원문확인` 칸이 바뀌고 그러면
`annotate_index.py` → `parse_atlas.py` → `atlas/*.json` → DB 반입까지 따라간다.
그 전에 정할 것이 둘이다.

1. **`apply_master()` 가 `T{Tafel}` 을 앞에 붙인다** — Schmidt 만 있던 시절의
   모양이다. 한국·동남극은 `#493`·`Plate 8` 이라 그대로 쓰면 어긋난다
2. **`속명이 잘못 펴졌다` 아홉을 색인 표제어까지 고칠 것인가.** 126 은
   `Actinoptychus ellipticus` → `Auliscus ellipticus` 를 **표시로만** 말하고
   표제어는 안 고쳤다(표시를 다는 도구는 `annotate_index.py` 하나여야 한다).
   같은 규칙이면 여기 아홉도 표시로만 간다

**작업지를 다시 낼 필요는 없다** — 지금 나가 있는 140건짜리는 그대로 쓸 수
있고, 이 32건은 **비워서 돌려주시면 된다**(빈 칸이 지금 판정을 못 이긴다).
적용한 뒤에 다시 내면 32건이 목록에서 빠져 **108건**이 된다.
