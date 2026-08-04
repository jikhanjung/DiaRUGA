# HANDOFF — 2026-08-01 현재 상태

이어서 작업할 사람(또는 다음 세션)을 위한 인수 문서. 무엇이 돌아가고 있고, 무엇이
반쯤 되어 있고, 어디를 밟으면 안 되는지를 적는다.

**브랜치** main · 워킹트리 깨끗

---

## 1. 한 줄 요약

파이프라인이 전부 DB 를 쓰고(P02 6단계 끝), 뷰어·파이프라인이 컨테이너로 돈다.
**NAS 에 새 슬라이드가 올라오면 1분 안에 감지해 검출까지 스스로 간다**(P03) —
실제로 그렇게 슬라이드 4장이 자동으로 들어와 처리를 마쳤다. 슬라이드 3 → **7**,
시야 124 → **270**.

**지금 걸려 있는 것**: 자동 처리는 끝났는데 **검토가 146 시야 밀려 있다.** 사람 손이
필요한 지점이고 파이프라인은 여기서 더 갈 곳이 없다(10절).

07-31 의 배율 문제(통과율 1.6%)는 **끝났다** — XML 의 대물렌즈 값을 믿지 않고 40x 로
계산한다(devlog 015). 7개 슬라이드가 전부 같은 배율이다.

---

## 2. 지금 돌아가는 것

### 뷰어 (Django 5.2, DB 기반)

**http://172.16.116.98/diatom/** — 랜딩 페이지(`/`)의 "Diatom Viewer" 카드에서도
간다. nginx 가 80 에서 `/diatom/` 을 떼고 `127.0.0.1:8090` 의 컨테이너로 넘긴다.

> **옛 주소 `:9090` 은 301 로 여기로 넘어온다.** 사내 VPN 이 9090 을 통과시키지
> 않아서 옮겼다 (devlog 018). 서빙하는 경로는 하나다.

화면: 데이터셋 목록 → 시야 목록 → 시야 화면 · 검출 갤러리(`/crops/`) ·
문턱 조정(`/thresholds/`) · 계측 표(`/detections/`) ·
**시료 속성 편집(`/d/<slug>/edit/`)**

```bash
cd /srv/diatom && docker compose up -d web
```

읽기·쓰기 모두 DB 다. 9절을 볼 것.

### DB (`diatom.db`, WAL)

| 표 | 행 |
|---|---|
| Site / Core / Slide | 3 / 3 / **7** |
| Viewpoint / Frame | **270** / **892** |
| Stack | **184** |
| Detection / Candidate | **349** / **38,638** |
| ViewpointReview / ObjectReview | 126 / **2,441** |
| ThresholdSet / ClassDef / Run | 2 / 5 / **55** |

**교정 현황**: 삭제 2,102 · 되살림 147 · 분류 지정 309 · 코멘트 2
분류 내역: `round_frag` 130 · `rod_frag` 122 · `rod` 30 · `eucampia` 22 · `round` 5

**검토는 124/270 시야.** 처음 3장(RS23 71cm · WAP13 116cm · 450cm)만 전수 검토가
끝났고, NAS 로 들어온 4장은 손대지 않았다.

| | 자동 통과 | 교정 반영 |
|---|---|---|
| 검토 끝난 3장 | 2,522 | **594** |
| 전체 7장 | 5,428 | 3,497 |

> 전체 행의 3,497 은 **검토 안 한 4장이 자동 판정 그대로**라서 큰 것이다. 정밀도로
> 읽으면 안 된다. 의미 있는 숫자는 위 줄(2,522 → 594, 정밀도 23.6%)이다.

### 슬라이드별 상태

| 슬라이드 | 시야 | 검토 | 비고 |
|---|---|---|---|
| RS23-GC03 71cm | 34 | **34/34** | 첫 전수 검토 |
| WAP13-GC47 116cm | 47 | **47/47** | 단독 시야 26개 (그룹핑 임계값 미확인) |
| WAP13-GC47 450cm | 43 | **43/43** | |
| RS23-GC03 231cm | 19 | 0 | NAS 자동 |
| RS23-GC03 369cm | 74 | 0 | NAS 자동 · 배율 문제로 재처리한 것 |
| AM22-GC10B 25cm | 26 | 0 | NAS 자동 · **그룹핑 의심**(3.6절) |
| AM22-GC10B 261cm | 27 | 0 | NAS 자동 |

7장 모두 `state=done`.

### 파이프라인 (전부 DB)

```
scan_nas → ingest_nas → group_focus_series → focus_stack --slide → segment_diatoms --slide
```

`import_json.py` 는 더 이상 파이프라인에 없다. `groups_*.json` 도 빠졌다 —
`-o` 를 줄 때만 내보낸다. 이 흐름을 `deploy/poll_nas.sh` 가 1분마다 돌린다.

**GPU 를 쓰는 작업은 한 번에 하나만 돈다.** 잠금이 `segment_diatoms` 안에 있어서
부르는 쪽이 기억할 필요가 없다 — 폴러가 도는 중에 손으로 돌리면 기다렸다 이어 간다.

---

## 3. 지금 조심할 것

### 3.1 교정은 DB 에만 있다

`review/*.json` 은 **이전 시점 스냅샷에서 멈춰 있다.** 뷰어에서 새로 하는 교정은
DB 에만 쓰인다(`export_review.py` 가 아직 없다 — P02 5단계).

- `diatom.db` 는 gitignore 다. 실물은 `/srv/diatom/db/`
- **큰 작업 전에 반드시** `python backup_db.py --note <설명>`
- `cp diatom.db` 로 뜨지 말 것 — WAL 이라 불완전한 사본이 된다
- 사본은 `/data3/diatom/backup/`, 오프사이트는 NAS (9.6절)

### 3.2 이상하면 `check_db.py` 부터

`refilter`·`segment_diatoms` 를 돌린 뒤, `judge.py` 의 판정 규칙을 고친 뒤, 그리고
숫자가 이상할 때 돌린다(1초). 여기서 잡는 것은 **예외가 나지 않고 그냥 틀린 상태**다.
실제로 `--scale 1.0` 을 빠뜨려 두 시야가 절반 해상도로 검출된 것을 이 검사가 잡았다.

현재 12개 검사 전부 OK, 바인딩 `{'exact': 2441}` — 고아 교정 0.

### 3.3 뷰어 동작은 사본 DB 로 시험한다

검토 차단을 시험하다 **실데이터의 교정 14건을 지웠다**(devlog 017). 화면을 눌러
보는 시험은 사본을 만들어 거기에 붙인다.

### 3.4 `import_json.py` 를 아무 때나 돌리지 말 것

멱등이지만 **`Candidate` 를 지우고 다시 만든다.** 교정은 `mask_key` 로 붙으므로
사라지지 않지만, DB 에서만 한 교정이 있는 상태에서 옛 JSON 을 다시 넣으면
JSON 쪽 값으로 되돌아간다. **지금은 JSON 이 DB 보다 한참 낡았다 — 돌리지 말 것.**

### 3.5 `tighten_bbox.py` 는 만들어 뒀지만 **적용하지 않았다**

떠돌이 픽셀 하나가 bbox 를 부풀리는 문제(devlog 005 §5)를 고치는 스크립트다.
dry-run 까지 했다. **`mask_key` 를 바꾸는 작업이라** P02 8단계(재바인딩·고아 화면)와
한 번에 푸는 것이 낫다. dry-run 숫자는 슬라이드 3장 시절 것이라 다시 재야 한다.

### 3.6 `AM22-GC10B 25cm` 의 그룹핑이 의심스럽다

새 경고 기준(여유 0.2)에 걸린다 — 그룹 안 최소 상관이 **0.594** 다(정상 0.90~0.99).
초점 시리즈가 잘못 묶였을 수 있다. **검토를 시작하기 전에 보는 것이 싸다** — 교정을
붙인 뒤에 재그룹핑하면 `Viewpoint` 가 재편되어 그 아래가 통째로 어긋난다.

---

## 4. 어디까지 왔나 (P02 8단계)

| 단계 | 상태 |
|---|---|
| 1. 모델 + 마이그레이션 + `DATABASES` | **끝** |
| 2. `import_json.py` (멱등) | **끝** — 8초 |
| 3. 대조 `verify_db.py` | **끝** — 검사 37개 전부 일치 |
| 4. 뷰어를 DB 로 | **끝** |
| 5. `export_review.py` | **남음** — 교정 2,441건이 DB 에만 있다 |
| 6. 스크립트 4개를 DB 에 쓰게 | **끝** — devlog 010·011·012 |
| 7. JSON 을 원본에서 내리기 | **거의** — 파이프라인에서 빠졌다. `import_json.py` 의 중복 코드가 남아 있다 |
| 8. 재바인딩 + 고아 화면 | **반** — `rebind.py` 는 만들었다(011). **`/orphans/` 화면이 없다** |

8단계는 **학습·엔진 교체의 전제다.** 엔진이 바뀌면 `exact` 바인딩이 거의 0 이 되고,
고아가 된 교정을 볼 화면이 없으면 사람의 판단이 조용히 버려진다.

---

## 5. 주요 파일

| 파일 | 무엇 |
|---|---|
| `web/viewer/models.py` | 스키마 14개 모델. 읽기 전에 파일 첫 주석부터 |
| `web/viewer/data.py` | DB → 뷰가 쓰는 dict. **함수 이름·반환 형태를 JSON 시절과 같게 유지**했다 |
| `check_db.py` | **DB 무결성**. 검사 단위가 **슬라이드**다(전체를 한 덩어리로 보면 진짜 사고를 못 본다). 1초 |
| `judge.py` | 판정 규칙. **여기가 유일한 정의다** (torch 없이 돈다) |
| `zen_meta.py` | ZEN XML → 배율. **대물렌즈는 40x 로 고정 계산**한다 (015) |
| `runlog.py` | `Run` 이력. 새 실행이 같은 종류의 오래된 `running` 을 닫는다 |
| `rebind.py` | 새 검출과 기존 교정을 다시 맺는다 |
| `scan_nas.py` · `ingest_nas.py` | NAS 감시·수집 |
| `sync_backup_nas.py` | 검증된 스냅샷만 NAS 로 |
| `backup_db.py` | DB 사본 (WAL 안전). **Django 를 임포트하지 않는 마지막 안전망** |
| `tighten_bbox.py` | bbox 본체 정렬 — **미적용** |
| `verify_db.py` | DB ↔ JSON 대조. **이전 직후용.** 지금은 어긋나는 것이 정상이다 |
| `devlog/20260730_P02_db-schema.md` | DB 설계와 근거. **DB 작업 전에 읽을 것** |
| `devlog/20260731_015_scale-mismatch.md` | 배율 사고. **계측이 사람 눈과 어긋나면 계측을 의심할 것** |
| `devlog/20260731_016_data-safety-contract.md` | `.guides` 규약 대조. 못 지키는 조항까지 적어 뒀다 |
| `devlog/20260802_018_subpath-on-80.md` | 80 의 `/diatom/` 으로 옮긴 것. **URL 을 만드는 곳이 어디어디인지** |
| `docs/20260731_..._progress-3.md` | 3차 진척 보고서 (devlog 007~017 종합) |

---

## 6. 알아 두면 좋은 것들 (밟기 쉬운 곳)

- **교정은 `Candidate` 가 아니라 `mask_key` 에 붙는다.** FK 로 매면 재검출에서
  사람의 판단이 사라진다
- **모든 교정 행이 `geom` 에 기하를 들고 있다.** 검출기가 바뀌어도 읽혀야 하고,
  지운 것도 학습의 음성 표본이다
- **캐시된 dict 를 고치지 말 것.** `detection_for()` 가 후보를 복사한 뒤 교정을
  얹는 이유다 (005 §4.2)
- **Django 의 `{# #}` 는 한 줄짜리만 주석이다.** `{% comment %}` 를 쓸 것
- **`verify_db.py` 는 임포트하면 `ImportError` 다** (실행 전용으로 막아 뒀다)
- **브라우저는 없지만 node 는 있다**(`/usr/bin/node`, 2026-08-02 확인). 뷰어 확인은
  Django 테스트 클라이언트로 URL 을 때려 보고, JS 는 **렌더한** 인라인 스크립트를
  뽑아 `node --check` 로 파싱한다 (템플릿 원본이 아니라 렌더한 것이어야 한다)
- **Django 태그는 JS 주석 안에서도 실행된다.** 주석에 태그 이름을 그대로 적었다가
  `TemplateSyntaxError` 로 죽은 적이 있다 (018)
- **배율은 슬라이드마다 다를 수 있다.** 검사도 문턱도 슬라이드 단위다. 한 슬라이드
  **안에서** 갈라지는 것이 사고다 (017)
- **`--scale` 을 빠뜨리지 말 것.** 절반 해상도로 검출되고 `um_per_px` 가 2배로
  기록된다. 폴러와 같은 인자를 쓸 것

---

## 7. 시료에 대해

남극에서 채취한 시추코어의 규조류다. 폴더명이 `<지역>-<코어> <깊이>cm` 꼴이다.

```
RS23-GC03      71 cm / 231 cm / 369 cm
WAP13-GC47    116 cm / 450 cm
AM22-GC10B     25 cm / 261 cm
```

DB 에 `Site`·`Core`·`Slide.depth_cm` 으로 갈라 담았다 — *같은 코어에서 깊이에 따른
군집 변화*와 *지역별 차이*가 분석 목적이다.

**지역 코드의 정식 명칭(`Site.name`·`region`)은 아직 비어 있다.** 채울 화면은
만들었다(`/d/<slug>/edit/` — 지역·코어·슬라이드를 한 트랜잭션으로 저장한다).
`RS = 로스해` 같은 것은 **추천과 힌트로만** 보여 주고 자동으로 단정하지 않는다.

---

## 8. 이 머신

작업 환경이 이전 서버에서 이 머신으로 바뀌었다(2026-07-31).

### 8.1 GPU 는 한 장이다

```
01:00.0  NVIDIA GA104 [GeForce RTX 3060 Ti]   VRAM 8 GB   드라이버 580.173.02
0a:00.0  AMD Cezanne [Radeon Vega]            내장, 화면용
```

이전 서버는 두 장이라 `CUDA_VISIBLE_DEVICES=0` 을 걸었지만 **여기서는 걸 이유가
없다.** VRAM 이 8 GB 뿐이라 파이프라인을 상주시키지 않는다(9.3절).

> 이전 직후 `nvidia-smi` 가 죽고 `torch.cuda.is_available()` 이 `False` 였던 것은
> `apt upgrade` 가 드라이버를 올렸는데 실행 중인 커널에 옛 모듈이 물려 있어서였다.
> **재부팅으로 끝났다.** 같은 증상(NVML mismatch / CUDA error 804)이 다시 보이면
> 이것을 의심할 것.

### 8.2 venv 는 `~/venv/diatom` 이다

README 의 `.venv` 가 아니다. Python 3.12.3 · `torch 2.13.0+cu126` ·
`torchvision 0.28.0+cu126` · `SAM-2 1.0` · Django 5.2.16 · opencv-headless.

requirements 는 셋으로 갈라져 있다 — 호스트는 `requirements.txt`, 컨테이너가
`-web`(Django·pillow·gunicorn)과 `-pipeline`(torch·SAM2)을 나눠 쓴다.

---

## 9. 배포 (P03)

자세한 것은 `devlog/20260731_008_containerize.md`, 계획은 `20260731_P03_*`.

### 9.1 어디서 무엇이 도는가

```
바깥 :80 /diatom/ ──nginx──▶ 127.0.0.1:8090 ──▶ diatom-web-1 (gunicorn, uid 1000)
바깥 :9090 ──301──▶ 위로                            │
                                                    │
/srv/diatom/    db/  docker-compose.yml  .env ──────┤  배포
/data3/diatom/  photos/<촬영일>/<슬라이드>/  ───────┘  사진·산출물·백업·HF 캐시·로그
                stacked/ out/ backup/ hf/ logs/
```

**저장소는 굽고, `/srv/diatom` 은 돌린다.** 컨테이너 안팎의 경로가 같아 명령을
그대로 옮겨 쓸 수 있다.

```bash
cd /srv/diatom && docker compose up -d web                    # 뷰어
cd /srv/diatom && docker compose run --rm pipeline <명령>      # GPU, 일회성
docker compose -f deploy/docker-compose.yml build web         # 이미지 굽기 (저장소)
```

### 9.2 데이터가 저장소 밖으로 나갔다

- 위치는 `.env` 의 `DIATOM_DATA_ROOT` 가 알려 준다 (`.env.template` 이 견본)
- `photos/` 아래는 `<촬영일>/<슬라이드>/` 두 단계 — NAS 구조와 1:1. 평탄하게 펴면
  같은 슬라이드를 다시 촬영했을 때 이름이 부딪힌다
- **`review/`·`groups_*.json` 은 저장소에 남아 있다** — git 이 추적하는 감사 기록이라
  `REVIEW_ROOT` 를 따로 본다
- **DB 디렉토리(`db/`)만 마운트한다.** `/srv/diatom` 을 통째로 물렸더니 `.env` 의
  `SECRET_KEY` 가 컨테이너에서 읽혔다 — 잘라 냈다(016). 파일 하나만 물려도 안 된다
  (`-wal`·`-shm` 이 컨테이너 안쪽에 생겨 WAL 을 공유하지 못한다)
- **컨테이너는 `1000:1000` 으로 돌린다.** root 로 돌면 소유자가 바뀌어 호스트의
  `backup_db.py`·`check_db.py` 가 못 쓰게 된다

### 9.3 파이프라인은 일회성으로만 돌린다

`profiles: [manual]` 로 묶어 `up` 에 딸려 뜨지 않는다. 상주 워커로 두면 PyTorch
캐싱 할당자가 최대치 VRAM 을 프로세스가 죽을 때까지 물고 있다.

컨테이너를 `--gpus all` 로 띄우는 것 자체는 VRAM 을 쓰지 않는다(77 MiB → 77 MiB).
메모리를 잡는 것은 컨테이너가 아니라 그 안에서 CUDA 컨텍스트를 만드는 프로세스다.

### 9.4 사내망이 TLS 를 가로챈다

KOPRI 망이 `download.pytorch.org` 를 자체 CA 로 다시 서명한다. 파이프라인 이미지
빌드가 `CERTIFICATE_VERIFY_FAILED` 로 죽으면 `deploy/ca/README.md` 를 볼 것.
`pip` 은 시스템 CA 저장소를 보지 않아 `PIP_CERT` 를 함께 줘야 한다.

### 9.5 nginx — 80 의 서브경로다

**컨테이너는 루프백에만 붙는다.** 바깥으로 나가는 문은 nginx 하나뿐이다.

| 파일 | 무엇 |
|---|---|
| `/etc/nginx/snippets/diatom-subpath.conf` | 실제 서빙. 원본은 `deploy/nginx/diatom-subpath.conf` |
| `/etc/nginx/sites-enabled/phyloserver` | 그 스니펫을 `include` 하는 한 줄이 여기 있다 |
| `/etc/nginx/sites-enabled/diatom` | `:9090` → 301. 원본은 `deploy/nginx/diatom.conf` |

80 은 phyloserver 블록이 `server_name 172.16.116.98` 로 잡고 있어서 **같은 블록 안에
location 으로 들어갔다.** 같은 `listen`·`server_name` 으로 server 블록을 둘 두면
nginx 가 앞의 것만 쓰고 뒤를 버린다.

- `proxy_pass http://127.0.0.1:8090/;` 의 **끝 슬래시가 접두를 뗀다.** 빼면 앱이
  `/diatom/…` 을 그대로 받아 전부 404 다
- Django 쪽은 `DIATOM_SCRIPT_NAME=/diatom`(`.env`) → `FORCE_SCRIPT_NAME`. 비우면
  예전처럼 뿌리에 붙는다
- **템플릿에 절대경로를 박지 말 것.** JS 는 `base.html` 이 내보내는 `window.ROOT` 를,
  파이썬은 `reverse()` 를 쓴다 (devlog 018)
- **phyloserver 저장소의 nginx 사본이 설치본보다 뒤처져 있다.** 그쪽에서 배포하면
  `include` 한 줄이 날아간다
- 랜딩 페이지의 카드는 `/srv/paleolab/index.html` 이다. **저장소 사본이 없다** —
  실물이 그 파일 하나뿐이다

**nginx 가 사진을 직접 서빙하지는 않는다** — `/img?p=…&w=400` 은
즉석에서 축소본을 만들고 `/crop` 은 bbox 로 잘라낸다. 썸네일 캐시 적중 1.1~1.4 ms,
시야 화면 전체 29 ms 라 병목이 아니다.

### 9.6 백업

```bash
python backup_db.py --note <꼬리말>          # 로컬 스냅샷 (검증 포함)
python sync_backup_nas.py --keep 30          # 검증된 것만 NAS 로, 수신 후 재검증
```

**호스트에서 돌린다.** 컨테이너가 서빙하는 중에 떠도 안전하다(30개 요청 처리 중
시험, `integrity=ok`). SQLite 온라인 백업 API 로 뜬 뒤 `journal_mode=DELETE` 를 걸어
`-wal`·`-shm` 이 따라다니지 않게 한다.

**오프사이트는 NAS 다.** 이 장비가 개발·운영·백업을 겸해서 `/data3` 안의 사본만으로는
디스크 한 장에 교정 2,441건이 걸린다. 라이브 DB 를 복사하지 않고 검증을 통과한 단일
파일 스냅샷만 소비한다. NAS 가 안 붙었으면 거부한다(`/proc/mounts` 확인). 검증
실패 시 **정리를 건너뛴다** — 지난 성공 사본이 유일한 안전망일 수 있다.

**cron 에 걸려 있다** (034). 세 track 이 다 있다 — 배포 전 스냅샷(`deploy.sh`, 20개)
· 시간별 · 일별 오프사이트.

```cron
20 * * * *  backup_db.py --keep 48                     → logs/backup.log
40 4 * * *  timeout 600 sync_backup_nas.py --keep 720   → logs/nas-sync.log
```

**유지 개수는 관계다** (`.guides/web/data-safety.md` §6): `개수 × 주기 ≥ 오프사이트
간격`. 48 × 1h ≥ 24h (2배 여유 — 손으로 뜬 스냅샷이 NAS 로 건너가기 전에 밀려나지
않게). NAS 의 720 은 **30일 × 24** 다 — 시간별이 되면서 옛 값 30 은 "30일" 이 아니라
"30시간" 이 되어 버렸다. **주기를 바꾸면 이 값을 같이 봐야 한다.**

**실패하면 셋을 다 한다** (034). 정리를 건너뛰고, `.corrupt` 로 증거를 남기고,
DB 옆에 `INTEGRITY_FAIL` 깃발을 세운다. `/healthz` 가 그 깃발을 읽어 `degraded` 를
내고 `smoke.sh` 가 배포를 세운다 — 로그에만 적으면 읽는 사람이 없는 동안 안전망은
꺼져 있는 것과 같다.

```bash
python db_sentinel.py show                   # 지금 선 깃발
python db_sentinel.py clear backup_db        # 원인을 확인한 뒤 손으로 내린다
```

### 9.6.1 smoke

```bash
/srv/diatom/bin/smoke.sh            # .env 의 IMAGE_TAG 를 기대값으로
/srv/diatom/bin/smoke.sh v0.2.0
```

`/healthz` 200 · `status=ok` · 판 일치 · **행 수 > 0** · nginx 경유 200 을 본다.
`deploy.sh` 가 마지막에 부르고, 따로도 돌린다. **200 만으로는 판이 갈렸는지도, 빈
DB 를 물었는지도 모른다** — 둘 다 형제 프로젝트가 실제로 당한 것이다.

### 9.7 NAS 자동 수집이 돈다

```
* * * * * deploy/poll_nas.sh      # 호스트 cron, 1분마다
```

새 슬라이드가 올라오면 가져와 그룹핑·합성·검출까지 스스로 돈다. 할 일이 없으면
1~2초에 끝나고 **GPU 를 건드리지 않는다**. 일이 있을 때만 로그를 남긴다
(`/data3/diatom/logs/poll.log`).

**복사가 끝났는지는 mtime 으로 판단하지 않는다.** `rsync -a` 가 원본 시각을
보존해서 한창 들어오는 중에도 조용해 보인다. 폴더의 (파일 수·바이트) 지문을
기억해 두고 `--stable-min`(기본 5분) 동안 안 바뀌어야 가져온다.

밀린 것은 다음 주기가 이어서 한다. `failed` 슬라이드는 건드리지 않는다.

### 9.8 아직 안 한 것

- **`sync_backup_nas.py` 가 cron 에 없다** (수동). 마지막 오프사이트는 07-31 21:51
- **`/` 가 80% (45G 남음).** 저장소 `backup/` 에 머신 이전 때 쓴 스냅샷·DB 사본이
  3.4 GB 남아 있다. `/data3` 는 9% 라 여유가 있다 — 판단해서 지울 것
- **뷰어에 인증이 없다.** 80 으로 나오면서 노출 면이 넓어졌다(랜딩 페이지에 카드도
  걸렸다). 필요해지면 `diatom-subpath.conf` 에 `auth_basic` 을 걸면 된다 —
  Django 를 건드릴 필요가 없다
- 표준 deploy 동사 5개 중 셋이 없다 — `rollback`·`preflight`·`seed` (016)
- **034 의 것이 아직 안 떴다.** 뜬 판은 `v0.1.19` 라 `/healthz` 가 평문 `ok` 를
  낸다. 판을 굽고 올려야 무결성 깃발·`smoke` 가 실제로 돈다

---

## 10. 다음에 할 일

순서대로 적는다. 자세한 것은 `TODOs.md`.

1. **`AM22-GC10B 25cm` 그룹핑 확인** — 교정을 붙이기 전이 가장 싸다 (3.6절)
2. **검토 146 시야** — 파이프라인이 더 갈 곳이 없다. 사람이 해야 한다
3. **`export_review.py`** (P02 5단계) — 교정 2,441건의 두 번째 안전망
4. **고아 화면 `/orphans/`** (P02 8단계) — 학습·엔진 교체의 전제
5. **원형 판정 기준 실물 확인 · 재현율 실측** — 당면 과제 1·2순위

외부에 걸린 것: **촬영 쪽에서 ZEN 의 대물렌즈 설정을 실제 교환대와 맞춰야 한다.**
지금은 어긋나도 경고만 찍고 40x 로 계산하고 넘어간다 — 배율이 다른 슬라이드를
`state="failed"` 로 세워 사람에게 묻는 장치는 아직 없다.
