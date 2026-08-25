# 155 — Docker Hub 네임스페이스를 koprifossillab 로 옮긴다

2026-08-25 · sclee

`git` 원격은 이미 `koprifossillab/DiaRUGA` 로 옮겨져 있었는데(45d33e9) **이미지
이름은 `honestjung` 그대로였다.** 계정을 바꾸고 PAT 를 교체한 뒤라 옛 이름으로는
더 올릴 수 없다 — 확인부터 하고 옮겼다.

## 1. 권한은 태그를 안 올리고 확인한다

"push 가 되는가" 를 알아보려고 실제로 태그를 올리면 **되든 안 되든 흔적이
남는다.** 레지스트리는 그 전에 두 군데서 답을 준다.

**하나 — 토큰이 무슨 권한을 받아 오는가.** `auth.docker.io` 에 scope 를 달라고
하면 **실제로 부여된 것만** JWT 의 `access` 에 담겨 온다. 달라는 대로 주지 않는다.

```
repository:koprifossillab/diaruga:pull,push   → pull,push
repository:honestjung/diaruga:pull,push       → pull        ← push 가 깎여서 온다
```

**둘 — 쓰기 세션이 열리는가.** blob 업로드를 열기만 하고 매니페스트를 안 올리면
**태그가 안 생긴다.** 권한이 없으면 이 자리에서 막힌다.

```
POST /v2/koprifossillab/diaruga/blobs/uploads/   → 202
POST /v2/honestjung/diaruga/blobs/uploads/       → 401
```

`docker login` 이 성공했다는 것은 **자격이 통한다**는 말일 뿐 그 저장소에 쓸 수
있다는 말이 아니다. 옛 이름 쪽이 `pull` 은 되고 `push` 만 401 인 것이 그 차이다.

## 2. 로컬 retag 이 넷 빠져 있었다

`honestjung/diaruga` 33개 중 `koprifossillab` 쪽에 29개만 있었다. 빠진 것은
`v0.17.0`·`v0.17.1`·`v0.17.2`·**`v0.18.0`** — **지금 운영에 도는 판이 그 안에
있었다.** 이름을 옮기는 작업이 어제 돌았고 오늘 판이 넷 더 나온 것이다.

**"옮겼다" 는 시점의 목록이라 오늘 것을 모른다.** 세어서 확인한다:

```bash
docker images --format '{{.Repository}}:{{.Tag}}' \
 | awk -F: '/^honestjung\/diaruga:/{h[$2]} /^koprifossillab\/diaruga:/{k[$2]}
            END{for(t in h) if(!(t in k)) print "빠졌다:", t}'
```

파이프라인 3개는 다 되어 있었다.

## 3. 첫 push 가 저장소를 만들고, 그때 공개 여부가 정해진다

`koprifossillab` 네임스페이스에는 `phyloserver`(private) 하나뿐이었다 —
`diaruga` 는 **없는 저장소였다.** 그런데도 push scope 는 나온다(제 네임스페이스라
그렇다). 저장소는 **매니페스트가 올라가는 순간 생긴다.**

여기가 배포에 걸린다. `deploy.sh` 는 **로그인 없이 `docker pull` 을 한다** —
`honestjung/diaruga` 가 public 이라 그동안 성립하던 것이다. 새 저장소가 private
으로 생기면 운영 호스트에서 그 pull 이 멈춘다. 게다가 개인 무료 계정은 private
한 개가 한도이고 **`phyloserver` 가 이미 그 자리를 쓰고 있다.**

`v0.18.0` 을 올리고 **public 으로 생긴 것과 익명으로 받아지는 것을 따로 봤다**:

```bash
curl -s 'https://auth.docker.io/token?service=registry.docker.io\
&scope=repository:koprifossillab/diaruga:pull'      # 자격 없이 — pull 이 나온다
```

같은 이미지라 레이어는 `Mounted from honestjung/diaruga` 로 넘어갔다(같은
레지스트리 안이라 다시 안 올린다).

## 4. 함정 — 파이프라인 이미지는 Hub 에 그 판이 없다

`/srv/DiaRUGA/.env` 의 `PIPELINE_TAG=v0.5.2` 인데 **Hub 의
`honestjung/diaruga-pipeline` 은 `v0.5.1` 까지다.** CI 가 파이프라인을 안 굽고
(러너에 GPU 가 없다) 이 머신에서 손으로 구웠기 때문이다. **이 호스트의 로컬
이미지에만 기대고 있다** — 이름 옮기기와 무관하게 원래 그랬다.

026 은 "뷰어 판에 끌려가 없는 파이프라인 태그를 가리켰다" 였는데, 이쪽은
**가리키는 태그가 레지스트리에 아예 없는데도 로컬에 있어서 돈다.** 로컬을 잃는
날에 드러난다. 옮기는 김에 `koprifossillab/diaruga-pipeline:v0.5.2` 를 올려 두는
편이 낫다 (7.58 GB — 아직 안 했다).

## 5. 고친 자리

이름을 박아 둔 곳이 **코드 일곱 파일 · 문서 넷**이었다.

| 파일 | 곳 |
|---|---|
| `.github/workflows/test.yml` | 1 (태그 push 때 올라갈 이름) |
| `deploy/srv/docker-compose.yml` | 3 (web · pipeline · dbtool) |
| `deploy/docker-compose.yml` | 2 |
| `deploy/test/docker-compose.yml` | 1 |
| `deploy/host/deploy.sh` · `testdeploy.sh` · `sync_to_srv.sh` | 1 · 3 · 1 |
| `CLAUDE.md` · `TODOs.md` | 각 1 |
| `docs/20260813_release-flow.md` · `20260805_operations-docker-and-backup.md` | 3 · 2 |

**GitHub secrets `DOCKERHUB_USERNAME`·`DOCKERHUB_TOKEN` 도 함께 간다.** 08-10
이후 안 바뀐 채였다 — **코드의 태그 문자열과 secrets 는 둘 다 고쳐야 한 판이
난다.** 하나만 고치면 CI 가 굽고 나서 push 에서 401 로 멈춘다(굽기 레이어는
초록이라 로그를 끝까지 봐야 보인다). 사람이 웹에서 넣었다.

**안 고친 자리** — `devlog/`·`docs/` 의 진척 보고서·`HANDOFF.md` 1111줄. 그때
`honestjung/diaruga:v0.12.0` 이 레지스트리에 선 것은 사실이고, 기록은 그때
이름으로 둔다.

**아직 안 한 것** — `/srv/DiaRUGA` 의 넷(`docker-compose.yml`·`bin/deploy.sh`·
`bin/sync_to_srv.sh`·`test/docker-compose.yml`)은 운영 자리라 손대지 않았다.
파일만 고치는 것이라 도는 컨테이너는 안 건드리지만, **다음 `up -d` 부터 새
이름을 본다.** 두 이미지 다 이 호스트에 새 이름으로 있으므로 그때 멈추지 않는다.

## 6. 다음 태그를 밀 때 볼 것

굽기 레이어가 초록인 것으로 끝내지 않는다 — **레지스트리에 섰는지를 따로 본다.**

```bash
docker manifest inspect koprifossillab/diaruga:<판> >/dev/null && echo 있다
```
