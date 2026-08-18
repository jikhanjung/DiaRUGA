# 126 — Schmidt 해설을 렌더해 29건을 닫는다

2026-08-18 · `work/20260818-sclee` · [121](20260814_121_name-triage-and-index-marks.md)·[124](20260814_124_algaebase-round-trip.md) 의 뒤 · P15 ⑦

색인 표제어 2,059개 중 **손봐야 할 것이 Schmidt 에서 165건**이었다. 121 이 해설
OCR 로 159건을 갈랐고, **거기서 갈리지 않는 자리**가 남았다 — OCR 이 흘린 철자와,
해설 OCR 이 아예 없는 Tafel 이다. 그것을 PDF 쪽을 렌더해 눈으로 읽어 닫았다.

**쪽 20개 · 29건.** 도구는 `tools/render_verify.py`, 근거는
`Diadiction/names/worms/render_verify_20260818.md` 에 항목마다 원문 구절까지 있다.

## 1. 해설 OCR 의 Tafel 번호가 묶음째로 어긋나 있다

이것이 오늘의 제일 큰 것이다. **판정 둘이 그래서 틀려 있었다.**

`schmidt_atlas_band*_notes_ocr.md` 는 Tafel 머리 숫자를 못 읽은 쪽을
`이어지는 면(추정)` 으로 **앞 번호에 붙인다.** 그런데 그것이 한 쪽씩이 아니라
묶음째다 — 렌더해 머리를 읽어 보면 이렇다.

| PDF | 원문에 찍힌 것 | 해설 OCR 이 달아 둔 것 |
|---|---|---|
| Band1 p.238 | **Tafel 110** | Tafel 109 — 이어지는 면(추정) |
| Band1 p.244 | **Tafel 113** | Tafel 118 |
| Band2 p.84 | **Tafel 185** | Tafel 188 — 이어지는 면(추정) |
| Band2 p.88 | **Tafel 187** | Tafel 188 — 이어지는 면(추정) |
| Band4 p.78 | **Tafel 373** | Tafel 377 — 이어지는 면(추정) |

Band4 는 p.74–86 **일곱 쪽이 전부 `Tafel 377`** 이다(실제로는 371–377).
`genus_screen.read_notes` 가 같은 번호를 **이어 붙이므로**(240 이 34쪽이라 그렇게
만든 것이다) 다른 쪽 본문이 한 Tafel 아래로 들어간다.

그래서 `Cymbella amphi` 가 *"원문 철자는 amphioxys"* 로 갈렸는데, 그
`Cymbella amphioxys` 는 **Tafel 373 fig 13** 의 것이다. 진짜 Tafel 377 fig 28–30 은
`Cymbella amphi- / cephala var. hercynica` — **줄바꿈에 잘린 것**이었다. 마찬가지로
`Navicula peeudo-quatrathres` 는 이어 붙인 짐작(`peeudoquatrathres`)이 답이 아니라
Tafel 259 fig 23 의 **`Navicula pseudo-quadratarea` n. sp.** 였다.

**053**(프레임 이름이 슬라이드끼리 겹친다) · **103**(판이 여럿인데 조회가 아무거나
집었다) · **119**(속명 복원)와 같은 줄이다. 번호가 어긋나는데 **조회가 그것을
모른다.** 여기서 쓸 열쇠는 번호가 아니라 **쪽**이다 — 색인이 항목마다
`PDF p.N` 을 들고 있고, 렌더한 쪽의 머리에 Tafel 번호가 찍혀 있다. 그 경고를
색인 머리말과 `render_verify.py` 머리말에 적었다.

## 2. Verzeichnis 넷 — 엉뚱한 본문을 보고 "원문에 없다" 가 나왔다

`Diploneis lineata`·`Triceratium campechianum`·`Coscinodiscus agapetos`·
`Auliscus pauper` 넷은 **권 뒤 Verzeichnis(색인) 쪽**에서 온 항목이다. 색인이
그것을 이미 알고 표시까지 달아 뒀는데(`→ 원래 참조는 Tafel 113 fig 18`),
`verify_from_notes` 는 **Tafel 70·78·113·125 의 해설 본문**을 뒤져서
"원문에 없다(제목 줄 조각)" 를 냈다.

Band2 p.204 를 열어 보니 넷이 나란히, **저자명까지 달고** 있었다.

```
70,  67.    Diploneis lineata Donk.
78,  18—20. Triceratium campechianum (Grun.?).
113, 18.    Coscinodiscus agapetos Rattr.
125, 5.     Auliscus pauper Rattr.
```

**항목이 어디서 왔는지가 어디를 볼지를 정한다.** 표시에 그 말이 이미 적혀
있었는데 판정하는 쪽이 그것을 안 읽었다.

## 3. 원문 자체가 오식인 자리 — 고쳐 쓰지 않는다

`Triceratium venustun` 은 Tafel 110 fig 18 에 **그대로 그렇게 찍혀 있다.**
400 dpi 로 키워 보면 같은 줄의 `ratium` 은 `m` 이 세 다리로 또렷한데
`venustun` 은 두 다리다 — OCR 이 흘린 것이 아니다.

색인은 원문을 옮긴 것이라 **틀리지 않았다.** 그래서 표제어를 고치지 않고
**바른 이름(`venustum`)은 표시가 말하게** 뒀다. 여기를 고쳐 쓰면 인용이 원문과
어긋난다 — `Diadiction/README.md` 가 "색인 텍스트를 그대로 인용하지 말라" 고
적어 둔 자리의 반대쪽이다.

같은 이유로 **표제어는 하나도 안 고쳤다.** 철자를 읽어 온 것도 전부 표시로만
싣는다 — 표시를 다는 도구는 `annotate_index.py` 하나여야 하고(124 에서 둘이
되자 표시가 줄마다 늘었다), `--strip` 하나로 색인이 원래 모양으로 돌아간다.

## 4. 목록만 따라갔으면 못 봤을 셋

`Actinoptychus ellipticus` 의 쪽(Tafel 149)을 여는 김에 그 쪽 항목을 전부 셌다.
**셋이 나왔는데 둘은 `확정` 으로 통과해 있던 것들이다.**

| 색인 | 원문 (Band2 p.12) | 무엇 |
|---|---|---|
| *Actinoptychus ellipticus* | fig 4 `A. ellipticus A. S.` | **속명이 잘못 펴졌다 → *Auliscus*** |
| *Actinoptychus erinnernde* | fig 2 `die an Actinoptychus erinnernde …` | 산문 |
| *Biddulphia pedalis* | fig 18 `Grovea pedalis A. S. (Biddulphia pedalis Gr. & St.)` | 괄호 안 이명 |

그 쪽은 fig 1 이 `Auliscus pruinosus`, fig 2 가 `A. fulcratus A. S.` 로 속을 펴
놓았는데, **fig 2 해설의 비교 문장에 한 번 나오는 `Actinoptychus`** 를 복원
규칙이 집었다. 119 의 Tafel 26·57·58·29 와 같은 고장이고 **다섯 번째 쪽**이다.

`genus_screen.py` 는 이 쪽을 **이미 잡아 두었다** — `Actinoptychus` 2회 ·
표제 자리 **0**, 후보로 *Auliscus ellipticus* 를 냈다(약함). 판별식이 맞았고
원문이 그것을 확정해 줬다. 같은 쪽의 `Cerataulus subangulatus`·
`Porodiscus interruptus` 는 **원문에 그 속으로 찍혀 있어** 후보가 기각된다.

## 5. 표시를 다는 규칙 — 근거의 무게를 낱말로 갈랐다

`annotate_index.verdict` 는 `원문확인` 칸의 마지막 조각을 보고 등록부보다 앞세울지
정한다. 08-14 에는 **이름이 아니라는** 판정 넷만 앞섰다(산문·괄호 안·줄바꿈·
원문에 없다). 여기에 **`렌더 확인`** 을 더했다.

낱말로 가른 이유가 있다. 해설 OCR 이 낸 `원문에 학명으로 있다` 91건은 **1절의
어긋난 본문에서 나온 것**이라 등록부를 밀어낼 무게가 아니다. 반대로 렌더로 본
것은 판정이 무엇이든(철자·Verzeichnis·속명·오식) 앞선다. 그래서 값에
`렌더 확인 — ` 을 적어 두고 표시하는 쪽이 그것을 본다.

**AlgaeBase 를 버리지 않고 뒤에 붙였다.** 원문은 *그 쪽에 무엇이 찍혀 있는가*
를 말하고 AlgaeBase 는 *지금 통용되는 이름이 무엇인가* 를 말한다 — 다른 물음이라
한쪽이 다른 쪽을 대신하지 못한다. 실제로 `Biddulphia pedalis` 는 원문이
`(Biddulphia pedalis Gr. & St.)` 를 괄호에 넣고 `Grovea pedalis` 를 표제로 쓰는데
AlgaeBase 도 `이명 → Grovea pedalis` 라 **둘이 겹친다.**

## 6. 옆 세션에서 넘어온 것

AlgaeBase 왕복 쪽(127)이 "등록부로는 원리적으로 안 풀린다" 며 11건을 넘겼다.
**다섯을 닫았다.**

- *Cocconeis* 셋(`glacialis`·`notabilis`·`citrina`)은 **원문에 저자가 `A. S.` 로
  찍혀 있다** — 동명이종 중 A. Schmidt 판이라는 뜻이라 "Schmidt 판 그대로" 가 답이다
- `Chaetoceros ikari`·`paradoxum` 둘은 **Schmidt 가 아니라 한국 도감 것**이고,
  그 색인은 **저자를 달고 있다** — 원문을 열 것도 없었다.
  `299. Chaetoceras Ikari SKVORTZOW` 는 대문자 `Ikari` 가 **종소명 자리**에 있다
  (같은 도감에서 IKARI 가 **저자**로 나오는 줄은 278·311·318 로 따로 있다).
  `306. Chaetoceras paradoxum PAVILLARD` 는 Cleve 도 Peragallo 도 아니다
- `Achnanthes lata`·`tenulstriata` 는 Tafel 410 이 **Hustedt 가 새 종을 세운 쪽**
  이라 등록부가 성긴 것이 당연했다 (`lata` 는 색인이 맞고, `tenulstriata` 는
  원문 철자가 `tenuistriata` 다)

## 남은 것

- **⑧ Tafel 번호에서 손대지 않은 묶음 셋** — 미간행 421–432 을 건너거나 권 끝이라
  셈이 안 서는 자리다. 1절이 그 셈의 전제를 흔든다 — **쪽으로 다시 세울 것**
- **119 의 속명 후보 33개 중 아직 30개**가 남아 있다. 오늘 Tafel 149 하나를
  원문으로 닫았고 같은 쪽에서 둘을 기각했다. `genus_screen` 의 판별식(표제 자리에
  한 번도 안 나온다)이 **또 맞았으니** 나머지도 이 순서로 가면 된다
- **색인에서 뺄 항목**(산문·괄호 안 이명·제목 줄 조각)은 여전히 **안 뺐다.**
  표시만 달려 있다 — P15 반입 때 그 표시를 읽어 거른다
