# CLAUDE.md

남극 시추코어 규조류(diatom) 현미경 사진 분석 파이프라인 + 검토·교정 뷰어.
문서는 한국어로 쓴다 — 커밋 메시지, devlog, 주석 모두.

**뷰어의 이름은 `DiaRUGA` 다** (Diatom Refocusing Using Genus-level AI, 041).
표기는 이 하나뿐 — `Diaruga`·`DIARUGA` 로 쓰지 않는다. **대문자 자리가 곧 약자의
자리다.** 화면에 약자를 풀어 쓰지 않는다.

**048 에서 이름을 한 겹으로 모았다.** 저장소·경로(`/srv/DiaRUGA`·`/data3/DiaRUGA`·
`~/venv/DiaRUGA`)·URL(`/DiaRUGA/`)·DB(`DiaRUGA.db`)가 전부 `DiaRUGA` 다. **기술이
소문자를 강제하는 자리만 `diaruga`** — Docker Hub 이미지(`honestjung/diaruga`),
파이썬 패키지(`diarugaweb`), 브라우저 `localStorage` 키. 환경변수는 `DIARUGA_*`.

**`diatom` 이 남아 있는 자리는 생물 이름이라 그렇다** — `segment_diatoms.py`,
`export_yolo.py` 의 YOLO 클래스 `diatom`, NAS 원본 폴더 `DiatomPhotos/`, 본문의
규조류(diatom). **여기를 바꾸면 안 된다.** 지난 devlog·`docs/` 의 진행 보고서도
그때 이름으로 둔다.

## 시작하기 전에 읽을 것

순서가 있다. **[HANDOFF.md](HANDOFF.md) 부터** — 지금 무엇이 돌아가고 무엇이
반쯤 되어 있고 어디를 밟으면 안 되는지가 거기 있다. 그 다음:

| 무엇을 하려는가 | 읽을 것 |
|---|---|
| DB·스키마를 건드린다 | `docs/20260804_db-specification.md`·`db-erd.md` (지금 모습), `devlog/20260730_P02_db-schema.md` (설계 근거), `web/viewer/models.py` 머리말 |
| 분류(속·형태)를 더한다 | `ClassDef` 머리말의 **채울 것 여덟**, `devlog/20260804_038`~`040` |
| 앞으로 할 일을 고른다 | `TODOs.md`, `devlog/20260729_P01_roadmap.md` |
| 판정 기준·문턱을 만진다 | `judge.py` 머리말, `devlog/20260731_007_*.md` |
| 검출기를 학습시킨다 | `devlog/20260803_P04_yolo-training.md`, `023`(자료 꾸러미), `025`(첫 판 성적) |
| 이미지·검출·교정의 관계를 만진다 | `devlog/20260805_P06_*`(계획·결정), `055`(실행), `models.py` 의 `Image` |
| 데스크탑 앱을 만든다 | `devlog/20260805_P05_desktop-app.md` (계획), `docs/20260805_desktop-app-review.md` (근거), `049`(CPU 실측), `.guides/desktop/` |
| 배포·백업을 만진다 | `.guides/web/`, `devlog/20260803_019_*`, `20260804_034_smoke-and-sentinel.md` |
| 파이프라인 알고리즘 | `README.md` (40 KB, 스크립트마다 "왜 이렇게 했는가"가 있다) |

**devlog 는 그때의 판단과 근거를 남기는 곳이다.** 계획은 `YYYYMMDD_PNN_주제.md`,
실제로 한 작업은 `YYYYMMDD_NNN_주제.md` 로 번호를 올려 가며 단계마다 끊어 적는다.
무엇을 했는지보다 **왜 그렇게 했고 무엇을 버렸는지**를 쓴다.

**라이선스는 AGPL-3.0 이다** (049). 검출 백엔드의 ultralytics 가 AGPL 이라
합쳐지는 이 저장소도 같이 간다. **`Modan2`(MIT)와 코드를 주고받을 때 방향이
있다 — MIT → 여기는 되고, 여기 → Modan2 는 안 된다.**

배포·데이터 안전 규약은 `.guides/web/README.md` (형제 프로젝트들이 같은 사고를
겪고 도달한 표준). **없으면 devdocs 클론이 안 걸린 것이다** — `../devdocs` 를
형제로 두고 `ln -s ../devdocs/guides .guides`. 이 저장소에는 커밋하지 않는다
(devdocs 는 private, 여기는 public).

## 환경

```bash
# venv 는 ~/venv/DiaRUGA 이다 (README 의 .venv 가 아니다 — HANDOFF 8.3)
python --version        # 3.12.3
```

requirements 는 넷으로 갈라져 있다 (P03·032). 호스트 venv 는 `requirements.txt`
하나면 되고, 컨테이너가 `-web`(Django·pillow·gunicorn)과 `-pipeline`(torch·SAM2)을
나눠 쓰며, `-yolo`(ultralytics)가 `--no-deps` 로 파이프라인 위에 얹힌다.

**데이터도 DB 도 저장소 안에 없다.** 위치는 `.env` 가 알려 준다(`.env.template`
참고 — 없으면 스크립트가 사진을 못 찾는다). `review/`·`groups_*.json` 은 git 추적
대상이라 저장소에 남아 있다.

```
/srv/DiaRUGA/   db/  scripts/  bin/  docker-compose.yml  .env      ← 배포
/data3/DiaRUGA/ photos/<촬영일>/<슬라이드>/                         ← NAS 구조와 1:1
               stacked/  out/  backup/  hf/  logs/  datasets/  .thumbcache/
```

컨테이너 안팎의 경로가 같다 — 명령을 그대로 옮겨 쓸 수 있다.

## 자주 쓰는 명령

### DB 를 만지는 것은 문 하나로만 들어간다

호스트 venv 로도 같은 DB 를 열 수 있지만 그러면 **같은 파일을 두 벌의 환경이
만진다 — 두 번 당했다**(낡은 `models.py` 가 NAS 반입을 죽였고, root 로 돈
컨테이너가 소유자를 바꿨다). 스크립트는 `/srv/DiaRUGA/scripts` 로 옮겨 놓은 것만
돈다. 저장소는 만들고, `/srv` 는 돌린다.

```bash
deploy/host/dbsync.sh check_db.py       # 저장소 → /srv (옆 모듈까지 따라간다)
deploy/host/dbrun.sh  check_db.py       # 컨테이너 안에서 돈다. 1초
deploy/host/dbrun.sh  check_db.py --slide rs23 -v
deploy/host/dbsync.sh --list            # 옮겨 둔 것이 저장소와 어긋났는가
```

`check_db.py` 는 **refilter/segment 뒤, `judge.py` 를 고친 뒤, 숫자가 이상할 때**
돌린다. 여기서 잡는 것은 예외가 안 나고 그냥 틀린 상태다.
`backfill_images.py --verify` 도 같은 성격이다 — 이미지·검출·교정이 앞뒤가 맞는가.

```bash
# 교정을 git 감사 기록으로 (호스트 venv 로 돈다 — Django 를 안 쓴다)
python export_review.py                 # review/<슬라이드>/g<n>.json
python export_review.py --check         # 파일 ↔ DB 대조. 아무것도 안 쓴다
python export_review.py --db <백업> --out /tmp/before && diff -r /tmp/before review/
```

```bash
# 큰 작업 전에는 반드시. 시간별 cron 이 따로 돌지만 그건 24시간 rolling 이고,
# 이건 backup/manual/ 에 따로 남아 로테이션이 안 건드린다. 일 끝나면 지우면 된다
deploy/host/dbrun.sh backup_db.py --note before-refilter

# 문턱만 바꿔 다시 거른다 (SAM2 재실행 없음, 밀리초)
deploy/host/dbsync.sh refilter.py           # 아직 안 옮겨 뒀다 — 처음 한 번
deploy/host/dbrun.sh  refilter.py --dry-run
deploy/host/dbrun.sh  refilter.py --round-texture-min 2000
```

지금 `/srv/DiaRUGA/scripts` 에 있는 것: `check_db.py` · `backup_db.py` ·
`db_sentinel.py` · `judge.py` · `batch_runs.py` · `prune_detections.py`.
없는 것을 부르면 `dbrun.sh` 가 **무엇을 옮기라고 알려 준다.**

**예외가 하나 있다 — 백업 cron 은 호스트 venv 로 돈다.** 규약이 막으려는 두 사고
(낡은 `models.py` · root 소유자)는 Django 를 거치는 코드에서 났는데,
`backup_db.py` 는 Django 를 임포트하지 않고 원본을 **읽기 전용**으로 열어
sqlite3 백업 API 만 쓴다 — 두 벌의 환경이 생기지 않는다. 그리고 이쪽이 더
중요하다: **시간별 안전망이 Docker 가 성한지에 매달리면 안 된다.** 이미지가
안 받아지거나 데몬이 죽은 날에 백업까지 같이 멈추는 것이 규약이 지키려던 것보다
비싸다. 손으로 뜰 때(`--note`)는 규약대로 `dbrun.sh` 로 간다.

### 뷰어·배포

```bash
cd /srv/DiaRUGA && docker compose up -d web      # 바깥 :80 /DiaRUGA/ 을 nginx 가 8090 으로 넘긴다
cd /srv/DiaRUGA && docker compose logs -f web
/srv/DiaRUGA/bin/deploy.sh <태그>                # pull → 스냅샷 → 교체 → 기동 게이트
/srv/DiaRUGA/bin/smoke.sh                        # 판·행 수·안전망까지 (200 은 "떴다" 일 뿐이다)
python db_sentinel.py show                      # 백업이 세운 무결성 깃발이 있는가

docker compose -f deploy/docker-compose.yml build web   # 이미지 굽기는 저장소에서
```

### 파이프라인 (GPU)

일회성으로만 돌린다. 상주시키면 VRAM 을 물고 놓지 않는다 (P03).
평소에는 `deploy/poll_nas.sh` 가 1분마다 알아서 돌린다 — 손으로 부를 일은 다시
돌릴 때뿐이다.

```bash
cd /srv/DiaRUGA
# 그룹핑만 경로를 받는다 (나머지는 슬라이드 slug). 시야가 이미 있으면 스스로 거부한다
docker compose run --rm pipeline python group_focus_series.py "/data3/DiaRUGA/photos/<촬영일>/<슬라이드>"
docker compose run --rm pipeline python focus_stack.py --slide <slug>
docker compose run --rm pipeline python segment_diatoms.py --slide <slug> \
    --scale 1.0 --points-per-side 48 --min-um 10 --max-um 150 --batch sam2-전수
docker compose run --rm pipeline python segment_diatoms.py --slide <slug> \
    --backend yolo --keep-current --batch yolo-3차      # 비교용으로 쌓기만 한다
```

**인자는 `deploy/poll_nas.sh` 와 같은 것을 쓴다** — 특히 `--scale 1.0`. 빠뜨리면
절반 해상도로 검출되고 `um_per_px` 가 2배로 기록된다.

**GPU 를 쓰는 작업은 한 번에 하나만 돈다** — 잠금이 `segment_diatoms` 안에 있어
폴러가 도는 중에 손으로 돌려도 기다렸다 이어 간다.

### 확인하는 법

**브라우저가 있다** — `playwright` + 헤드리스 크로미움(045). 키 입력·클릭·
페이지 이동·**콘솔 오류**·화면 캡처가 된다. 이벤트 배선 고장은 이것으로만 잡힌다.
**반드시 사본 DB 에 붙인다** (`DIARUGA_DB=…/사본.db DIARUGA_SCRIPT_NAME=`
`manage.py runserver 127.0.0.1:8099`). 설치는 HANDOFF 3.3 — `NODE_EXTRA_CA_CERTS`
를 빠뜨리면 사내망 TLS 때문에 죽는다.

가볍게 볼 때는 **Django 테스트 클라이언트**로 URL 을 때려 본다
(`ALLOWED_HOSTS` 에 `testserver` 를 넣어야 한다).
**node 는 있다**(`/usr/bin/node` v18) — JS 는 **렌더한** 인라인 스크립트를 뽑아
`node --check` 로 파싱한다(템플릿 원본이 아니라 렌더한 것이어야 한다).

**속성에 값이 들어 있는 것과 그 값이 유효한 것은 다르다.** SVG 경로에 10 KB 가
멀쩡히 들어 있는데 화면은 백지였던 적이 있다. 템플릿을 가를 때는 `div` 짝이 아니라
**렌더 결과의 중첩**을 파싱해서 본다.

## 구조

```
group_focus_series.py  →  focus_stack.py  →  segment_diatoms.py  →  refilter.py
   초점 시리즈 묶기         all-in-focus 합성    SAM2 / YOLO 검출 + 지표   문턱만 다시 적용
                                                        ↑
                                                    judge.py  ← 판정 규칙은 여기 하나뿐
web/viewer/
  models.py      16개 모델. 읽기 전에 파일 첫 주석부터
  images.py      Image 를 만드는 문 하나 — 파이프라인 넷과 regroup 이 지난다
  data.py        DB → 뷰가 쓰는 dict
  thresholds.py  문턱 미리보기·적용
  antarctica.py  미리 구운 해안선 (korea.py 와 짝) — 투영식이 tools/ 에도 있다
```

**검출과 교정은 `Image` 에 붙는다** (P06 · 055). `Image` 는 **검출을 돌릴 수
있는 이미지 한 장**이고 `kind` 가 `stack|frame|depth` 다 — 예전에는 `Detection` 이
`target` + nullable `frame` 으로 다형 연관을 흉내 냈다. 열쇠는 `path` 이고,
교정의 유일 제약은 `(image, mask_key)` 다.

**데이터의 원본은 `DiaRUGA.db` 다** (SQLite, WAL). `out/*.json` 등은 내보내기
형식으로만 남아 있다.

**검출 엔진이 두 벌이다.** 뷰어가 보는 것은 `sam2-전수` 묶음이고, YOLO 는
`--keep-current` 로 나란히 쌓아 두었다(`RunBatch`). **검토 화면의 `◉ SAM / ○ YOLO`
라디오**로 같은 시야를 두 엔진으로 비교한다(051, `?batch=<실행>`). `/engine/` 은
묶음 전체를 한 표로 훑는 다른 화면으로 남아 있다.

**YOLO 쪽은 읽기 전용이고, 그것을 세 겹으로 막아 뒀다**(아래). 화면이 **되는
것처럼 보이는 것**까지 막는다 — 저장만 잠그면 사람이 한 시야를 헛검토한다.

## 밟기 쉬운 곳

여기 있는 것은 **전부 실제로 한 번씩 당한 것들이다.**

**교정**

- **교정은 `Candidate` 가 아니라 `mask_key` 에 붙는다.** FK 로 매면 재검출에서
  사람의 판단이 조인 실패로 사라진다. **정규화가 덜 된 것이 아니라 소유 방향의
  선택이다** — 재생성 불가한 것(교정)이 재생성 가능한 것(검출)의 자식이 되면
  안 된다. 모든 교정 행이 `geom` 에 기하를 스스로
  들고 있어 검출기가 바뀌어도 읽힌다 — 지운 것도 학습의 음성 표본이다
  (실제로 P04 에서 음성 4,039건이 그렇게 쓰였다)
- **검출은 덮어쓰지 않고 쌓는다.** `Detection.is_current` 가 뷰어가 볼 것을 가리킨다
- **캐시된 dict 를 고치지 말 것.** `detection_for()` 가 후보를 복사한 뒤 교정을
  얹는 이유다 — 원본을 고치면 교정을 되돌려도 옛 상태가 따라붙는다
- **`/review` POST 는 그 시야의 교정 전체를 갈아치운다.** "뷰어는 늘 전체를
  보낸다" 는 전제이고, 깨지면 나머지를 지운다. **두 번 당했다** — 빈 키 목록을
  운영 DB 로 보내 14건, "읽기 전용" 이라 적어 놓고 CSS 로 버튼만 감춘 화면이
  37건. **화면을 눌러 보는 시험은 사본 DB 에 붙인다**
- **읽기 전용은 저장을 막는 것으로 끝나지 않는다.** 화면이 **되는 것처럼 보이면**
  안 된다 — 저장은 잠갔는데 우클릭 메뉴가 살아 있어서, 누르면 마스크가 지워지고
  분류가 바뀌었다(051). 그렇게 한 시야를 검토하고 새로고침하면 판단이 통째로
  사라진다. `readOnly` 갈래를 더할 때는 **반응하는 자리를 전부 센다**:
  키보드 · 우클릭 메뉴 · 탈락 펼침판 · 코멘트 칸

**DB·스키마**

- **`cp DiaRUGA.db` 금지.** WAL 이라 불완전한 사본이 나온다. `backup_db.py` 를 쓸 것
- **`NOT NULL` 칸을 더할 때는 `db_default` 를 함께 준다.** Django 의 `default` 는
  파이썬 쪽이라 **판이 다른 옛 이미지의 INSERT 에는 칼럼이 안 들어간다** — 뷰어와
  파이프라인 이미지는 굽는 주기가 달라 판이 같아질 일이 없다
- **프레임 이름은 슬라이드끼리 겹친다.** 카메라 일련번호라 같은 날 이어 찍으면
  번호대가 이어진다(260803 두 슬라이드에서 143종). 이름만으로 찾지 말 것 —
  `Frame` 에 `(slide, name)` 유일 제약이 **이미 있었다**. **제약이 있다는 것과
  조회가 그걸 쓴다는 것은 다르다** — 경고를 적어 두고도 `_viewpoint_of` 가
  `.first()` 로 아무거나 집고 있었고, 싱글턴 시야 12개의 검토가 **다른 슬라이드의
  시야를 열고 있었다**(053). 저장은 `(slug, gid)` 로 짚는다
- **파이프라인이 도는 중에 검토를 저장하면 잠긴다.** WAL 이라 읽기는 여럿이지만
  쓰기는 하나다 — 프레임 229장을 그렇게 잃었다. 트랜잭션을 나눠 고쳤지만,
  동시 작업이 일상이 되면 SQLite 를 다시 볼 문제다
- **`import_json.py` 를 아무 때나 돌리지 말 것.** 파이프라인에서는 빠졌다.
  멱등이지만 `Candidate` 를 지우고 다시 만들어서, DB 에서만 한 교정이 있는데
  옛 JSON 을 넣으면 JSON 쪽으로 되돌아간다. **지금 JSON 은 DB 보다 한참 낡았다**
- **`verify_db.py` 는 임포트하면 `ImportError` 다.** 본문이 전부 최상위에 있어
  임포트만으로 실행됐고, DB 가 없으면 빈 `DiaRUGA.db` 를 만들었다. 막아 뒀다
- **`refilter.py` 에서 주지 않은 문턱은 현재 값을 그대로 쓴다.** 전부 기본값으로
  되돌리는 것이 아니다 — 하나 바꾸려다 나머지가 조용히 초기화되는 것을 막는 설계다
- **분류를 더할 때 "표에 행 하나" 로 끝나지 않는다.** `label`·`short`·`badge`·
  `color`·`hotkey`·`counted`·`is_taxon`·`sort_order` 여덟에 **`base.html` 의 CSS**
  까지다(`ClassDef` 머리말에 목록이 있다). 하나라도 비면 **예외는 안 나고 그
  분류만 조용히 다르게 굴러간다** — 마스크가 투명해 "지정은 되는데 화면에 안
  보이는" 상태가 될 뻔했다. `check_db.py` 가 단축키·색만 잡아 준다 (038·040)
- **분류를 되돌릴 때는 지우지 말고 `active=False` 로 끈다.** 행을 지우면 그
  분류로 붙인 교정이 이름 없는 분류가 되어 화면에서 안 읽힌다

**성능 — 같은 실수를 세 번 했다**

- **개체 하나 재려고 이미지 전체를 훑지 말 것.** 개체는 이미지의 0.3% 다.
  **`bbox` 는 부르는 쪽에서 받는다** — 안 받고 `np.nonzero` 로 찾으면 아끼려던
  비용을 그대로 쓴다 (두 번 다 그렇게 만들었다가 되돌렸다)
- **개수를 세려고 자료를 물질화하지 말 것.** 목록 화면이 그렇게 1.3초였다
- **빠르게 만드는 것보다 값이 안 바뀐 것을 확인하는 편이 어렵다.** `judge` 가 그
  값으로 판정하므로 달라지면 검출·문턱 이력과 어긋난다
- **고친 코드가 실제로 도는지부터 확인한다.** 컨테이너가 이미지 안의 옛 `/app` 을
  돌고 있어 "고쳤는데 안 빨라진다" 가 두 번 나왔다

**배포·컨테이너**

- **`/healthz` 의 `degraded` 는 503 이 아니라 200 이다.** 503 으로 바꾸면
  `deploy.sh` 의 기동 게이트가 200 을 기다리다 **배포가 스스로 멈춘다**.
  배포를 세우는 판단은 `smoke.sh` 가 `status != ok` 로 한다 (034)
- **백업 사본은 검증을 통과한 뒤에 제 이름을 받는다.** 뜨는 중에는 `.part` 다.
  반쯤 쓴 파일이 `DiaRUGA_*.db` 라는 이름을 달면 정리 glob 에 걸려 **가장 새
  파일로 살아남고 멀쩡한 사본을 밀어낸다** (034)
- **`DiaRUGA.db` 는 파일이 아니라 디렉토리째로 마운트한다.** 파일 하나만 물리면
  WAL 이 만드는 `-wal`·`-shm` 형제가 컨테이너 안쪽에 생겨 호스트와 WAL 을 공유하지
  못한다. 같은 DB 를 보는 줄 알았는데 아닌 상태가 된다 (P03)
- **컨테이너는 `1000:1000` 으로, `TZ=Asia/Seoul` 로 돌린다.** root 로 돌면
  `DiaRUGA.db` 소유자가 바뀌고, 시간대를 빠뜨리면 UTC 로 돌아 **사본 이름이 아홉
  시간 어긋나 정리 규칙이 가장 새 사본을 지운다** (036)
- **뷰어와 파이프라인의 판은 따로다**(`IMAGE_TAG` / `PIPELINE_TAG`). 하나로 묶으면
  뷰어 판을 올리는 순간 폴러가 없는 이미지를 가리킨다 — **4시간 반 멈췄다** (026)
- **그런데 스키마를 조이는 마이그레이션은 둘을 함께 올려야 한다.** 갈라 놓은
  것이 이번엔 반대로 문다 — 칼럼을 걷었는데 옛 파이프라인 이미지가 그 칼럼에
  INSERT 하면 폴러가 선다. **조인 사본에 파이프라인 컨테이너를 붙여 먼저 돌려
  볼 것** (055 에서 그렇게 잡았다)
- **폴러를 세울 때 crontab 을 고치지 않는다.** `poll_nas.sh` 가 `flock -n` 으로
  겹침을 막으므로 `flock /tmp/DiaRUGA-poll.lock <명령>` 이면 그 사이 실행이
  조용히 물러난다. 남의 설정을 고쳤다가 되돌리기를 잊는 쪽이 위험하다
- **`dbrun.sh` 로 돌릴 스크립트는 `check_db.py` 의 머리를 베껴 온다.**
  컨테이너 안에서는 코드가 `/app` 이라 `DIARUGA_APP` 을 봐야 한다 — 자기 옆의
  `web/` 을 보게 짜면 `No module named 'diarugaweb'` 로 죽는다
- **사내망이 `download.pytorch.org` 의 TLS 를 가로챈다.** 파이프라인 이미지 빌드가
  거기서 죽으면 `deploy/ca/` 를 볼 것. `pip` 은 시스템 CA 저장소를 보지 않아
  `PIP_CERT` 를 함께 줘야 한다

**템플릿**

- **Django 의 `{# #}` 는 한 줄짜리 주석이다.** 여러 줄이면 화면에 그대로 나온다.
  `{% comment %}` 를 쓸 것. 태그는 **JS 주석 안에서도 실행된다**
- **부모를 `extends` 한 템플릿에서 `block` 바깥에 적은 것은 렌더되지 않는다.**
  `<style>` 이 한 번도 먹은 적이 없었다 — 예외도 경고도 없는 종류의 고장이다
- **절대경로를 박지 말 것.** JS 는 `base.html` 의 `window.ROOT`, 파이썬은
  `reverse()` 를 쓴다 (서브경로 `/DiaRUGA/` 아래에서 돈다)
- **감추는 CSS 는 `base.html` 이 그 요소를 어떤 선택자로 잡고 있는지 보고 쓴다.**
  `.tools { display: none }` 이 한 번도 먹은 적이 없었다 — `.detview .tools` 가
  `display: flex` 로 특이도에서 이긴다. 세 화면이 도구를 감춘 줄 알고 계속
  내보이고 있었다(051). **`getComputedStyle` 로 확인할 것** — 예외도 경고도 없다

## 사람의 교정은 재생성 불가다

`DiaRUGA.db` 안의 교정(삭제·되살림·분류·코멘트 **6,700여 건**)은 사람이 347 시야를
검토해 만든 것이고, **다시 만들 수 없다.** `stacked/`·`out/` 은 다시 돌리면 나오고
`photos/` 는 촬영 원본이다.

`export_review.py`(P02 5단계 · P06)가 **`review/<슬라이드>/g<n>.json` 으로
내보낸다** — git 에 남는 감사 기록이자, `--check` 로 DB 와 대조하는 도구다.
Django 를 임포트하지 않고 sqlite3 로 **읽기 전용**으로 열어 `backup_db.py` 와 같은
자리에 있다(그래서 호스트에서 돌고 백업 파일도 `--db` 로 그대로 읽는다).

```bash
python export_review.py                 # 저장소 review/ 로
python export_review.py --check         # 파일 ↔ DB 대조 (안 쓴다)
python export_review.py --db <백업> --out /tmp/before && diff -r /tmp/before review/
```

**그래도 `backup_db.py` 는 계속 첫 안전망이다** — 내보내기는 교정만 담는다.
**큰 작업 전에는 반드시 사본을 뜬다.**

## 커밋

메시지는 한국어 평서문으로, **무엇을 했는지**를 쓴다. 최근 예:

```
DB 무결성 검사를 만든다 (check_db.py)
문턱 이력에 바뀐 것만 보여준다
refilter.py 를 DB 로 옮기고, 판정 규칙을 judge.py 로 떼어낸다
검토 264 시야를 YOLO 자료로 내보낸다 (export_yolo.py)
배포 전 스냅샷을 컨테이너 안에서 뜬다
```

**`git add` 는 이 세션에서 내가 직접 고친 파일만 지정한다.** `git add -A` ·
`git add .` · `git commit -a` 는 쓰지 않는다.

이 저장소는 **여러 Claude 세션이 같은 작업 트리에서 동시에 돈다.** 남의 미커밋
변경이 내 커밋에 쓸려 들어간 적이 있고, 한 번은 HANDOFF 전면 개편이 엉뚱한
메시지로 push 됐다.

```bash
git status --short                       # 커밋 전에 본다
git commit -F - -- <내가 고친 파일…>      # 파일을 지정해서
```

**"지금 트리가 전부 내 것으로 보인다" 는 확인은 근거로 삼지 않는다.** 그 사이에
늘어난다 — 실제로 048 작업 중에 옆 세션이 템플릿 셋을 고치고 있었다. 내가 손대지
않은 파일이 `git status` 에 보이면 **그대로 둔다.**

`DiaRUGA.db`·`photos/`·`out/`·`stacked/`·`backup/`·`runs/`·`datasets/` 는
gitignore 다.
