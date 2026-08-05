# 048 — 이름을 DiaRUGA 한 겹으로 모았다

2026-08-05 아침. 041 에서 뷰어 이름을 `DiaRUGA` 로 정하면서 **저장소·경로·DB·URL 은
`diatom` 으로 두기로** 했었다. 그 결정을 뒤집는다. 이름이 두 겹인 상태가
석 달째였고, "화면은 DiaRUGA 인데 주소는 /diatom/" 을 사람에게 설명하는 비용이
계속 들었다.

## 1. 먼저 범위를 좁게 제안했다가 뒤집혔다

처음에는 **저장소 이름과 작업 디렉토리만** 바꾸자고 했다. 근거는 `/srv`·`/data3`·
이미지 태그·URL 이 사람의 교정 6,731건이 든 DB 와 롤백 경로에 걸려 있다는 것.
싸게 얻을 것을 다 얻고 잃을 것이 없는 선이라고 봤다.

**전부 바꾸기로 했다.** 두 겹으로 남겨 두면 "여기는 왜 옛 이름인가" 를 앞으로
계속 설명해야 하고, 그 설명이 041 처럼 문서에 눌러앉는다.

## 2. 어디를 무엇으로 바꿨는가

원칙 하나로 정리했다 — **프로젝트 정체성은 `DiaRUGA`, 기술이 소문자를 강제하는
자리만 `diaruga`.**

| 층 | 바뀐 것 |
|---|---|
| GitHub | `jikhanjung/diatom` → `jikhanjung/DiaRUGA` |
| 작업 디렉토리 | `~/projects/diatom` → `~/projects/DiaRUGA` |
| 배포·자료 | `/srv/diatom`·`/data3/diatom` → `/srv/DiaRUGA`·`/data3/DiaRUGA` |
| venv | `~/venv/diatom` → `~/venv/DiaRUGA` |
| NAS 공유 | `/nfs/temp-share/diatom` → `.../DiaRUGA` |
| DB | `diatom.db` → `DiaRUGA.db`, 사본 `diatom_*` → `DiaRUGA_*` |
| URL | `/diatom/` → `/DiaRUGA/` |
| 이미지 | `honestjung/diatom{,‑pipeline}` → `honestjung/diaruga{,‑pipeline}` (Hub 은 소문자만) |
| 파이썬 패키지 | `diatomweb` → `diarugaweb` |
| 환경변수 | `DIATOM_*` → `DIARUGA_*` |
| localStorage | `diatom.*` → `diaruga.*` |

판은 뷰어 `v0.4.0` · 파이프라인 `v0.2.0`. **PATCH 가 아니라 MINOR 다** — 기능은
그대로지만 `.env` 의 키 이름이 전부 바뀌어 **옛 설정 파일로는 뜨지 않는다.**
바뀐 것은 기능이 아니라 계약이다.

## 3. `diatom` 을 남긴 자리 — 여기가 핵심이다

`diatom` 은 프로젝트 이름이면서 **규조류라는 생물의 이름**이다. 무차별 치환은
분석 대상 자체를 지운다. 그래서 **패턴 허용목록으로 쓸어내고 남은 잔여물을 손으로
판단**했다. 남긴 것:

- `segment_diatoms.py`, `viewer/regroup.py` 의 `diatoms` — 하는 일이 규조류 검출이다
- `export_yolo.py` 의 `--classes default="diatom"` — **YOLO 클래스 이름**이다.
  바꿨으면 이미 학습한 가중치와 라벨이 어긋난다
- NAS 원본 폴더 `/nfs/temp-share/DiatomPhotos` — **우리가 만든 것이 아니다.**
  촬영이 거기에 쌓인다
- 본문의 `규조류(diatom)`
- 지난 devlog 와 `docs/` 의 진행 보고서 — 그때 이름 그대로

`viewer_run.params` 에 `/data3/diatom/datasets/...` 가 든 행이 둘 있는데 이것도
남겼다. "그때 이렇게 돌렸다" 는 기록이라 devlog 와 성격이 같다.

**진척 보고서는 6차부터 `DiaRUGA-` 다** — `docs/YYYYMMDD_DiaRUGA-analysis-system-
progress-6.md`. 1~5차는 그 이름으로 이미 NAS 공유에 docx 가 올라가 있어 바꾸지
않았다. 남이 열어 둔 파일의 이름을 뒤에서 바꾸면 저쪽 링크가 끊긴다. 새 보고서가
옛 보고서를 링크할 때는 **그 파일의 실제 이름**을 쓴다.

## 4. 밟을 뻔한 것들

**URL 은 대소문자를 가린다.** 정식 주소가 `/DiaRUGA/` 면 `/diaruga/` 로 친 사람은
404 를 본다. 대소문자 무시 정규식으로 301 을 걸었는데, **그냥 걸면 무한 루프였다** —
CLAUDE.md 에 적어 둔 대로 nginx 는 접두 location 보다 **정규식을 먼저 본다.**
`location ^~ /DiaRUGA/` 로 "접두가 맞으면 정규식을 보지 말라" 고 해야 멈춘다.
옛 `/diatom/` 도 같은 블록이 받는다.

**localStorage 키를 그냥 갈아치우면 사람의 설정이 조용히 초기화된다.** 꺼 둔
레이어가 되살아나고 "늘 이동" 을 고른 사람에게 다시 묻는다. 예외도 경고도 없이
그냥 기본값으로 돌아간다. 읽는 자리마다 **옛 키를 대체로 읽게** 했다. 쓰기는
새 키로만 한다.

**DB 에 절대경로가 들어 있으면 디렉토리만 옮기고 끝낼 수 없다.** 옮기기 전에
모든 테이블의 모든 칼럼을 `LIKE '%/data3/%'` 로 훑었다. 위의 `run.params` 둘뿐이라
안전했지만, 확인하지 않고 옮겼으면 사진을 못 찾는 상태를 나중에 발견했을 것이다.

**백업 사본 이름이 바뀌면 옛 사본이 로테이션에서 빠진다.** `--keep 24` 는
`DiaRUGA_????????_??????.db` 만 세므로 `diatom_*` 는 영원히 남는다. 위험하지는
않다 — 오히려 정리 glob 이 옛 사본을 못 건드린다. 다만 로컬 24개(약 2.6 GB)와
NAS 쪽이 쌓인 채로 있다.

**`/healthz` 가 곧바로 degraded 를 냈다.** 사본을 `DiaRUGA_*.db` 로 찾는데 그
이름을 가진 것이 하나도 없었다. 새 이름으로 한 판 뜨자 풀렸다. 이름을 바꾸는
작업에서 **안전망이 이름으로 대상을 찾고 있으면 같이 눈이 먼다**는 것을 기억할 것.

**compose 프로젝트 이름은 디렉토리 이름에서 나온다.** `/srv/DiaRUGA` 는 대문자가
섞여 있어 compose 가 조용히 소문자로 깎는다. 그 암묵적 변환에 컨테이너 이름을
맡기지 않으려고 `name: diaruga` 를 파일에 박았다.

## 5. venv 는 다시 만들지 않고 옮겼다

`requirements.txt` 가 torch 를 끌고 와 6.5 GB 다. 새로 만들면 사내망이
`download.pytorch.org` 의 TLS 를 가로채는 문제까지 다시 만난다. **옮기고 안에
박힌 절대경로만 고쳤다** — `bin/` 의 스크립트 shebang 과 `activate` 계열이다.
`grep -rlI` 로 텍스트 파일만 골라 치환했고, torch·CUDA 까지 정상 동작을 확인했다.

## 6. 순서를 한 번 바꿨다

처음 계획은 `경로 이동 → 이미지 굽기` 였다. 그러면 **경로를 옮긴 순간부터 이미지가
없어서 빌드가 끝날 때까지 뷰어가 내려가 있다.** 뒤집어서 **이미지를 먼저 굽고**
경로를 옮겼다. 옛 스택이 도는 동안 굽는 것은 서로 방해하지 않는다.
실제 정지 시간은 09:49~09:53, **4분**이었다.

`/srv`·`/data3` 의 부모가 root 소유라 이름 변경에 sudo 가 필요했다. nginx 도
마찬가지여서, 두 번 부탁하지 않도록 **하나의 스크립트로 묶어** 전제 확인 →
디렉토리 이동 → nginx 설치 → `nginx -t` 통과할 때만 reload 하게 했다. 옛 nginx
설정은 `.bak-048` 로 남겼다.

## 7. 확인한 것

- 렌더한 인라인 스크립트 10개를 `node --check` 로 파싱 (CLAUDE.md 의 그 방법)
- `manage.py check` — 사본 DB 에 붙여서
- `check_db.py` — DB 가 앞뒤가 맞는다
- `smoke.sh` — 판 `v0.4.0` · 슬라이드 10 · 교정 6,731 · nginx 경유 200
- 주소 여덟 형태(`/DiaRUGA/`·`/diaruga/`·`/DIARUGA/`·`/diatom/`·슬래시 없는 것·
  옛 :9090)가 전부 정식 주소로 모이는 것

## 8. 남은 것

- 옛 백업 사본(`diatom_*.db`) 정리 여부 — 로컬 2.6 GB · NAS 쪽
- NAS 공유를 `N:\diatom` 으로 매핑해 쓰는 사람들에게 알리기
- 옛 이미지 `honestjung/diatom:*` 는 **지우지 않았다.** 롤백 경로다
