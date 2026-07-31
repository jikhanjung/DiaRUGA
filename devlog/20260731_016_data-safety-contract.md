# 형제 프로젝트의 배포 규약과 대조하고, 그 자리에서 한 건 걸렸다

**작성일** 2026-07-31
**대조 대상** `.guides/web/data-safety.md` · `deployment.md`

---

## `.guides` 가 무엇인가

`../devdocs/guides` 로 가는 심볼릭 링크다. 형제 프로젝트들이 **같은 사고를 각각
겪고 같은 결론에 도달한 것**을 이식 가능하게 일반화해 둔 문서 모음이다.

devdocs 는 private 이고 이 저장소는 public 이라 **커밋하지 않는다.** 대신
`.gitignore` 에 넣고 `CLAUDE.md` 에 한 줄 적어 뒀다 — *"없으면 devdocs 클론이 안
걸린 것"*. 끊어진 심볼릭 링크는 조용히 빈 디렉토리처럼 보여서 원인을 한참 찾게 된다.

컨테이너로 옮긴 직후(008) 이 규약과 내 구성을 하나씩 맞춰 봤다.

## MUST 위반이 하나 나왔다

`data-safety.md` §8:

> Mount a dedicated DB *directory*, not the single file and **not the whole `/srv`** —
> a whole-`/srv` mount exposes backups/scripts/secrets to the container (blast radius).

`/srv/diatom` 을 통째로 물리고 있었다. 확인해 보니 컨테이너에서 `SECRET_KEY` 가 든
`.env` 가 **실제로 읽혔다.**

```
이전:  컨테이너가 /srv/diatom 에서  diatom.db  docker-compose.yml  .env  를 본다
이후:  db/ 하나만.  cat .env → No such file or directory
```

옮기는 순서도 같은 절이 정한 대로 했다 — `down → mkdir → DB 먼저 이동 → .env →
deploy`. **빈 디렉토리를 먼저 마운트하면 컨테이너가 빈 DB 를 만들고 경로 존재
검사는 통과한다.** 그래서 `rows > 0` 스모크로 확인했다(objectreview 2408).

## 이미 맞고 있던 것

| 조항 | 상태 |
|---|---|
| §2 스냅샷 검증 후 채택, **실패 시 prune 금지** | `backup_db.py` 가 `integrity_check` 뒤 실패면 prune 전에 `return 1` |
| §5 스냅샷을 `journal_mode=DELETE` 로 | 이미 그렇게 하고 `-wal`·`-shm` 부산물도 지운다 |
| §8 파일이 아니라 디렉토리 마운트 | 처음부터 그랬다 |
| §7 세션 토큰 제거 | **비해당** — 인증·세션 앱이 없어 `django_session` 표 자체가 없다 |

§2 는 우연히 맞은 게 아니라 006 에서 같은 판단을 했던 것이다. 세 프로젝트가
독립적으로 같은 결론에 이르렀다는 뜻이고, 가이드가 말하는 *"unwritten convergence
doesn't propagate"* 의 반대 사례다 — 이번엔 글로 있어서 전파됐다.

## 이 장비에서는 성립하지 않는 MUST

**개발서버이자 운영서버이자 백업서버다.** 그래서 두 조항은 구조상 못 지킨다.

- *"빌드는 prod 밖에서, prod 는 pull·swap 만"* — 호스트가 하나뿐이다
- *"오프사이트 호스트가 prod 에서 pull"* — 백업서버가 곧 prod 다

두 번째가 실질적인 위험이었다. `backup_db.py` 의 사본이 전부 `/data3` 안이라
디스크 한 장이 죽으면 교정 2,400여 건이 같이 간다. NAS 가 물리적으로 별개 장비라
거기로 미는 것으로 절충했다 — devlog 009.

**못 지키는 것을 못 지킨다고 적어 두는 것**이 규약을 반쯤 지키고 다 지킨 척하는
것보다 낫다.

## 남은 격차

- **표준 deploy 동사 5개**(preflight/deploy/seed/smoke/rollback) 가 없다
- 무결성 실패를 health 엔드포인트로 잇는 sentinel 이 없다(§2). `/healthz` 는
  백업 상태를 보지 않는다
- 복구 리허설(§11)은 했다 — devlog 009
