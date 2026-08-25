"""개체에 **앵커**를 단다 — 카탈로그 번호를 어느 판정에서 뽑을지 (P18).

카드 하나가 개체 하나가 되면서 필요해진 칸이다. 번호는 계속 파생이고
(`catalog.py` 의 "저장하지 않는다"), 저장하는 것은 **재료를 어디서 가져올까**다.

## 채우기 — 가장 오래된 멤버

그 개체가 선 순서가 곧 판정이 생긴 순서다. 가장 오래된 것을 앵커로 두면
**나중에 무엇을 묶어 넣어도 안 움직인다** — `test_묶어도_번호가_그대로다` 가
지키는 그 성질이다.

**`pk` 로 고른다.** `created_at` 은 같은 초에 여럿이 생겨 순서가 안 갈리는데
(한 시야를 저장하면 판정이 수십 개 한꺼번에 선다), `pk` 는 언제나 갈린다.

## 되돌리기

칸을 걷는 것으로 끝난다 — 파생 번호는 앵커가 없으면 예전처럼 판정마다 나온다.
**되돌릴 수 있어야 한다**: 배포가 막혀 판을 되돌릴 때 화면이 비면 안 된다 (063).
"""
import django.db.models.deletion
from django.db import migrations, models


def fill(apps, schema_editor):
    """개체마다 가장 오래된 멤버를 앵커로."""
    DiatomObject = apps.get_model("viewer", "DiatomObject")
    ObjectReview = apps.get_model("viewer", "ObjectReview")

    # **개체마다 되묻지 않는다** — 운영에 개체가 만 단위다(실측 `yolo-3차` 3,044 ·
    # `sam2-전수` 7,725). 판정을 한 번 훑으며 개체별 최소 pk 를 모은다.
    first = {}
    for pk, obj_id in ObjectReview.objects.order_by("pk").values_list(
            "pk", "diatom_object_id").iterator():
        if obj_id is not None and obj_id not in first:
            first[obj_id] = pk
    if not first:
        return

    rows = []
    for obj in DiatomObject.objects.only("id").iterator():
        anchor = first.get(obj.pk)
        if anchor is None:
            continue                     # 멤버 없는 유령 — check_db 가 센다
        obj.anchor_id = anchor
        rows.append(obj)
    DiatomObject.objects.bulk_update(rows, ["anchor"], batch_size=500)


def unfill(apps, schema_editor):
    """칸을 걷기 전에 비운다 — 되돌리기가 자료를 안 남기게."""
    apps.get_model("viewer", "DiatomObject").objects.update(anchor=None)


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0039_core_series'),
    ]

    operations = [
        migrations.AddField(
            model_name='diatomobject',
            name='anchor',
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='anchor_of',
                                    to='viewer.objectreview'),
        ),
        migrations.RunPython(fill, unfill),
    ]
