# CLAUDE.md

규조류(diatom) 현미경 사진 분석 파이프라인 + 검토·교정 뷰어.
남극 시추코어에서 시작했고 육상 노두(북평분지)가 들어와 있다.
문서는 한국어로 쓴다 — 커밋 메시지, devlog, 주석 모두.

## 자료의 층 — 말과 표가 같다 (063)

```
권역   한국 · 남극                       Site.area
 └ 지역   BP(북평분지) · RS23            Site
    └ 지점   BP09(노두) · GC03(시추코어)  Locality   ← 예전 이름이 Core 였다
       └ 시료   0901 · 71cm              Sample
          └ 관찰   (1) · (2)             Slide      = 폴더 하나 = 슬라이드글라스 하나
             └ 시야 → 사진 → 검출 → 교정
```

**"코어" 라고 부르지 않는다** — 노두는 시추한 것이 아니다. 어느 쪽인지는
`Locality.kind` 가 말하고, **그것은 지점의 성질이다**(한 지점이 코어이면서
노두일 수 없다). 육상은 지점 = 노두 = 단면이 하나라 단면 층을 따로 두지 않는다.

**관찰은 시료 하나를 처리 방법·회차를 달리해 본 것**이고 서로 동등하다. 대표를
두지 않고 이름표(`obs_label`)로 구분하며, 통계에 무엇을 넣을지는 `hide_in_list`·
`exclude_from_totals` 로 사람이 고른다.

**폴더 이름 규칙은 `web/viewer/naming.py` 하나뿐이다.** 두 체계가 다르다 —
남극은 `<지역>-<지점> <깊이>cm`, 육상은 `<지점>-<시료>` 이고 **가르는 표시는
`cm` 이 있느냐다.** 육상은 지역이 폴더에 없어 지점 코드에서 숫자를 떼어 얻는다
(`BP09` → `BP`). 뷰어·파이프라인·마이그레이션이 전부 이 파일을 본다.

**뷰어의 이름은 `DiaRUGA` 다** (Diatom Refocusing Using Genus-level AI, 041).
표기는 이 하나뿐 — `Diaruga`·`DIARUGA` 로 쓰지 않는다. **대문자 자리가 곧 약자의
자리다.** 화면에 약자를 풀어 쓰지 않는다.

**048 에서 이름을 한 겹으로 모았다.** 저장소·경로(`/srv/DiaRUGA`·`/data3/DiaRUGA`·
`~/venv/DiaRUGA`)·URL(`/DiaRUGA/`)·DB(`DiaRUGA.db`)가 전부 `DiaRUGA` 다. **기술이
소문자를 강제하는 자리만 `diaruga`** — Docker Hub 이미지(`honestjung/diaruga`),
파이썬 패키지(`diarugaweb`), 브라우저 `localStorage` 키. 환경변수는 `DIARUGA_*`.

**`diatom` 이 남아 있는 자리는 생물 이름이라 그렇다** — `pipeline/segment_diatoms.py`,
`ops/export_yolo.py` 의 YOLO 클래스 `diatom`, NAS 원본 폴더 `DiatomPhotos/`, 본문의
규조류(diatom). **여기를 바꾸면 안 된다.** 지난 devlog·`docs/` 의 진행 보고서도
그때 이름으로 둔다.

## 말을 고르는 규칙

문서·주석·커밋 메시지·화면 문구에 다 걸린다. **지난 devlog 와 `docs/` 의 진척
보고서는 그때의 기록이라 안 고친다** — 보고서는 이미 docx 로 NAS 에 나가 있다.

**한 낱말이 두 뜻을 겸하지 않게 한다.** `선다` 가 그렇게 됐다 — "폴러가
선다"(멈춘다)와 "표가 선다"(생긴다)가 같은 문서 안에 섞여 있었다. 08-03 에
들어와 70여 곳으로 번진 뒤 2026-08-12 에 뜻마다 갈랐다:

| 뜻 | 쓰는 말 |
|---|---|
| 돌다 말고 멈추다 | **멈춘다** |
| 임포트·설정이 성립하다 | **돈다** (평평해야 돈다) |
| 경고·띠가 나타나다 | **뜬다** |
| 행·개체가 만들어지다 | **생긴다** |
| 화면에서 자리를 잡다 | **놓인다** |
| 정렬·축의 기준이 되다 | **잡힌다** |
| 전제·비교가 유효하다 | **성립한다** |

**비유를 쓰지 않는다.** 이 저장소의 말은 전부 담백한 서술어다(판정·교정·묶음·
시야). 비유를 하나 끼우면 그것만 튀고, **실제와 어긋나는 그림을 심는다** —
`auto_confirmed` 를 "서명" 이라 불렀다가 "확인 표시" 로 바꿨다(2026-08-12).
마스크마다 도장을 찍는 그림을 떠올리게 하는데 실제로는 완료 한 번이 남는 것
전부에 자동으로 붙는 표시다. 그 어긋남이 나중에 **이 칸을 손그림과 같은 무게로
쓰는 실수**를 부른다. 이름과 문구가 어긋나면 둘 중 하나를 고친다.

**그 밖에 정해 둔 말** — 견주다 말고 **비교하다** · DB 의 것은 표 말고
**테이블**(화면의 표는 "표") · 겹 말고 **레이어**(시험·CI 의 layer. "두 겹으로
막다" 같은 관용 표현은 그대로) · 순서대로 늘어놓는 것은 세운다·나열한다 말고
**정렬한다**(`세운다` 는 대표·깃발·띠를 **만들어 놓는** 자리다).

## 시작하기 전에 읽을 것

순서가 있다. **[HANDOFF.md](HANDOFF.md) 부터** — 지금 무엇이 돌아가고 무엇이
반쯤 되어 있고 어디에 함정이 있는지가 거기 있다. 그 다음:

| 무엇을 하려는가 | 읽을 것 |
|---|---|
| DB·스키마를 건드린다 | `docs/20260810_db-specification.md`·`db-erd.md` (지금 모습), `devlog/20260730_P02_db-schema.md` (설계 근거), `web/viewer/models.py` 머리말 |
| 층(지역·지점·시료·관찰)을 만진다 | `devlog/20260806_063_layers-and-locality.md`, `web/viewer/naming.py`, `models.py` 의 `Locality`·`Sample` 머리말 |
| 분류(속·형태)를 더한다 | `ClassDef` 머리말의 **채울 것 여덟**, `devlog/20260804_038`~`040` |
| 앞으로 할 일을 고른다 | `TODOs.md`, `devlog/20260729_P01_roadmap.md` |
| 판정 기준·문턱을 만진다 | `pipeline/judge.py` 머리말, `devlog/20260731_007_*.md` |
| 검출기를 학습시킨다 | `devlog/20260803_P04_yolo-training.md`, `023`(자료 꾸러미), `025`(첫 판 성적) |
| 이미지·검출·교정의 관계를 만진다 | `devlog/20260805_P06_*`(계획·결정), `055`(실행), `models.py` 의 `Image` |
| 데스크탑 앱을 만든다 | `devlog/20260805_P05_desktop-app.md` (계획), `docs/20260805_desktop-app-review.md` (근거), `049`(CPU 실측), `.guides/desktop/` |
| 판을 내보낸다 | **`docs/20260813_release-flow.md`** (절차 · 태그가 이미지를 만든다) |
| 배포·백업을 만진다 | `.guides/web/`, `devlog/20260803_019_*`, `20260804_034_smoke-and-sentinel.md` |
| 파이프라인 알고리즘 | `docs/20260811_pipeline-rationale.md` (스크립트마다 "왜 이렇게 했는가" · 판정 기준·실측·성능이 함께 있다) |
| 뷰어 화면이 왜 그런가 | `docs/20260811_viewer-guide.md` (지금 어떤 화면이 있는지는 `HANDOFF.md` 2절) |
| 스키마가 왜 그 모양인가 | `docs/20260811_schema-rationale.md` (지금 모습은 위 DB 명세) |

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
# venv 는 ~/venv/DiaRUGA 이다 (저장소 안의 .venv 가 아니다 — HANDOFF 8.3)
python --version        # 3.12.3
```

requirements 는 넷으로 갈라져 있다 (P03·032). 호스트 venv 는 `requirements.txt`
하나면 되고, 컨테이너가 `-web`(Django·pillow·gunicorn)과 `-pipeline`(torch·SAM2)을
나눠 쓰며, `-yolo`(ultralytics)가 `--no-deps` 로 파이프라인 위에 얹힌다.

**데이터도 DB 도 저장소 안에 없다.** 위치는 `.env` 가 알려 준다(`.env.template`
참고 — 없으면 스크립트가 사진을 못 찾는다). **교정 감사 기록 `review/` 만 git 추적
대상이라 저장소에 남아 있다** — `groups_*.json` 은 DB 이전 전의 산물이라 지웠다.

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

`ops/check_db.py` 는 **refilter/segment 뒤, `pipeline/judge.py` 를 고친 뒤, 숫자가 이상할 때**
돌린다. 여기서 잡는 것은 예외가 안 나고 그냥 틀린 상태다.
`backfill_images.py --verify` 도 같은 성격이다 — 이미지·검출·교정이 앞뒤가 맞는가.

```bash
# 교정을 git 감사 기록으로 (호스트 venv 로 돈다 — Django 를 안 쓴다)
python ops/export_review.py                 # review/<슬라이드>/g<n>.json
python ops/export_review.py --check         # 파일 ↔ DB 대조. 아무것도 안 쓴다
python ops/export_review.py --db <백업> --out /tmp/before && diff -r /tmp/before review/
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

지금 `/srv/DiaRUGA/scripts` 에 있는 것: `ops/check_db.py` · `ops/backup_db.py` ·
`ops/db_sentinel.py` · `pipeline/judge.py` · `ops/batch_runs.py` · `ops/prune_detections.py`.
없는 것을 부르면 `dbrun.sh` 가 **무엇을 옮기라고 알려 준다.**

**예외가 하나 있다 — 백업 cron 은 호스트 venv 로 돈다.** 규약이 막으려는 두 사고
(낡은 `models.py` · root 소유자)는 Django 를 거치는 코드에서 났는데,
`ops/backup_db.py` 는 Django 를 임포트하지 않고 원본을 **읽기 전용**으로 열어
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
deploy/host/sync_to_srv.sh                       # 저장소 → /srv (개발 중)
/srv/DiaRUGA/bin/sync_to_srv.sh --from-image <판>  # 이미지 → /srv (저장소가 없어도 된다)
python ops/db_sentinel.py show                      # 백업이 세운 무결성 깃발이 있는가

docker compose -f deploy/docker-compose.yml build web   # 눌러 볼 때만. 릴리스는 이걸로 안 한다
```

**판을 내보내는 것은 `docs/20260813_release-flow.md` 하나를 따른다.** 손으로
굽지 않는다 — **`v*` 태그를 밀면** CI 가 시험을 돌리고 굽고 Docker Hub 로
올리며(`main` push 는 굽기만 한다), `deploy.sh` 가 그것을 받아 갈아 끼운다.

### 저장소 소스를 그대로 사내망에 띄운다 (Django 개발 서버)

**이미지를 굽지 않고 지금 작업 트리를 눌러 볼 때** 쓴다.

> **테스트를 띄울 때 DB 는 언제나 `/data3/DiaRUGA/backup/` 의 최근 사본을
> 복사해서 쓴다.** 개발 서버(아래)도, 테스트 컨테이너(`testdeploy.sh`)도 같다 —
> 그쪽은 5단계가 **사본을 자동으로 갈아 끼우고**(`--keep-db` 로만 유지),
> 사본이 낡았으면 `backup_db.py` 를 먼저 돌리라고 멈춘다. **운영 DB 를 그대로
> 붙이지 않는다** — 눌러 보다가 `/review` 한 번이 그 시야의 교정을 갈아치운다.
> **`cp` 로 운영 DB 를 직접 뜨지도 않는다**(WAL 이라 불완전한 사본이 된다).
> 백업 사본은 이미 완결된 파일이라 그대로 복사해도 된다.

```bash
cd ~/projects/DiaRUGA
cp "$(ls -t /data3/DiaRUGA/backup/DiaRUGA_*.db | head -1)" ./DiaRUGA.db   # 사본 (gitignore)

export DIARUGA_DB=$PWD/DiaRUGA.db          # 운영 /srv/DiaRUGA/db 를 가리키지 않는다
export DIARUGA_DATA_ROOT=/data3/DiaRUGA    # 사진은 읽기만 한다
export DIARUGA_THUMB_CACHE=$PWD/web/.thumbcache   # /data3 쪽은 남의 소유라 못 쓴다
export DIARUGA_SCRIPT_NAME=                # 서브경로 없이 뿌리(/)에 붙인다
export IMAGE_TAG="v0.11.2-dev $(git rev-parse --short HEAD)"   # 좌상단에 판이 뜬다

python web/manage.py migrate viewer        # 사본을 지금 소스의 판으로 올린다
PORT=$(for p in $(seq 8051 8059); do ss -ltn | grep -q ":$p " || { echo $p; break; }; done)
setsid nohup python web/manage.py runserver 0.0.0.0:$PORT > /tmp/runserver.log 2>&1 < /dev/null &
echo "http://172.16.116.98:$PORT/"
```

- **포트는 `8051`~`8059` 중 비어 있는 것**을 쓴다(`ss -ltn` 으로 고른다).
  **`8060` 은 빼 두었다 — `refserver` 가 쓰고 있다**(2026-08-12 정정).
  **`9091` 도 쓰지 않는다 — 컨테이너 자리다**(지금 안 듣고 있어도 그렇다)
- **`0.0.0.0` 에 붙여야 사내망에서 보인다.** `127.0.0.1` 이면 이 머신에서만 열린다
- **`IMAGE_TAG` 가 없으면 판이 화면에 안 뜬다** — 자리는 원래 있다
  (`base.html` 의 `{{ image_tag }}` · `viewer/context.py`). 운영과 눈으로 갈리게
  `-dev` 와 커밋을 붙인다
- **`Test Server` 워터마크가 저절로 뜬다** — `DEBUG` 가 켜져 있으면 이름을 안 적어도
  화면 전체에 빨간 글자가 대각선으로 얹힌다(`viewer/context.py` · `.envwm`).
  **끄지 않는다** — 이 화면을 운영으로 알고 검토하면 그 교정이 아무 데도 안 남는다.
  다른 이름을 쓰고 싶으면 `DIARUGA_ENV_LABEL` 을 준다
- **`DEBUG=1` 인 서버가 사내망에 열린다.** 볼 일이 끝나면 내린다
- **`pkill -f "runserver …"` 는 자기 명령줄까지 잡아 셸을 죽인다** — 실제로 두 번
  당했다. `pkill -f "runserver 0.0.0.0:805[1]"` 처럼 **패턴을 비껴 쓴다**
- 템플릿을 고치면 **서버를 다시 띄운다**(자동 리로드가 템플릿 캐시를 안 비운다)

**포트 대역을 ufw 에서 여는 것은 `sudo` 가 필요하다** — `paleoadmin` 에서 한 번만
하면 된다. **사내망으로 좁혀서 연다**(`9091` 규칙과 같은 모양).

```bash
sudo ufw allow proto tcp from 172.16.0.0/16 to any port 8051:8059 \
     comment 'DiaRUGA dev server (임시)'
sudo ufw status numbered          # 규칙 번호를 본다
sudo ufw delete <번호>             # 다 쓰면 걷는다
```

### 파이프라인 (GPU)

일회성으로만 돌린다. 상주시키면 VRAM 을 물고 놓지 않는다 (P03).
평소에는 `deploy/poll_nas.sh` 가 1분마다 알아서 돌린다 — 손으로 부를 일은 다시
돌릴 때뿐이다.

```bash
cd /srv/DiaRUGA
# 그룹핑만 경로를 받는다 (나머지는 슬라이드 slug). 시야가 이미 있으면 스스로 거부한다
docker compose run --rm pipeline python pipeline/group_focus_series.py "/data3/DiaRUGA/photos/<촬영일>/<슬라이드>"
docker compose run --rm pipeline python pipeline/focus_stack.py --slide <slug>
docker compose run --rm pipeline python pipeline/segment_diatoms.py --slide <slug> \
    --scale 1.0 --points-per-side 48 --min-um 10 --max-um 150 --batch sam2-전수
docker compose run --rm pipeline python pipeline/segment_diatoms.py --slide <slug> \
    --backend yolo --keep-current --batch yolo-3차      # 비교용으로 쌓기만 한다
```

**인자는 `deploy/poll_nas.sh` 와 같은 것을 쓴다** — 특히 `--scale 1.0`. 빠뜨리면
절반 해상도로 검출되고 `um_per_px` 가 2배로 기록된다.

**GPU 를 쓰는 작업은 한 번에 하나만 돈다** — 잠금이 `segment_diatoms` 안에 있어
폴러가 도는 중에 손으로 돌려도 기다렸다 이어 간다.

### 확인하는 법

**자동 시험이 있다 — 고치고 나면 이것부터 돌린다** (P08 · 064).

```bash
python web/manage.py test viewer --exclude-tag browser   # 771개 · 9.7초
python web/manage.py test viewer                         # 940개 (브라우저 169개 포함, 207초)
```

호스트 venv 로 돈다 — `dbrun.sh` 를 안 거친다. 규약이 막으려는 "같은 파일을 두
벌의 환경이 만진다" 가 성립하지 않기 때문이다: 시험은 **자기 DB 를 새로 만들고
끝나면 버린다**(`ops/backup_db.py`·`ops/export_review.py` 와 같은 자리). 그 사실을 사람이
기억하는 대신 `tests/base.py` 가 확인한다 — 운영 DB 나 `/data3` 를 가리키면 멈춘다.

**커버리지를 목표로 하지 않는다.** 시험 목록은 이 절의 "자주 빠지는 함정" 이다 —
027·051·053·057·038~040·045. 시험을 더할 때도 그 기준이다: **되살려서 잡히는
것을 보고 나서 "있다" 고 말한다.** 실패할 수 없는 시험은 없는 것보다 나쁘다
(덮은 줄 알게 한다 — 실제로 한 번 그렇게 짰다가 064 에서 고쳤다).

**URL 을 덮는 것과 갈래를 덮는 것은 다르다** (086). `/crops/`·`/detections/` 를
여는 시험이 셋이나 있었는데 **세운 자료가 전부 합성본 시야라** 프레임 갈래를 한
번도 안 지났고, 그 사이 두 화면이 **v0.8.0 이후 내내 500** 이었다 — 운영에서도.
`/healthz` 도 `smoke.sh` 도 그 화면을 안 연다. 화면 시험을 더할 때는 **자료가
어느 갈래로 가는지**를 본다 (`make_world(with_stack=False)` 가 그 반대쪽이다).

**GitHub Actions 가 push 마다 돈다** — 시험이 통과한 것만 뷰어 이미지가 된다.
**파이프라인 이미지는 거기서 안 굽는다**(러너에 GPU 가 없어 구워도 확인이 안
된다). `deploy.sh` 는 사람이 부른다. 자세한 것은 P08 §5.

**브라우저가 있다** — `playwright` + 헤드리스 크로미움(045). 키 입력·클릭·
페이지 이동·**콘솔 오류**·화면 캡처가 된다. 이벤트 배선 고장은 이것으로만 잡힌다.
**반드시 사본 DB 에 붙인다** — 띄우는 법은 위 "저장소 소스를 그대로 사내망에
띄운다" 에 있다(백업 사본을 복사해 쓰는 것까지 거기 한 곳에 적었다). 브라우저만
쓸 때는 밖에 낼 일이 없으니 `127.0.0.1` 로 충분하다. 설치는 HANDOFF 3.3 —
`NODE_EXTRA_CA_CERTS` 를 빠뜨리면 사내망 TLS 때문에 죽는다.

**템플릿을 고치면 시험 서버를 다시 띄운다** — `--noreload` 는 템플릿 캐시를
안 비운다. 고쳤는데 안 바뀌면 그것부터 의심할 것 (063).

가볍게 볼 때는 **Django 테스트 클라이언트**로 URL 을 때려 본다
(`ALLOWED_HOSTS` 에 `testserver` 를 넣어야 한다).
**node 는 있다**(`/usr/bin/node` v18) — JS 는 **렌더한** 인라인 스크립트를 뽑아
`node --check` 로 파싱한다(템플릿 원본이 아니라 렌더한 것이어야 한다).

**속성에 값이 들어 있는 것과 그 값이 유효한 것은 다르다.** SVG 경로에 10 KB 가
멀쩡히 들어 있는데 화면은 백지였던 적이 있다. 템플릿을 가를 때는 `div` 짝이 아니라
**렌더 결과의 중첩**을 파싱해서 본다.

## 구조

```
pipeline/  group_focus_series.py → focus_stack.py → segment_diatoms.py → refilter.py
   초점 시리즈 묶기         all-in-focus 합성    SAM2 / YOLO 검출 + 지표   문턱만 다시 적용
                                                        ↑
                                                    judge.py  ← 판정 규칙은 여기 하나뿐
**저장소는 넷으로 갈려 있다** (100). **운영 서버에 저장소가 없을 수 있다** —
그래서 운영에 필요한 것은 `deploy/host/sync_to_srv.sh` 가 `/srv/DiaRUGA` 로 민다.

| 디렉토리 | 무엇이 | /srv 로 가나 |
|---|---|---|
| `pipeline/` | 컨테이너 안에서 도는 것 + 그들이 쓰는 모듈(`judge`·`zen_meta`·`runlog`) | **간다** |
| `ops/` | 주기적으로 돌거나 상태를 보는 것 (백업·무결성·검사·내보내기) | **간다** |
| `migrate/` | 이전기·일회성 (backfill·rebind·verify) | 안 간다 — 필요할 때 `dbsync.sh <이름>` |
| `tools/` | 개발 도구 (지도 굽기·보고서 변환·벤치) | 안 간다 |

**`/srv/DiaRUGA/scripts` 는 평평하다** — 컨테이너가 그 디렉토리 하나만 물고,
스크립트끼리의 임포트도 평평해야 돈다. 저장소에서만 디렉토리가 갈려 있어,
`ops/check_db.py` 처럼 `pipeline/judge.py` 를 쓰는 것은 `sys.path` 에 그 자리를
한 줄 알려 준다.

web/viewer/
  models.py      23개 모델. 읽기 전에 파일 첫 주석부터
  naming.py      폴더 이름 → 층. **규칙은 여기 하나뿐이다** (Django·cv2 를 안 부른다)
  images.py      Image 를 만드는 문 하나 — 파이프라인 넷과 regroup 이 지난다
  data.py        DB → 뷰가 쓰는 dict. **읽기 전용이라는 약속이 있다**
  manage_data.py 관리 화면이 쓰는 문 — 층을 만들고 옮기고 지운다 (쓰는 쪽)
  outcrop.py     노두 현장 사진. NAS 공유에 파일로만 산다 — DB 에 행이 없다
  thresholds.py  문턱 미리보기·적용
  antarctica.py  미리 구운 해안선 (korea.py 와 짝) — 투영식이 tools/ 에도 있다
```

**검출과 교정은 `Image` 에 붙는다** (P06 · 055). `Image` 는 **검출을 돌릴 수
있는 이미지 한 장**이고 `kind` 가 `stack|frame|depth` 다 — 예전에는 `Detection` 이
`target` + nullable `frame` 으로 다형 연관을 흉내 냈다. 열쇠는 `path` 이고,
교정의 유일 제약은 `(image, mask_key)` 다.

**데이터의 원본은 `DiaRUGA.db` 다** (SQLite, WAL). `out/*.json` 등은 내보내기
형식으로만 남아 있다.

**검출 엔진이 두 벌이다.** 뷰어가 보는 것은 **`RunBatch.for_review` 가 켜진
묶음**이고(P10, 관리 화면에서 고른다), 나머지는 `--keep-current` 로 나란히 쌓여
있다. **검토 화면의 `◉ SAM / ○ YOLO` 라디오**로 같은 시야를 두 엔진으로
비교한다(051, `?batch=<실행>`). 묶음 전체를 한 표로 훑던 `/engine/` 화면은
**075 에서 지웠다** — 라디오가 같은 일을 자리를 안 잃고 한다.

**검토 대상이 아닌 묶음은 읽기 전용이고, 그것을 세 겹으로 막아 뒀다**(아래).
화면이 **되는 것처럼 보이는 것**까지 막는다 — 저장만 잠그면 사람이 한 시야를
헛검토한다.

## 자주 빠지는 함정

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
- **층이 다른 것을 한 payload 에 싣지 않는다** (116). 검토 완료는 **시야에
  붙는 표시**(`(시야, 묶음)` 한 줄)인데 **판 단위 교정**(`(이미지, 묶음)`)과
  한 요청으로 갔다. 그래서 표시 하나를 켜는 일이 **그 판의 교정을 갈아치우는
  일**이 되고, "어느 판을 고르고 있나" 가 완료에까지 걸린다 — 갈래 둘이 났다.
  (1) 지나가는 판을 거르는 자리(074)가 완료까지 삼켜 **화면은 완료인데 서버는
  요청을 못 받았다**(실패 띠도 안 뜬다 — 실패한 요청이 없으니까). (2) **검출이
  없는 판**(깊이 맵 · 그 묶음에 검출이 없는 프레임)을 고르면 화면이 `image` 를
  못 실어 저장이 **대표 이미지**로 가서 그 판의 교정이 지워졌다. 걸러 놓고 다시
  통과시키는 것으로는 못 막는다 — **완료를 payload 에서 뗐다**(`{"only": "done"}`)
- **`keepalive` 는 본문 64 KiB 를 넘으면 보내 보지도 않고 거절한다** (116).
  HTTP 오류가 아니라 **약속의 거절**이라 `.catch` 로 떨어진다 — 서버는 멀쩡한데
  "닿지 못했습니다" 가 뜬다. 페이지가 사라져도 브라우저가 대신 보내 주는
  요청이라 규격이 상한을 뒀고, 교정·그린 폴리곤이 많은 시야가 그 크기다.
  **떠나기 전에 기다린다면 안 붙여도 된다** — 크기를 재서 작을 때만 붙인다
- **떠나기 전에 밀어낸 저장은 기다렸다 떠난다** (116). `leave()` 가 `flushSave()`
  의 약속을 안 기다리고 `location.href` 를 줬다. 실패하면 **떠나지 않는다**:
  떠나면 그 판단이 화면에서도 사라져 실패 띠를 볼 사람이 없다. **떠나는 자리는
  전부 그 문으로 보낸다** — 엔진 라디오가 옛 모양으로 남아 있었다. 안 떠났으면
  부르는 쪽이 **자기 화면도 되돌린다**(고른 표시만 옮겨 가 있으면 지금 보는
  것이 어느 엔진인지가 화면에서 갈린다)
- **번지기(106)는 `src` 를 "그린 판" 으로 알면 안 된다** (116). 그것은 **저장할
  때 열려 있던 판**이다. 대표(`is_rep`)를 거기 세우면 판을 옮겨 저장할 때마다
  개체의 얼굴이 따라다닌다 — 카탈로그 크롭과 학습 자료가 흐린 단일 프레임이
  된다. 대표는 **합성본**이고, 없을 때만 `src` 다. 제약은 계속 지켜지므로
  `check_db` 8번에 안 걸린다

**DB·스키마**

- **자동 생성 마이그레이션을 읽지 않고 쓰지 말 것.** 모델 이름을 바꾸면 Django 는
  **옛 표를 지우고 새 표를 빈 채로 만드는** 순서를 낸다 — `Core` → `Locality` 를
  그대로 돌렸으면 지점 다섯과 모든 관찰의 소속이 날아갔다. 순서는
  **새 표 → `RunPython` 으로 자료 이동 → 옛 칸 걷기** 여야 하고, `reverse` 도
  함께 적는다(배포가 막혀 판을 되돌릴 때 빈 화면이 나오면 안 된다) (063)
- **SQLite 는 칼럼을 지울 때 표를 통째로 다시 만든다.** 그 칼럼을 가리키는 제약이
  남아 있으면 `NewCore has no field named 'site'` 로 죽는다 — 제약을 먼저 뗀다
- **자동값이 사람이 채운 것을 덮으면 안 된다.** `update_or_create` 의 `defaults`
  에 `None` 을 실으면 **다시 반입할 때 사람이 넣은 소속이 지워진다.** 폴더에서
  못 읽은 것은 **아무것도 안 쓰는** 것이 맞다 (`group_focus_series.sample_fields`).
  `obs_label` 을 defaults 에서 뺀 것과 같은 이유인데 `core`·`depth_cm` 는 안
  그랬다가 당했다 (063)
- **`cp DiaRUGA.db` 금지.** WAL 이라 불완전한 사본이 나온다. `ops/backup_db.py` 를 쓸 것
- **판이 여럿이라는 것과 검사가 그걸 아는 것도 다르다**(103). 프레임 이름 건(053)과
  같은 실수의 다음 판이다 — `/review` 의 덧문이 "시야의 현재 검출" 중 아무거나
  하나를 집는 바람에 **시야 11개의 교정이 통째로 거절되고 있었다**
- **`Site.area`(한국/남극)와 `Site.region`(해역 이름)은 다른 칸이다.**
  **`Locality.kind`(시추코어/노두)와 `collect_kind`(채취 방식)도** 그렇다
- **소속(지점·시료)은 `Slide` 에 없다.** `slide.locality` 는 지름길 property 이고
  질의에는 `sample__locality__site` 로 조인한다
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
- **`migrate/import_json.py` 를 아무 때나 돌리지 말 것.** 파이프라인에서는 빠졌다.
  멱등이지만 `Candidate` 를 지우고 다시 만들어서, DB 에서만 한 교정이 있는데
  옛 JSON 을 넣으면 JSON 쪽으로 되돌아간다. **지금 JSON 은 DB 보다 한참 낡았다**
- **`migrate/verify_db.py` 는 임포트하면 `ImportError` 다.** 본문이 전부 최상위에 있어
  임포트만으로 실행됐고, DB 가 없으면 빈 `DiaRUGA.db` 를 만들었다. 막아 뒀다
- **`pipeline/refilter.py` 에서 주지 않은 문턱은 현재 값을 그대로 쓴다.** 전부 기본값으로
  되돌리는 것이 아니다 — 하나 바꾸려다 나머지가 조용히 초기화되는 것을 막는 설계다
- **분류를 더할 때 "테이블에 행 하나" 로 끝나지 않는다.** `label`·`short`·`badge`·
  `color`·`hotkey`·`counted`·`is_taxon`·`sort_order` 여덟에 **`base.html` 의 CSS**
  까지다(`ClassDef` 머리말에 목록이 있다). 하나라도 비면 **예외는 안 나고 그
  분류만 조용히 다르게 굴러간다** — 마스크가 투명해 "지정은 되는데 화면에 안
  보이는" 상태가 될 뻔했다. `ops/check_db.py` 가 단축키·색만 잡아 준다 (038·040)
- **분류를 되돌릴 때는 지우지 말고 `active=False` 로 끈다.** 행을 지우면 그
  분류로 붙인 교정이 이름 없는 분류가 되어 화면에서 안 읽힌다

**화면이 아무 일도 안 하고 "됐다" 고 말하는 것**

- **저장이 성공으로 보이는데 아무것도 안 바뀌는 갈래를 남기지 말 것.** 속성
  편집이 지역 코드가 비면 지점을 찾는 갈래를 통째로 건너뛰면서 "저장했습니다"
  를 냈다 — 사람이 같은 일을 몇 번이고 다시 한다. 못 한 것은 **오류로 말한다** (063)
- **남의 행에 붙기만 할 때 폼의 빈 칸을 저장에 쓰지 말 것.** 그 칸들은 소속이
  없던 시점에 그려져 전부 비어 있다 — 그대로 쓰면 이미 채워 둔 좌표·해역이
  지워지고 **그 행을 쓰는 관찰 전부가 함께 당한다** (063)
- **지우기 문턱은 눌러 보기 전에 보여야 한다.** "지울 수 없습니다" 만 내면 무엇을
  먼저 치워야 하는지 알 수 없다 — 무엇이 몇 개 걸려 있는지 버튼에 적는다.
  그리고 **서버가 다시 검사한다**: 화면에서 막는 것은 막는 것이 아니다 (063)
- **소속을 잃은 행은 화면에서 그냥 사라진다.** 500 도 404 도 아니다 — 목록을
  세어 보기 전에는 알 수가 없다. `/manage/` 와 `ops/check_db.py` 7번이 그것을 센다 (063)

**성능 — 같은 실수를 세 번 했다**

- **개체 하나 재려고 이미지 전체를 훑지 말 것.** 개체는 이미지의 0.3% 다.
  **`bbox` 는 부르는 쪽에서 받는다** — 안 받고 `np.nonzero` 로 찾으면 아끼려던
  비용을 그대로 쓴다 (두 번 다 그렇게 만들었다가 되돌렸다)
- **개수를 세려고 자료를 물질화하지 말 것.** 목록 화면이 그렇게 1.3초였다
- **같은 값을 되묻지 말 것**(105). 카탈로그가 카드마다 검토 대상 묶음을 물어 질의가
  390~560번 났다 — 한 번만 묻고 내려보낸다(크롭·계측 표도 같이 빨라졌다)
- **유일 제약을 옮기면 그것을 짚어 쓰던 질의도 함께 옮긴다**(058). 코드는 한 글자도
  안 바뀌었는데 딛고 서 있던 인덱스가 없어져 첫 페이지가 0.5 → 2.0초가 됐다
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
- **운영 DB 를 호스트에서 직접 열지 않는다 — `mode=ro` 도 안 된다** (132).
  읽기 전용으로 여는 것이라 안전하다고 믿었는데, `db/` 가 `drwxrwsr-x` 라
  **열기가 성공해 버리고 그 순간 `-wal`·`-shm` 이 연 사람 소유(644)로 생긴다.**
  컨테이너는 `1000:1000` 이라 그때부터 **DB 전체가 읽기 전용**이 되고,
  `/healthz` 는 읽기만 해서 계속 `ok` 다 — 5시간 46분 뒤 배포가 마이그레이션을
  쓰려다 죽고서야 드러났다(운영 3분 다운). **물리 상태는
  `/data3/DiaRUGA/backup/` 의 사본을 열어 본다.** `testdeploy.sh` 는 같은
  함정을 알고 사본에 `chmod g+w` 를 하는데, **운영 쪽에는 그 방어가 없다**
- **`DiaRUGA.db` 는 파일이 아니라 디렉토리째로 마운트한다.** 파일 하나만 물리면
  WAL 이 만드는 `-wal`·`-shm` 형제가 컨테이너 안쪽에 생겨 호스트와 WAL 을 공유하지
  못한다. 같은 DB 를 보는 줄 알았는데 아닌 상태가 된다 (P03)
- **컨테이너는 `1000:1000` 으로, `TZ=Asia/Seoul` 로 돌린다.** root 로 돌면
  `DiaRUGA.db` 소유자가 바뀌고, 시간대를 빠뜨리면 UTC 로 돌아 **사본 이름이 아홉
  시간 어긋나 정리 규칙이 가장 새 사본을 지운다** (036)
- **사본을 손으로 지울 때, 파일 목록을 이름순으로 정렬해 놓고 앞에서부터
  자르지 말 것** (2026-08-13). "이름순으로 정렬하면 시간순이 된다" 가
  **접두사가 한 가지일 때만 성립한다.** `DiaRUGA_` 와 `diatom_`(048 이전
  이름)이 섞인 디렉토리를 `ls | sort` 로 정렬하면 대문자가 앞이라 **최근
  것들이 목록 앞쪽에 모이고**, 뒤에서 N개만 남기는 `head -n -N`(파이썬으로는
  `sorted(...)[:-keep]`)이 **남기려던 바로 그것을 지운다.** `pre_deploy/` 의
  최근 30개(`v0.6.3`~`v0.12.2`)를 그렇게 지웠다 — 036 과 같은 줄인데 그때는
  시간대였고 이번엔 대소문자였다. **시각으로 정렬한다**(`ls -1t`).
  `ops/backup_db.py`·`sync_backup_nas.py` 는 안 물린다 — 앞엣것은 glob 이
  접두사를 못 박아 한 가지 이름만 걸리고, 뒤엣것은 **이름에서 시각을 못 읽는
  파일을 남긴다**
- **그 대신 굴리지 않는 사본이 조용히 쌓인다.** `backup_db.py` 의 정리 glob 은
  `DiaRUGA_` 로 못 박혀 **다른 접두사를 아예 못 본다** — 안 지우는 쪽이라
  안전하지만 `--keep` 수에도 안 들어간다. `pre_deploy/` 에 08-04 의 `diatom_*`
  10개(1 GB)가 9일째 남아 있었고 경고는 없었다. **이름을 또 바꾸면 같은 침묵이
  돌아온다** — `backup/`·`manual/`·`pre_deploy/` 를 가끔 눈으로 볼 것
- **뷰어와 파이프라인의 판은 따로다**(`IMAGE_TAG` / `PIPELINE_TAG`). 하나로 묶으면
  뷰어 판을 올리는 순간 폴러가 없는 이미지를 가리킨다 — **4시간 반 멈췄다** (026)
- **그런데 스키마를 조이는 마이그레이션은 둘을 함께 올려야 한다.** 갈라 놓은
  것이 이번엔 반대로 문다 — 칼럼을 걷었는데 옛 파이프라인 이미지가 그 칼럼에
  INSERT 하면 폴러가 멈춘다. **조인 사본에 파이프라인 컨테이너를 붙여 먼저 돌려
  볼 것** (055 에서 그렇게 잡았다)
- **함께 올려야 하는 축이 하나 더 있다 — 슬러그·경로 같은 "값의 모양" 규칙이다**
  (057). 그 규칙은 **파이프라인이 만들고 뷰어가 쓴다.** 코드만 고치고 이미지를
  안 올리면 옛 규칙이 계속 값을 만들고, 규칙을 어긴 값이 DB 에 앉으면 **그 값을
  읽는 화면이 전부 죽는다** — 괄호가 든 슬러그 하나로 목록이 `NoReverseMatch` 를
  내 뷰어 전체가 500 이었다. **들어오는 값이 404 가 되는 것과 나가는 값을 못
  만드는 것은 고장의 크기가 다르다.** `/healthz`·`smoke.sh` 는 링크를 안 만들어
  이것을 통과시킨다
- **폴러를 `flock` 으로 잡아 뒀다가 풀 때는 `sleep` 의 pid 를 죽인다.** 감싼 셸만
  죽이면 `sleep` 이 살아남아 fd 를 쥐고 있다 — 락이 안 풀리고, 로그가 안 늘어나는
  것을 보고 크론을 의심하게 된다 (057)
- **폴러를 세울 때 crontab 을 고치지 않는다.** `poll_nas.sh` 가 `flock -n` 으로
  겹침을 막으므로 `flock /tmp/DiaRUGA-poll.lock <명령>` 이면 그 사이 실행이
  조용히 물러난다. 남의 설정을 고쳤다가 되돌리기를 잊는 쪽이 위험하다
- **`dbrun.sh` 로 돌릴 스크립트는 `ops/check_db.py` 의 머리를 베껴 온다.**
  컨테이너 안에서는 코드가 `/app` 이라 `DIARUGA_APP` 을 봐야 한다 — 자기 옆의
  `web/` 을 보게 짜면 `No module named 'diarugaweb'` 로 죽는다
- **사내망이 `download.pytorch.org` 의 TLS 를 가로챈다.** 파이프라인 이미지 빌드가
  거기서 죽으면 `deploy/ca/` 를 볼 것. `pip` 은 시스템 CA 저장소를 보지 않아
  `PIP_CERT` 를 함께 줘야 한다

**템플릿**

- **`<script>` 를 넣을 때 어느 블록 안인지 본다.** "마지막 `{% endblock %}` 앞"
  이라고 생각한 자리가 `{% block title %}` 의 끝이었다 — `<title>` 안이라 JS 가
  한 번도 안 돌았고, 끌어다 놓기가 예외도 경고도 없이 죽어 있었다 (063)
- **개발 서버가 템플릿을 캐시한다.** `--noreload` 로 띄워 두면 템플릿을 고쳐도
  안 바뀐다 — 두 번 헛다리를 짚었다. **템플릿을 고치면 서버를 다시 띄운다** (063)
- **폼에 같은 `name` 이 둘이면 Django 는 뒤엣것을 집는다.** 숨은 칸이 층 이름을
  `kind` 로 나르는데 유형 셀렉트도 `kind` 라 지점이 "모르는 층" 이 되어 조용히 안
  만들어졌다 — 겹치는 이름을 쓰지 말 것 (063)
- **브라우저 기본 `[hidden] { display: none }` 은 특이도 (0,0,1) 이다.** 요소에
  클래스 규칙(`.tile { display: block }`)이 걸려 있으면 진다 — 감추라고 해 놓고
  그대로 보인다. `.tools` 에 이어 두 번째다 (063)
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
- **테마가 둘인 화면에 색을 박지 말 것**(107). `#fff4f2` 가 어두운 쪽에서 흰
  덩어리가 된다 — 이미 갈려 있는 토큰(`--warn-bg`·`--warn-fg`)을 빌린다
- **조사는 앞 글자를 따라간다**(107). `title + '이 엇갈립니다'` 로 만들면
  "분류이 엇갈립니다" 가 나온다 — **문구를 통째로** 든다

**GPU·의존성**

- **`except` 블록 안에서 `empty_cache()` 는 아무것도 못 비운다.** 재시도는 `except`
  **밖으로** 뺀다
- **`retina_masks=False` 는 값을 바꾼다** — 모든 개체의 경계가 달라진다
- **8 GB 카드에 안 들어가는 프레임이 1,318장 중 1장 있다** (`Run.status='partial'`)
- **`ultralytics` 는 `--no-deps` 로 넣는다.** 의존은 `requirements-yolo.txt` 에
  손으로 적었다 — 올릴 때 함께 봐야 한다

**측정·비교**

- **두 경로를 비교할 때는 입력이 같은지 먼저 확인한다** (계측값이 이상하면 계측 자체를)
- **숫자를 비교할 때는 양쪽이 같은 층인지 본다**
- **DB 의 시각을 그냥 찍으면 UTC 다** (`USE_TZ=True`). `git log` 는 KST 라 나란히
  놓고 읽다가 **아홉 시간이 어긋나 결론이 반대로 나왔다** — 함정은 DB 를 직접
  조회하는 진단 스크립트 쪽에만 있다(화면은 템플릿이 알아서 바꾼다)
- **배율은 슬라이드마다 다를 수 있다.** 한 슬라이드 **안에서** 갈라지는 것이 사고다

## 사람의 교정은 재생성 불가다

`DiaRUGA.db` 안의 교정(삭제·되살림·분류·코멘트 **6,700여 건**)은 사람이 347 시야를
검토해 만든 것이고, **다시 만들 수 없다.** `stacked/`·`out/` 은 다시 돌리면 나오고
`photos/` 는 촬영 원본이다.

`ops/export_review.py`(P02 5단계 · P06)가 **`review/<슬라이드>/g<n>.json` 으로
내보낸다** — git 에 남는 감사 기록이자, `--check` 로 DB 와 대조하는 도구다.
Django 를 임포트하지 않고 sqlite3 로 **읽기 전용**으로 열어 `ops/backup_db.py` 와 같은
자리에 있다(그래서 호스트에서 돌고 백업 파일도 `--db` 로 그대로 읽는다).

```bash
python ops/export_review.py                 # 저장소 review/ 로
python ops/export_review.py --check         # 파일 ↔ DB 대조 (안 쓴다)
python ops/export_review.py --db <백업> --out /tmp/before && diff -r /tmp/before review/
```

**그래도 `ops/backup_db.py` 는 계속 첫 안전망이다** — 내보내기는 교정만 담는다.
**큰 작업 전에는 반드시 사본을 뜬다.**

## 커밋

**코드 작업은 하루치 브랜치에서 한다** — `work/<YYYYMMDD>-<계정>` (2026-08-12 부터).
**코드에 손대기 직전에** 만들고(`git switch -c work/20260812-jikhanjung`),
그 뒤로 **커밋·push·확인을 전부 그 브랜치 기준으로** 한다. **브랜치를 파는 것과
그 위에서 확인하는 것은 다르다** — 체크아웃을 안 하면 `git status`·`git log` 는
계속 `main` 을 본다. **`main` 병합은 사람이 정한다.**

**문서·기록만 고치는 커밋은 `main` 에 바로 올린다**(HANDOFF·TODOs·담당 표시 같은
것). 브랜치는 **부딪힐 수 있는 것**을 격리하려고 있는 것이라, 한 줄짜리 메모까지
브랜치·병합을 태우면 무거워지기만 한다. 애매하면 **묻는다** — 임의로 파지 않는다.

**계정마다 작업 트리가 따로다**(`jikhanjung`·`paleoadmin`·`sclee`). 남의 트리에서
접어 둔 것(stash·미커밋)은 여기 `git stash list` 에 **안 보이고 저장소에도 안
남는다** — 안 보인다고 유실된 것이 아니다. **미커밋 상태를 인수 근거로 삼지 말 것.**

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

## 새 작업자 붙이기

계정 하나가 곧 작업 트리 하나다(위 참조). 새 사람이 붙을 때 정할 것은 셋이고
**서로 다른 층이다 — 하나가 되면 나머지도 된다고 믿지 말 것.**

| | 무엇 | 누가 검증하나 |
|---|---|---|
| **identity** (`user.name`·`user.email`) | 커밋에 글자로 박히는 서명 | **아무도 안 한다** — 아무 문자열이나 들어간다 |
| **인증** (SSH 키) | push 할 수 있는가 | GitHub |
| **연결** (attribution) | 커밋이 그 사람 프로필에 붙는가 | GitHub — **이메일이 일치할 때만** |

**같은 이메일을 쓰면 이름을 달리해도 GitHub 에서는 한 사람이다.** 실제로
`Jikhan Jung` 과 `Jikhan Jung (paleo-server)` 가 그렇게 섞여 있다.

웹에서 한 번: 그 사람의 GitHub 계정에 **이메일을 인증**하고, 저장소
`Settings → Collaborators` 로 초대한다. **Deploy key 는 사람이 아니라 저장소에
붙는 키라** 이 자리에 안 맞는다.

그 계정의 셸에서:

```bash
git config --global user.name  "<이름>"
git config --global user.email "<그 GitHub 계정에 인증된 주소>"   # 연결의 열쇠
git config --list --show-origin | grep -E '^.*user\.'          # 어느 파일의 값인가

ssh-keygen -t ed25519 -C "<계정>@paleo-server"                  # 공개키를 GitHub 에 등록
ssh -T git@github.com                                          # "Hi <아이디>!" 가 나와야 한다

git clone git@github.com:jikhanjung/DiaRUGA.git
git switch -c work/<YYYYMMDD>-<계정>
```

**첫 커밋을 밀고 나서 `git log -1 --format='%an <%ae>'` 와 GitHub 화면을 함께
본다** — 아바타가 안 붙으면 이메일이 그 계정에 인증되지 않은 것이다(인증하면
**과거 커밋도 소급해서 붙는다**). 이미 다른 이메일로 올라간 커밋은 **그대로
둔다** — 고치려면 히스토리를 다시 써야 한다.

환경은 이 문서의 "환경" 절대로 따로 세운다 — **`.env` 도 데이터도 DB 도 저장소
안에 없다**(`.env.template` 이 견본). `.guides` 심볼릭 링크도 각자 건다.
