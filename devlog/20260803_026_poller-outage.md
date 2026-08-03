# 뷰어 판을 올렸더니 폴러가 멈췄다 — 그리고 로그가 엉뚱한 말을 했다

**날짜** 2026-08-03
**앞선 문서** `20260731_P03_containerize-nas-ingest.md` (5단계 주기 실행)

NAS 자동 수집이 **4시간 반 동안 멈춰 있었다.** 원인은 내가 뷰어 판을 올린 것이고,
그것을 4시간 반 동안 몰랐던 이유는 따로 있다.

---

## 1. 무슨 일이 있었나

```
11:47   뷰어를 v0.1.1 로 올림
        → 폴러가 honestjung/diatom-pipeline:v0.1.1 을 찾기 시작
        → 그런 이미지는 없다 (파이프라인은 v0.1.0 뿐)
16:10   발견. 524번 실패해 있었다
```

`/srv/diatom/docker-compose.yml` 이 **두 이미지에 같은 `IMAGE_TAG` 를 쓰고 있었다.**

```yaml
web:       image: honestjung/diatom:${IMAGE_TAG}
pipeline:  image: honestjung/diatom-pipeline:${IMAGE_TAG}     # ← 같은 값
```

처음 컨테이너로 옮길 때는 둘을 함께 v0.1.0 으로 굽고 시작해서 맞았다. 그런데
**두 이미지의 수명이 전혀 다르다.**

| | 크기 | 언제 다시 굽나 |
|---|---|---|
| `diatom` (뷰어) | 174 MB | 화면을 고칠 때마다 — 오늘만 6번 |
| `diatom-pipeline` | 6.92 GB | 파이프라인 알고리즘이 바뀔 때 — 07-31 이후 없음 |

그러니 뷰어 판을 올리는 것이 **자동으로 파이프라인을 없는 판으로 가리키게 만든다.**
v0.1.0 다음의 첫 뷰어 판에서 바로 깨졌다.

## 2. 더 나쁜 것 — 로그가 원인을 짐작했다

```
[2026-08-03 11:47:04] 정찰 실패 — NAS 가 내려갔는가
     Image honestjung/diatom-pipeline:v0.1.1 Error manifest ... not found
```

`scan_nas.py` 가 0 이 아닌 값을 내면 무조건 **"NAS 가 내려갔는가"** 라고 적었다.
NAS 는 멀쩡했다. 이미지가 없었을 뿐이다.

**엉뚱한 진단이 진짜 원인을 가린다.** 로그를 열어 본 사람이 있었더라도 첫 줄만
보고 NAS 를 확인하러 갔을 것이고, NAS 는 정상이니 더 헷갈렸을 것이다. 아래
들여쓴 원문에 답이 있었는데 요약 줄이 그것을 덮었다.

**짐작해서 쓰지 않는다.** 원인을 가릴 수 있는 만큼만 가르고, 못 가르면 그냥
"정찰 실패" 로 둔다.

```bash
if grep -qi "manifest unknown|not found: manifest|pull access denied" "$SCAN_OUT"; then
    say "정찰 실패 — 파이프라인 이미지를 못 찾는다 (.env 의 PIPELINE_TAG 를 볼 것)"
elif grep -qi "no such file|Stale file handle|Input/output error|/nfs" "$SCAN_OUT"; then
    say "정찰 실패 — NAS 를 못 읽는다"
else
    say "정찰 실패"
fi
```

## 3. 고친 것

**판을 갈랐다.** `PIPELINE_TAG` 를 따로 둔다.

```yaml
web:       image: honestjung/diatom:${IMAGE_TAG:?...}
pipeline:  image: honestjung/diatom-pipeline:${PIPELINE_TAG:?...}
```

`.env` 에는 **제자리로 한 줄만 더했다** — 통째로 다시 만들면 `DIATOM_SECRET_KEY`
가 날아간다(`.guides/web/deployment.md` §5, 형제 프로젝트가 그렇게 크롤러 자격증명을
잃고 3.5개월을 몰랐다).

`deploy/srv/env.template` 에도 키를 넣었다. `sync_to_srv.sh` 가 견본과 `.env` 의
키를 대조해 **없는 키를 알려 주므로**, 앞으로 같은 종류의 누락은 배포 때 잡힌다.

## 4. 확인

```
파이프라인 기동   torch 2.13.0+cu126 · cuda True
폴러 수동 실행    종료코드 0
정찰 결과        16:10:24 · 슬라이드 7 · 전부 known
고친 뒤 실패     0건
```

## 5. 남는 것 — 이게 진짜 문제다

**아무도 몰랐다는 것이 고장 자체보다 크다.** 524번 실패하는 동안 화면은 멀쩡했고
(뷰어는 따로 도니까) 로그를 보는 사람이 없었다.

P03 5단계가 폴러를 만들 때 **실패 알림을 안 만들었다.** 지금 상태로는:

- 폴러가 죽어도 뷰어는 정상으로 보인다
- 로그는 사람이 열어야 보인다
- `Run(status="failed")` 은 남지만 **컨테이너가 안 뜨면 그 행조차 안 생긴다**
  — 이번이 정확히 그 경우다

최소한 이 셋 중 하나는 있어야 한다.

1. **뷰어에 "마지막 정찰 시각" 을 띄운다.** 한 시간 넘게 조용하면 눈에 띄게.
   화면을 보는 사람이 있으니 가장 싸다
2. 폴러가 연속 N 회 실패하면 알린다 (메일·웹훅)
3. `check_db.py` 에 "마지막 ingest 가 언제인가" 를 더한다

**1번이 이 프로젝트에 맞는다.** 뷰어는 늘 열려 있고 정적 파일도 알림 설비도
필요 없다. 다음 작업으로 둔다.

부수적으로: **판 올리기가 두 이미지에 걸치는 일이 또 있는지** 봐야 한다. 지금은
`deploy.sh` 가 `IMAGE_TAG` 한 줄만 고치므로 파이프라인은 건드리지 않는다 —
파이프라인을 새로 구우면 `PIPELINE_TAG` 를 사람이 올려야 한다. 그것도 잊기 쉬운
자리라 `deploy.sh` 에 인자로 받는 것을 검토한다.
