# 뷰어를 컨테이너로 옮기고 데이터를 큰 디스크로 뺀다

**작성일** 2026-07-31
**계획** `20260731_P03_containerize-nas-ingest.md` 의 0·1·2단계

---

## 무엇을 했나

서버를 바꾸면서 뷰어가 안 떴다. `ALLOWED_HOSTS` 에 옛 장비의 주소와 이름이
박혀 있었기 때문인데, 고치고 보니 같은 뿌리에서 나온 것이 더 있었다 —
`run_batch.sh` 가 없는 venv(`.venv`)를 부르고, `requirements.txt` 에 뷰어가 쓰는
Django 가 빠져 있었다. 환경이 장비 한 대에 손으로 맞춰져 있었다.

그래서 P03 을 세우고 그 앞 세 단계를 했다. **기능은 하나도 바꾸지 않았다.**

---

## requirements 를 셋으로 가른다

뷰어가 실제로 무엇을 쓰는지 세어 보고 갈랐다. 결과가 뜻밖이었다 —
**뷰어는 torch·numpy·opencv 를 하나도 쓰지 않는다.** `web/` 전체가 Django 와
PIL 뿐이고, 판정 규칙 `judge.py` 는 **import 가 한 줄도 없다**(P02 6단계에서
torch 없이 돌게 떼어낸 것이 여기서 값을 했다).

| 파일 | 내용 | 이미지 크기 |
|---|---|---|
| `requirements-web.txt` | Django, pillow, gunicorn | 174 MB |
| `requirements-pipeline.txt` | web + torch, SAM2, opencv | ~6 GB |
| `requirements.txt` | pipeline + python-docx (호스트 venv 입구) | — |

이 경계 덕분에 뷰어 한 줄 고칠 때 6 GB 를 다시 굽지 않는다.
빠져 있던 Django 를 넣었고, `.venv` 라고 적혀 있던 설치 안내도 실제 경로로 고쳤다.

## 데이터를 `/data3/diatom` 으로 뺀다

`/` 가 74% 차 있었고 슬라이드가 계속 들어온다. `/data3` 는 7.3 T 에 6.3 T 여유이고
ext4 이며 이미 `/data3/epma` 가 같은 용도로 쓰이고 있다.

뷰어는 모든 경로를 단일 `DATA_ROOT` 기준 상대경로로 다루고 `IMAGE_DIRS` 를
화이트리스트로 쓴다. **이 구조를 그대로 두고 뿌리만 환경변수로 뺐다** —
경로 해석 코드는 한 줄도 건드리지 않았다.

```
DATA_ROOT = Path(os.environ.get("DIATOM_DATA_ROOT", PROJECT_ROOT))
```

지우기 전에 저장소·`/data3`·NAS 세 곳이 **690 파일 1,040,300,038 바이트**로
일치하는 것을 확인했다.

### 평탄하게 폈다가 되돌렸다

처음에 `260729/RS23-GC03 71cm` 를 `photos/RS23-GC03 71cm` 로, 촬영일 층을 없애고
옮겼다. 그런데 NAS 가 `DiatomPhotos/<촬영일>/<슬라이드>/` 두 단계 구조이고
`260731/RS23-GC03 369cm` 가 새로 올라온 것을 보고 되돌렸다.

**평탄하게 펴면 같은 슬라이드를 다시 촬영했을 때 이름이 부딪힌다.** 초점을 다시
잡거나 시야를 더 찍는 일은 충분히 있다. NAS 구조를 그대로 비추면 그 문제가 없고,
스캔·인제스트도 상대경로 하나를 키로 쓰면 되어 단순해진다.

마이그레이션 `0004` 를 되돌리고(`migrate viewer 0003`) 내용을 고쳐 다시 적용했다.
데이터 마이그레이션에 `backward` 를 제대로 써 둔 것이 값을 했다.

```
photos/260729/RS23-GC03 71cm/Snap-21365.jpg    ← NAS 와 1:1
```

경로를 담는 칼럼은 여섯인데 셋(`Slide.image_dir`·`Frame.path`·`Detection.image_path`)만
바뀌었다. `Stack.*_path` 는 `stacked/` 로 시작해 손댈 것이 없었다.

### `review/` 는 따라가지 않는다

`review/*.json`(124개)은 git 이 추적하는 감사 기록이다. 사진·산출물은 용량 때문에
나갔지만 이것은 저장소에 남아야 한다. 그런데 `verify_db.py`·`import_json.py` 가
`DATA_ROOT / review` 로 읽고 있어서 뿌리를 옮기면 조용히 못 찾게 된다.

`REVIEW_ROOT` 를 따로 두어 `PROJECT_ROOT` 를 가리키게 했다. `groups_*.json`(3개)도
git 추적 대상이라 같은 이유로 저장소에 남겼다.

### `.env` 를 읽는 열 줄

사진이 저장소 밖으로 나가면서, 호스트에서 `check_db.py` 를 그냥 돌리면 데이터
위치를 모르게 됐다. 라이브러리를 들이지 않고 `settings.py` 에 최소한의 `.env`
리더를 두었다(`KEY=VALUE` 와 주석만, `setdefault` 라 이미 있는 값은 덮지 않는다).
컨테이너는 compose 가 환경변수를 직접 주므로 이 파일 없이 돈다.

## 컨테이너

`../phyloserver/deploy/` 를 본떴다. 다만 **`collectstatic` 은 넣지 않았다** —
이 뷰어는 정적 파일이 하나도 없다(`{% static %}` 을 한 번도 쓰지 않고 CSS·JS 를
템플릿에 인라인으로 들고 있다). 선례를 그대로 베끼면 실패를 `|| true` 로 삼키는
줄이 하나 늘 뿐이었다.

- `Dockerfile.base` → `Dockerfile.pipeline` 2층
- `docker-compose.yml` — `pipeline` 은 `profiles: [manual]` 로 묶어 `up` 에 딸려
  뜨지 않게. 일회성으로만 돌린다
- `user: "1000:1000"` — root 로 돌면 `diatom.db` 소유자가 바뀌어 호스트의
  `backup_db.py`·`check_db.py` 가 못 쓰게 된다
- `.dockerignore` — 없으면 `260729/`(994 MB)와 `backup/`(3.3 GB)이 빌드 컨텍스트로
  올라간다. `.env` 도 뺐다(이미지에 호스트 경로와 앞으로는 비밀키까지 박힌다)

`diatom.db` 는 **디렉토리째로** 물린다. 파일 하나만 물리면 WAL 이 만드는
`-wal`·`-shm` 형제가 컨테이너 안쪽에 생겨 호스트와 WAL 을 공유하지 못한다.
조용히 어긋나므로 더 위험하다.

썸네일 캐시는 이미지 안(`/app/web/.thumbcache`)이라 uid 1000 으로 못 쓴다.
`DIATOM_THUMB_CACHE` 로 빼서 `/data` 쪽에 두었다 — 이미지를 다시 구워도 살아남는다.

## 막힌 것 — 사내망이 TLS 를 가로챈다

파이프라인 빌드가 `download.pytorch.org` 에서 죽었다.

```
CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain
```

KOPRI 망이 TLS 를 가로채 자체 CA(`O=KOPRI, CN=KOPRI SSL`)로 다시 서명한다.
호스트에는 `/usr/local/share/ca-certificates/` 에 깔려 있지만 이미지에는 없었다.

컨테이너에서 하나씩 때려 보니 **가로채는 대상은 `download.pytorch.org` 뿐**이고
PyPI·GitHub·huggingface.co 는 통과한다. 그래도 대상이 늘 수 있으므로 CA 를
이미지에 넣었다(`deploy/ca/`).

**`pip` 은 시스템 CA 저장소를 보지 않고 `certifi` 묶음을 쓴다.** CA 를 깔기만
해서는 여전히 막힌다 — `PIP_CERT` 를 함께 줘야 했다. 런타임에 huggingface 에서
SAM2 가중치를 받을 때를 위해 `SSL_CERT_FILE`·`REQUESTS_CA_BUNDLE` 도 같이 두었다.

망 밖에서 쓸 경우 `deploy/ca/` 를 비우면 그냥 넘어간다. 이 CA 를 신뢰한다는 것이
무슨 뜻인지는 `deploy/ca/README.md` 에 적었다.

## 확인

컨테이너 뷰어(9091)와 호스트 뷰어(9090)를 같은 DB 로 나란히 띄우고 대조했다.

| URL | 결과 |
|---|---|
| `/api/d/rs23.json` | 동일 (56,815 bytes) |
| `/d/rs23/` | 동일 (118,188 bytes) |
| `/d/rs23/g/0/` | 동일 (168,205 bytes) |
| `/d/rs23/detections/` | 동일 (95,558 bytes) |
| `/img?p=…&w=400` | 동일 (10,721 bytes) |

바이트 단위로 같다. 데이터 이전 뒤에도 `check_db.py` 전 항목 통과,
`verify_db.py` 의 JSON↔DB 대조 수치가 전부 일치한다.

---

## 남은 것

- **P02 6단계** — 스크립트 셋을 DB 로. 자동 수집의 전제다(P03 참고)
- 파이프라인 스크립트가 아직 호스트 venv 기준이다 (`run_batch.sh` 의 `PY=.venv/bin/python`)
- `260731/RS23-GC03 369cm`(412장)가 NAS 에 올라와 있다. 인제스트 시험 대상

---

## 덧 — 배포 위치와 nginx

이 머신에는 `/srv/<앱>/` 규약이 있다(phyloserver·scoda-engine·paleolab). **저장소는
굽고 `/srv/diatom` 은 돌린다**로 갈랐다.

```
/srv/diatom/  docker-compose.yml  .env  diatom.db
```

배포 compose 는 `build:` 가 없다 — 구워진 이미지를 참조만 한다. `diatom.db` 도
저장소에서 여기로 옮겼다(계획에서는 미뤘던 것인데, 배포 디렉토리가 생기니 여기가
제자리다).

**컨테이너 안팎의 경로를 같게 두었다.** `/data` 로 줄여 마운트하려다 바꿨다 —
파이프라인 스크립트가 파일 경로를 인자로 받으므로(`group_focus_series.py "<경로>"`),
경로가 같아야 명령을 호스트와 컨테이너 사이에 그대로 옮겨 쓸 수 있다.

nginx 는 **포트를 나눴다.** 80 은 phyloserver 블록이 `server_name 172.16.116.98` 로
이미 잡고 있고, 서브경로로 얹으려면 템플릿의 `fetch()` 5곳이 절대경로라 손봐야 한다.
바깥 `:9090` → `127.0.0.1:8090` 으로 넘기고 **컨테이너는 루프백에만 붙인다**.
쓰던 URL 이 그대로 유지된다.

`nginx` 가 사진을 직접 서빙하지는 않는다 — `/img` 는 즉석 축소, `/crop` 은 bbox
잘라내기라 정적 파일이 아니다. 재 보니 썸네일 캐시 적중 1.1~1.4 ms, 시야 화면 전체
29 ms 로 병목도 아니다.

### 백업이 컨테이너와 부딪히지 않는지 확인했다

뷰어 요청 30개를 처리하는 중에 호스트에서 `backup_db.py` 를 돌렸다 —
`integrity=ok`, 교정 2,408건 그대로, 사본은 파일 하나(`journal_mode=delete`).

**디렉토리째 마운트한 것이 여기서 값을 했다.** 호스트와 컨테이너가 같은 inode 를
보고 `-wal`·`-shm` 을 공유하므로 같은 커널의 POSIX 잠금이 그대로 작동한다.
파일 하나만 마운트했다면 두 프로세스가 서로 다른 WAL 을 보게 됐을 것이다.

호스트에서 도는 게 오히려 낫다 — `backup_db.py` 는 Django 를 임포트하지 않는
마지막 안전망이라 컨테이너가 안 뜨는 상황에서도 돌아야 한다. 다만 DB 가 옮겨다닐 수
있게 됐으므로 `DIATOM_DB`·`DIATOM_BACKUP_DIR` 을 읽도록 고쳤다(settings.py 의 `.env`
리더와 일부러 중복해 두었다 — 이 스크립트는 혼자 돌아야 한다).
