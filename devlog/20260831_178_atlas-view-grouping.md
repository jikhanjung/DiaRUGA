# 도감 목록을 다권 도감과 논문 도판집으로 가른다 (178)

`web/viewer/views.py` · `web/viewer/templates/viewer/atlas.html`

사용자가 "도감이 이제 15종으로 들어가서 도감 뷰어 화면이 다소 지저분하네"라고
물었다 — 확인해 보니 "종" 이 아니라 `/atlas/` 검색 전 기본 화면에 뜨는
**도감(`Atlas`) 15건**이었다. 전부 같은 `.atlasrow`(표지+제목+쪽수+권 칩)로
세로로 줄 서 있어, 표지 없는 발췌본 다수가 진짜 도감 소수를 밀어내는 모양이
됐다.

## 가르는 기준을 한 번 틀렸다

처음엔 어느 파서가 만들었는지로 갈랐다 — `tools/parse_atlas.py` 의
`ATLASES`(3개) vs `tools/parse_paper_atlas.py` 의 `PAPER_META`(12개). 그런데
사용자가 "east-antarctic 도 사실 논문에서 도판만 떼온거야" 라고 정정했다.
확인해 보니 `east-antarctic` 의 title 자체가 **"플라이스토세 중기 이후
동남극 규조 (도판집)"** 이고 note 에도 "본문 없이 도판·학명·시료 위치만 실린
발췌본" 이라고 이미 적혀 있었다 — `ATLASES` 목록에 있다고 다권 도감인 것이
아니다. **소스 모듈은 못 믿는 신호였다.**

진짜 다권 도감은 **`korean`·`schmidt` 둘뿐**이다. `Atlas` 모델에도
`atlas.py` 의 목록 함수에도 이 구분을 담을 칸이 없다 — 사람이 정한 값이라
파일이나 DB 어디에도 재생성 가능한 형태로 없다.

## 어디에 못 박았나

`atlas.py` 는 "파일이 곧 자료" 원칙이라 사람의 분류 판단을 여기 담는 것이
그 파일의 성격과 어긋난다. `views.py` 의 `atlas_index` 바로 위에
`_BOOK_ATLAS_CODES = {"korean", "schmidt"}` 로 짧게 못 박고, `plates` 를
`book_atlases`/`paper_atlases` 로 갈라 컨텍스트에 얹었다 — `atlas.py` 의 다른
소비자(`atlas_volume`·`atlas_page`·`atlas_spread`)는 이 구분을 몰라도 되므로
오염이 없다.

## 화면

- `book_atlases`(2건) — 기존 `.atlasrow` 그대로, 표지·권 칩을 다 낸다.
- `paper_atlases`(13건) — "논문 도판집" 소제목 아래 `.papergrid` 로 접었다.
  표지 없이 작은 그리드 타일(썸네일 100px+제목+쪽수)로 줄여, 화면 세로
  길이가 15줄에서 2줄+그리드 한 판으로 준다.

## 확인

관련 시험 5개 파일(65개) · `--exclude-tag browser` 전체(823개) 통과. 화면
렌더는 도감 넷(book 둘·paper 둘)을 `atlas/atlases.json` 에 임시로 세운
스모크 시험으로 두 섹션이 실제로 갈라 뜨는 것까지 확인한 뒤 지웠다(커밋에
안 남긴다 — 시험은 "되살려서 잡히는 것을 보고 나서 있다고 말한다" 는 원칙에
맞는 회귀 자료가 아니라 렌더 확인용 1회성이었다).
