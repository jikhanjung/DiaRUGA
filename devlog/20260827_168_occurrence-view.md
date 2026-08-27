# 도감 검색에 출현 기록을 붙인다 (168)

`web/viewer/data.py` · `web/viewer/templates/viewer/atlas.html` ·
`web/viewer/tests/test_atlas_search.py`

164 가 `Reference`·`Occurrence` 를 반입까지 끝냈지만 화면 어디에도 안 붙어
있었다(사용자가 물어서 드러났다). 사람이 볼 자리를 새로 만들지 않고 **이미
있는 도감 검색(`/atlas/?q=`) 결과 카드에 얹었다** — 종 전용 페이지가 아직
없고, 검색 결과가 이미 종 하나를 카드 하나로 보여주는 자리다.

## 왜 `icontains` 가 아니라 정확 일치인가

`Occurrence.binomial` 은 `AtlasEntry` 를 낳은 것과 같은 색인
(`tools/parse_occurrence.py` 가 `atlas/korean.json` 의 `binomial` 을 그대로
옮긴다)에서 왔다 — 표기가 갈릴 일이 없다. `icontains` 를 썼으면 `Melosira`
검색이 `Melosira ambigua` 의 출현 기록까지 끌고 온다. 시험 15번이 이것을
지킨다.

## 카드마다 되묻지 않는다 (105)

한 판에 50행이라 행마다 물으면 50번 나간다. `atlas_search` 가 이미 뜬 페이지
(`page = list(qs[...])`)의 이명법을 모아 `_occurrences_by_binomial()` 로 한
번에 묻고 dict 로 나눠 붙인다.

## 없으면 안 낸다

`r.extra.distribution`(도감 원문 문장)과 `r.occurrences`(갈라 맞춘 값)는
다른 칸이라 나란히 뒀다 — 원문과 맞춰 읽을 수 있어야 한다. 출현 기록이 없는
항목(도감 셋 중 둘, 논문 넷)은 **"출현" 줄 자체를 안 낸다** — 빈 줄을 내면
"이 종은 어디서도 안 보고됐다" 로 읽힌다(시험 14번).

## 시험 셋을 더했다 (13~15번, `test_atlas_search.py`)

기존 픽스처의 `Sceletonema costatum`(binomial `Skeletonema costatum`)에
`정 영호 외 1965 · 경기도 행주` 출현 기록 하나를 붙였다. 정확 일치·빈 줄 없음·
지역과 문헌이 함께 뜨는 것 셋을 각각 되살려서 잡히는 것을 확인했다(icontains
로 돌리면 13·15번이 죽고, `if r.occurrences` 가드를 빼면 14번이 죽는다).

`python web/manage.py test viewer --exclude-tag browser` 820개 통과.
