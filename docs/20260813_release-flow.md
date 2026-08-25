# 뷰어 판을 내보내는 절차

`v0.12.2`(116)를 내보내며 정리했다. **여기 적힌 순서가 표준이다** — 그 앞의
판들은 사람이 손으로 굽고 손으로 밀어 올렸는데(114 7절), 시크릿이 들어오면서
그 자리가 CI 로 넘어갔다.

- **왜 그렇게 하는지**는 `.guides/web/deployment.md`(형제 프로젝트와 공유하는
  규약)와 devlog `019`·`034`·`087`·`114`
- **무엇이 지금 도는지**는 [HANDOFF.md](../HANDOFF.md) 와 `/healthz`
- **어느 판에 무엇이 나갔는지**는 [CHANGELOG.md](../CHANGELOG.md)

## 먼저 — 이미지는 태그가 만든다

`.github/workflows/test.yml` 이 그렇게 되어 있다.

| 무엇이 일어났나 | 시험 | 이미지 굽기 | Docker Hub 로 밀기 |
|---|---|---|---|
| PR (`pull_request`) | 돈다 | 돈다 | **안 한다** |
| `main` 에 push | 돈다 | 돈다 (`:ci`) | **안 한다** |
| **`v*` 태그 push** | 돈다 | 돈다 | **한다** (`koprifossillab/diaruga:<태그>`) |

**굽기는 늘 검증하되 올리는 것은 태그일 때만이다.** 그러니 **손으로 굽지
않는다** — `deploy/docker-compose.yml` 은 남아 있지만 그것은 개발용이고,
릴리스는 태그를 미는 것으로 시작한다. `deploy.sh` 는 레지스트리에 올라간 것을
받아 갈아 끼우기만 한다(그 머리말에도 적혀 있다).

## 1. 병합까지 (114)

하루치 브랜치 → PR → CI 통과 → **로컬 `--ff-only`** 병합 → `main` push.
병합 커밋을 안 만든다.

```bash
git fetch origin
git merge --ff-only origin/work/<날짜>-<계정>
git push origin main
```

## 2. 판 번호를 정한다

**사람이 정한다.** semver 를 엄격히 따른다 — 고침·성능은 PATCH, 칸이나 화면이
늘면 MINOR. `v0.1.9` 다음은 `v0.1.10` 이다.

**뷰어와 파이프라인은 판이 따로다**(`IMAGE_TAG` / `PIPELINE_TAG`). 하나로
묶었다가 폴러가 4시간 반 멈춘 적이 있다(026). 다만 **스키마를 조이는
마이그레이션**과 **슬러그·경로 같은 "값의 모양" 규칙**은 둘을 함께 올려야
한다(055·057).

## 3. 문서를 먼저 맞춘다 — 태그가 그 커밋을 가리킨다

태그를 붙이고 나서 문서를 고치면 **판이 가리키는 나무에 그 문서가 없다.**

- `CHANGELOG.md` — 새 항목 (판·날짜·마이그레이션 번호·무엇이 바뀌었나)
- `HANDOFF.md` — 머리의 "도는 판", 2절 표의 뷰어 판·다음 판
- `CLAUDE.md` — 시험 수가 바뀌었으면 그 줄
- 배포 뒤에 돌릴 일회성 스크립트가 있으면 **HANDOFF 3.8** 에

## 4. 시험을 다 돌린다

```bash
python web/manage.py test viewer          # 브라우저 포함. 3분
```

`main` 에 push 하고 **GitHub Actions 가 통과하는 것까지 본다.** 로컬만 보고
태그를 밀면, 실패한 CI 를 태그 CI 에서 다시 만난다.

```bash
gh run watch <run-id> --exit-status
```

## 5. 태그를 붙여 민다

**주석 태그**(`-a`)로 만든다 — 가벼운 태그는 메시지가 없어 `git tag -n` 이
비어 보인다. 본문은 CHANGELOG 항목을 줄여 적는다.

```bash
git tag -a v0.12.2 -F -   # 또는 -m
git push origin v0.12.2
```

CI 가 시험을 다시 돌리고, 굽고, 민다 (약 4분). **레지스트리에 섰는지 확인한다** —
`deploy.sh` 는 없는 태그를 받으려다 멈추지만, 여기서 보는 편이 빠르다.

```bash
gh run watch <run-id> --exit-status
docker manifest inspect koprifossillab/diaruga:v0.12.2 >/dev/null && echo 있다
```

## 6. 사본을 뜬다

시간별 cron 이 따로 돌지만 그건 24시간 rolling 이다. 이건 `manual/` 에 남아
로테이션이 안 건드린다.

```bash
deploy/host/dbrun.sh backup_db.py --note before-<devlog 번호>
```

## 7. 배포한다

```bash
/srv/DiaRUGA/bin/deploy.sh v0.12.2
```

순서가 곧 안전장치다 — 받기 → `.env` 의 `IMAGE_TAG` 만 갈기 → 유지보수 플래그 →
내리기 → **배포 전 스냅샷** → 올리고 health 게이트 → 플래그 해제 → smoke.
받다 실패하면 지금 도는 것을 안 건드리고 끝난다.

**`/healthz` 의 `degraded` 는 503 이 아니라 200 이다** — 503 으로 바꾸면 기동
게이트가 200 을 기다리다 배포가 스스로 멈춘다. 배포를 세우는 판단은 `smoke.sh`
가 `status != ok` 로 한다(034).

## 8. smoke 가 안 여는 화면을 손으로 연다

`smoke.sh` 가 여는 것은 `/healthz` 와 시야 목록 하나뿐이다. **200 은 "떴다" 일
뿐이고, 링크를 만드는 화면은 그 검사를 통과한다**(057). `/crops/` 와
`/detections/` 가 **v0.8.0 이후 내내 500** 이었던 것이 이 구멍으로 나왔다(086).

일곱을 연다 — `/crops/` · `/detections/` · `/catalog/` · `/g/1/` ·
`/thresholds/` · `/system-settings/` · 목록.

## 9. 뒤처리 스크립트 (있으면)

**순서는 사본 → 배포 → 스크립트다.** 옛 이미지가 도는 동안 자료를 되돌리면
다음 저장이 도로 옮겨 놓는다.

```bash
deploy/host/dbsync.sh <이름>.py    # migrate/ 는 /srv 에 없다 (100)
deploy/host/dbrun.sh  <이름>.py    # 먼저 눈으로 본다
deploy/host/dbrun.sh  <이름>.py --apply
```

## 10. 자료가 성한지 본다

```bash
deploy/host/dbrun.sh check_db.py
```

**있던 경고와 새 경고를 가른다** — 배포 전 사본을 같은 질의로 세어 비교한다.
안 그러면 원래 있던 1건을 방금 만든 것으로 읽는다.

## 11. 테스트 인스턴스도 올린다

```bash
deploy/host/testdeploy.sh v0.12.2
```

운영과 같은 갈래인데 셋이 다르다 — **DB 사본을 갈아 끼우고**(`--keep-db` 로만
유지), 유지보수 안내가 없고, 먼저 안전 검사를 한다. **사본이 낡는 것이 테스트의
기본 고장이다**: 옛 자료로 새 판을 보면 "고쳤는데 안 바뀐다" 가 나오고 그 시간은
판을 의심하는 데 쓰인다.

뒤처리 스크립트(9번)를 돌렸다면 그 사본이 **그 전 것일 수 있다.** 그 변화를
테스트에서 봐야 하면 `--fresh-db` 로 다시 뜬다.

## 12. 문서를 닫는다

- `HANDOFF.md` — "배포를 기다리는 판이 없다" 로, 도는 판을 새 판으로
- `CHANGELOG.md` — 항목에서 "배포 대기" 를 뗀다
- 3.8 에 적어 둔 일회성 스크립트는 **돌렸다고 적는다**(안 적으면 다음 사람이
  또 돌린다)

## 한눈에

```bash
# 1~4  병합 · 판 번호 · 문서 · 시험
python web/manage.py test viewer
git push origin main && gh run watch <id> --exit-status

# 5    태그 → CI 가 굽고 민다
git tag -a v0.12.2 -F - && git push origin v0.12.2
gh run watch <id> --exit-status
docker manifest inspect koprifossillab/diaruga:v0.12.2 >/dev/null && echo 있다

# 6~8  사본 · 배포 · 눈으로
deploy/host/dbrun.sh backup_db.py --note before-116
/srv/DiaRUGA/bin/deploy.sh v0.12.2

# 9~11 뒤처리 · 검사 · 테스트 자리
deploy/host/dbsync.sh refix_drawn_reps.py
deploy/host/dbrun.sh  refix_drawn_reps.py            # 먼저 눈으로
deploy/host/dbrun.sh  refix_drawn_reps.py --apply
deploy/host/dbrun.sh  check_db.py
deploy/host/testdeploy.sh v0.12.2
```
