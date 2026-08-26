# 논문 도감 코드에서 밑줄을 걷는다 (165)

`tools/parse_paper_atlas.py` · `web/viewer/atlas.py`

`render_atlas_pages.py` 를 논문 PDF 도 받게 늘리려고 시작했다가, 163 에서
이미 반입해 둔 논문 넷의 `Atlas.key`(`1936_skvortzov_ampen_neogene` 같은
것)가 **뷰어의 도판 이미지 서빙 자체를 영영 못 열게 막아 둔 것**을 발견했다.

## 무엇이 어긋났나

`web/viewer/atlas.py` 는 도판 PNG 를 `/data3/DiaRUGA/atlas/<code>/<권>/`
에서 읽는데, `<code>` 가 주소에서 오는 값이라 `CODE = re.compile(r"^[a-z0-9]
[a-z0-9-]{0,31}$")` 로 못 박아 둔다(밑줄 금지·32자 이하 — 경로 조작을 막는
자리다). `_ok()` 가 이 정규식으로 모든 접근 함수를 지키는데, 어긋나면
**예외 없이 조용히 `None`** 을 낸다.

163 에서 `Atlas.key` 를 `plate_figs.py` 의 내부 파일-스템 키
(`1936_skvortzov_ampen_neogene`, 밑줄 있고 43자짜리도 있다)를 그대로
썼다 — 도감 항목은 DB 에 잘 들어가지만 **도판 이미지는 이 코드로는 영원히
안 열린다.** 개수도 맞고 검산도 통과해서 조용히 지나갈 뻔한 자리다.

## 고친 것

**내부 열쇠와 공개 코드를 갈랐다.** `plate_figs.py`·`crop_plates.py`·
`ASSIGN`·크롭 파일 이름을 잇는 내부 키(밑줄 있는 파일 스템)는 그대로 두고
— 여기를 바꾸면 도판 크롭 파이프라인 전체의 표를 다시 짜야 한다 — `Atlas.key`
로 나가는 값만 `PAPER_META[...]["atlas_key"]` 로 새로 두었다.

```
1936_skvortzov_ampen_neogene          → 1936-skvortzov
1992_lee_galmal_quaternary_flora      → 1992-lee-galmal
1993_lee_chaetoceros_yeonil           → 1993-lee-chaetoceros
1985_akiba_yanagisawa_dsdp87_zonal_markers → 1985-akiba-yanagisawa
```

`atlas/*.json` 파일 이름도 이 코드로 다시 냈다(`git mv` 로 이력이 남는다).
아직 `/srv` 에 반입한 적이 없어(164 의 "안 한 것") DB 마이그레이션은 필요
없었다 — 저장소 파일만 고치면 끝이었다.

## 남긴 교훈

**"항목이 들어갔다" 와 "그 항목이 화면에서 열린다" 는 다른 검사다.**
`test_저장소의_JSON_이_그대로_들어온다` 는 개수·표제어만 맞춰 보고 통과했다
— `Atlas.key` 가 URL 조각으로 쓰일 자격이 있는지는 아무도 안 봤다. 다음에
도감(또는 논문)을 더할 때는 **`atlas_key` 가 `CODE` 정규식을 통과하는가**를
반입 전에 확인한다.
