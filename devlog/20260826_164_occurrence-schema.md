# 출현 기록 층의 DB — `Reference`·`Occurrence` (164)

`web/viewer/models.py` · `ops/import_occurrence.py` · `ops/check_db.py` 12번 ·
P20 2단계

P20 이 설계만 해 두고 "아직 안 만들었다" 고 적어 둔 자리를 채웠다. 1단계
(`tools/parse_occurrence.py`)가 이미 뽑아 둔 `atlas/occurrence/korean.json`
(문헌 15 · 출현 기록 924)을 그대로 반입 대상으로 쓴다 — 새로 뽑지 않았다.

## 표 둘, 그리고 FK 를 매는 자리와 안 매는 자리

```
Reference   문헌 하나 (key·authors·year·kind·title·journal·note)
Occurrence  출현 기록 하나 (source·item_no·binomial·region_raw·region·reference→FK·note)
```

**`Occurrence.reference` 는 FK 다.** `Reference` 와 `Occurrence` 는 같은
반입 안에서 함께 다시 만들어지므로(아래) `AtlasEntry`→`AtlasPlacement` 와
같은 자리다 — CASCADE 로 잃을 것이 없다.

**`Occurrence.source` 는 FK 가 아니다.** `Atlas.key`(지금은 `korean`) 나
앞으로 올 논문의 `Reference.key` 를 담는 문자열이다 — `Atlas` 는
`ops/import_atlas.py` 가 통째로 갈아치우는 표라 거기 FK 를 매는 순간 반입이
도는 날 CASCADE 로 사라진다(P20 이 이미 못 박아 둔 규칙, `TODOs.md`). 교정이
`Candidate` 가 아니라 `mask_key` 에 붙는 것과 같은 소유 방향의 선택이다.

## 반입 규약이 도감과 하나 다르다

`Atlas` 는 도감 하나를 통째로 갈아치우지만, **`Reference` 는 upsert 다**
(`key` 로 `update_or_create`). 논문이 들어오면 같은 저자가 다른 source 에도
나올 수 있어 — 도감을 지우듯 지우면 먼저 반입된 source 의 참조가 끊긴다.
**`Occurrence` 는 `source` 단위로 통째로 갈아치운다** — 그 source 것만
지우고 다시 넣는다.

## `Reference.key` 는 사람이 정한다 — 자동 생성이 아니다

로마자 인명이 애매한 자리가 셋이다(殖田三郎·奧野春雄·羽田良禾, P20 이 이미
"확실한 훈독을 모른다" 고 적어 둔 이름들). `ref_key()` 는 그래서 표를 안
짜고 **`REF_KEY` 라는 손으로 채운 사전**을 쓴다 — 못 보던 (저자, 연도)가
나오면 멈춘다. 로마자 표기가 틀려도 화면·서지에는 안 나온다 — `authors` 가
원문 그대로를 든다. `key` 는 성씨만 짚는 내부 열쇠다.

**"한 인용이 두 편" 문제(P20)는 1단계가 이미 정해 뒀다.** `Skvortzow 1929`·
`박태수 1956` 은 실제 논문이 둘인데 도감이 구별 없이 인용한다 — 1단계가
`references[].cite` 에 둘 다 이어 적고 `note` 에 적었다. 2단계는 그 결정을
그대로 받아 **한 `Reference` 행**으로 넣는다. 새로 가를 근거가 없다.

## `check_db` 12번 — 만들면서 잡은 함정 하나

처음엔 `Occurrence` 가 하나도 없으면 검사를 통째로 건너뛰게 했다. 그런데
**`Reference` 만 남고 `Occurrence` 가 전부 사라진 상태**(반입이 반쪽만 됐거나
지워진 것)가 바로 다음 줄이 잡으려는 자리인데, `Occurrence` 없음만 보고
먼저 돌아가면 그 상태를 통과시킨다. 시험(`test_출현_기록이_없는_문헌을_잡는다`)
이 심어서 잡았다 — 둘 다 없을 때만 건너뛰게 고쳤다.

## 시험 — `test_occurrence.py` 9개

`test_atlas.py` 와 같은 모양(반입 두 번, source 별 갈아치움, 검산, 저장소의
진짜 JSON, `check_db` 심어 잡기). **저장소의 JSON 을 그대로 넣는 시험이
문헌 15·출현 기록 924 를 박아 둔다** — 논문이 늘면 여기가 먼저 걸린다.

```
python web/manage.py test viewer --exclude-tag browser   # 817개 (전부 통과)
```

## 안 한 것

- **`/srv` 반입은 안 했다.** `dbsync.sh import_occurrence.py` → `dbrun.sh` 는
  판을 내는 순서(운영 DB 를 건드리는 일)라 이 세션의 몫이 아니다
- **논문에서 사람이 손으로 넣는 값은 아직 안 다룬다.** P20 이 이미 적어 둔
  전제다 — "지금은 전부 기계가 뽑은 것이라 재생성 가능하다." 사람이 채우는
  값이 섞이는 순간 이 표를 그대로 갈아치우면 안 된다 — 그때 갈라야 한다
