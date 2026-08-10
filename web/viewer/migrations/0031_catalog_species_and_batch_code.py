"""개체 카탈로그가 쓸 두 칸 (2026-08-10).

`ObjectReview.species` — 사람이 적는 종명. **재생성 불가다.**
`RunBatch.code` — 카탈로그 번호의 꼬리 (`RS23-GC03-071-g03-…-S1` 의 `S1`).

**넓히기만 한다 — 조이는 것이 없다.** 두 칼럼 다 `db_default` 를 들고 들어가므로
**옛 파이프라인 이미지의 INSERT 가 이 칼럼을 안 실어도 죽지 않는다**(뷰어와
파이프라인은 판이 따로 돈다 — HANDOFF 3.7). 그래서 이 판은 뷰어만 올려도 된다.

`reverse` 는 칼럼을 걷는다 — **그러면 적어 둔 종명이 사라진다.** 되돌릴 일이
생기면 `ops/backup_db.py` 사본이 먼저다. 배포를 되돌릴 때 빈 화면이 나오면 안
되므로 reverse 를 적어 두기는 하지만, 자료가 든 뒤에 쓰는 것은 다른 이야기다.
"""
from django.db import migrations, models

# 지금 있는 두 묶음의 코드. **여기서 한 번만 넣는다** — 뒤로는 사람이 관리 화면에서
# 정한다. 자동으로 뽑으면 `yolo-3차`·`yolo-4차` 가 같은 글자로 눕고, 그때는 이미
# 번호가 논문·표에 적힌 뒤다 (`RunBatch.code` 머리말).
SEED_CODES = {"sam2-전수": "S1", "yolo-3차": "Y3"}


def seed_codes(apps, schema_editor):
    """빈 코드만 채운다. **이미 정해진 것은 안 건드린다** — 자동값이 사람이 넣은
    것을 덮으면 안 된다 (063 에서 `core`·`depth_cm` 로 당한 그 자리다)."""
    RunBatch = apps.get_model("viewer", "RunBatch")
    for label, code in SEED_CODES.items():
        RunBatch.objects.filter(label=label, code="").update(code=code)


def clear_codes(apps, schema_editor):
    """되돌릴 때는 이 마이그레이션이 넣은 것만 뺀다."""
    RunBatch = apps.get_model("viewer", "RunBatch")
    for label, code in SEED_CODES.items():
        RunBatch.objects.filter(label=label, code=code).update(code="")


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0030_objectlink_objectlinkmember_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='objectreview',
            name='species',
            field=models.CharField(blank=True, db_default='', default='', max_length=120),
        ),
        migrations.AddField(
            model_name='runbatch',
            name='code',
            field=models.CharField(blank=True, db_default='', default='', max_length=8),
        ),
        migrations.AddConstraint(
            model_name='runbatch',
            constraint=models.UniqueConstraint(condition=models.Q(('code', ''), _negated=True), fields=('code',), name='uniq_batch_code'),
        ),
        migrations.AddConstraint(
            model_name='runbatch',
            constraint=models.CheckConstraint(condition=models.Q(('code__in', ['M', 'm']), _negated=True), name='batch_code_not_manual'),
        ),
        # **제약을 세운 뒤에 채운다.** 반대 순서면 유일 제약이 걸릴 때 이미 겹친
        # 값이 앉아 있을 수 있고, 그때는 마이그레이션이 배포 한가운데서 선다.
        migrations.RunPython(seed_codes, clear_codes),
    ]
