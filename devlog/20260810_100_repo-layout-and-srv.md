# 100 — 저장소를 넷으로 가르고, 운영을 `/srv` 하나로 세운다

2026-08-10 · 사용자 요청 ("repo 루트에 파이썬 스크립트가 너무 많네" →
"운영에 쓰는 스크립트는 /srv 에서" → **"운영 서버에 repo 가 없을 수도 있다"**)

## 두 가지 일이었다

**하나는 정리다** — 루트에 `.py` 가 35개였다. 넷으로 갈랐다:

| 디렉토리 | 무엇이 | 개수 |
|---|---|---|
| `pipeline/` | 컨테이너 안에서 도는 것 + 그들이 쓰는 모듈(`judge`·`zen_meta`·`runlog`) | 11 |
| `ops/` | 주기적으로 돌거나 상태를 보는 것 | 10 |
| `migrate/` | 이전기·일회성 | 9 |
| `tools/` | 개발 도구 (이미 있던 자리) | +5 |

**다른 하나가 진짜다** — 마지막 한마디가 설계를 바꿨다. 저장소가 없는 서버에서
운영이 돌아야 한다면, **`/srv/DiaRUGA` 하나로 완결돼야 한다.**

## 저장소를 붙잡고 있던 자리 셋

```
cron  * * * * *  /home/paleoadmin/projects/DiaRUGA/deploy/poll_nas.sh
cron  20 * * * * …/projects/DiaRUGA/backup_db.py
cron  40 4 * * * …/projects/DiaRUGA/sync_backup_nas.py
```

그리고 폴러 안에서 `REPO=` 로 저장소를 되짚어 `db_sentinel.py` 를 불렀다.
전부 끊었다 — 이제 cron 은 `/srv/DiaRUGA/bin/` 과 `/srv/DiaRUGA/scripts/` 만 본다.

## 파이프라인 스크립트도 `/srv` 것이 돈다

예전에는 이미지 안의 `/app/*.py` 가 돌았다. `dbtool` 이 쓰던 문을 파이프라인에도
열었다 — `scripts/` 를 읽기 전용으로 물리고 `DIARUGA_APP=/app` 로 Django 코드만
이미지 것을 쓴다.

**이득이 크다**: 스크립트 한 줄을 고칠 때마다 **7.2 GB 를 다시 굽지 않아도 된다.**
이미지를 다시 굽는 것은 **의존성이 바뀔 때**뿐이고, 그때는 판이 올라간다.

`sync_to_srv.sh` 가 `pipeline/`·`ops/` 를 `scripts/` 로, `poll_nas.sh` 를
`bin/` 으로 민다. `migrate/`·`tools/` 는 **안 옮긴다** — 운영이 스스로 부를 일이
없고, 필요하면 그때 `dbsync.sh <이름>` 으로 하나만 옮긴다.

> **`/srv/DiaRUGA/scripts` 는 평평하다.** 컨테이너가 그 디렉토리 하나만 물고,
> 스크립트끼리의 임포트도 평평해야 선다. 그래서 `dbsync.sh` 는 이름 하나로
> 저장소의 `ops/`·`pipeline/`·`migrate/`·`tools/` 를 뒤져 찾는다.

## 확인해 둔 것 — 컨테이너 밖에서 Django 를 쓰는 것은 하나도 없다

사용자가 물어서 전부 셌다: cron 둘(`backup_db`·`sync_backup_nas`), 폴러의
`db_sentinel`, 정찰 JSON 세기, smoke 의 응답 파싱, 개발용 `export_review`.
**여섯 다 Django 를 안 쓴다.** 우연이 아니라 이미 서 있던 설계다 — "DB 를
만지는 것은 문 하나로만" 이 그것이고, `backup_db.py`·`export_review.py` 가
일부러 sqlite3 만 쓰는 이유도 같다.

그래서 **저장소 없는 운영 서버가 성립한다**: 호스트에는 파이썬 + sqlite3 만
있으면 되고 Django·torch 는 전부 이미지 안에 산다.

## 밟은 자리 넷 (전부 시험이 잡았다)

1. **`ops/check_db.py` → `pipeline/judge.py`** — 판정 규칙이 하나뿐이라 공유한다.
   같은 모양이 셋 더(`export_yolo`→`runlog`, `import_json`·`backfill_scale_source`
   →`zen_meta`). `sys.path` 에 한 줄씩 알려 줬다
2. **뷰어도 둘을 쓴다** — `web/viewer/views.py`·`thresholds.py` 가 `judge` 를,
   `views.py` 가 `db_sentinel` 을 임포트한다. **이미지 안에서도 같은 경로**라
   구운 이미지로 확인했다(`/app/pipeline/judge.py`·`/app/ops/db_sentinel.py`)
3. **시험 부트스트랩** — `tests/__init__.py` 가 뿌리만 넣고 있었다. 넷을 넣는다
4. **스크립트의 `DIARUGA_APP` 기본값** — 한 단계 깊어져 `parent.parent` 가 됐다.
   20개를 함께 고쳤다

## 덧 — 근원이 둘이면 안 된다: `--from-image` (사용자 지적)

"/srv 쪽의 스크립트들은 repo 에서부터 복사해?" 라는 물음이 전제의 구멍을
짚었다. **운영이 도는 데는 저장소가 필요 없지만, 운영을 갱신하는 데는
필요했다** — `sync_to_srv.sh` 가 저장소에서 `cp` 하기 때문이다.

답은 이미 이미지 안에 있었다. `COPY . .` 라 **뷰어 이미지가 스크립트를 그대로
담고 있고**(21개), `/srv` 것과 바이트가 같다(md5 확인). 그래서 갈래를 하나 더 뒀다:

| | 언제 | 근원 |
|---|---|---|
| (기본) | 개발 중 — 스크립트만 고쳐 밀어 넣는다 | 저장소 |
| `--from-image <판>` | 운영 · 저장소가 없는 서버 | **이미지** |

**이미지 갈래가 판을 정의상 맞춘다** — 스크립트와 Django 코드가 같은 이미지에서
나오므로 어긋날 수가 없다. 그래서 **`deploy.sh` 가 배포 뒤에 이것을 부른다**(8단계).
오늘 `check_db.py` 를 손으로 `dbsync` 한 일이, 080 에서 옛 `check_db.py` 가 없는
고장을 외친 일이 이것으로 없어진다.

**막지는 않는다** — 스크립트 갱신 실패가 "방금 올린 판이 잘못됐다" 는 뜻은
아니다. smoke 의 표류 검사가 경고만 하는 것과 같은 이유다.

`sync_to_srv.sh` 는 **자기 자신도 옮긴다** — 저장소 없는 서버에서는
`/srv/bin/sync_to_srv.sh` 가 유일한 사본이고, `deploy.sh` 가 그것을 부른다.

확인: 시험 자리(`DIARUGA_SRV=…`)로 이미지에서 뽑아 스크립트 20개 + `bin/` 넷 +
compose + 안내 페이지가 서는 것, 뽑은 것이 저장소 것과 같은 것, 그리고 **저장소가
없는 자리에서 저장소 갈래를 부르면 "`--from-image` 를 쓸 것" 으로 거절**하는 것.

## 덧 2 — 스크립트는 `/srv` 것인데 모듈은 이미지 것을 물고 있었다

배포 직전에 사용자가 물었다: **"파이프라인은 여전히 손댈 거 없어?"** 있었다.

탐침으로 재 보니 이랬다:

```
스크립트 본체 : /srv/DiaRUGA/scripts/segment_diatoms.py   ← 새것
그 안의 judge : /app/judge.py                             ← 옛 이미지 것
```

전제가 `sys.path.insert(0, str(APP))` 였다. `APP=/app` 을 **맨 앞**에 넣으니
이미지 안의 `judge.py`·`zen_meta.py`·`runlog.py` 가 **자기 옆의 것을 가린다** —
파이썬이 `sys.path[0]` 에 놓아 준 스크립트 자신의 디렉토리를 밀어낸 것이다.

지금은 내용이 같아 안 드러났지만, **판정 규칙을 고쳐 `/srv` 에 밀어 넣어도 안
먹는다.** 이 구조가 세우려던 것("스크립트는 `/srv` 것이 돈다")이 반쯤 거짓이었다.

`insert` 를 `append` 로 바꿨다 — `APP` 은 **Django 코드를 찾는 자리일 뿐**이고
앞자리를 차지할 이유가 없다. 18개를 함께 고쳤다.

```
고친 뒤:  judge → /srv/DiaRUGA/scripts/judge.py · Django → 이미지 것 (12 슬라이드)
```

**이것이 이 구조의 핵심 시험이다** — 한 자리라도 `insert(0, APP)` 로 남으면 그
스크립트만 조용히 옛 규칙으로 돈다. 확인은 탐침 하나로 되고, `refilter.py
--dry-run`(판정 규칙을 실제로 쓴다)이 정상으로 도는 것까지 봤다.

## 남은 거스러미

- ~~`/srv/DiaRUGA/scripts/fix_bp09.py`~~ **지웠다** (같은 날). 063 때 북평분지의
  층을 고친 일회성 스크립트인데 **이미 죽어 있었다** — `from viewer.models import
  Core` 를 하고 `Core` 는 063 에서 `Locality` 가 됐다(`ImportError`). 하려던 일도
  다 됐다(지역 `BP` · `(1)` 이 `BP09` 에 붙음 · 소속 없는 관찰 0).

  > **일회성 스크립트가 `/srv` 에 남으면 이렇게 된다** — 아무도 안 부르는데
  > 표류 검사만 매번 운다. 그것이 `sync_to_srv` 가 `migrate/` 를 안 옮기는
  > 이유이기도 하다: 필요할 때 `dbsync.sh <이름>` 으로 하나 옮기고, 쓰고 나면
  > 지운다.
- **`smoke.sh` 의 표류 검사는 `migrate/`·`tools/` 사본까지 센다.** 운영에 필요
  없는 것들이라 `/srv` 에서 걷는 편이 깔끔한데, 지워도 되는지는 판단이 필요하다
