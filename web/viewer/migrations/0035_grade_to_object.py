"""등급을 판정에서 개체로 옮긴다 (2026-08-12 사용자 · 111).

`0034` 로 넣은 지 하루 만에 뒤집는다. 근거는 `DiatomObject.grade` 머리말에
적었다 — **"어느 판이 잘 보이는가" 는 `is_rep`(대표)이 이미 하고 있었다.**

**지금이 가장 싸다.** 운영에 등급이 **0건**이고 `v0.11.2` 도 아직 안 나갔다.
값이 쌓인 뒤였으면 판마다 다른 등급을 하나로 접는 규칙을 사람이 정해야 했다.

순서를 지킨다 — **새 칸 → `RunPython` 으로 자료 이동 → 옛 칸 걷기.** 자동 생성이
내는 순서(옛 칸을 먼저 지우고 새 칸을 빈 채로 만든다)를 그대로 돌리면 사람이
매긴 것이 날아간다(063 에서 `Core` → `Locality` 로 겪을 뻔했다). `reverse` 도
함께 적는다 — 배포가 막혀 판을 되돌릴 때 빈 화면이 나오면 안 된다.
"""
from django.db import migrations, models


def to_object(apps, schema_editor):
    """판정의 등급을 그 개체로 올린다.

    **판마다 다르면 대표의 것을 쓴다.** 개체가 값을 하나만 들 수 있어 고를
    수밖에 없고, 대표는 *이 규조각을 어느 판으로 보는가* 라서 그 판의 판단이
    개체를 대표하기에 가장 가깝다. 대표가 없으면 아무거나 집지 않고 **먼저
    적힌 것**을 쓴다 — 순서를 못 박아야 다시 돌려도 같은 결과가 난다.

    (실제로는 운영에 0건이라 아무 행도 안 옮긴다. 그래도 적는 이유는 시험
    DB·개발 사본에는 값이 있을 수 있어서다.)
    """
    ObjectReview = apps.get_model("viewer", "ObjectReview")
    DiatomObject = apps.get_model("viewer", "DiatomObject")
    seen = {}
    for r in (ObjectReview.objects.exclude(grade="")
              .order_by("-is_rep", "pk")
              .values_list("diatom_object_id", "grade")):
        seen.setdefault(r[0], r[1])
    for oid, grade in seen.items():
        DiatomObject.objects.filter(pk=oid).update(grade=grade)


def to_judgement(apps, schema_editor):
    """되돌리기 — 개체의 등급을 그 개체의 **모든** 판정에 적는다.

    올릴 때 잃은 것(판마다 달랐던 값)은 되살릴 수 없다. 그래도 대표에만 적으면
    되돌린 화면에서 나머지 판이 빈 칸으로 보여 **사람이 지워진 줄 안다** —
    되돌리기의 목적은 옛 판이 멀쩡히 도는 것이다.
    """
    ObjectReview = apps.get_model("viewer", "ObjectReview")
    DiatomObject = apps.get_model("viewer", "DiatomObject")
    for oid, grade in (DiatomObject.objects.exclude(grade="")
                       .values_list("pk", "grade")):
        ObjectReview.objects.filter(diatom_object_id=oid).update(grade=grade)


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0034_grade_and_pose'),
    ]

    operations = [
        migrations.AddField(
            model_name='diatomobject',
            name='grade',
            field=models.CharField(blank=True, choices=[('A', 'A — 동정키도 완형도 잘 드러난다'), ('B', 'B — 완형이나 형태가 덜 드러난다 · 또는 상태가 나쁘나 동정키가 남았다'), ('C', 'C — 완형도 동정키도 잘 안 드러난다')], db_default='', default='', max_length=1),
        ),
        migrations.RunPython(to_object, to_judgement),
        migrations.RemoveField(
            model_name='objectreview',
            name='grade',
        ),
    ]
