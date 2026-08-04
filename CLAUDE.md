# CLAUDE.md

남극 시추코어 규조류(diatom) 현미경 사진 분석 파이프라인 + 검토·교정 뷰어.
문서는 한국어로 쓴다 — 커밋 메시지, devlog, 주석 모두.

## 시작하기 전에 읽을 것

순서가 있다. **[HANDOFF.md](HANDOFF.md) 부터** — 지금 무엇이 돌아가고 무엇이
반쯤 되어 있고 어디를 밟으면 안 되는지가 거기 있다. 그 다음:

| 무엇을 하려는가 | 읽을 것 |
|---|---|
| DB·스키마를 건드린다 | `devlog/20260730_P02_db-schema.md` (설계 근거), `web/viewer/models.py` 머리말 |
| 앞으로 할 일을 고른다 | `TODOs.md`, `devlog/20260729_P01_roadmap.md` |
| 판정 기준·문턱을 만진다 | `judge.py` 머리말, `devlog/20260731_007_*.md` |
| 파이프라인 알고리즘 | `README.md` (40 KB, 스크립트마다 "왜 이렇게 했는가"가 있다) |

**devlog 는 그때의 판단과 근거를 남기는 곳이다.** 계획은 `YYYYMMDD_PNN_주제.md`,
실제로 한 작업은 `YYYYMMDD_NNN_주제.md` 로 번호를 올려 가며 단계마다 끊어 적는다.
무엇을 했는지보다 **왜 그렇게 했고 무엇을 버렸는지**를 쓴다.

배포·데이터 안전 규약은 `.guides/web/README.md` (형제 프로젝트들이 같은 사고를
겪고 도달한 표준). **없으면 devdocs 클론이 안 걸린 것이다** — `../devdocs` 를
형제로 두고 `ln -s ../devdocs/guides .guides`. 이 저장소에는 커밋하지 않는다
(devdocs 는 private, 여기는 public).

## 환경

```bash
# venv 는 ~/venv/diatom 이다 (README 의 .venv 가 아니다 — HANDOFF 8.3)
python --version        # 3.12.3
```

requirements 는 셋으로 갈라져 있다 (P03). 호스트 venv 는 `requirements.txt` 하나면
되고, 컨테이너가 `-web`(Django·pillow·gunicorn)과 `-pipeline`(torch·SAM2)을 나눠 쓴다.

**데이터도 DB 도 저장소 안에 없다.** 위치는 `.env` 가 알려 준다(`.env.template`
참고 — 없으면 스크립트가 사진을 못 찾는다). `review/`·`groups_*.json` 은 git 추적
대상이라 저장소에 남아 있다.

```
/srv/diatom/   diatom.db  docker-compose.yml  .env      ← 배포
/data3/diatom/ photos/<촬영일>/<슬라이드>/               ← NAS 구조와 1:1
               stacked/  out/  backup/  hf/  .thumbcache/
```

컨테이너 안팎의 경로가 같다 — 명령을 그대로 옮겨 쓸 수 있다.

## 자주 쓰는 명령

```bash
# 뷰어 — 배포는 /srv/diatom 에서. 바깥 :9090 은 nginx 가 127.0.0.1:8090 으로 넘긴다
cd /srv/diatom && docker compose up -d web
cd /srv/diatom && docker compose logs -f web

# 파이프라인은 일회성으로만. 상주시키면 VRAM 을 물고 놓지 않는다 (P03)
cd /srv/diatom && docker compose run --rm pipeline <명령>

# 이미지 굽기는 저장소에서 (저장소는 굽고, /srv/diatom 은 돌린다)
docker compose -f deploy/docker-compose.yml build web

# DB 가 앞뒤가 맞는지 — 1초. refilter/segment 뒤, judge.py 를 고친 뒤, 숫자가 이상할 때
python check_db.py
python check_db.py --slide rs23 -v

# 큰 작업 전에는 반드시. 시간별 cron 이 따로 돌지만 그건 24시간 rolling 이고,
# 이건 backup/manual/ 에 따로 남아 로테이션이 안 건드린다. 일 끝나면 지우면 된다
python backup_db.py --note before-refilter

# 배포한 것이 실제로 사는지 — 판·행 수·안전망까지 본다 (200 은 "떴다" 일 뿐이다)
/srv/diatom/bin/smoke.sh
python db_sentinel.py show          # 백업이 세운 무결성 깃발이 있는가

# 문턱만 바꿔 다시 거른다 (SAM2 재실행 없음, 밀리초)
python refilter.py --dry-run
python refilter.py --round-texture-min 2000

# 파이프라인 (GPU 필요)
python group_focus_series.py "/data3/diatom/photos/260729/RS23-GC03 71cm" -o groups_RS23.json
./run_batch.sh                      # 합성 + 검출 일괄
python import_json.py               # JSON 산출물을 DB 로 (6단계 끝나면 사라진다)
```

브라우저·node 가 없는 머신이다. **뷰어를 확인할 때는 Django 테스트 클라이언트**로
URL 을 때려 보는 것이 가장 확실하다(`ALLOWED_HOSTS` 에 `testserver` 를 넣어야 한다).
JS 는 렌더한 인라인 스크립트를 뽑아 구문·미선언 참조 검사로 확인해 왔다.

## 구조

```
group_focus_series.py  →  focus_stack.py  →  segment_diatoms.py  →  refilter.py
   초점 시리즈 묶기         all-in-focus 합성      SAM2 검출 + 지표        문턱만 다시 적용
                                                        ↑
                                                    judge.py  ← 판정 규칙은 여기 하나뿐
web/viewer/
  models.py      14개 모델. 읽기 전에 파일 첫 주석부터
  data.py        DB → 뷰가 쓰는 dict
  thresholds.py  문턱 미리보기·적용
```

**데이터의 원본은 `diatom.db` 다** (SQLite, WAL). `out/*.json` 등은 내보내기
형식으로만 남아 있다. 다만 파이프라인 스크립트 일부가 아직 JSON 을 쓴다 —
P02 6단계가 진행 중이다(`refilter.py` 끝, `focus_stack.py` 다음).

## 밟기 쉬운 곳

여기 있는 것은 **전부 실제로 한 번씩 당한 것들이다.**

- **교정은 `Candidate` 가 아니라 `mask_key` 에 붙는다.** FK 로 매면 재검출에서
  사람의 판단이 조인 실패로 사라진다. 모든 교정 행이 `geom` 에 기하를 스스로
  들고 있어 검출기가 바뀌어도 읽힌다 — 지운 것도 학습의 음성 표본이다
- **검출은 덮어쓰지 않고 쌓는다.** `Detection.is_current` 가 뷰어가 볼 것을 가리킨다
- **캐시된 dict 를 고치지 말 것.** `detection_for()` 가 후보를 복사한 뒤 교정을
  얹는 이유다 — 원본을 고치면 교정을 되돌려도 옛 상태가 따라붙는다
- **`cp diatom.db` 금지.** WAL 이라 불완전한 사본이 나온다. `backup_db.py` 를 쓸 것
- **`/healthz` 의 `degraded` 는 503 이 아니라 200 이다.** 503 으로 바꾸면
  `deploy.sh` 의 기동 게이트가 200 을 기다리다 **배포가 스스로 멈춘다** —
  "백업이 깨졌다" 는 신호가 배포를 못 끝내게 만드는 꼴이다. 배포를 세우는 판단은
  `smoke.sh` 가 `status != ok` 로 한다 (034)
- **백업 사본은 검증을 통과한 뒤에 제 이름을 받는다.** 뜨는 중에는 `.part` 다.
  반쯤 쓴 파일이 `diatom_*.db` 라는 이름을 달면 정리 glob 에 걸려 **가장 새
  파일로 살아남고 멀쩡한 사본을 밀어낸다** (034)
- **`import_json.py` 를 아무 때나 돌리지 말 것.** 멱등이지만 `Candidate` 를 지우고
  다시 만든다. DB 에서만 한 교정이 있는데 옛 JSON 을 넣으면 JSON 쪽으로 되돌아간다
- **`verify_db.py` 는 임포트하면 `ImportError` 다.** 본문이 전부 최상위에 있어
  임포트만으로 실행됐고, DB 가 없으면 빈 `diatom.db` 를 만들었다. 막아 뒀다
- **Django 의 `{# #}` 는 한 줄짜리 주석이다.** 여러 줄이면 화면에 그대로 나온다.
  `{% comment %}` 를 쓸 것
- **`refilter.py` 에서 주지 않은 문턱은 현재 값을 그대로 쓴다.** 전부 기본값으로
  되돌리는 것이 아니다 — 하나 바꾸려다 나머지가 조용히 초기화되는 것을 막는 설계다
- **`diatom.db` 는 파일이 아니라 디렉토리째로 마운트한다.** 파일 하나만 물리면
  WAL 이 만드는 `-wal`·`-shm` 형제가 컨테이너 안쪽에 생겨 호스트와 WAL 을 공유하지
  못한다. 같은 DB 를 보는 줄 알았는데 아닌 상태가 된다 (P03)
- **컨테이너는 `1000:1000` 으로 돌린다.** root 로 돌면 `diatom.db` 소유자가 바뀌어
  호스트의 `backup_db.py`·`check_db.py` 가 못 쓰게 된다
- **사내망이 `download.pytorch.org` 의 TLS 를 가로챈다.** 파이프라인 이미지 빌드가
  거기서 죽으면 `deploy/ca/` 를 볼 것. `pip` 은 시스템 CA 저장소를 보지 않아
  `PIP_CERT` 를 함께 줘야 한다

## 사람의 교정은 재생성 불가다

`diatom.db` 안의 교정(삭제·되살림·분류·코멘트·검토완료 2,400여 건)은 사람이
124 시야를 전수 검토해 만든 것이고, **다시 만들 수 없다.** `stacked/`·`out/` 은
다시 돌리면 나오고 `260729/` 는 촬영 원본이다.

`export_review.py`(P02 5단계)가 아직 없어서 교정이 DB 에만 있다. 그동안은
`backup_db.py` 가 유일한 안전망이다. **큰 작업 전에는 반드시 사본을 뜬다.**

## 커밋

메시지는 한국어 평서문으로, **무엇을 했는지**를 쓴다. 최근 예:

```
DB 무결성 검사를 만든다 (check_db.py)
문턱 이력에 바뀐 것만 보여준다
refilter.py 를 DB 로 옮기고, 판정 규칙을 judge.py 로 떼어낸다
```

`diatom.db`·`260729/`·`out/`·`stacked/`·`backup/` 은 gitignore 다.
