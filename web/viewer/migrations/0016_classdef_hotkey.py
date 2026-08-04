"""검토 화면의 분류 단축키를 표에 넣는다.

    q → 원형 → 원형 파편 → 원형 …      w → 봉상 → 봉상 파편 → 봉상 …
    e → Eucampia                        r → Chaetoceros

**본체와 파편이 같은 키를 나눠 가진다.** 손가락은 한 자리에 두고 누른 횟수로
온전한 것과 깨진 것을 가른다 — 039 에서 색을 그렇게 묶었으니 조작도 같은
모양이어야 한다. 순환 차례는 `sort_order` 다.

키는 q·w·e·r 로 붙였다. 왼손이 안 움직이고, 화살표(사진·시야 이동)·Ctrl+Z
(실행취소)·Esc(닫기)와 겹치지 않는다.
"""
from django.db import migrations, models

KEYS = {
    "round": "q", "round_frag": "q",
    "rod": "w", "rod_frag": "w",
    "eucampia": "e",
    "chaetoceros": "r",
}


def assign(apps, schema_editor):
    model = apps.get_model("viewer", "ClassDef")
    for key, hot in KEYS.items():
        model.objects.filter(key=key).update(hotkey=hot)


def clear(apps, schema_editor):
    apps.get_model("viewer", "ClassDef").objects.update(hotkey="")


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0015_fragment_family_colors"),
    ]

    operations = [
        migrations.AddField(
            model_name="classdef",
            name="hotkey",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.RunPython(assign, clear),
    ]
