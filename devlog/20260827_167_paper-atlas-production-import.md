# 논문 도감 넷을 운영에 반입한다 — `v0.20.0` (167)

`ops/import_atlas.py` · `ops/import_occurrence.py` · 배포

163~166 에서 논문 도감 넷을 저장소(`atlas/*.json`)와 도판 이미지(`/data3`)까지
만들어 뒀지만, 운영 DB 에는 아직 안 들어가 있었다(TODOs 의 당면 과제). 이 세션이
그 반입과 배포를 끝냈다.

## 반입 전에 판을 먼저 내야 했다

`import_atlas.py`(컨테이너 안에서 돈다)로 `--dry-run` 을 돌려 보니 도감 셋만
잡히고 논문 넷이 안 나왔다. 원인은 `atlas/*.json` 이 `COPY . .` 로 이미지
빌드 시점에 실리는 자료라는 것 — 그때 도는 `v0.19.0` 이미지는 163~166 이전에
구운 것이라 논문 JSON 을 아예 안 갖고 있었다. **v0.16.1 devlog 가 이미 적어 둔
교훈("판 먼저, 반입 나중")을 다시 확인한 것**이다.

그래서 이번 세션은 반입 하나가 아니라 **판을 내는 절차 전체**(163~166 을 main
에 병합 → `v0.20.0` 태그 → 배포)를 거쳐야 했다.

## 병합이 ff-only 로 안 됐다

`work/20260826-sclee-index` 를 main 에 병합하려는데 "diverging branches" 로
막혔다 — `merge-base`가 `fe21174`(main 최신)가 아니라 그 이전 `6e1acb0` 이었다.
그 사이 `fe21174`("논문 도감 넷의 운영 DB 반입을 당면 과제에 적는다")가 **다른
세션이 main 에 직접 커밋한 문서 전용 커밋**으로 들어와 있었다 — 규약대로다
(CLAUDE.md "문서·기록만 고치는 커밋은 main 에 바로 올린다"). `git rebase main`
으로 14개 커밋을 충돌 없이 얹었다(TODOs.md 를 건드린 두 커밋도 자리가 안
겹쳤다).

## 낸 판

`v0.20.0` — 마이그레이션 `0041`(`Reference`·`Occurrence`, 164). 리베이스 뒤
전체 시험(989개, 브라우저 포함)을 두 번 돌렸다(리베이스 전후로 한 번씩).
`docs/20260813_release-flow.md` 순서 그대로: main push → CI 통과 확인 → 주석
태그 → 태그 CI(굽기 + Docker Hub push) 통과 확인 → 레지스트리 조회로 확인 →
배포 전 스냅샷 → `deploy.sh v0.20.0` → smoke 통과.

## 반입

```
dbrun.sh import_atlas.py --dry-run   # 도감 7 . 논문 넷이 처음 잡혔다
dbrun.sh import_atlas.py             # 항목 2277 . 자리 2746 . 자기 검산 통과
dbrun.sh import_occurrence.py --dry-run
dbrun.sh import_occurrence.py        # 문헌 15 . 출현 기록 924
dbrun.sh check_db.py                 # 11 . 12 번 다 OK
```

`check_db.py` 11번의 "PDF 쪽이 없는 자리" 1건은 새로 생긴 것이 아니다 — 165 의
색인이 원래 그 자리를 안 적어 둔 것과 같다(주석에 이미 "색인이 원래 안 적은
자리다"로 적혀 있다).

## 눈으로 본 것

`Cladogramma californicium`(TODOs 가 예로 든 그 종)을 `/atlas/?q=Cladogramma`
로 찾아 `1993 Lee Chaetoceros` 칩과 함께 뜨는 것, 그리고 `해설 p.16` 링크가
`/atlas/1993-lee-chaetoceros/main/16/` 을 200 으로 여는 것을 확인했다 — 반입
전에는 이 검색이 빈 결과였다.
