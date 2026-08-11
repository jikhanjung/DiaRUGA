# DiaRUGA

극지 퇴적물 코어 시료의 규조류 광학현미경 사진 분석 파이프라인 + 검토·교정 뷰어.

사진에서 개별 규조각을 찾아 µm 단위로 계측하고, 웹 뷰어에서 확인·교정한다.

```
NAS 새 폴더 ─[반입]→ 사진 ─[그룹핑]→ 시야 ─[합성]→ all-in-focus ─[검출]→ 후보
                                                                 ─[판정]→ 규조각
                                                                 ─[교정]→ 사람
```

**원본은 `DiaRUGA.db` 다** (SQLite, WAL). 파이프라인 다섯 단계와 뷰어가 같은 DB 를
읽고 쓴다. `groups_*.json`·`out/*.json` 은 이제 **내보내기 형식**으로만 남아 있고
파이프라인 흐름에서는 빠졌다(P02 7단계).

**NAS 에 새 슬라이드가 올라오면 1분 안에 검출까지 스스로 간다** — `poll_nas.sh` 가
반입부터 검출까지 돌린다(P03). 손으로 부를 일은 다시 돌릴 때뿐이다.

> **지금 몇 장이 들어와 있고 검토가 어디까지 갔는지는 여기 적지 않는다** —
> 사람이 검토하는 동안에도 움직이는 값이라 적는 순간 낡는다. 그 숫자는
> [HANDOFF.md](HANDOFF.md) 와 `/healthz` 가 낸다.

## 자료의 층

```
권역   한국 · 남극                       Site.area
 └ 지역   BP(북평분지) · RS23            Site
    └ 지점   BP09(노두) · GC03(시추코어)  Locality
       └ 시료   0901 · 71cm              Sample
          └ 관찰   (1) · (2)             Slide   = 폴더 하나 = 슬라이드글라스 하나
             └ 시야 → 사진 → 검출 → 교정
```

**"코어" 라고 부르지 않는다** — 노두는 시추한 것이 아니다. 어느 쪽인지는
`Locality.kind` 가 말한다. **관찰은 시료 하나를 처리 방법·회차를 달리해 본 것**
이고 서로 동등하다 — 대표를 두지 않고 이름표로 구분한다.

폴더 이름에서 이 층을 읽는 규칙은 **`web/viewer/naming.py` 하나뿐이다**
(남극은 `<지역>-<지점> <깊이>cm`, 육상은 `<지점>-<시료>` — 가르는 표시는 `cm`).

## 구성

```
pipeline/  group_focus_series.py → focus_stack.py → segment_diatoms.py → refilter.py
   초점 시리즈 묶기        all-in-focus 합성    SAM2 / YOLO 검출 + 지표   문턱만 다시 적용
                                                       ↑
                                                   judge.py  ← 판정 규칙은 여기 하나뿐
```

| 디렉토리 | 무엇이 | 운영(`/srv`)으로 가나 |
|---|---|---|
| `pipeline/` | 컨테이너 안에서 도는 것 + 그들이 쓰는 모듈(`judge`·`zen_meta`·`runlog`) | **간다** |
| `ops/` | 주기적으로 돌거나 상태를 보는 것 (백업·무결성·검사·내보내기) | **간다** |
| `migrate/` | 이전기·일회성 (backfill·rebind·verify) | 안 간다 |
| `tools/` | 개발 도구 (지도 굽기·보고서 변환·벤치) | 안 간다 |
| `web/viewer/` | Django 뷰어 — 18개 모델 · 화면 · 교정 | 이미지로 간다 |
| `deploy/` | compose·nginx·폴러·호스트 스크립트 | **간다** |
| `review/` | **교정의 git 감사 기록** (`ops/export_review.py` 가 뽑는다) | — |

**운영 서버에 저장소가 없어도 돈다** — 필요한 것은 `deploy/host/sync_to_srv.sh` 가
`/srv/DiaRUGA` 로 민다. **`/srv/DiaRUGA/scripts` 는 평평하다**(컨테이너가 그
디렉토리 하나만 물어서, 스크립트끼리의 임포트도 평평해야 선다).

## 돌리는 법

**평소에는 손댈 것이 없다** — `deploy/poll_nas.sh` 가 1분마다 반입부터 검출까지
돌린다. 손으로 부를 일은 다시 돌릴 때뿐이고, 명령은
[CLAUDE.md](CLAUDE.md) 의 "자주 쓰는 명령" 에 있다.

- **GPU 를 쓰는 작업은 한 번에 하나만 돈다** (잠금이 `segment_diatoms` 안에 있다)
- **DB 를 만지는 스크립트는 문 하나로만 들어간다** — `deploy/host/dbsync.sh` 로
  옮기고 `dbrun.sh` 로 컨테이너 안에서 돌린다. 호스트에서 같은 DB 를 열면 **같은
  파일을 두 벌의 환경이 만진다** (두 번 당했다)
- **큰 작업 전에는 사본을 뜬다** — `dbrun.sh backup_db.py --note <설명>`

## 배포

뷰어와 파이프라인이 **컨테이너 두 벌**로 돌고 **판이 따로다**(`IMAGE_TAG` /
`PIPELINE_TAG`). 다만 **스키마를 조이는 마이그레이션**과 **슬러그·경로 같은 "값의
모양" 규칙**은 둘을 함께 올려야 한다 — 갈라 두는 것이 이 두 자리에서는 반대로 문다.

자주 빠지는 함정은 [CLAUDE.md](CLAUDE.md) 의 "배포·컨테이너" 에 모아 두었고,
지금 무엇이 어디서 도는지는 [HANDOFF.md](HANDOFF.md) 9절이다. 배포·백업 규약의
전문은 `.guides/web/README.md` 에 있다(형제 프로젝트들이 같은 사고를 겪고 도달한
표준 · 이 저장소에는 커밋하지 않는다).

## 설치

**requirements 가 넷으로 갈라져 있다** (P03). 호스트 venv 는 `requirements.txt`
하나면 되고, 컨테이너가 나머지를 나눠 쓴다.

| 파일 | 누가 쓰나 |
|---|---|
| `requirements.txt` | 호스트 venv (`~/venv/DiaRUGA`) |
| `requirements-web.txt` | 뷰어 컨테이너 — Django · pillow · gunicorn |
| `requirements-pipeline.txt` | 파이프라인 컨테이너 — torch · SAM2 |
| `requirements-yolo.txt` | ultralytics. `--no-deps` 로 파이프라인 위에 얹는다 |

torch 는 CUDA 12.6 기준이다(`--extra-index-url https://download.pytorch.org/whl/cu126`).
드라이버가 더 낮으면 cu121 등으로 바꾼다. Python 3.12~3.14 에서 동작을 확인했다.

**사내망이 `download.pytorch.org` 의 TLS 를 가로챈다.** 파이프라인 이미지 빌드가
거기서 죽으면 `deploy/ca/` 를 볼 것 — `pip` 은 시스템 CA 저장소를 보지 않아
`PIP_CERT` 를 함께 줘야 한다.


## 산출물

| 경로 | 내용 | 재생성 |
|---|---|---|
| **`DiaRUGA.db`** | **원본. 시료·시야·검출·교정 전부** | **불가** (교정 부분) |
| `photos/` | 촬영 원본 (NAS 에서 반입) | NAS 가 원본 |
| `stacked/` | all-in-focus 합성본 + 깊이 맵 | 가능 |
| `out/*_candidates.json` | 검출 내보내기 (요청할 때만) | 가능 |
| `groups_*.json` | 시야 그룹핑 내보내기 (요청할 때만) | 가능 |
| `.thumbcache/` | 크롭 썸네일 | 가능 |
| **`review/<슬라이드>/g<n>.json`** | **교정의 git 감사 기록** | DB 에서 다시 뽑는다 |

DB·사진·중간 산출물은 전부 저장소 밖(`/data3/DiaRUGA/`·`/srv/DiaRUGA/db/`)에 있고
gitignore 다. **`review/` 만 저장소에 남는다** — `ops/export_review.py` 가 DB 에서 뽑아
git 에 넣으므로 `git diff` 로 "언제 무엇이 달라졌나" 가 보인다. 감사 기록이지
원본이 아니다.


## 문서

**이 README 는 소개와 구성만 맡는다.** 자세한 것은 아래로 간다.

| | |
|---|---|
| [HANDOFF.md](HANDOFF.md) | **지금** 상태와 인수 사항. 이어서 작업할 때 여기부터 |
| [CLAUDE.md](CLAUDE.md) | 자주 쓰는 명령과 **자주 빠지는 함정** |
| [TODOs.md](TODOs.md) | 앞으로 할 일 |
| [CHANGELOG.md](CHANGELOG.md) | **판 이력** — 판 하나에 한 줄, 근거 devlog 번호와 함께 |
| [docs/…_pipeline-rationale.md](docs/20260811_pipeline-rationale.md) | **파이프라인이 왜 이렇게 되어 있는가** — 촬영 조건·그룹핑·합성·검출·판정 기준·실측·성능 |
| [docs/…_schema-rationale.md](docs/20260811_schema-rationale.md) | **스키마의 근거** — 교정이 `mask_key` 에 붙는 이유 · `Image` 정규화 · 개체와 판정 |
| [docs/…_viewer-guide.md](docs/20260811_viewer-guide.md) | **뷰어 안내** — 화면이 무엇을 하고 왜 그런가 |
| [docs/…_db-specification.md](docs/20260810_db-specification.md) · [db-erd.md](docs/20260810_db-erd.md) | DB 의 **지금 모습** (테이블·칼럼·ERD) |
| `docs/*-progress-*.md` | 종합 진척 보고서 (11차까지) |
| `devlog/YYYYMMDD_NNN_*.md` | 작업 기록 — 무엇을 했는지보다 **왜 그렇게 했고 무엇을 버렸는지** |
| `devlog/YYYYMMDD_PNN_*.md` | 계획 문서 (P01 큰 그림 · P02 DB 스키마 · P03 컨테이너·NAS · P04 YOLO 학습 · P05 데스크탑 앱 · P06 Image 정규화 · P08 자동 시험 · P09 마스크 그리기 · P10 묶음 고르기 · P11 개체 묶기 · P12 개체와 판정) |

## 알려진 한계

1. **SAM2 파이프라인의 재현율은 50~60% 추정.** 눈에 보이는 봉상 중 절반가량을
   놓친다. 원인은 판정 기준이 아니라 분할 단계다 — SAM2 AMG 가 조밀한 무리 속
   **투명한** 규조각을 온전한 하나로 분할하지 못한다. 불투명한 쇄설물은 깨끗하게
   따면서 정작 목표물에 약하다. **이것이 YOLO 로 간 이유다** — 사람이 검토한 시야로
   학습시키니 같은 재현율에서 정밀도가 1.7배였다. 다만 **아직 갈아타지 않았다.**
2. **원형(중심목) 문턱은 실물로 검증된 적이 없다.** 오검출을 걸러내며 잡은 값이라
   진짜를 놓치고 있을 수 있다. 특히 **텍스처는 크기와 같이 움직여** 작은 중심목을
   먼저 떨어뜨린다. 이제 표본이 충분하므로 검증할 수 있다 (TODOs 1순위).
3. **Plate 7·8 형태(뿔·원뿔)는 설계상 제외.** 윤곽이 오목해 타원 기준을 통과할 수
   없다. 텍스처는 통과하지만 형태 관문에서 걸린다.
4. **종 동정은 아직 사람 몫이다.** 자동 판정은 "규조각인가", "봉상인가 원형인가"
   까지고, 속(屬) 단위인 Eucampia·Chaetoceros 는 사람이 지정한다.
5. **깊이 맵의 정량화**는 Z 좌표가 기록된 z-stack 촬영이 전제다.
6. **SQLite 는 쓰기가 하나다.** 파이프라인이 도는 중에 검토를 저장하면 잠긴다 —
   프레임 229장을 그렇게 잃었다. 트랜잭션을 나눠 고쳤지만, 동시 작업이 일상이 되면
   다시 볼 문제다.


## 라이선스

**GNU Affero General Public License v3.0** ([LICENSE](LICENSE)).

검출 백엔드가 쓰는 [Ultralytics](https://github.com/ultralytics/ultralytics)
YOLO11 이 AGPL-3.0 이라, 그것과 합쳐지는 이 저장소도 같은 라이선스로 나간다.
학술 도구라 소스를 여는 것이 오히려 자연스럽다는 판단이다
(`docs/20260805_desktop-app-review.md` 4절).

받는 사람에게 주는 것과 요구하는 것:

- **쓰고 고치고 다시 배포할 수 있다.** 연구·상업 용도 구분이 없다
- **고쳐서 배포하면 소스를 함께 열어야 한다** — AGPL 은 여기에 하나를 더 얹는다.
  **네트워크 너머로 서비스하는 것도 배포로 본다**(13조). 고친 판을 웹으로
  제공하면 그 소스를 이용자에게 제공해야 한다
- 합쳐지는 저작물 전체가 AGPL 이 된다

**형제 프로젝트와 코드를 주고받을 때 방향이 있다.** `Modan2` 는 MIT 다 —
**MIT → 여기로 가져오는 것은 되지만, 여기 코드를 Modan2 로 되돌려 넣으면
Modan2 가 오염된다.** 방향을 지킬 것.

사진·DB·학습 자료는 저장소에 없고 이 라이선스의 대상도 아니다.
