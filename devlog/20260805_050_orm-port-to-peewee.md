# 050 — 데스크탑은 peewee 로 간다. 옮길 때 잃기 쉬운 것을 세었다

2026-08-05. P05 에서 나는 **"데스크탑도 Django ORM 을 그대로 쓴다"** 고 적었다.
그 판단이 뒤집혔다. 근거 하나가 틀렸기 때문이다.

---

## 1. 먼저 근거 하나를 제자리에 돌려놓는다

*"파이썬이라 `judge.py` 를 한 벌로 유지할 수 있다"* 는 논거를 나는 **두 곳에**
썼다 — GUI 를 고를 때(Electron·Tauri 대신 파이썬)와, ORM 을 고를 때(Django 유지).

**앞은 여전히 맞다.** `judge.py` 는 파이썬이고, JS 로 다시 구현하면 판정이 두 벌이 된다.

**뒤는 틀렸다. 세어 보니 `judge.py` 는 ORM 을 한 줄도 쓰지 않는다.**

| 파일 | ORM 호출 자리 |
|---|---|
| **`judge.py`** | **0** |
| `web/viewer/data.py` | 58 |
| `segment_diatoms.py` | 16 |
| `refilter.py` | 8 |
| `focus_stack.py` | 5 |

`judge.py` 는 값을 받아 판정만 하는 순수 함수 묶음이다(그래서 torch 없이도 돈다).
**ORM 이 무엇이든 그대로 간다** — GUI 만 파이썬이면 된다. **ORM 선택과는 무관하다.**

그러면 Django 를 유지할 이유는 "**`models.py` 의 제약을 잃지 않는다**" 하나만
남는다. 그런데 그것은 **제약을 옮기면 되는 문제**이지 Django 를 통째로 얼려야 할
이유는 아니다 — 다만 **옮길 것이 무엇인지 세어 본 적이 없다는 것이 진짜 문제**였다.
이 문서의 나머지가 그 셈이다. 반대편에는 PyInstaller + Django 의 까다로움과 부피,
그리고 `Modan2` 에서 쌓은 peewee 경험이 있다.

**peewee 로 간다.**

---

## 2. 그런데 진짜 결정은 ORM 이 아니다

> **같은 `DiaRUGA.db` 파일을 웹(Django)과 앱(peewee)이 **둘 다** 열 수 있어야 하는가?**

**그래야 한다.** 연구소에서 만든 DB 를 앱으로 열어 보고, 밖에서 만든 DB 를
서버로 반입하는 길이 막히면 두 갈래가 영영 갈라진다. 그러면 결론은 하나다.

> **스키마를 옮기지 않는다. peewee 모델을 지금 스키마에 붙인다.**

peewee 로 새 스키마를 설계하는 것이 아니라, `viewer_slide` · `slide_id` 같은
Django 가 만든 이름에 **모델을 바인딩**한다. 스키마의 원본은 **Django 마이그레이션
한 곳**으로 유지한다(지금 18개). 앱은 그것을 **따라간다.**

---

## 3. 옮길 때 잃기 쉬운 것 — 실제 스키마에서 센 목록

추측이 아니라 운영 DB 의 `sqlite_master` 에서 뽑았다.

### 3.1 이름 붙은 유일 제약 6개 + OneToOne 1개

| 제약 이름 | 표 | 칼럼 |
|---|---|---|
| `uniq_frame_name` | frame | (slide_id, name) |
| `uniq_viewpoint_idx` | viewpoint | (slide_id, idx) |
| `uniq_objreview_key` | objectreview | **(viewpoint_id, mask_key)** |
| `uniq_candidate_key` | candidate | (detection_id, mask_key) |
| `uniq_core_code` | core | (site_id, code) |
| `uniq_batch_label` | runbatch | (kind, label) |
| (이름 없음) | viewpointreview | viewpoint_id UNIQUE |

**`uniq_frame_name` 은 이 프로젝트가 실제로 당한 사고를 막는 것이다** — 프레임
이름이 슬라이드끼리 겹친다(카메라 일련번호라 같은 날 이어 찍으면 번호대가
이어진다. 260803 두 슬라이드에서 143종). **`uniq_objreview_key` 는 사람의 교정이
중복으로 들어가는 것을 막는 마지막 방어선이다.**

**함정.** Django 는 이것들을 `CREATE TABLE` 안의 `CONSTRAINT … UNIQUE (…)` 로
만든다. **peewee 는 `Meta.indexes` 로 선언하면 별도 `CREATE UNIQUE INDEX` 를
만든다.** 강제하는 효과는 같지만 **스키마 텍스트가 달라진다** — 그래서 아래 5절의
동등성 시험이 "글자 비교" 여서는 안 된다.

### 3.2 JSON 유효성 CHECK 6개

`CHECK ((JSON_VALID("geom") OR "geom" IS NULL))` 이 여섯 칼럼에 걸려 있다 —
`run.params` · `run.counts` · `setting.value` · `candidate.polygon` ·
**`objectreview.geom`** · `frame.meta`.

Django `JSONField` 가 자동으로 붙인 것이다. **peewee 의 JSON 필드는 안 붙인다.**
직접 `constraints=[Check('JSON_VALID(geom) OR geom IS NULL')]` 을 써야 한다.

**`objectreview.geom` 은 특히 중요하다.** 교정이 `Candidate` FK 가 아니라 기하를
스스로 들고 있어야 검출기가 바뀌어도 읽힌다는 것이 이 스키마의 뼈대다(P02).
거기 깨진 JSON 이 들어가면 **재생성 불가한 자료가 조용히 못 읽는 상태**가 된다.

### 3.3 DB 기본값 2개 — **이 프로젝트가 이미 당했다**

| 표 | 칼럼 | 기본값 |
|---|---|---|
| `viewer_site` | `area` | `'ant'` |
| `viewer_slide` | `sample_kind` | `'core'` |

`NOT NULL` 칸을 더할 때 Django 의 `default`(파이썬 쪽)만 주면 **판이 다른 옛
이미지의 INSERT 에 칼럼이 안 들어가서** NAS 반입이 죽는다 — 그래서 `db_default`
를 함께 준 자리다. **peewee 의 `default=` 도 파이썬 쪽이다.** DB 기본값은
`constraints=[SQL("DEFAULT 'ant'")]` 로 따로 줘야 한다.

**웹과 앱이 같은 파일을 쓰는 이상 이 사고가 그대로 재현될 수 있다.**

### 3.4 외래키 — 여기가 가장 미묘하다

DB 안의 FK 21개가 **전부 `on_delete=NO ACTION`** 이고
`DEFERRABLE INITIALLY DEFERRED` 다. **`ON DELETE CASCADE` 가 스키마에 없다.**

Django 는 `on_delete=CASCADE` 를 **파이썬에서 흉내 낸다** — 지울 때 관련 행을
찾아 직접 지운다. DB 에 맡기지 않는다.

**peewee 는 반대다. DB 에 맡긴다.** 그래서:

- peewee 모델에 `on_delete='CASCADE'` 를 적으면 **스키마가 달라진다**
  (같은 파일을 웹과 나눠 쓰는 전제가 깨진다)
- 적지 않으면 **연쇄 삭제가 아예 안 일어난다.** 시야를 지웠는데 그 아래 검출·
  교정이 남는다 — **고아가 조용히 쌓인다**
- 게다가 SQLite 는 `PRAGMA foreign_keys` 가 **기본 꺼짐**이다(방금 확인:
  새 연결에서 `0`). Django 는 연결할 때마다 켜 준다. **peewee 쪽도 켜야 한다**

> **결론: 앱에서는 연쇄 삭제를 DB 에 맡기지 말고 파이썬에서 명시적으로 지운다.**
> Django 와 같은 방식이 되고, 스키마도 그대로 유지된다. 지우는 코드가 한 곳에
> 모이므로 **"교정까지 같이 지워지는가" 를 시험으로 붙잡을 수 있다.**

### 3.5 auto_now / auto_now_add

`updated_at` 계열이 Django 의 `auto_now` 로 자동 갱신된다
(`objectreview` · `viewpointreview` · `frame`). **peewee 에는 이 기능이 없다.**
`save()` 를 감싸거나 시그널로 직접 넣어야 한다.

**빠뜨리면 예외가 안 난다.** `updated_at` 이 멈춘 채로 계속 돌고, 나중에
"언제 고친 교정인가" 를 물을 때 답이 없다.

### 3.6 그 밖

- `AUTOINCREMENT` (단순 `INTEGER PRIMARY KEY` 와 다르다 — 재사용 안 함)
- `DEFERRABLE INITIALLY DEFERRED`
- `django_migrations` 표 — 앱이 이 표를 **건드리면 안 된다.** 읽어서 "이 DB 가
  어느 판인가" 를 판단하는 용도로만 쓴다

---

## 4. 두 ORM 이 같은 파일을 볼 때의 규칙

- **스키마를 바꿀 권한은 Django(서버) 쪽에만 둔다.** 앱이 스키마를 바꾸면
  서버가 못 읽는다
- **앱은 DB 판을 확인하고, 모르는 판이면 열지 않는다.** `django_migrations` 의
  마지막 이름을 보고 "이 앱이 아는 판보다 새롭다" 면 **읽기 전용으로 열거나
  거부한다.** 조용히 열어서 새 칼럼을 무시하는 것이 가장 나쁘다
- **WAL 은 그대로 쓴다.** 데스크탑은 혼자 쓰므로 동시 쓰기 문제가 없다
- `PRAGMA foreign_keys=ON` 을 앱 연결에서도 켠다 (Django 와 같게)

---

## 5. 안전장치 — 스키마 동등성 시험

**이 이식에서 유일하게 믿을 수 있는 것은 시험이다.** 사람이 표 15개 ×
칼럼 수십 개를 눈으로 맞출 수는 없다.

```
Django migrate 로 만든 빈 DB   ─┐
                                ├→ 스키마를 정규화해서 비교 → 다르면 실패
peewee 로 만든 빈 DB           ─┘
```

**정규화가 핵심이다.** 3.1 에서 봤듯 같은 제약도 표현이 다를 수 있으므로,
글자 비교가 아니라 **의미 비교**여야 한다:

| 무엇을 | 어떻게 |
|---|---|
| 표·칼럼·형·NULL 여부 | `PRAGMA table_info` |
| 유일 제약 | **테이블 제약이든 인덱스든 모아서 `(표, 칼럼 집합)` 으로 비교** |
| 외래키 | `PRAGMA foreign_key_list` — 대상·`on_delete` 까지 |
| CHECK | `sqlite_master` 에서 뽑아 정규화 |
| DB 기본값 | `PRAGMA table_info` 의 `dflt_value` |

그리고 **왕복 시험**을 붙인다 — 앱으로 교정한 DB 를 `check_db.py` 에 통과시키고,
웹 뷰어로 열어 같은 교정이 보이는지 본다. 반대 방향도 같다.
**이 두 시험이 CI 에 있으면 이식이 안전해지고, 없으면 안 된다.**

### 만들었다 — `tools/schema_diff.py`

```bash
python tools/schema_diff.py A.db B.db              # 견준다 (다르면 종료코드 1)
python tools/schema_diff.py --dump db -o ref.json  # 기준 지문을 뜬다
python tools/schema_diff.py ref.json B.db          # 지문과 견준다 (Django 불필요)
```

stdlib 만 쓴다. 시험해 확인한 것:

| 시험 | 결과 |
|---|---|
| 운영 DB ↔ 자기 자신 | 같다 |
| **운영 DB ↔ 마이그레이션으로 새로 만든 빈 DB** | **같다** — 운영 스키마가 마이그레이션과 어긋나지 않았다 |
| 일부러 유일 제약·CHECK·기본값·FK 규칙을 망가뜨린 사본 | **4건 전부 잡았다** |
| `bigint` → `integer` (친화도 같음) | **경고만** — 실패로 세지 않는다 |

정규화가 실제로 필요했다는 증거가 마지막 줄이다. 그리고 유일 제약은 **테이블
제약이든 별도 인덱스든 한 자루에 담아** `(표, 칼럼 집합)` 으로 견준다 — 이름은
무시하고 보고에만 적는다.

---

## 6. 마이그레이션 — 양쪽에 필요하다

정직하게, **여기에는 중복이 생긴다.** 피할 방법을 못 찾았다.
**스키마가 바뀌면 Django 쪽과 peewee 쪽 둘 다 이행 스크립트가 필요하다.**

- **처음 한 번은 지금 스키마로 squash 한다.** 18개를 옮기지 않는다. 앱의
  이행 이력은 "현재 스키마" 에서 시작하고, **그 뒤로만 나란히 간다**
- **새 DB 를 만들 때**는 peewee 로 만들고 5절 시험으로 확인한다
- **쓰던 DB 를 올릴 때**는 `peewee-migrate` (`Modan2` 가 쓰는 것)

### 절차

```bash
# 1) 스키마의 원본은 Django 마이그레이션이다
python web/manage.py makemigrations && python web/manage.py migrate

# 2) 빈 DB 에 적용해 기준 지문을 다시 뜬다 (운영 DB 를 쓰지 않는다)
DIARUGA_DB=/tmp/fresh.db python web/manage.py migrate
python tools/schema_diff.py --dump /tmp/fresh.db -o docs/schema-reference.json

# 3) peewee 쪽 이행을 쓴 뒤, 만든 DB 를 지문과 견준다
python tools/schema_diff.py docs/schema-reference.json build/peewee.db
```

**지문(`docs/schema-reference.json`)을 저장소에 두는 이유**는 3번을 **Django 없이**
돌릴 수 있게 하기 위해서다. 데스크탑 쪽 CI 에 Django 를 깔지 않아도 된다.

### DB 를 공유하지 않는 경우

개별 연구자가 자기 자료만 데스크탑에서 쓰고 **웹과 DB 를 주고받지 않을** 수도
있다. 그러면 스키마가 글자까지 같아야 할 이유는 약해지고, **데스크탑만 이행하면
된다.** 앱이 자기 표(설정·최근 폴더 같은)를 더하는 것도 자연스럽다.

그럴 때를 위해 `--allow-extra` 를 뒀다 — **B 가 더 가진 것은 넘어가고, 잃은 것만
실패한다.** 다만 **바뀐 것은 더한 것이 아니다**: 형·NOT NULL·기본값이 다르거나
외래키 규칙이 달라지면 이 모드에서도 잡힌다.

> **그래도 스키마는 최대한 공용으로 간다.** 공유하지 않더라도 값이 있다 —
> `data.py`·`segment_diatoms.py`·`refilter.py` 를 두 쪽이 함께 쓰고, 사용자가
> 보내온 DB 를 우리 도구로 열어 볼 수 있고, 나중에 반입이 필요해졌을 때 길이
> 열려 있다. **`--allow-extra` 는 기본이 아니라 비상구다.**

---

## 7. 이식 순서

1. **`desktop/models_peewee.py`** — 지금 스키마에 바인딩. 3절의 일곱 항목을
   하나씩 옮긴다
2. **스키마 동등성 시험** — 여기서 빠진 제약이 드러난다. **1번보다 이것이 먼저
   끝나야 다음으로 간다**
3. **읽기 경로부터** — `data.py` 의 58개 호출 중 읽기만 먼저. P05 1단계가
   읽기 전용인 것과 맞는다
4. **쓰기 경로** — 교정 저장. 연쇄 삭제를 파이썬으로 명시(3.4)
5. **왕복 시험** — 앱 ↔ 웹

---

## 8. P05 를 고친다

P05 의 "새로 정하는 것 2. Django ORM 을 그대로 쓴다" 를 **"peewee 로 옮기되
스키마는 지금 것에 붙인다"** 로 바꾼다. 1단계 완료 기준에 있던
"PyInstaller + Django 가 얼려지는가" 는 **"스키마 동등성 시험이 통과하는가"** 로
바뀐다 — 계획이 흔들릴 수 있는 자리를 가장 먼저 부딪히게 한다는 뜻은 같다.
