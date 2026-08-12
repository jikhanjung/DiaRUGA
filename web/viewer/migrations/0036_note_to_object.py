"""코멘트를 판정에서 개체로 옮긴다 (2026-08-12 사용자 · 112).

`0035`(등급)와 **같은 이야기의 나머지 반쪽이다.** 근거는 `DiatomObject.note`
머리말에 적었다 — 사람이 실제로 적은 말이 *그 규조각에 대한 말*이었고
("가장자리가 깨졌다"), 번지기(106)가 들어오면서 같은 말을 판 넷에 네 번 적게
됐다.

**`DiatomObject.note` 는 이미 있었다** — `ObjectLink.note`("묶음에 대한 메모")가
0032 로 따라온 칸인데 **아무도 읽지도 쓰지도 않았다.** 그래서 새 칸을 세우지
않고 그 자리를 넓혀 쓴다(`CharField(200)` → `TextField`): 화면 상한이 500자
(`views.NOTE_MAX`)라 200 으로는 잘리고, 아래에서 이을 때 그보다 길어진다.

순서를 지킨다 — **칸을 넓히고 → `RunPython` 으로 자료 이동 → 옛 칸 걷기.**
자동 생성이 내는 순서(옛 칸을 먼저 지운다)를 그대로 돌리면 사람이 적은 글이
날아간다(063 에서 `Core` → `Locality` 로 겪을 뻔했다). `reverse` 도 함께 적는다
— 배포가 막혀 판을 되돌릴 때 빈 화면이 나오면 안 된다.

**등급과 달리 값을 안 버린다.** 등급은 판마다 다르면 대표의 것을 골랐다(글자
하나이고 운영에 0건이었다). 코멘트는 **사람이 쓴 글이라 재생성 불가**이고, 판
셋에 다른 말이 적혀 있으면 그 셋이 전부 이 규조각에 대한 사실이다 — 고르면
둘을 버린다. 그래서 **이어 붙인다.**
"""
from django.db import migrations, models


def _joined(notes) -> str:
    """여러 판의 코멘트를 한 글로 잇는다. 같은 말은 한 번만.

    **순서를 못 박는다** — 대표 먼저, 그다음 적힌 차례(pk). 다시 돌려도 같은
    결과가 나야 두 DB 를 비교하는 감사 기록(`export_review.py`)이 거짓말을 안
    한다.
    """
    out = []
    for n in notes:
        n = (n or "").strip()
        if n and n not in out:
            out.append(n)
    return "\n".join(out)


def to_object(apps, schema_editor):
    """판정의 코멘트를 그 개체로 올린다. **버리지 않고 잇는다.**"""
    ObjectReview = apps.get_model("viewer", "ObjectReview")
    DiatomObject = apps.get_model("viewer", "DiatomObject")
    seen = {}
    for oid, note in (ObjectReview.objects.exclude(note="")
                      .order_by("-is_rep", "pk")
                      .values_list("diatom_object_id", "note")):
        seen.setdefault(oid, []).append(note)
    for oid, notes in seen.items():
        # **개체에 이미 적힌 것을 앞에 둔다.** 지금은 늘 비어 있지만(아무도 안
        # 쓰던 칸이다), 비었다고 단정하고 덮으면 개발 사본에서 조용히 지운다.
        obj = DiatomObject.objects.filter(pk=oid).first()
        if obj is None:
            continue
        joined = _joined([obj.note] + notes)
        if joined != obj.note:
            DiatomObject.objects.filter(pk=oid).update(note=joined)


def to_judgement(apps, schema_editor):
    """되돌리기 — 개체의 코멘트를 그 개체의 **모든** 판정에 적는다.

    올릴 때 잃은 것(어느 판이 어느 문장을 적었는가)은 되살릴 수 없다. 그래도
    대표에만 적으면 되돌린 화면에서 나머지 판이 빈 칸으로 보여 **사람이 지워진
    줄 안다** — 되돌리기의 목적은 옛 판이 멀쩡히 도는 것이다 (0035 와 같다).

    **개체의 것은 안 지운다.** 옛 판에서 `DiatomObject.note` 는 아무도 안 읽는
    칸이라 남아 있어도 화면이 달라지지 않고, 다시 앞으로 갈 때 그 값이 필요하다.
    """
    ObjectReview = apps.get_model("viewer", "ObjectReview")
    DiatomObject = apps.get_model("viewer", "DiatomObject")
    for oid, note in (DiatomObject.objects.exclude(note="")
                      .values_list("pk", "note")):
        ObjectReview.objects.filter(diatom_object_id=oid).update(note=note)


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0035_grade_to_object'),
    ]

    operations = [
        migrations.AlterField(
            model_name='diatomobject',
            name='note',
            field=models.TextField(blank=True, db_default='', default=''),
        ),
        migrations.RunPython(to_object, to_judgement),
        migrations.RemoveField(
            model_name='objectreview',
            name='note',
        ),
    ]
