# `render_atlas_pages.py` 가 논문 PDF 도 받는다 — 실제로 구웠다 (166)

`tools/render_atlas_pages.py` · P20 3단계 마무리

163 에서 논문 넷을 `Atlas`/`AtlasEntry`/`AtlasPlacement` 로 넣었지만 도판
이미지가 없어 화면에서 못 열었다(163 의 "이미지가 아직 없다"). 그 자리를
채웠다 — 도감 셋과 같은 굽는 스크립트로, 같은 `/data3/DiaRUGA/atlas/<code>/`
자리에 놓는다.

## 뿌리가 도감과 다르다

원본이 `Diadiction/origin/` 이 아니라 `Diadiction/papers/` 에 산다(163 의
자료 분리 — "도감은 이름을 세우는 것이고 논문은 어디서 얼마나 나왔는지를
말한다"). `SOURCES` 튜플에 **원본이 있는 뿌리**를 한 칸 추가해서(`NAS` 하나만
쓰던 것을 `NAS`/`PAPERS_NAS` 둘로) 도감·논문이 한 표에 같이 앉게 했다.

## 165 가 여기서 나온 것이다

이 작업을 시작하다가 **논문의 `Atlas.key` 가 뷰어의 도판 서빙 코드
(`viewer/atlas.py` 의 `CODE` 정규식)를 못 지나는 것**을 발견해 165 로 먼저
고쳤다 — 밑줄 있는 내부 키(`1936_skvortzov_ampen_neogene`)를 그대로 공개
코드로 냈던 것을 `atlas_key`(`1936-skvortzov`)로 갈랐다. **이 스크립트의
`SOURCES` 코드도 165 에서 정한 `atlas_key` 를 그대로 쓴다** — 어긋나면
`Atlas` 행은 있는데 도판 폴더 이름이 달라 이미지가 안 열린다.

## 펼침(spread) 은 논문에 근거가 없다

`LEFT_PARITY` 는 "펼침에서 왼쪽이 홀수냐 짝수냐" 를 도감마다 실측해 정한
것인데(131), 논문은 **저널 낱장을 이어 스캔한 것**이라 애초에 좌우가 짝지어
제본된 적이 없다 — 잴 대상이 없다. 넷 다 `"odd"`(모르면 쓰는 기본값과
같다)로 채워 `spread()` 가 죽지 않게만 해 뒀다. **도판을 보는 자리는 격자
(쪽 하나씩)다** — 펼침 화면은 논문에서는 장식일 뿐 근거 있는 뷰가 아니다.

## 실제로 구웠다

```
python tools/render_atlas_pages.py
  1936-skvortzov/main     50쪽
  1992-lee-galmal/main     23쪽
  1993-lee-chaetoceros/main     29쪽
  1985-akiba-yanagisawa/main     72쪽
구운 쪽 174개 (회색조로 줄인 것 174) · 실패 0 · 0.21 GB
```

도감 셋(korean·schmidt·east-antarctic)은 이미 다 구워져 있어 건너뛰었다 —
`atlases.json` 이 그 셋을 그대로 담고 논문 넷을 새로 얹었다. `/data3` 여유가
6.2 TB 라 용량은 문제가 아니었다(전부 회색조로 줄어 0.21 GB).

## 확인한 것

- `p0041.png`(1936 Plate I) 을 직접 열어 `SOURCE["1936_..."][1] = (40, 41)`
  이 실제로 PL. I 쪽을 짚는지 눈으로 봤다 — 맞다
- 굽기 전 스크래치 디렉토리(`DIARUGA_ATLAS_ROOT` 로 돌린 임시 자리)에서
  먼저 두 쪽을 떠 확인한 뒤에 진짜 `/data3` 로 돌렸다
- 실패 0 · `atlases.json` 의 `rendered` 가 전부 `pages` 와 같다

## 안 한 것

`/srv` 반입(`ops/import_atlas.py`)은 이 세션의 몫이 아니다(164 와 같은 이유
— 판을 내는 순서). DB 에 논문 `Atlas` 행이 아직 없는 운영에서는 이 이미지가
당장 안 보이고, 다음에 반입기가 돌 때 비로소 화면에 연결된다.
