"""분류에 Chaetoceros 를 더한다 — Eucampia 와 같은 층(속)이다.

`ClassDef` 를 표로 둔 값을 처음으로 쓰는 자리다. 마이그레이션으로 넣는 이유는
**배포마다 같은 상태가 되어야 하기 때문이다** — 손으로 INSERT 하면 운영 DB 에만
있고 새로 만든 DB(시험·복구)에는 없다.

색은 표에 적어 두지만 지금은 CSS 가 키로 색을 잡는다(base.html). 그래서 이
행 하나로 끝나지 않고 CSS 도 함께 갔다 — 037 참고.
"""
from django.db import migrations

ROW = {
    "key": "chaetoceros",
    "label": "Chaetoceros",
    "badge": "cha",
    # 남은 색 중 쓰이는 것들과 가장 멀다(색상환 90°). 파랑 217·초록 150·
    # 청록 180·보라 258·분홍 325·주황 36·빨강 0·노랑 51 사이의 빈자리다.
    "color": "150,225,75",
    "is_taxon": True,
    "counted": True,
    "sort_order": 5,
    "active": True,
}


def add(apps, schema_editor):
    apps.get_model("viewer", "ClassDef").objects.update_or_create(
        key=ROW["key"], defaults=ROW)


def remove(apps, schema_editor):
    """되돌리면 행을 지우는 것이 아니라 끈다.

    지운 뒤에 그 분류로 붙인 교정이 남아 있으면 화면에서 이름 없는 분류가 된다.
    `active=False` 면 메뉴·집계에서 빠지되 붙은 교정은 읽힌다.
    """
    apps.get_model("viewer", "ClassDef").objects.filter(
        key=ROW["key"]).update(active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0013_classdef_counted"),
    ]

    operations = [migrations.RunPython(add, remove)]
