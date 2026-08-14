# 124 — AlgaeBase 148건을 왕복시킨다

2026-08-14 · `work/20260814-sclee` · [121](20260814_121_name-triage-and-index-marks.md) 의 뒤

AlgaeBase 는 자동으로 못 연다(Turnstile). **사람이 브라우저로 열어 조회해 온다.**
121 에서 그 목록을 추렸고, 이번에 148건이 채워져 돌아와 색인까지 들어갔다.
누적 **448/1,845**.

## 1. 목록을 어떻게 줄였나 — 물어봐야 소용없는 것을 먼저 뺐다

남은 것이 1,545개였다. 그대로 넘기면 **사람이 브라우저를 1,545번 연다.**

121 에서 Schmidt 해설 원문으로 154건을 확인해 뒀다. 거기서 **학명이 아니라고
밝혀진 것은 뺐다** — 등록부에 물어 봐야 "없다" 만 나온다.

| 뺀 것 | 왜 |
|---|---|
| 원문이 산문이다 | 독일어 낱말 (`erinnernde`·`gerechnet`) |
| 제목 줄 조각 | `Diatoma cull` ← `Atlas der Diatomaceenkunde` |
| 괄호 안 이명 · Verzeichnis 줄 | 그 쪽 항목이 아니다 |
| 줄바꿈으로 잘렸다 | **이미 풀렸다** — 이어 붙인 이름을 WoRMS 가 확인해 줬다 |

**148건이 됐다.** 나머지 1,397건은 급하지 않다 — 순번대로 오면 걸린다.

## 2. 돌아올 모양으로 내보냈다

작업지를 `ingest_algaebase.py` 가 읽는 표 모양 그대로 만들어 `temp/` 에 뒀다.
**형식이 어긋나면 사람이 148건을 채워 온 뒤에야 알게 된다** — 그래서 내보내기
전에 왕복을 시험했다. 다섯 갈래가 다 갈리고, 번호 검산을 통과하고, **빈 칸
줄도 148건 전부 잡히는 것**까지 봤다(일부만 채워 와도 조용히 사라지는 줄이
없어야 한다).

채우는 법과 함정 셋(Turnstile 화면은 HTTP 200 이다 · 판정은 상세 페이지의
`Status of Name` 이다 · 갱신 시점을 함께 적어 달라)도 작업지 안에 적었다.
**돌아온 표는 형식이 하나도 안 어긋났고 Turnstile 은 한 건도 안 걸렸다.**

## 3. 길이 규칙을 걷은 것이 여기서 값을 했다

121 에서 "종소명이 짧으면 잘린 낱말" 을 근거에서 뺐다(사용자 지적). 그때
사람에게 돌려보낸 것들이 이번에 **전부 진짜 이름으로 돌아왔다.**

```
Coscinodiscus boliv  → Coscinodiscus boliviensis   Grunow, 갱신 2023-01-17
Navicula transit     → Navicula transitans         Cleve
Cymbella amphi       → Cymbopleura amphicephala
Cymbella micro       → Encyonopsis microcephala
Ditylium sol         → Ditylum sol                 ← 속 철자까지 맞았다
Hemidiscus cunei     → Actinocyclus cuneiformis    ← 줄바꿈 복원과 일치
```

`Hemidiscus cunei` 는 121 에서 `cuneiformis` 로 이어 붙여 WoRMS 가 확인해 준
것인데, AlgaeBase 가 **지금 통용되는 조합**(`Actinocyclus cuneiformis`)까지
준다. 두 근거가 어긋나지 않고 겹친다.

**`Chaetoceros` 열한 건은 성이 안 맞은 것이었다** — `affine`→`affinis` ·
`didymum`→`didymus` · `coarctatum`→`coarctatus`. 한국 도감이 중성으로 적었다.
WoRMS 는 이것들을 통째로 "없다" 고 했다.

## 4. 조회해 온 쪽이 자기 판정을 하나 뒤집었다

`Chaetoceros paradoxum` 을 08-13 보고서에서 "AlgaeBase 에 없음" 으로 적었는데
**틀렸다고 스스로 고쳐 왔다** — 정확 일치만 찾다가 놓쳤고 `Chaetoceros
paradoxus` 가 유효하다. `didymum`→`didymus` 와 같은 구조다.

**같은 실수가 양쪽에서 났다.** 우리는 규칙이 넓어서, 저쪽은 검색이 좁아서다.
어느 쪽이든 **한 번 낸 판정을 다시 볼 길이 있어야** 잡힌다.

## 5. "AlgaeBase 에 없음" 은 "가짜 이름" 이 아니다

68건이 그렇게 왔다. 조회해 온 쪽이 못을 박아 뒀다 — **화석속은 두 DB 다 종
수준이 성글다**(*Auliscus*·*Stictodiscus*·*Triceratium*·*Craspedodiscus*·*Rouxia*).

가장 분명한 예가 **`Rouxia leventerae`** 다. **AlgaeBase 에도 WoRMS 에도 없는데**
남극 규조 층서에서 실제로 쓰는 이름이다. 두 DB 가 못 따라온 것이고 원기재
문헌을 봐야 한다. 짝인 `Rouxia constricta` 는 유효하고 **갱신이 2026-02-12 로
이 목록에서 가장 최근**인데, 과 배치가 아직 `incertae sedis` 라 **과 이름을
확정적으로 적으면 안 된다.**

**이 저장소가 오늘 세 번 겪은 것과 같은 말이다** — 없다는 것과 아니라는 것은
다르다. 121 에서 "덤프에 없다" 를 "WoRMS 에 없다" 로 읽으면 안 된다고 적었고,
여기서는 "두 DB 에 없다" 를 "이름이 아니다" 로 읽으면 안 된다.

## 6. 표시가 스물한 줄에서 늘고 있었다

반입한 뒤 색인을 보니 `Coscinodiscus boliv` 에 AlgaeBase 답이 안 붙어 있었다.
도구는 맞는 값을 냈는데 **색인 줄이 낡아 있었다.**

`annotate_index.py` 가 표시를 걷는 정규식이 **줄 끝에 고정**돼 있었다
(`  〔WoRMS …〕$`). 그런데 `tafel_numbering.py` 가 Verzeichnis 표시를 **뒤에**
하나 더 달면서 내 것이 줄 끝이 아니게 됐다 — 안 걷히고, 다시 돌릴 때마다
**하나씩 늘었다.** 21줄이 그랬고 그 줄들은 낡은 판정을 달고 있었다.

`$` 를 뗐다. 두 칸 + `〔WoRMS` 로 시작하는 것만 걷으므로 한국 색인이 줄바꿈으로
쓰는 **줄 끝 공백 두 칸은 여전히 안 건드린다** — 걷었다 다시 붙이면 그대로다.

**고정이 원래는 그 공백을 지키려고 넣은 것이었다**(121 §5). 지키려던 것은
맞았는데 **지키는 방법이 다른 도구를 못 견뎠다.** 표시를 다는 도구가 둘이 된
순간부터 "내 것이 줄 끝" 이 성립하지 않는다.

## 남은 것

- **AlgaeBase 1,397건** — 순번대로 오면 된다. 급한 자리는 이번에 다 뺐다
- **`Rouxia leventerae` 처럼 두 DB 가 못 따라온 이름** — 원기재 문헌 자리다
- **P15 로 넣을 때의 함정 셋**은 `HANDOFF.md` 3절에 적어 뒀다
