# P06 — 교정을 내보내고(`export_review.py`), 그 다음 `Image` 를 뽑는다

2026-08-05. 계획 문서. **순서가 요점이다.**

`Image` 정규화(프레임별 검토의 전제)를 지금 하는 것이 가장 싸다는 결론이 섰다 —
자료가 가장 적고, 스키마가 아직 한 벌이고, 프레임별 검토를 아직 안 만들었다.
셋 다 시간이 갈수록 나빠지기만 한다.

**그런데 그 이사는 교정 6,732행을 만진다. 지금 안전망은 `backup_db.py` 하나다.**
백업은 "몇 행이었나" 는 알려 주지만 **"무엇이 달라졌나" 는 못 알려 준다** — 027 을
알아챈 것도 숫자였지 내용이 아니었다. 그래서 `export_review.py`(P02 5단계)를
먼저 만든다.

---

## 1. 무엇을 만드는가

| 단계 | 내용 | 되돌릴 수 있나 |
|---|---|---|
| **1** | `export_review.py` — DB → `review/` (git 감사 기록) | — |
| **2** | `Image` 테이블 + `Detection.image`(nullable) 추가 | 판을 되돌리면 옛 코드가 그대로 돈다 |
| **3** | 백필 — Image 1,635 · Detection 2,076 · ObjectReview 6,732 | 옛 칼럼이 그대로 있다 |
| **4** | 파이프라인 이미지가 `image` 를 쓰기 시작 | 판 되돌리기 |
| **5** | `NOT NULL` 로 조이고 `target`·`frame` 제거 | **여기부터 못 되돌린다** |

**5번은 프레임별 검토를 실제로 붙일 때 함께 한다.** 서두를 이유가 없고, 위험이
거기 몰려 있다.

지금 문서에서 자세히 정하는 것은 **1번**이다. 2~5는 §5 에 뼈대만 둔다 — 1번이
끝나야 그 위에서 판단할 것들이 보인다.

---

## 2. `export_review.py` — 무엇을 위한 물건인가

셋 다 만족해야 한다. 하나라도 빠지면 다른 물건이 된다.

1. **감사 기록** — git 에 남아 `diff` 로 "언제 무엇이 달라졌나" 가 보인다
2. **안전망** — DB 가 상해도 사람의 판단을 되살릴 수 있다
3. **대조 도구** — 두 시점(백업 파일 포함)의 교정을 견줄 수 있다

3번이 이번 이사의 실질적인 이유다. **마이그레이션 전후로 돌려 같은지 보는 것**이
"어긋나면 멈춘다" 를 실제로 가능하게 한다.

---

## 3. 정하는 것들

### 3.1 Django 를 임포트하지 않는다 — `sqlite3` 로 읽기 전용

**규약의 예외를 하나 더 만드는 것이 아니라, `backup_db.py` 와 같은 자리에 두는
것이다.** 그 예외의 근거가 그대로 성립한다 — Django 를 안 쓰고, 원본을
**읽기 전용**으로만 열며, 그래서 "같은 파일을 두 벌의 환경이 만진다" 가 성립하지
않는다(CLAUDE.md).

얻는 것이 셋이다.

- **저장소에 바로 쓴다.** 컨테이너는 `/srv/DiaRUGA/db` 와 `/data3` 만 물고
  저장소를 안 문다. ORM 을 쓰면 컨테이너 안에서 내보내고 사람이 저장소로 옮겨야
  하는데, 그 왕복이 있는 감사 기록은 아무도 안 돌린다
- **`models.py` 가 흔들려도 돈다.** 감사 기록이 코드 판에 매이면 안 된다.
  특히 **2~5단계에서 스키마가 바뀌는 동안에도 같은 도구로 견줘야 한다**
- **백업 파일을 그대로 읽는다** — `--db backup/DiaRUGA_20260804_114433.db`.
  두 시점을 견주는 일이 이것 하나로 된다

### 3.2 무엇을 내보내는가 — `geom` 을 반드시 넣는다

`removed`·`accepted` 만 있는 지금 `review/*.json`(2026-07 형식)으로는 **되살릴 수
없다.** 키(`mask_key`)는 bbox 문자열이라 검출이 바뀌면 안 맞고, 그때 다시 붙이는
근거가 `geom` 이다. **`geom` 이 빠진 내보내기는 감사 기록이지 안전망이 아니다.**

크기는 문제가 안 된다 — 실측 **1.4 MB**(6,732행 · 평균 218 B). 폴리곤이
`approxPolyDP` 로 단순화돼 있어서 점이 10~20개다.

내보낼 것: `mask_key` · `removed` · `accepted` · `label` · `note` · `geom` ·
`bind_method` · `bind_score`, 그리고 시야마다 `done` · `note`.

| 지금 DB | 수 |
|---|---|
| 교정(`ObjectReview`) | 6,732 (`geom` 100%) |
| 분류 지정 | 1,250 |
| 개체 코멘트 | 2 |
| 시야 검토(`ViewpointReview`) | 432 (완료 343 · 코멘트 6) |
| 내보낼 시야 | **432** (그중 싱글턴 119) |

### 3.3 파일 이름 — `review/<슬라이드>/g<n>.json`

**지금 `review/<stem>_review.json` 은 쓸 수 없다.** stem 이 겹치기 때문이다 —
싱글턴 시야는 stem 이 곧 프레임 이름이고 **프레임 이름은 슬라이드끼리 겹친다**
(143종). 053 에서 저장이 남의 시야로 가던 것과 **정확히 같은 원인**이고, 여기서는
파일이 서로를 덮어쓰는 모습으로 나타난다. 내보낼 시야 432 중 싱글턴이 119다.

`(슬라이드 슬러그, 시야 번호)` 는 겹치지 않는다 — `Viewpoint` 에
`(slide, idx)` 유일 제약이 있다. 주소(`/d/<slug>/g/<n>/`)와도 같은 열쇠다.

```
review/260731_am22-gc10b_25cm/g001.json
review/260803_bp09-0901/g002.json
```

**옛 124개 파일은 지운다.** 이미 낡았고(HANDOFF 3.1), 새 형식과 섞이면 어느 쪽이
진짜인지 알 수 없다. git 이 지운 것을 기억한다.

### 3.4 diff 가 읽히게 쓴다

감사 기록의 값은 **`git diff` 가 읽히는가**에 달렸다. 개체 하나가 한 줄이어야
"이 개체의 분류가 바뀌었다" 가 한 줄로 보인다.

- 바깥 구조는 들여쓰기, **개체는 한 줄에 하나**
- `mask_key` 로 정렬 (dict 순서가 아니라)
- `ensure_ascii=False` — 코멘트가 한글이다
- 줄바꿈으로 끝낸다

### 3.5 되돌려 넣는 것(import)은 이번에 안 만든다

**형식은 되살릴 수 있게 만들되, 넣는 도구는 따로 본다.** `import_json.py` 가
이미 "아무 때나 돌리면 DB 를 옛 상태로 되돌리는" 물건이라(CLAUDE.md) 같은 것을
하나 더 만들 이유가 없다. 되살릴 일이 생기면 그때 그 상황에 맞게 만든다.

### 3.6 `--check` 를 함께 만든다

내보낸 파일과 DB 를 견줘 다른 것만 낸다. 이것이 2~5단계의 안전장치다.

```bash
python export_review.py                         # 저장소 review/ 로
python export_review.py --check                 # 파일 ↔ DB 대조
python export_review.py --db <백업> --out /tmp/before   # 두 시점 견주기
diff -r /tmp/before review/
```

---

## 4. 1단계 완료 기준

- `review/` 에 432개 파일 · 교정 6,732행이 빠짐없이 들어간다
- `--check` 가 "다른 것 없음" 을 낸다
- **다시 돌려도 파일이 한 바이트도 안 바뀐다**(멱등) — 안 그러면 diff 가 잡음이
  된다
- 백업 파일을 `--db` 로 읽어 옛 시점과 견줄 수 있다
- 호스트 venv 로 돌고 Django 를 임포트하지 않는다

---

## 5. 2~5단계의 뼈대 (자세한 것은 1단계 뒤에)

### 왜 `Image` 인가

`시야 1:N 프레임 1:N 검출` 이 이 스키마에서 성립하지 않는다 — **합성본은
프레임이 아니다.** 검출이 도는 이미지가 `Stack.focused_path` 아니면 `Frame.path`
라 테이블이 둘이고, `Detection` 이 `target`(`stack|frame`) + nullable `frame` 으로
다형 연관을 흉내 낸다.

```
Viewpoint 1:N Image(kind = stack | frame | depth, path, …) 1:N Detection 1:N Candidate
                    ↑
           ObjectReview.image   NOT NULL FK
           unique (image, mask_key)
```

판별자 문자열도, `__stack__` 센티널도, "유일 제약에서 NULL 은 서로 다른 값" 이라는
규칙도 전부 필요 없어진다. `Detection.target`·nullable `frame`·`_engine_pick` 의
분기·캐러셀의 `STACK_KEY` 도 함께 사라지고, **깊이맵에 검출이 안 붙는다는 것이
관행이 아니라 스키마에 드러난다.**

**`Stack` 은 뜯지 않는다.** 칼럼 17개 중 이미지 정체는 `focused_path`·`depth_path`
둘뿐이고 나머지는 합성 실행의 산물(`align_failed`·`object_px_frac`·
`sharpness_fused`·`gain`·`resize_scale`…)이다. `Image` 를 뽑으면 `Stack` 은
"합성 실행 기록" 으로 성격이 오히려 선명해진다.

### 다형 연관을 실제로 만지는 자리 — 아홉

```
쓰기  segment_diatoms.py:738  Detection.objects.create(target=, frame=)
      focus_stack.py:316      Stack(focused_path=, depth_path=)
      import_json.py:296      update_or_create(target=, frame=)
읽기  data.py:488 · 1209 · 1446~1448   (candidate_rows · group_detail · _engine_pick)
      prune_detections.py:68  묶음 열쇠 (viewpoint, target, frame_id)
```

### 밟으면 안 되는 것

- **`NOT NULL` 을 먼저 걸면 옛 파이프라인 이미지의 INSERT 가 죽는다.** 뷰어와
  파이프라인은 판이 따로 돈다 — CLAUDE.md 의 `db_default` 함정을 칼럼이 아니라
  FK 규모로 겪는 셈이다. 그래서 **nullable → 백필 → 파이프라인 배포 → 조이기**다
- **폴러가 1분마다 돈다.** 3단계(백필) 동안은 세운다
- **한 판에 `Image` 를 넣고 `target`·`frame` 을 지우지 않는다.** 되돌릴 지점이
  없어진다

### 함께 볼 것

- **050 의 peewee 이식은 아직 시작 전이다**(`desktop/` 이 없다). 이식 후에
  정규화하면 스키마 두 벌과 `tools/schema_diff.py` 의 기준 지문까지 함께 고쳐야
  한다. **이식 전에 끝내는 편이 싸다**
- 5단계와 함께 갈 것들은 "프레임별 검출을 검토할 수 있게 한다"(TODOs)에 있다 —
  `/review` 의 갈아치우기 범위 · `detection_for_viewpoint` 의 거르기 ·
  "검토 완료" 의 뜻 · 집계 분리

---

## 6. 진행 기록

| 단계 | 상태 |
|---|---|
| 1. `export_review.py` | **끝** — 2026-08-05. 시야 432 · 교정 6,732 |
| 2. `Image` + `Detection.image`·`ObjectReview.image`(nullable) | **끝** — `0019_image_table` · v0.5.4 로 배포 |
| 3. 백필 | **끝** — 2026-08-05 v0.5.4. 이미지 1,952 · 검출 2,076 · 교정 6,738 |
| 4. 파이프라인이 `image` 를 쓴다 | 남음 |
| 5. 조이기 + 프레임별 검토 | 남음 |

---

## 7. 2·3단계를 실제로 한 기록 (2026-08-05, v0.5.4)

```
배포          deploy.sh v0.5.4 → 0019_image_table 적용 → smoke 통과
사본          backup_db.py --note before-image-backfill
폴러 정지     flock /tmp/DiaRUGA-poll.lock  ← crontab 을 건드리지 않는다
백필          dbrun.sh backfill_images.py --apply
검증          dbrun.sh backfill_images.py --verify   (일곱 항목 전부 OK)
대조          export_review.py --check               (달라진 것 없음)
```

**폴러는 crontab 을 고쳐 세우지 않았다.** `poll_nas.sh` 가 이미 `flock -n` 으로
겹침을 막고 있어서, 그 잠금을 잡고 있으면 그 사이의 실행은 조용히 물러난다.
남의 설정을 고쳤다가 되돌리는 것을 잊는 쪽이 위험하다.

**교정이 한 글자도 안 바뀐 것을 파일로 증명했다.** 백필 직전 사본을
`export_review.py --db` 로 내보내고 지금 저장소의 `review/` 와 `diff -r` 했다 —
차이 없음. 이것이 1단계를 먼저 만든 이유 그대로다.

### 걸린 것 하나

`backfill_images.py` 가 처음에 `/srv/DiaRUGA/scripts` 에서 안 돌았다
(`No module named 'diarugaweb'`). 스크립트가 **자기 옆의 `web/`** 을 보게 짜여
있었는데, 컨테이너에서는 코드가 이미지 안의 `/app` 에 있다. `check_db.py` 가
`DIARUGA_APP` 으로 이미 풀어 둔 문제였다 — **`dbrun.sh` 로 돌릴 스크립트는 그
머리를 그대로 베껴 온다.**

## 8. 5단계에서 내보내기 형식도 함께 올린다 (format 2 → 3)

**스키마를 조이는 것만으로는 내보내기가 안 바뀐다.** `export_review.py` 는
`viewpoint`·`slide`·`viewpointreview`·`objectreview` 넷만 읽고 `detection` 을 아예
안 본다 — `target`·`frame` 이 사라져도 출력이 바이트 단위로 같다.

**바뀌는 것은 프레임별 검토를 실제로 쓰기 시작할 때다.** 한 시야가 이미지 여럿에
대한 교정을 갖게 되면 지금 형식이 셋에서 무너진다.

- 파일 하나 안에서 `key` 가 겹친다 — `mask_key` 가 프레임끼리 45% 겹친다
- 어느 이미지를 보고 한 판단인지 안 남는다 → **되살릴 수 없다**(§2-2 붕괴)
- `done`·`note` 가 시야당 하나라 이미지별 검토 완료를 못 담는다

**모양은 아직 정하지 않는다** — "검토 완료" 가 시야 단위인지 이미지 단위인지가
안 정해졌고(TODOs 의 열린 질문), 그것이 형식을 가른다.

대신 **그날을 조용히 맞지 않게** 막아 두었다. 시야 하나의 교정이 이미지 여럿에
걸치면 `export_review.py` 가 **쓰지 않고 멈춘다.** 셋 다 "예외 없이 그럴듯한
파일이 나오는" 종류라 여기서 세우지 않으면 나중에 파일을 믿고 있다가 당한다.
형식을 3 으로 올릴 때 이 검사도 함께 걷는다.

> 함께: `image_id` 칸이 없는 **옛 백업 파일도 계속 읽힌다**(`PRAGMA table_info`
> 로 보고 없으면 `NULL`). 두 시점을 견주는 것이 이 도구의 목적 중 하나다.
