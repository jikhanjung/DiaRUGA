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

**devlog 는 그때의 판단과 근거를 남기는 곳이다.** 의미 있는 작업을 마치면
`devlog/YYYYMMDD_NNN_주제.md` 로 기록한다. 무엇을 했는지보다 **왜 그렇게 했고
무엇을 버렸는지**를 쓴다.

## 환경

```bash
# venv 는 ~/venv/diatom 이다 (README 의 .venv 가 아니다 — HANDOFF 8.3)
python --version        # 3.12.3
```

`requirements.txt` 에 **Django 가 빠져 있다**(뷰어가 Django 5.2 로 돈다).
새 환경을 만들면 따로 깔아야 한다.

## 자주 쓰는 명령

```bash
# 뷰어
cd web && python manage.py runserver 0.0.0.0:9090

# DB 가 앞뒤가 맞는지 — 1초. refilter/segment 뒤, judge.py 를 고친 뒤, 숫자가 이상할 때
python check_db.py
python check_db.py --slide rs23 -v

# 큰 작업 전에는 반드시
python backup_db.py --note before-refilter

# 문턱만 바꿔 다시 거른다 (SAM2 재실행 없음, 밀리초)
python refilter.py --dry-run
python refilter.py --round-texture-min 2000

# 파이프라인 (GPU 필요)
python group_focus_series.py "260729/RS23-GC03 71cm" -o groups_RS23.json
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
- **`import_json.py` 를 아무 때나 돌리지 말 것.** 멱등이지만 `Candidate` 를 지우고
  다시 만든다. DB 에서만 한 교정이 있는데 옛 JSON 을 넣으면 JSON 쪽으로 되돌아간다
- **`verify_db.py` 는 임포트하면 `ImportError` 다.** 본문이 전부 최상위에 있어
  임포트만으로 실행됐고, DB 가 없으면 빈 `diatom.db` 를 만들었다. 막아 뒀다
- **Django 의 `{# #}` 는 한 줄짜리 주석이다.** 여러 줄이면 화면에 그대로 나온다.
  `{% comment %}` 를 쓸 것
- **`refilter.py` 에서 주지 않은 문턱은 현재 값을 그대로 쓴다.** 전부 기본값으로
  되돌리는 것이 아니다 — 하나 바꾸려다 나머지가 조용히 초기화되는 것을 막는 설계다

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
