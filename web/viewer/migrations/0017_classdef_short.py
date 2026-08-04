"""자리가 좁은 곳에서 쓸 약칭을 표에 넣는다.

속명은 길다. `Chaetoceros` 는 목록 표의 열 하나를 두 배로 넓히고, 검출 화면
머리의 개수 줄을 한 줄 더 밀어낸다. `CRS` 로 줄인다.

**비어 있으면 `label` 을 그대로 쓴다** — 짧은 이름(원형·봉상)에는 약칭이
필요 없고, 없다고 화면이 비지 않아야 한다.

Eucampia 는 두지 않았다. 지금 자리에 들어가고, 줄일 이름이 늘수록 화면에서
무엇을 보는지가 흐려진다. 필요해지면 표에서 채우면 된다.
"""
from django.db import migrations, models


def assign(apps, schema_editor):
    apps.get_model("viewer", "ClassDef").objects.filter(
        key="chaetoceros").update(short="CRS")


def clear(apps, schema_editor):
    apps.get_model("viewer", "ClassDef").objects.update(short="")


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0016_classdef_hotkey"),
    ]

    operations = [
        migrations.AddField(
            model_name="classdef",
            name="short",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.RunPython(assign, clear),
    ]
