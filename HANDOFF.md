# HANDOFF — 2026-07-31 현재 상태

이어서 작업할 사람(또는 다음 세션)을 위한 인수 문서. 무엇이 돌아가고 있고, 무엇이
반쯤 되어 있고, 어디를 밟으면 안 되는지를 적는다.

**마지막 커밋** `0fef61a` · 워킹트리 깨끗
**브랜치** main (origin/main 과 같음)

---

## 1. 한 줄 요약

파이프라인 스크립트가 **전부 DB 를 쓴다**(P02 6단계 끝). 뷰어와 파이프라인이
컨테이너로 돌고, **NAS 에 새 슬라이드가 올라오면 1분 안에 감지해 검출까지 스스로
간다**(P03). 첫 슬라이드(260729, 124 시야)는 사람이 전수 검토를 마쳤다.

**지금 걸려 있는 것**: 새로 들어온 260731 슬라이드가 100x 로 찍혀 배율이 다르고
(0.045 vs 0.1126 µm/px), 텍스처 문턱이 안 맞아 통과율이 1.6% 다. 촬영 확인 대기
(9.9절·devlog 013).

---

## 2. 지금 돌아가는 것

### 뷰어 (Django 5.2, DB 기반)

화면: 데이터셋 목록 → 시야 목록 → 시야 화면 · 검출 갤러리(`/crops/`) ·
**문턱 조정(`/thresholds/`)** · 계측 표(`/detections/`)

```bash
cd /srv/diatom && docker compose up -d web     # 바깥 :9090 은 nginx 가 받는다
```

읽기·쓰기 모두 DB 다. 9절을 볼 것 — 배포 구조가 바뀌었다.

### DB (`diatom.db`, WAL)

| 표 | 행 |
|---|---|
| Site / Core / Slide | 2 / 2 / 3 |
| Viewpoint / Frame | 124 / 345 |
| Stack | 81 |
| Detection / Candidate | 124 / 18,936 |
| ViewpointReview / ObjectReview | 124 / 2,306 |
| ThresholdSet / ClassDef | 1 / 5 |

**교정 현황**: 삭제 2,044 · 되살림 133 · 분류 지정 174 · 코멘트 2 ·
**검토 완료 124/124** · 통과 개체 2,522(자동) → 627(교정 반영)

### 파이프라인 (전부 DB)

```
scan_nas → ingest_nas → group_focus_series → focus_stack --slide → segment_diatoms --slide
```

`import_json.py` 는 더 이상 파이프라인에 없다. `groups_*.json` 도 빠졌다 —
`-o` 를 줄 때만 내보낸다. 이 흐름을 `deploy/poll_nas.sh` 가 1분마다 돌린다.

---

## 3. 지금 조심할 것

### 3.1 교정은 DB 에만 있다

`review/*.json` 은 **이전 시점 스냅샷에서 멈춰 있다.** 뷰어에서 새로 하는 교정은
DB 에만 쓰인다(`export_review.py` 가 아직 없다 — P02 5단계).

- `diatom.db` 는 gitignore 다
- 사본: `backup/diatom_20260730_104445_post-migration.db` (12.6 MB, integrity ok)
- **큰 작업 전에 반드시** `python backup_db.py --note <설명>`
- `cp diatom.db` 로 뜨지 말 것 — WAL 이라 불완전한 사본이 된다

### 3.2 이상하면 `check_db.py` 부터

`refilter`·`segment_diatoms` 를 돌린 뒤, `judge.py` 의 판정 규칙을 고친 뒤, 그리고
숫자가 이상할 때 돌린다(1초). 여기서 잡는 것은 **예외가 나지 않고 그냥 틀린 상태**다.

### 3.3 `import_json.py` 를 아무 때나 돌리지 말 것

멱등이지만 **`Candidate` 를 지우고 다시 만든다.** 교정은 `mask_key` 로 붙으므로
사라지지 않지만, DB 에서만 한 교정이 있는 상태에서 옛 JSON 을 다시 넣으면
JSON 쪽 값으로 되돌아간다. 지금은 JSON = DB 라 안전하다(대조 확인).

### 3.4 `tighten_bbox.py` 는 만들어 뒀지만 **적용하지 않았다**

떠돌이 픽셀 하나가 bbox 를 부풀리는 문제(devlog 005 §5)를 고치는 스크립트다.
dry-run 까지 했다(개체 18,936 중 11,472의 bbox 가 줄고, 중복 정리를 다시 돌리면
2,522 → 2,193). **`mask_key` 를 바꾸는 작업이라 DB 이전이 끝난 뒤에 하는 것이
낫다** — 그때 `ObjectReview` 재바인딩과 한 번에 푼다.

### 3.5 devlog 005 의 숫자가 조금 낮다

devlog 를 쓴 뒤에도 교정이 이어졌다. 실제 값은 위 2절(삭제 2,044 · 분류 174)이다.

---

## 4. 어디까지 왔나 (P02 8단계)

| 단계 | 상태 |
|---|---|
| 1. 모델 + 마이그레이션 + `DATABASES` | **끝** |
| 2. `import_json.py` (멱등) | **끝** — 8초 |
| 3. 대조 `verify_db.py` | **끝** — 검사 37개 전부 일치 |
| 4. 뷰어를 DB 로 | **끝** — JSON 판과 개체 dict 하나하나까지 같은 값 |
| 5. `export_review.py` | **남음** (당분간 DB 위주로 작업하기로 해서 미뤘다) |
| 6. 스크립트 4개를 DB 에 쓰게 | **끝** — devlog 010·011·012 |
| 7. JSON 을 원본에서 내리기 | **거의** — 파이프라인에서 빠졌다. `import_json.py` 의 중복 코드가 남아 있다 |
| 8. 재바인딩 + 고아 화면 | **반** — `rebind.py` 는 만들었다(011). 고아 화면이 남았다 |

### 6단계 — `refilter.py` 는 끝났다

UPDATE 한 번이 됐고(0.9초), 문턱이 `ThresholdSet` 행에 남고 실행이 `Run` 에
기록된다. 판정 규칙은 `judge.py` 로 떼어냈다(torch 없이 돈다).

### 6단계 — `focus_stack.py` 도 끝났다 (devlog 010)

이미지는 파일 그대로 두고 메타데이터만 `Stack` 행으로 간다. **`stack_report.json`
이 없어졌다** — 슬라이드마다 덮어써져서 마지막 것만 남았고, 실제로 **81개 중
49개가 품질 지표를 잃은 상태였다.** 다시 합성해 되찾았다.

경로는 이제 DB 에서 얻는다. `groups_*.json` 의 `dir` 은 사진을 옮기면 낡는다
(실제로 `260729/…` 를 가리킨 채 남아 있었다). 이미 합성된 시야는 스스로
건너뛴다 — 예전에는 `run_batch.sh` 가 파일 존재로 판단했다.

**다음은 `segment_diatoms.py`**(489줄)가 가장 크다. 새 `Detection` 을 쌓고
`is_current` 를 옮기며 교정을 다시 맺어야 하고, **`is_current` 이동과 재바인딩은
한 트랜잭션**이어야 한다 — 중간에 끊기면 뷰어가 "교정이 붙지 않은 새 검출"을
보여준다.

`group_focus_series.py` 는 **마지막에.** 가장 짧지만(110줄) 재그룹핑이
`Viewpoint` 를 재편하므로 그 아래 검출·교정이 통째로 어긋난다.

---

## 5. 주요 파일

| 파일 | 무엇 |
|---|---|
| `web/viewer/models.py` | 스키마 14개 모델. 읽기 전에 파일 첫 주석부터 |
| `web/viewer/data.py` | DB → 뷰가 쓰는 dict. **함수 이름·반환 형태를 JSON 시절과 같게 유지**했다(템플릿을 안 건드리려고) |
| `import_json.py` | JSON → DB (멱등) |
| `check_db.py` | **DB 무결성**. 판정 캐시·현재 검출·교정 바인딩·분류·파일·문턱을 본다. 1초 |
| `verify_db.py` | DB ↔ JSON 대조. **이전 직후용**. 지금은 교정 항목이 어긋나는 것이 정상이다(DB 가 원본) |
| `backup_db.py` | DB 사본 (WAL 안전) |
| `tighten_bbox.py` | bbox 본체 정렬 — **미적용** |
| `backfill_scale_source.py` | 배율 출처 소급 — 적용 완료(일회성) |
| `devlog/20260730_P02_db-schema.md` | DB 설계와 근거. **DB 작업 전에 읽을 것** |
| `devlog/20260729_P01_roadmap.md` | 큰 그림 6가지 |
| `devlog/20260730_005_...md` | 교정 도구와 전수 검토, 그때 잡은 버그 7건 |
| `devlog/20260731_007_...md` | 문턱 조정 UI 와 무결성 검사. **문턱 적용 단위를 왜 전역으로 했는지** |
| `judge.py` | 판정 규칙. **여기가 유일한 정의다** (torch 없이 돈다) |
| `web/viewer/thresholds.py` | 문턱 미리보기·적용 |

---

## 6. 알아 두면 좋은 것들 (밟기 쉬운 곳)

- **Django 의 `{# #}` 는 한 줄짜리만 주석이다.** 여러 줄이면 화면에 그대로 나온다.
  `{% comment %}` 를 쓸 것 (devlog 005 §4.3)
- **교정은 `Candidate` 가 아니라 `mask_key` 에 붙는다.** FK 로 매면 재검출에서
  사람의 판단이 사라진다
- **모든 교정 행이 `geom` 에 기하를 들고 있다.** 검출기가 바뀌어도 읽혀야 하고,
  지운 것도 학습의 음성 표본이다
- **캐시된 dict 를 고치지 말 것.** `detection_for()` 가 후보를 복사한 뒤 교정을
  얹는 이유다 — 원본을 고치면 교정을 되돌려도 옛 상태가 따라붙는다 (005 §4.2)
- 이 머신에는 **node·브라우저가 없다.** JS 는 렌더한 인라인 스크립트를 뽑아
  구문·미선언 참조 검사로 확인해 왔다(그 검사가 실제 버그를 잡았다)
- **`verify_db.py` 는 임포트하면 `ImportError` 를 낸다.** 본문이 전부 최상위에
  있어서 임포트만으로 `django.setup()` 이 돌고, **DB 가 없으면 빈 `diatom.db` 를
  만든다.** 실제로 한 번 그렇게 만들어져서 막아 뒀다(실행 전용)
- GPU·디스크는 아래 8절 — **머신이 바뀌었다**

---

## 7. 시료에 대해

남극에서 채취한 시추코어의 규조류다. 폴더명이 `<지역>-<코어> <깊이>cm` 꼴이다.

```
RS23-GC03     71 cm
WAP13-GC47   116 cm      <- 같은 코어의 두 깊이
WAP13-GC47   450 cm
```

DB 에 `Site`·`Core`·`Slide.depth_cm` 으로 갈라 담았다 — *같은 코어에서 깊이에 따른
군집 변화*와 *지역별 차이*가 분석 목적이라 통짜 문자열로는 질의가 안 된다.
**지역 코드의 정식 명칭(`Site.name`·`region`)은 비어 있다.** 사람이 채울 값이다.

---

## 8. 머신을 옮겼다 (2026-07-31)

작업 환경이 **이전 서버에서 이 머신으로 바뀌었다.** 코드는 git 에서 받았고, 데이터는
`backup/diatom-snapshot-20260731_024326.tar.gz` (1.13 GB) 를 풀어 옮겼다.

### 8.1 GPU — 재부팅으로 해결됐다 (아래는 그때 기록)

`apt upgrade` 가 드라이버를 올렸는데 **실행 중인 커널에는 옛 모듈이 그대로 물려
있다.** 그래서 `nvidia-smi` 가 죽고 `torch.cuda.is_available()` 이 `False` 다.

| | 버전 |
|---|---|
| 로드된 커널 모듈 | `580.126.09` ← 옛 것 |
| 유저스페이스 (`libnvidia-ml`, `libcuda`) | `580.173.02` |
| 디스크에 설치된 모듈 | `580.173.02` |

증상은 두 가지 얼굴로 나온다 — `nvidia-smi` 는 `Failed to initialize NVML:
Driver/library version mismatch`, torch 는 `CUDA error 804: forward compatibility
was attempted on non supported HW`. **둘 다 원인이 같다.**

**재부팅 한 번이면 끝난다.** DKMS 가 `580.173.02` 를 현재 커널(`6.8.0-106`)과
새 커널(`6.8.0-136`) **양쪽에 이미 빌드해 뒀다** — 재설치나 재빌드가 필요 없다.
재부팅하면 커널이 `6.8.0-136` 으로 올라간다.

> **모듈만 다시 올리는 것(`rmmod`)은 권하지 않는다.** GDM 이 떠 있고
> `graphical.target` 이라 `nvidia` 참조수가 152 다 — 데스크톱을 내려야 해서
> 재부팅과 다를 게 없으면서 실패할 구석만 많다. `libc6`·`apparmor` 때문에
> `/var/run/reboot-required` 도 이미 서 있다.

재부팅 뒤 확인:

```bash
uname -r                     # 6.8.0-136-generic
nvidia-smi                   # 580.173.02
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

### 8.2 GPU 구성이 달라졌다 — **한 장이다**

이전 서버는 두 장이었고 "1번은 다른 작업이 점유 중이니 `CUDA_VISIBLE_DEVICES=0`"
이라고 적혀 있었다. **이 머신은 다르다.**

```
01:00.0  NVIDIA GA104 [GeForce RTX 3060 Ti]     <- 이것 하나
0a:00.0  AMD Cezanne [Radeon Vega]              <- 내장, 화면용
```

`CUDA_VISIBLE_DEVICES` 를 걸 이유가 없어졌다. 대신 **VRAM 8 GB 다** — 검출을
돌릴 때 `--scale`·`points_per_side` 에서 이전 서버 설정이 그대로 통하는지는
**아직 확인하지 못했다**(재부팅 전이라 돌려보지 못했다).

### 8.3 venv 위치가 README 와 다르다

README·스냅샷 README.txt 는 `.venv` 를 만들라고 하지만, 이 머신은
**`~/venv/diatom`** 을 쓴다 (Python 3.12.3). 설치는 끝났다 —
`torch 2.13.0+cu126` · `torchvision 0.28.0+cu126` · `SAM-2 1.0` · Django 5.2.16 ·
opencv-headless · numpy · pillow.

> **`requirements.txt` 에 Django 가 없다.** 뷰어가 Django 로 도는데 목록에는
> torch·SAM2·opencv 만 있어서 따로 깔아야 했다. 넣어 두는 편이 낫다.

### 8.4 데이터 복원 상태 — 검증까지 끝냈다

`diatom.db` (12.7 MB) · `260729/` (994 M) · `out/` (92 M) · `stacked/` (68 M) 를
프로젝트 루트에 놓았다. `groups_*.json` 과 `review/` 는 git 것과 **바이트 동일**이라
건드리지 않았다. 마이그레이션도 DB 와 코드가 3건으로 일치해 `migrate` 가 필요 없다.

- `check_db.py` **12개 검사 전부 OK**. 특히 **`바인딩: {'exact': 2408}`** —
  교정이 하나도 고아가 되지 않았다(이전에서 제일 잃기 쉬운 것이다)
- 뷰어 전 화면 200 (데이터셋 3종 × 목록·`/crops/`·`/detections/`·`/thresholds/`,
  시야 화면, `/healthz`). `/img` 로 원본 프레임·합성본이 실제로 스트리밍된다
- `journal_mode` 는 스냅샷의 `delete` 에서 Django 가 붙으며 **`wal` 로 돌아왔다** —
  다시 `cp diatom.db` 금지, `backup_db.py` 를 쓸 것 (3.1 절)

보관본은 `backup/*.tar.gz` 하나만 남겼다(gzip CRC·목록 1,400 항목 확인). 푼
디렉터리는 지웠다.

### 8.5 DB 표(2절)가 이 스냅샷보다 오래됐다

2절 표는 이전 시점 값이다. 실측은 이렇다 — 문턱 조정 UI 를 실제로 쓴 흔적이다.

| | 2절 표 | 실측 |
|---|---|---|
| ObjectReview | 2,306 | **2,408** |
| 삭제 / 되살림 / 분류 | 2,044 / 133 / 174 | **2,084 / 139 / 293** |
| ThresholdSet | 1 | **2** |
| Run | — | **25** |

분류 내역: `rod_frag` 118 · `round_frag` 120 · `rod` 29 · `eucampia` 21 · `round` 5

---

## 9. 컨테이너로 옮겼다 (2026-07-31, P03)

**뷰어는 이제 컨테이너로 돈다.** 파이프라인 이미지도 있지만 아직 상주하지 않는다.
자세한 것은 `devlog/20260731_008_containerize.md`, 계획은 `20260731_P03_*`.

### 9.1 어디서 무엇이 도는가

```
바깥 :9090 ──nginx──▶ 127.0.0.1:8090 ──▶ diatom-web-1 (gunicorn, uid 1000)
                                              │
/srv/diatom/    docker-compose.yml  .env  ────┤  배포. diatom.db 가 여기 있다
/data3/diatom/  photos/<촬영일>/<슬라이드>/  ──┘  사진·산출물·백업·HF 캐시
                stacked/ out/ backup/ hf/
```

**저장소는 굽고, `/srv/diatom` 은 돌린다** (phyloserver 와 같은 갈래).
컨테이너 안팎의 경로는 같다 — 명령을 그대로 옮겨 쓸 수 있다.

```bash
cd /srv/diatom && docker compose up -d web                    # 뷰어 (배포)
cd /srv/diatom && docker compose run --rm pipeline <명령>      # GPU, 일회성

docker compose -f deploy/docker-compose.yml build web         # 이미지 굽기 (저장소)
```

### 9.2 데이터가 저장소 밖으로 나갔다

사진·산출물은 `/data3/diatom/` 이다. `/` 가 74% 차 있었고 슬라이드가 계속 들어온다.

- 위치는 `.env` 의 `DIATOM_DATA_ROOT` 가 알려 준다 (`.env.template` 이 견본,
  `.env` 는 gitignore). **없으면 호스트에서 `check_db.py` 가 사진을 못 찾는다**
- `photos/` 아래는 `<촬영일>/<슬라이드>/` 두 단계다 — NAS 구조와 1:1 이다.
  평탄하게 펴면 같은 슬라이드를 다시 촬영했을 때 이름이 부딪힌다
- **`review/`(124개)와 `groups_*.json`(3개)은 저장소에 남아 있다.** git 이 추적하는
  감사 기록이라 `DATA_ROOT` 를 따라가지 않는다 — `REVIEW_ROOT` 가 따로 있다

### 9.3 파이프라인은 일회성으로만 돌린다

`profiles: [manual]` 로 묶어 `up` 에 딸려 뜨지 않는다. 상주 워커로 두면 PyTorch
캐싱 할당자가 최대치 VRAM 을 프로세스가 죽을 때까지 물고 있다. 3060 Ti 는 8 GB 뿐이다.

컨테이너를 `--gpus all` 로 띄우는 것 자체는 VRAM 을 쓰지 않는다(확인함: 77 MiB →
77 MiB). 메모리를 잡는 것은 컨테이너가 아니라 그 안에서 CUDA 컨텍스트를 만드는
프로세스다.

### 9.4 사내망이 TLS 를 가로챈다

KOPRI 망이 `download.pytorch.org` 를 자체 CA 로 다시 서명한다. 파이프라인 이미지
빌드가 `CERTIFICATE_VERIFY_FAILED` 로 죽으면 `deploy/ca/README.md` 를 볼 것.
PyPI·GitHub·huggingface.co 는 통과한다.

### 9.5 nginx

`/etc/nginx/sites-enabled/diatom` 에 설치돼 있다(원본은 `deploy/nginx/diatom.conf`).
바깥 `:9090` 을 받아 `127.0.0.1:8090` 으로 넘긴다. **컨테이너는 루프백에만 붙는다** —
바깥으로 나가는 문은 nginx 하나뿐이다.

80 을 쓰지 않은 이유: 이 머신의 80 은 phyloserver 블록이 `server_name 172.16.116.98`
로 이미 잡고 있다. 서브경로(`/diatom/`)로 얹으려면 `FORCE_SCRIPT_NAME` 에 더해
템플릿의 `fetch()` 5곳이 절대경로라 손봐야 한다.

**nginx 가 사진을 직접 서빙하지는 않는다.** `/img?p=…&w=400` 은 즉석에서 축소본을
만들고 `/crop` 은 bbox 로 잘라낸다 — 정적 파일이 아니고 경로도 쿼리 문자열이다
(폴더명에 공백이 있어서). 재 보니 썸네일 캐시 적중이 1.1~1.4 ms, 시야 화면 전체가
29 ms 라 병목도 아니다. 필요해지면 `X-Accel-Redirect` 가 맞는 방식이다.

### 9.6 백업

`backup_db.py` 는 **호스트에서 돌린다.** 컨테이너가 서빙하는 중에 떠도 안전하다
(30개 요청을 처리하는 중에 시험함 — `integrity=ok`). 디렉토리째 마운트해서 호스트와
컨테이너가 같은 inode·같은 WAL 을 보기 때문이다.

호스트에서 도는 게 **오히려 낫다** — 이 스크립트는 Django 를 임포트하지 않는 마지막
안전망이라 컨테이너가 안 뜨는 상황에서도 돌아야 한다.

사본은 파일 하나로 떨어진다. SQLite 온라인 백업 API 로 뜬 뒤 `journal_mode=DELETE`
를 걸어 `-wal`·`-shm` 이 따라다니지 않게 한다. 사본은 `/data3/diatom/backup/` 이다.

**오프사이트는 NAS 다** (`sync_backup_nas.py`, devlog 009). 이 장비가 개발·운영·
백업을 겸해서 `/data3` 안의 사본만으로는 디스크 한 장에 교정 2,408건이 걸린다.

```bash
python backup_db.py --note <꼬리말>          # 로컬 스냅샷 (검증 포함)
python sync_backup_nas.py --keep 30          # 검증된 것만 NAS 로, 수신 후 재검증
```

**라이브 DB 를 복사하지 않는다** — 검증을 통과한 단일 파일 스냅샷만 소비한다.
NAS 가 안 붙었으면 거부한다(`/proc/mounts` 확인). 빈 디렉토리에 쓰면 "오프사이트에
뒀다"고 믿으면서 같은 디스크에 쌓인다. 검증 실패 시 **정리를 건너뛴다** — 지난
성공 사본이 유일한 안전망일 수 있다. 두 게이트 모두 실제로 터뜨려 확인했다.

아직 cron 에 걸지 않았다. NAS 가 `hard` 마운트라 cron 에서는 `timeout` 으로 감쌀 것
(스크립트 머리말에 한 줄 있다).

### 9.7 NAS 자동 수집이 돈다 (P03 4·5단계, devlog 013·014)

```
* * * * * deploy/poll_nas.sh      # 호스트 cron, 1분마다
```

새 슬라이드가 NAS 에 올라오면 가져와 그룹핑·합성·검출까지 스스로 돈다.
할 일이 없으면 1~2초에 끝나고 **GPU 를 건드리지 않는다**. 일이 있을 때만 로그를
남긴다 (`/data3/diatom/logs/poll.log`).

**복사가 끝났는지는 mtime 으로 판단하지 않는다.** `rsync -a` 가 원본 시각을
보존해서 한창 들어오는 중에도 조용해 보인다. 폴더의 (파일 수·바이트) 지문을
기억해 두고 `--stable-min`(기본 5분) 동안 안 바뀌어야 가져온다.

밀린 것은 다음 주기가 이어서 한다. `failed` 슬라이드는 건드리지 않는다.

### 9.8 아직 안 한 것

- 파이프라인 스크립트는 아직 호스트 venv 기준이다. `run_batch.sh` 의
  `PY=.venv/bin/python` 도 그대로다 — P02 6단계와 함께 정리한다
- 저장소 `backup/` 에 머신 이전 때 쓴 스냅샷이 2.3 GB 남아 있다
  (`diatom-snapshot-*.tar.gz` 와 풀어 놓은 디렉토리). DB 사본 6개는
  `/data3/diatom/backup/` 으로 옮겼다. 스냅샷은 판단해서 지울 것
