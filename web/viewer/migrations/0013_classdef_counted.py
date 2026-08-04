"""분류에 "개체 수로 세는가" 를 붙인다.

파편은 개체가 아니다. 기존 행 중 `rod_frag`·`round_frag` 만 False 로 내리고
나머지는 기본값(True)을 그대로 둔다 — 키로 찾는 것은 이 한 번뿐이고, 앞으로
분류가 늘면 표에서 끄면 된다.
"""
from django.db import migrations, models

FRAGMENTS = ("rod_frag", "round_frag")


def uncount_fragments(apps, schema_editor):
    apps.get_model("viewer", "ClassDef").objects.filter(
        key__in=FRAGMENTS).update(counted=False)


def recount_fragments(apps, schema_editor):
    apps.get_model("viewer", "ClassDef").objects.filter(
        key__in=FRAGMENTS).update(counted=True)


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0012_frame_created_at_frame_updated_at_slide_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="classdef",
            name="counted",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(uncount_fragments, recount_fragments),
    ]
