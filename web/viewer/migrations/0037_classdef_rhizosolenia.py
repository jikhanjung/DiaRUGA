"""분류에 Rhizosolenia 를 더한다 — Eucampia·Chaetoceros 와 같은 층(속)이다.

**지금까지 봉상(`rod`)으로만 갈라 왔다.** 형태 칸에 들어가 있던 것을 속으로
빼내는 것이라, **이미 붙은 교정은 안 건드린다** — 봉상으로 적어 둔 것을 기계가
Rhizosolenia 로 옮기면 사람이 안 한 판단이 사람의 판단으로 앉는다. 옮기는 것은
검토 화면에서 사람이 한다.

`0014`(Chaetoceros)와 같은 자리다. **마이그레이션으로 넣는 이유는 배포마다 같은
상태가 되어야 하기 때문이다** — 손으로 INSERT 하면 운영 DB 에만 있고 새로 만든
DB(시험·복구)에는 없다.

**행 하나로 안 끝난다** (`ClassDef` 머리말 · 038·040). 여덟 칸을 다 채우고
`base.html` 의 CSS **여덟 자리**도 함께 간다 — 색은 아직 표에서 뿜어내지 않는다.

    배지 · 타일 폴리곤 · 시야 폴리곤 · 크롭 테두리 · 검토 폴리곤 ·
    윤곽만 보기 · 상자 테두리 · 상자 감추기

색은 **남은 색 중 쓰이는 것들과 가장 멀다.** 분류가 쓰는 색상(초록 145 ·
연초록 · 파랑 217 · 연파랑 · 분홍 327 · 연두 90)에 화면 색(빨강 0 · 주황 36 ·
초록 130 · 하늘 197)까지 놓고 보면 **파랑과 분홍 사이 108° 가 가장 큰 빈자리**이고
그 한가운데가 보라 266° 다.

단축키는 `t` — `q`·`w`·`e`·`r` 다음 자리다. `d`(그리기)·스페이스(삭제)·
화살표(이동)와 겹치지 않는다.
"""
from django.db import migrations

ROW = {
    "key": "rhizosolenia",
    "label": "Rhizosolenia",
    # 속명이 길다. `Chaetoceros` → `CRS` 와 같은 모양으로 줄인다 — 안 줄이면
    # 목록 표의 열이 넓어지고 검출 화면 머리의 개수 줄이 밀린다 (0017).
    "short": "RHZ",
    "badge": "rhi",
    "color": "185,130,255",
    "hotkey": "t",
    "is_taxon": True,
    "counted": True,
    "sort_order": 6,
    "active": True,
}


def add(apps, schema_editor):
    apps.get_model("viewer", "ClassDef").objects.update_or_create(
        key=ROW["key"], defaults=ROW)


def remove(apps, schema_editor):
    """되돌리면 행을 지우는 것이 아니라 끈다 (`0014` 와 같다).

    지운 뒤에 그 분류로 붙인 교정이 남아 있으면 화면에서 이름 없는 분류가 된다.
    `active=False` 면 메뉴·집계에서 빠지되 붙은 교정은 읽힌다.
    """
    apps.get_model("viewer", "ClassDef").objects.filter(
        key=ROW["key"]).update(active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0036_note_to_object"),
    ]

    operations = [migrations.RunPython(add, remove)]
