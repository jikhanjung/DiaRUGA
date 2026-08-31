# 논문 도판을 DB 에 넣는다 (계획)

P22(169~177)가 8편(2017·1994·1993남해·2001·1975·1986·1996·1991) 논문 도판
119~89~…개를 전부 `Diadiction/plate/*.png` 로 잘라내고 `tools/plate_figs.py`
(`SOURCE`·`CAPTIONS`)에 사람이 원문 대조한 학명을 적어 뒀다. 지금은 파일
하나에 갇혀 있어 뷰어 검색이 못 본다 — 이것을 DB 로 옮긴다.

**사용자 결정(2026-08-31)**:
- 스키마는 기존 `Atlas`/`AtlasEntry`/`AtlasPlacement`(P15)에 얹는다 — 도감
  검색·화면을 그대로 재사용한다(선택지 C)
- `AtlasPlacement` 에 개체별 크롭 이미지 칸을 더해, 화면에서 **마우스를
  올리면 그 그림 하나의 크롭을 미리 보여주는 것**으로 "도판 쪽 단위로만
  보여준다"는 C 의 약점을 덮는다
- `TaxonName`(AlgaeBase 유효성 판정)은 아직 방침 대기 — **유효명 칼럼 없이
  진행한다.** `paper_plates_pending.md` 배치 조회는 별도 일이다

## 왜 얹을 수 있는가 — 모양이 이미 맞는다

`AtlasPlacement` 는 "항목이 도감 어디에 놓여 있나" 를 도판(`plate`)·
그림(`figures`)·PDF 쪽(`pdf_page`·`pdf_plate_page`)으로 이미 담는다(129·
P15 4.1). 논문 한 편 = `Atlas` 행 하나, 캡션의 학명 하나 = `AtlasEntry`
하나(같은 이름이 여러 도판에 나오면 `AtlasPlacement` 가 여럿), 이게
`tools/plate_figs.py` 의 `SOURCE`(캡션쪽·도판쪽)·`CAPTIONS`(도판→그림→학명)
구조와 그대로 맞아떨어진다. **새 모델이 필요 없다** — 칸 하나만 는다.

## 스키마 변경

```python
# AtlasPlacement 에 추가
crop_image = models.CharField(max_length=200, blank=True, default="", db_default="")
```

`Diadiction/plate/` 의 크롭 파일이 있을 때만 채운다(도감 셋은 계속 빈
문자열 — 도판 쪽 단위로만 있어 개체 크롭이 없다). **경로가 아니라
`atlas.rel_of` 와 같은 규칙으로 `/img?p=` 가 먹는 `DATA_ROOT` 상대경로를
그대로 저장한다** — 화면이 다시 조립하지 않는다(`text_rel`·`plate_rel`
과 같은 자리).

마이그레이션은 새 칼럼 하나만 더하는 것이라 `db_default` 로 충분하다(옛
파이프라인 이미지가 이 테이블에 안 쓰므로 055 의 "함께 올려야 하는 축"
문제도 없다 — 뷰어 전용 테이블).

## Atlas.key 규칙 — 크롭 파일 접두사를 그대로 쓴다

`Diadiction/plate/plate_<코드>_pl<N>_fig<NN>_<학명>.png` 의 `<코드>`
(예: `1991lee`·`1996lee`·`2001park`·`2017yun`·`1994lee`·`1993bae`·
`1986lee`·`1975lee`)를 `Atlas.key` 로 그대로 쓴다 — 전부 `atlas.py`
의 `CODE` 정규식(`^[a-z0-9][a-z0-9-]{0,31}$`)을 이미 통과한다. 새 표기를
만들지 않는다.

**주의 — 12편 중 8편만 지금 대상이다.** 조사(178 조사 fork)에서
`plate_figs.py` 의 파이썬 키(`1936_skvortzov_...`)와 실제 크롭 파일
접두사(`1936skv`)가 어긋나고, 1985 는 캡션 651 개 · 파일 841 개로 수까지
안 맞는 것을 확인했다. **1936·1992·1993(Chaetoceros)·1985 넷은 이번에
안 넣는다** — 접두사 통일과 개수 검산이 먼저다. P22 의 8편(전부 177 까지
같은 관례로 자른 것)만 이번 대상.

## `Reference` 와 안 겹치나

`Reference.key`(예: `jung1967`)는 **한국 도감의 "분포" 문장이 인용하는
문헌**(164·P20)이고, 이번 8편(2017·1994·1993남해·2001·1975·1986·1996·
1991)은 그것과 다른 자료(`Diadiction/papers/`, 08-26 반입, 자기 자신이
동정 도판을 실은 원 논문)다. **이름이 같은 논문이라도 두 표에 각자
있는 게 맞다** — `Reference` 는 "누가 이 종을 어디서 봤다고 인용됐나"
이고 `Atlas`(논문판)는 "이 논문 자신이 이 종을 도판으로 실었다" 이다.
나중에 두 표가 실제로 같은 논문을 가리키면(예: 1986 이 도감에도
인용되고 자기 도판도 있다) `Reference.key` ↔ `Atlas.key` 매핑은 그때
가서 본다 — 지금은 안 묶는다.

## 임포터

`ops/import_atlas.py` 와 같은 자리(멱등 · 통째로 지우고 다시 만든다 —
**사람이 만든 칸이 없다**는 `Atlas` 의 전제가 그대로 성립한다, 크롭
경로는 파일 시스템에서 다시 뽑을 수 있다). 새 스크립트
`ops/import_paper_plates.py`(가칭)를 만든다:

1. `tools/plate_figs.py` 의 `SOURCE`·`CAPTIONS` 를 8편만 읽는다
2. 논문마다 `Atlas` upsert(`key`=크롭 접두사, `title`=논문 제목,
   `source`=`tools/plate_figs.py` 상대경로, `source_sha256`=그 파일의
   해시 — 다시 반입할 자리를 알린다)
3. 같은 학명은 `AtlasEntry` 하나로 묶는다(도판이 달라도). `binomial` 은
   `harvest_worms.binomial` 규칙 재사용(맞추기용 — 이미 다른 도감들과
   같은 함수)
4. 그림마다 `AtlasPlacement`: `plate`=도판 번호(1~5, 정수) · `figures`=
   그림 번호 문자열 · `pdf_page`=`SOURCE` 의 캡션쪽 · `pdf_plate_page`=
   도판쪽 · **`crop_image`=`Diadiction/plate/plate_<key>_pl<N>_fig<NN>_*.png`
   를 glob 으로 찾아 상대경로로 적는다**(파일이 없으면 빈 채로 — 링크
   없는 자리는 조용히 빠지는 기존 규칙과 같다)
5. 개수 검산: `CAPTIONS` 항목 수 == 실제 크롭 파일 수 == 임포트한
   `AtlasPlacement` 행 수. 안 맞으면 반입을 멈추고 무엇이 안 맞는지
   찍는다(1985 사고를 여기서 미리 막는다)

## 이미지 서빙 — 기존 `/img?p=` 를 그대로 쓴다

크롭 PNG 를 `/data3/DiaRUGA/atlas/<key>/crops/pl<N>_fig<NN>.png` 로
동기화하는 스크립트(가칭 `tools/sync_paper_plate_images.py`, 또는
`import_paper_plates.py` 안의 한 단계)가 `Diadiction/plate/`(NAS)에서
복사한다 — 도감 도판 PNG 가 서빙되는 자리와 같은 뿌리(`atlas.py::_root()`)
아래라 **새 URL 라우트가 필요 없다.** `crop_image` 칸에는 이 상대경로
(`atlas/<key>/crops/pl<N>_fig<NN>.png`, `atlas.rel_of` 와 같은 모양)를
저장한다.

## 화면 — 새 칩 하나, JS 변경 없음

`data.py::_placement_dict()` 에 `crop_url`/`crop_rel` 을 더한다(`text_rel`·
`plate_rel` 과 같은 자리, `p.crop_image` 를 그대로 옮긴다 — 디스크를
안 짚는다). `atlas.html` 의 `places` 루프에 칩 하나를 더 낸다:

```html
{% if pl.crop_rel %}<a class="chip" href="{{ pl.plate_url }}"
   data-prev="{{ pl.crop_rel }}" data-prevlabel="fig.{{ pl.figures }}">그림 보기</a>{% endif %}
```

**141 의 `data-prev` 미리보기가 이미 범용이다**(`a[data-prev]` 를
잡는 JS, 특정 칩에 안 매여 있다) — 이 칩 하나로 "마우스를 올리면 개체
이미지" 가 그대로 된다. **JS 를 한 줄도 안 고친다.**

## 안 하는 것 (이번 범위 밖)

- **AlgaeBase 유효명 칼럼** — `TaxonName` 방침이 서기 전까지 없다
- **1936·1992·1993(Chaetoceros)·1985 넷** — 접두사·개수 불일치를 먼저
  고친다
- **`Reference` ↔ 논문판 `Atlas` 자동 연결** — 지금은 필요가 안 생겼다
- **도감 카드 목록(`atlases()`)에 8편을 노출할지** — 검색은 되지만
  `/atlas/` 첫 화면 카드 목록에 넣을지는 화면 쪽 판단이 남았다(사람이
  기존 3 도감과 나란히 보이길 원하는지 확인 필요)

## 검증

```
python web/manage.py test viewer --exclude-tag browser
python ops/check_db.py
```

임포터가 멱등인지(두 번 돌려도 행 수가 같은지), `crop_rel` 링크가
실제로 뜨는지(브라우저 시험 한 화면 추가 고려)까지 확인한다.
