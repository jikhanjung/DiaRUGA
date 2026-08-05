# DiaRUGA DB 명세

**2026-08-04**

남극 시추코어 규조류 분석 파이프라인이 쓰는 데이터베이스의 명세다. 표 하나하나가
무엇을 담는지, 서로 어떻게 매이는지, 그리고 **왜 그렇게 두었는지**를 적는다.

> **원본은 `web/viewer/models.py` 다.** 이 문서는 그것을 읽기 좋게 편 것이고,
> 둘이 어긋나면 코드가 맞다. 설계 근거는 `devlog/20260730_P02_db-schema.md`.

---

## 1. 물리 구성

| | |
|---|---|
| 엔진 | SQLite 3 (Django 5.2 ORM) |
| 파일 | `/srv/DiaRUGA/db/DiaRUGA.db` — 로컬 ext4 |
| 저널 | **WAL** (`journal_mode=WAL`, `synchronous=NORMAL`) |
| 외래키 | `PRAGMA foreign_keys=ON` |
| 잠금 대기 | `timeout=20` (초) |
| 페이지 | 4 096 B |
| 크기 | 108.6 MB (2026-08-04 기준) |

### 왜 SQLite 인가

읽는 쪽이 대부분이고, 쓰는 쪽은 사람의 교정과 파이프라인 둘뿐이다. 서버 프로세스가
하나 더 늘지 않는 것이 배포·백업 양쪽에서 이득이 크다.

**대신 쓰기는 한 번에 하나다.** WAL 이라 읽기는 여럿이 동시에 되지만 쓰기는
직렬화된다. 실제로 파이프라인이 도는 중에 사람이 검토를 저장하다가 `database is
locked` 로 **프레임 229장이 날아간 적이 있다.** 그래서 지금은

- 검출 저장을 **두 트랜잭션으로 나눈다** — 후보를 넣는 긴 부분과, `is_current` 를
  옮기고 교정을 다시 매는 짧고 원자적이어야 하는 부분
- 잠금 오류에만 재시도를 건다 (`with_db_retry`, 6회 지수 백오프)

"파이프라인이 도는 동안 사람이 검토한다" 가 일상이 되면 이 선택을 다시 봐야 한다.

### 파일이 아니라 디렉토리째 마운트한다

컨테이너에 `DiaRUGA.db` **파일 하나만** 물리면 WAL 이 만드는 `-wal`·`-shm` 형제가
컨테이너 안쪽에 생겨 호스트와 WAL 을 공유하지 못한다. 같은 DB 를 보는 줄 알았는데
아닌 상태가 된다. 그래서 `/srv/DiaRUGA/db` 디렉토리를 통째로 물린다.

### 들어가는 문은 하나다

DB 를 만지는 일회성 스크립트는 **전부 컨테이너 안에서** 돈다.

```bash
deploy/host/dbsync.sh check_db.py     # 저장소 → /srv/DiaRUGA/scripts
deploy/host/dbrun.sh  check_db.py     # 컨테이너 안에서 돈다
```

호스트 venv 로도 같은 파일을 열 수 있지만 그러면 **환경이 두 벌**이 된다. 그것으로
두 번 당했다 — 컨테이너의 낡은 `models.py` 가 새 칼럼을 몰라 NAS 반입이 죽었고,
root 로 돈 컨테이너가 파일 소유자를 바꿔 호스트 스크립트가 못 쓰게 됐다.
컨테이너는 `1000:1000` 으로 돌고, 시간대는 `TZ=Asia/Seoul` 로 호스트와 맞춘다.

### 사본

`cp DiaRUGA.db` 는 **금지**다 — WAL 때문에 불완전한 사본이 나온다. `backup_db.py` 가
sqlite 백업 API 로 뜨고, 검증을 통과한 뒤에야 제 이름을 준다(뜨는 중에는 `.part`).

| 어디 | 무엇 | 로테이션 |
|---|---|---|
| `backup/` | 시간별 자동 | 24시간 rolling, NAS 로 간다 |
| `backup/manual/` | 사람이 `--note` 로 뜬 것 | 안 걷는다 — 일 끝나면 사람이 지운다 |
| `backup/pre_deploy/` | 배포 직전 | 최근 20개 |

---

## 2. 전체 그림

```mermaid
flowchart LR
    Site[Site<br/>지역] --> Core[Core<br/>코어] --> Slide[Slide<br/>슬라이드]
    Slide --> VP[Viewpoint<br/>시야] --> Frame[Frame<br/>사진]
    VP --> Stack[Stack<br/>합성본 1:1]
    VP --> Det[Detection<br/>is_current] --> Cand[Candidate<br/>개체]
    VP --> VR[ViewpointReview<br/>시야 검토 1:1]
    VP --> OR[ObjectReview<br/>개체 교정]
    Cand -. "mask_key 로 느슨히" .-> OR
    Cand -. "cls 문자열" .-> CD[ClassDef<br/>분류 정의]
    RB[RunBatch<br/>이름표] --> Run[Run<br/>실행]
    Run -.-> Det
    Run -.-> Stack
    Run -.-> VP
    TS[ThresholdSet<br/>판정 문턱] -.-> Det
    ST[Setting<br/>key-value]

    classDef stem fill:#e8f0fe,stroke:#4285f4,stroke-width:2px
    classDef human fill:#fce8e6,stroke:#ea4335,stroke-width:2px
    classDef det fill:#e6f4ea,stroke:#34a853
    classDef side fill:#f8f9fa,stroke:#9aa0a6,color:#5f6368
    class Site,Core,Slide,VP,Frame stem
    class OR,VR human
    class Det,Cand,Stack det
    class RB,Run,TS,CD,ST side
```

**파랑**이 줄기(시료 계통), **초록**이 검출, **빨강**이 사람의 교정, **회색**이
설정과 이력이다. 실선은 소유(FK — 지우면 따라 지워진다), 점선은 참조이거나 FK 가
아예 아닌 것이다.

굵은 줄기는 **지역 → 코어 → 슬라이드 → 시야 → 사진**이다. 폴더 이름
`RS23-GC03 71cm` 을 통짜 문자열로 두지 않고 갈라 담은 결과이고, 그래야 "같은
코어에서 깊이에 따른 군집 변화" 나 "지역별 차이" 를 질의할 수 있다.

관계 하나하나(방향·필수 여부·`on_delete`)는 [ERD 문서](20260804_db-erd.md)에 있다.

---

## 3. 표별 명세

### 3.1 시료 계통

#### `Site` — 채취 지역

폴더명의 앞 토막(`RS23`, `WAP13`).

| 칸 | 형 | 비고 |
|---|---|---|
| `code` | char(32) **unique** | `RS23` |
| `name` | char(200) | 정식 명칭 — **사람이 채운다** |
| `area` | char(8) choices | `kr` 한국 / `ant` 남극. 기본 `ant`, **`db_default` 도 함께** |
| `region` | char(200) | 로스해 · 웨델해 … |
| `lat` / `lon` | float | |
| `note` | text | |

- **코드만으로 이름을 단정하지 않는다.** `RS` 가 Ross Sea 일 가능성이 크지만
  사람이 확인해 채운다.
- **`area` 와 `region` 은 다른 칸이다.** `region` 은 이미 세부 지명으로 차 있어
  목록을 가르는 상위 칸을 겸할 수 없다.
- **`db_default` 를 함께 주는 이유:** `default` 는 파이썬 쪽이라 그 모델을 아는
  코드에만 붙는다. 이 DB 는 뷰어 이미지와 파이프라인 이미지가 함께 쓰는데 판이
  따로 돌아서, 파이프라인이 옛 코드일 때 `Site` 를 만들면 이 칸을 안 보내고
  `NOT NULL constraint failed` 로 죽는다 — 실제로 NAS 반입이 그렇게 막혔다.

#### `Core` — 시추코어

폴더명의 가운데 토막(`GC03`). `(site, code)` 가 unique.

`code` · `kind`(gravity core 등, 사람이 채움) · `lat` · `lon` ·
`water_depth_m` · `collected_at` · `note`.

#### `Slide` — 슬라이드글라스 = 폴더 하나

| 칸 | 형 | 비고 |
|---|---|---|
| `name` / `slug` | char | `slug` unique — URL 에 쓴다 |
| `image_dir` | char(500) | `DATA_ROOT` 기준 상대경로 |
| `core` | FK null | 폴더 이름이 규칙을 안 따르면 안 붙는다 |
| `depth_cm` | float | 코어 안에서 이 값으로 정렬 |
| `description` | text | 사람이 적는다 — `state_note` 와 갈라 둔다 |
| `um_per_pixel_override` | float | 사람이 박는 배율 |
| `corr_thresh` | float | 그룹핑 상관 문턱 |
| `state` | char(12) | 아래 상태기계 |
| `state_note` | text | **자동 처리가 덮어쓴다** |
| `discovered_at` / `copied_at` / `processed_at` | datetime | NAS 반입 이력 |
| `created_at` / `updated_at` | datetime | 이 칸이 생기기 전 행은 `updated_at` 이 비어 있다 |

**배율을 사람이 박을 수 있게 둔 이유:** ZEN 이 소프트웨어에서 선택된 대물렌즈를
적어서 실제와 어긋난 적이 있다(260731 이 100x 로 기록돼 µm/px 가 2.5배 작았다).
비어 있으면 40x 로 가정해 계산한다 — 40x · 1.6x 옵토바 · 0.63x 어댑터 = 0.1126.

#### `Viewpoint` — 시야

`(slide, idx)` unique. `idx` 가 URL 의 `g0`, `tag` 는 `g000_Snap-21365-21370`.
`n_frames` · `span_sec` · `sharpest_frame` · `grouping_run`.

> **`Group` 이라 부르지 않는다** — SQL 과 Django 양쪽에서 뜻이 겹친다.

#### `Frame` — 사진 한 장

`(slide, name)` unique. **슬라이드를 넘으면 이름이 겹친다** — 실제로 143개가
겹쳐 있었고, 슬라이드를 안 보고 이름만으로 찾다가 12개 시야가 엉뚱한 슬라이드로
붙어 파이프라인이 1분마다 헛돌았다.

`path` · `width`/`height` · `um_per_pixel`(+ `_source`: xml/sidecar/default/cli) ·
`acquired_at` · `sharpness` · `is_sharpest` · `seq` · `meta`(JSON) ·
`created_at`/`updated_at`.

- **`acquired_at` 과 `created_at` 은 다르다.** 앞은 촬영 시각(딸린 XML 이 알려
  준다), 뒤는 우리 시스템이 받은 때다.
- 광학계 정보는 전 사진 동일하고 지금 쓰는 곳이 없어 칼럼 대신 `meta` 에 담는다.

#### `Stack` — all-in-focus 합성본 (`Viewpoint` 와 1:1)

`focused_path` · `depth_path` · `depth_npz_path` · `um_per_pixel`(+ native,
`resize_scale`) · `ref_frame` · `align_failed` · `object_px_frac` ·
`sharpness_best_single` / `sharpness_fused` / `gain` · `run`.

합성 전후 선명도를 함께 들고 있어 **합성이 실제로 이득이었는지**를 사후에 따질 수 있다.

### 3.2 검출

#### `Detection` — 이미지 한 장에 대한 검출 실행

| 칸 | 비고 |
|---|---|
| `viewpoint` | FK cascade |
| `target` | `stack` / `frame` |
| `frame` | `target=frame` 일 때만 |
| `image_path` · `width` · `height` · `scale` | |
| `um_per_pixel`(+ native, source, `backfilled`) | |
| `n_raw_masks` · `n_sized` | 원시 마스크 수, 크기 통과 수 |
| `thresholds` | FK `ThresholdSet` |
| `run` | FK `Run` |
| `is_current` | **뷰어가 볼 것** |
| `superseded_by` | self FK, `SET_NULL` |

**검출은 덮어쓰지 않고 쌓는다.** 재실행마다 새 행이 생기고 `is_current` 가 옮겨
간다. 엔진 교체 전후를 같은 시야에서 견주려면 옛것이 남아 있어야 한다.

- 엔진마다 검출을 다는 자리가 다르다 — **SAM2 는 합성본 한 장에만**, **YOLO 는
  프레임마다 + 합성본에도** 단다.
- `superseded_by` 가 `SET_NULL` 이라 옛 검출을 지워도 현재 검출이 딸려 가지 않는다.
- **같은 묶음 안에서 같은 이미지에 둘 이상 쌓인 것은 기록이 아니라 찌꺼기다**
  (빠진 프레임을 다시 돌리면 이미 끝난 것까지 다시 쌓인다). `prune_detections.py`
  가 현재 검출 → 없으면 번호가 큰 것 하나만 남기고 지운다. **묶음을 넘어서는
  지우지 않는다.**

#### `Candidate` — 개체 하나

`(detection, mask_key)` unique. 통과분과 탈락분을 **한 표에 담고 `passed` 로 가른다** —
문턱을 바꾸면 개체가 무리를 옮겨 다니는데, 칼럼 하나면 `refilter` 가 UPDATE 한 번이다.

| 갈래 | 칸 |
|---|---|
| 자리 | `bbox_x/y/w/h` · `center_x/y` · `mask_key`(bbox 로 만든 키) · `raw_id` |
| 크기 | `area_px` · `area_um2` · `major_um` · `minor_um` · `long_side_um` · `short_side_um` |
| 모양 | `aspect_ratio` · `fill_ratio` · `circularity` · `convexity` · `solidity` · `elongation` · `ellipse_iou` · `shape_ok` |
| 질감·신뢰 | `texture` · `predicted_iou` · `stability_score` |
| 기하 | `polygon` — `[x0,y0,x1,y1,…]` 평탄 배열 |
| 판정 | `passed` · `cls` · `reject` |

`polygon` 이 **용량의 대부분**이다 (26.8 MB / 108.6 MB ≈ 25 %). 마스크를 그리는
근거라 줄일 수 없다.

**`passed`·`cls`·`reject` 는 저장된 사실이 아니라 순수 함수의 캐시다.** 같은 지표와
같은 문턱이면 `judge.py` 가 언제나 같은 답을 낸다. `check_db.py` 가 그 셋을 다시
계산해 저장된 값과 맞는지 본다 — 어긋나면 문턱을 바꾸고 다시 안 걸렀다는 뜻이다.

### 3.3 사람의 교정 — **재생성 불가**

#### `ObjectReview` — 개체 단위 교정

`(viewpoint, mask_key)` unique.

| 칸 | 비고 |
|---|---|
| `mask_key` | **진짜 키** |
| `candidate` | FK null — **바인딩 결과일 뿐이다** |
| `bind_method` | `exact` / `iou` / `manual` / `orphan` |
| `bind_score` | IoU 로 붙었을 때의 값 |
| `geom` | `{"bbox": [x,y,w,h], "polygon": [...]}` |
| `removed` · `accepted` | 지웠다 / 되살렸다 |
| `label` · `note` | 분류 지정 · 메모 |

**교정은 `Candidate` 가 아니라 `mask_key` 에 붙는다.** FK 로 매면 재검출에서
후보 행이 새로 생기므로 사람의 판단이 조인 실패로 사라진다. 실측으로 같은
설정이면 100 % 붙지만 엔진을 갈면 거의 0 이 된다 — 그래서 교정 행은 `geom` 에
기하를 스스로 들고 있어 **검출기와 독립적으로 읽힌다.**

**`removed` 와 `accepted` 를 한 칼럼으로 합치지 않는다.** 되살렸다가 다시 지운
개체가 있고, "사람이 지웠다가 이긴다" 는 규칙이 두 값의 조합으로 표현된다.

지운 것까지 전부 저장한다 — **학습의 어려운 음성 표본**이다.

#### `ViewpointReview` — 시야 단위 (1:1)

`done` · `note`. **고칠 것이 없어 교정이 비어도 검토는 끝났을 수 있다**. 그래서
따로 남긴다.

### 3.4 설정과 이력

#### `ThresholdSet` — 판정 문턱 11개

`min_um` · `max_um` · `texture_min` ·
`round_max_elong` · `round_min_iou` · `round_min_solidity` · `round_texture_min` ·
`rod_min_elong` · `rod_max_elong` · `rod_min_iou` · `rod_min_solidity`.

표로 두어 이름을 붙여 견줄 수 있다 — "1500 대 2000 을 같은 시야에 걸고 개수를
나란히". 원형은 areolae 를 더 무겁게 본다(`round_texture_min` 이 따로 있는 이유) —
형태만으로는 밋밋한 원반을 가려낼 수 없다.

#### `ClassDef` — 분류 정의

| 칸 | 무엇 | 비면 |
|---|---|---|
| `key` **unique** | `round` · `rod_frag` · `chaetoceros` | — |
| `label` | 전체 이름 | |
| `short` | 약칭. 자리가 좁은 곳에서 쓴다 | `label` 을 쓴다 |
| `badge` | 배지 CSS 클래스 | `base.html` 에 `.badge.<badge>` 규칙이 있어야 한다 |
| `color` | `"60,220,120"` | **마스크가 투명해진다** |
| `hotkey` | 검토 화면 단축키 | 그 분류만 메뉴로만 지정된다 |
| `counted` | 개체 수로 세는가 | |
| `is_taxon` | 형태가 아니라 분류학으로 알아본 것인가 | |
| `sort_order` · `active` | 차례, 켜고 끄기 | |

표로 두면 분류를 더할 때 배포가 필요 없다 — Eucampia 를 넣은 것이 코드 수정이었다.
형태 칸(원형·봉상)과 분류학 칸(`is_taxon`)은 성격이 달라 메뉴에서 줄을 그어 나눈다.

`counted` 는 **개체 수로 세는가**다. 파편은 개체가 아니다 — 깨진 조각 하나를 규조
한 개로 세면 밀도가 부풀고 그 숫자가 보고서에 실린다. 목록의 "검출" 칸은 이 값이
참인 분류만 더한 것이고, 미분류는 분류 자체가 없어 애초에 빠진다.

**하나라도 비면 예외는 안 나고 그 분류만 화면에서 조용히 다르게 굴러간다.**
Chaetoceros 를 넣으며 실제로 겪은 것들이라 `check_db.py` 의 4번 검사가 `hotkey` 와
`color` 가 빈 것을 잡는다.

**데이터가 어떻게 들어가는가**

행은 사람이 화면에서 만드는 것이 아니라 **코드가 넣는다.** 두 경로가 있고, 둘 다
`update_or_create(key=…)` 라 **몇 번 돌려도 같은 상태**가 된다.

| 언제 | 무엇 | 어디 |
|---|---|---|
| 처음 DB 를 세울 때 | 다섯 행 (원형·원형 파편·봉상·봉상 파편·Eucampia) | `import_json.py` 의 `CLASS_SEED` → `seed_settings()` |
| 그 뒤에 더하거나 고칠 때 | 마이그레이션 | `0013` `counted` · `0014` Chaetoceros · `0015` 파편 색 · `0016` `hotkey` · `0017` `short` |

**마이그레이션으로 넣는 이유는 배포마다 같은 상태가 되어야 하기 때문이다.** 손으로
INSERT 하면 운영 DB 에만 있고 새로 만든 DB(시험·복구)에는 없다. 되돌릴 때는 행을
지우지 않고 `active=False` 로 끈다 — 지운 뒤에 그 분류로 붙인 교정이 남아 있으면
화면에서 이름도 색도 없는 분류가 된다.

읽는 쪽은 `data.py` 가 `active=True` 인 것만 가져와 **프로세스 수명 동안 캐시**한다
(거의 안 바뀌는데 템플릿과 클라이언트가 여러 번 묻는다). 표를 고치면
`invalidate_classes()` 로 버린다.

`color` 는 표에 적혀 있지만 **화면의 색은 아직 CSS 가 키로 잡는다.** 그래서 분류를
하나 더하거나 색을 바꾸면 이 행만으로 끝나지 않고 `base.html` 도 함께 가야 한다 —
표로 옮기다 만 자리이고, 기계로도 아직 못 본다. `0015` 가 파편을 제 본체와 같은
색 가족으로 묶은 것(진하기로만 가른다)도 표와 CSS 양쪽을 고친 작업이다.

#### `Run` / `RunBatch` — 실행 이력

`Run`: `kind`(group/stack/detect/refilter/reconcile/ingest/export) ·
`status`(running/**partial**/done/failed) · `params`(JSON) · `counts`(JSON) ·
`host` · `gpu` · `code_version` · `error`.

- **`partial` 이 따로 있는 이유:** GPU 를 다른 작업이 침범해 9장이 조용히 빠졌는데
  실행은 `done` 이었다. 나중에 프레임 수를 세어 보고서야 알았다.
- **`RunBatch` 는 실행이 아니라 이름표다.** 파이프라인은 슬라이드 단위로 도는데
  ("전체를 한 번 훑었다" 는 작업이 실행 여럿으로 흩어진다) 엔진을 견주려면 그
  한 번을 한 덩어리로 봐야 한다. 부모 `Run` 을 두지 않은 것은 그쪽이 자기
  `started_at`·`counts` 를 갖게 되어 뜻이 겹치기 때문이다. `(kind, label)` unique.

#### `Setting` — 그 밖의 설정

`key` unique · `value`(JSON). 경로처럼 **배포마다 다른 값은 여기 두지 않는다**
(환경변수). 지금은 `upright_min_ratio` · `crops_per_page` 둘.

---

## 4. 반드시 지켜지는 것 (`check_db.py` 가 보는 것)

`python check_db.py` — 1초. `refilter`·`segment` 뒤, `judge.py` 를 고친 뒤,
숫자가 이상할 때 돌린다.

| # | 불변식 | 깨지면 |
|---|---|---|
| 1 | `passed`·`cls`·`reject` 가 `judge.py` 를 다시 돌린 값과 같다 | 문턱을 바꾸고 다시 안 걸렀다 |
| 2 | 시야마다 `is_current=True` 인 검출이 **정확히 하나** | 둘이면 어느 것을 보일지 모르고, 없으면 검출이 사라진 것처럼 보인다 |
| 3 | 교정이 현재 검출의 개체를 가리킨다 (`bind_method` 분포) | 재검출에서 교정이 떨어져 나갔다 |
| 4 | 붙어 있는 `cls`·`label` 이 전부 `ClassDef` 에 있고, 활성 분류에 `hotkey`·`color` 가 있다 | 이름도 색도 없이 나오거나, 마스크가 투명해지거나, 그 분류만 메뉴로만 지정된다 |
| 5 | 경로가 실제 파일을 가리키고 배율이 있다 | 사진이 안 뜬다 |
| 6 | 문턱이 **슬라이드 안에서 하나** | 같은 슬라이드의 시야끼리 개수를 못 견준다 |

**예외가 나지 않고 그냥 틀린 상태**를 잡는 것이 목적이다.

---

## 5. 상태기계

### `Slide.state`

```mermaid
stateDiagram-v2
    direction LR
    [*] --> pending : NAS 에서 새 폴더를 봤다
    pending --> copying : 복사 시작
    copying --> processing : 파이프라인
    processing --> done
    processing --> failed : 그룹핑을 못 믿겠다
    failed --> processing : 사람이 손보고 다시
    done --> [*]
```

NAS 에서 새 폴더를 발견하면 `pending`, 복사 중 `copying`, 파이프라인이 도는 동안
`processing`, 끝나면 `done`. **그룹핑 신뢰도가 낮으면 자동으로 넘기지 않고**
`failed` + `state_note` 로 사람을 부른다.

`processing` 인 동안 검토 저장은 서버가 거절한다 — 반쯤 처리된 슬라이드를 검토하면
아직 안 돌아간 시야의 검출이 뒤늦게 들어오면서 이미 본 화면이 바뀐다.

### `Detection.is_current`

```mermaid
flowchart TB
    A["후보 bulk_create<br/>(길다 — 수만 행)"] --> B{"--keep-current ?"}
    B -- "예: 나란히 쌓아 둔다" --> Z["끝. is_current 는 그대로"]
    B -- 아니오 --> C["옛 is_current 내리기<br/>새 is_current 올리기<br/>교정 재바인딩 (exact → IoU → orphan)"]
    C --> Z2[끝]

    classDef tx1 fill:#e8f0fe,stroke:#4285f4
    classDef tx2 fill:#fef7e0,stroke:#f9ab00,stroke-width:2px
    class A tx1
    class C tx2
```

**파랑이 첫 트랜잭션, 주황이 두 번째다.**

가운데가 끊기면 뷰어가 "교정이 붙지 않은 새 검출" 을 보여준다. 그래서 그 부분은
반드시 한 덩어리다. `--keep-current` 를 주면 첫 트랜잭션만 하고 끝낸다 — 다른
엔진의 결과를 나란히 쌓아 두는 길이다.

---

## 6. 지금 담긴 것 (2026-08-04)

| 표 | 행 |
|---|---|
| `Site` / `Core` / `Slide` | 5 / 5 / 10 |
| `Viewpoint` / `Frame` / `Stack` | 448 / 1 318 / 317 |
| `Detection` / `Candidate` | 3 705 / 128 583 |
| `ObjectReview` / `ViewpointReview` | 6 753 / 436 |
| `Run` / `RunBatch` | 188 / 3 |
| `ThresholdSet` / `ClassDef` / `Setting` | 2 / 6 / 2 |

**교정 6 753건의 속내** — 삭제 5 467 · 되살림 637 · 분류 지정 1 254 · 메모 2.
바인딩은 전부 `exact` 다.

**실행 188건** — detect 133 · ingest 29 · stack 12 · group 7 · refilter 5 · export 2.

**묶음 셋** — `sam2-전수` · `yolo-1차` · `yolo-2차`.

**분류 여섯** — 원형 · 원형 파편 · 봉상 · 봉상 파편 · Eucampia · Chaetoceros
(뒤의 둘이 `is_taxon`, 파편 둘이 `counted=False`).

> 이 교정은 사람이 124 시야를 전수 검토해 만든 것이고 **다시 만들 수 없다.**
> `stacked/`·`out/` 은 다시 돌리면 나오고 원본 사진은 NAS 에 있지만, 이것만은
> 아니다. 큰 작업 전에는 반드시 `backup_db.py` 로 사본을 뜬다.

---

## 7. 마이그레이션

`web/viewer/migrations/` 에 0001 … 0017. **전부 걸려 있다** (2026-08-04 07:11,
`v0.3.0` 배포 때). 컨테이너가 뜨면서 `migrate` 가 돈다.

최근 것들은 전부 `ClassDef` 였다 — `0013` `counted`, `0014` Chaetoceros,
`0015` 파편 색, `0016` `hotkey`, `0017` `short`.

**여기서 조심할 것이 하나 있다.** 작업 트리의 `models.py` 는 새 칸을 아는데 DB 는
아직 모르는 상태가 **정상적으로 존재한다** — 코드를 커밋한 때와 그것을 담은
이미지를 배포한 때 사이다. 그 사이에 호스트에서 작업 트리 코드로 DB 를 물으면
`no such column` 으로 죽는다. 실제로 이 문서를 쓰다가 그렇게 죽었다(그때 DB 는
0012, 작업 트리는 0014 였다).

`dbrun.sh` 로 물으면 배포된 코드와 배포된 스키마가 함께 움직이므로 이 어긋남이
생기지 않는다. §1 의 "들어가는 문은 하나다" 가 이것을 막는다.

## 8. 아직 빈 곳

- **`export_review.py` 가 없다** (P02 5단계). 교정이 DB 에만 있어 `backup_db.py`
  가 유일한 안전망이다
- **파이프라인 일부가 아직 JSON 을 쓴다.** `refilter.py` 는 DB 로 왔고
  `focus_stack.py`·`group_focus_series.py` 가 남았다 (P02 6단계)
- `import_json.py` 는 **멱등이지만 `Candidate` 를 지우고 다시 만든다.** DB 에서만
  한 교정이 있는데 옛 JSON 을 넣으면 JSON 쪽으로 되돌아간다 — 아무 때나 돌리지 않는다
- `ObjectReview.bind_method` 가 전부 `exact` 다. IoU 바인딩은 코드에 있지만 아직
  실전에서 쓰인 적이 없다 — 엔진을 갈아 끼우는 날 처음 시험대에 오른다
