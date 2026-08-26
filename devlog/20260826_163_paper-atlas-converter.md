# 논문 도판을 도감 표로 옮긴다 (163)

`tools/parse_paper_atlas.py` · P20 3단계

161·162 에서 딴 도판 크롭(1936·1992·1993·1985 넷)의 캡션 표
(`tools/plate_figs.py` 의 `CAPTIONS`)를 `atlas/<논문>.json` 으로 뽑아
`ops/import_atlas.py` 가 그대로 삼키게 했다. **새 스키마를 안 만들었다** —
`Atlas`·`AtlasEntry`·`AtlasPlacement` 가 이미 "이름 + 도판·그림·쪽" 을
말하는 표라 논문도 그 모양에 그대로 들어간다. 이름 뽑는 규칙도 새로 안 짰다
— `tools/parse_atlas.py` 의 `name_fields`·`entry`·`place` 를 그대로 부른다.

## 결과

```
1936 Skvortzov 안변      — 항목 49 · 자리 55
1992 Lee 갈말            — 항목 74 · 자리 75
1993 Lee Chaetoceros     — 항목 34 · 자리 46
1985 Akiba & Yanagisawa  — 항목 61 · 자리 90
```

도감 셋(2,059) + 논문 넷(218) = **일곱 · 2,277**. `test_atlas.py` 의
`test_저장소의_JSON_이_그대로_들어온다` 가 이 수를 박아 둔다 — 다음에 논문을
더 넣을 때도 여기가 먼저 걸린다.

## 종 하나가 도판 여럿에 걸치면 자리를 여럿 담는다

1985(속 재검토 논문)이 그 모양이다 — *Crucidenticula nicobarica* 가 도판
1·2·3·5 에 걸쳐 22종이 자리 둘 이상을 갖는다. 한국 도감의 종이 그림을 여럿
갖는 것과 같은 구조라 `AtlasPlacement` 를 새로 안 늘렸다.

## 함정 둘 — 둘 다 `name_fields` 를 새로 안 짜고 앞단에서 막았다

**"n. sp." 의 `sp` 가 `GENUS_ONLY` 미확정 표시와 우연히 겹친다.** 1985 의
"새 종" 표시(`n. sp.`·`n. comb.`)는 종을 확정하는 말인데, 표제어 끝 낱말이
그대로 `sp`(온점 없이 — `extract_name` 이 걷은 자리)가 되어 `parse_atlas.py`
의 `GENUS_ONLY = {"sp.", "sp", ...}` 판정에 걸렸다. *Crucidenticula kanayae
Akiba and Yanagisawa n. sp* 가 학명이 뻔히 있는데 `rank: genus_only` 로
떨어졌다 — 5건. **`parse_atlas.py` 는 안 고쳤다** — 저기는 도감 색인의 규칙
이고 도감엔 "n. sp." 가 안 나온다. 대신 이쪽에서 분류용으로만 그 꼬리
(` n. sp`·` n. comb`·` n. gen`)를 떼고 `name_fields` 에 넣은 뒤, 화면에 보일
`name` 은 꼬리를 그대로 되살렸다. `Neodenticula sp. A`(진짜 미확정)는
그대로 `genus_only` 로 남는다 — 걸러 낸 것은 "n." 로 시작하는 새이름 표시
뿐이다.

**쉼표 하나가 종을 둘로 갈랐다.** 같은 문장이 도판마다 다시 조판되며
*kanayae*·*seminae* 두 종이 "…Yanagisawa n. sp" 와 "…Yanagisawa, n. sp" 로
쉼표만 다르게 나왔다 — 그대로 묶으면 표제어가 달라 서로 다른 항목이 된다
(63 → 겉보기엔 맞는 수인데 둘이 몰래 갈라져 있었다). "n. sp/comb/gen" 바로
앞 쉼표만 지우는 정규식으로 묶었다. **이런 조판 차이는 종이 아니다** —
검산(`names 중복`)을 넣어 두면 다음 논문에서 같은 모양이 나와도 잡힌다.

## 이미지가 아직 없다

`AtlasPlacement.pdf_page` 는 채웠지만 **그 쪽을 PNG 로 구운 적이 없다** —
기존 도감 셋은 `tools/render_atlas_pages.py` 가 미리 구워 `/data3/DiaRUGA/atlas/<code>/`
에 놓아 두고, `web/viewer/atlas.py` 가 그 파일을 읽어 도판을 넘긴다. 논문
넷은 아직 그 자리가 비어 있다. **화면이 죽지는 않는다** — `atlas.py` 머리말이
"자리가 없어도 죽지 않는다" 고 이미 못 박아 둔 규칙이라(outcrop.py 와 같은
모양) 이미지 없는 항목은 그냥 링크가 안 뜬다. 다음 일: `render_atlas_pages.py`
가 PDF 도 받게 늘리거나, 각 논문의 PDF 를 쪽마다 굽는 자리를 새로 만든다.

## 안 옮긴 것

`ClassDef` 와 안 맞는 속 이름(1985 의 `Kisseleviella`·`Denticulopsis` 등
화석 전용 속)이 늘어난다 — `check_db.py` 11번이 세는 자리이지 막는 자리가
아니다(P15 8.2). 그대로 둔다.

`Neodenticula seminae … n. comb` 계열의 이명(옛 *Denticulopsis seminae*)은
여기서 안 푼다 — 그것은 `Reference`/`Occurrence`(P20 다음 단계)가 할 일이지
도감 표가 할 일이 아니다.
