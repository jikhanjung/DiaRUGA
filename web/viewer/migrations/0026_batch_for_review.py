"""검토 대상 묶음을 **묶음이 스스로 알게** 한다 (P10 0단계).

`RunBatch.for_review` 를 더하고, 지금 화면이 보고 있는 묶음에 켠다.

## 적용해도 아무것도 안 달라 보인다 — 그것이 안전 기준이다

이 이행은 **칼럼 하나를 더하고 깃발 하나를 켜는 것**이 전부다. 읽는 쪽은 아직
`is_current` 만 보므로 화면·집계·파이프라인이 전부 그대로 돈다.

**자료 정규화(묶음마다 이미지별 최신을 `is_current` 로)는 여기서 안 한다.**
지금 `yolo-3차` 의 검출 1,799개는 전부 `is_current=False` 인데, 그것을 여기서
켜 버리면 **읽는 쪽이 아직 `for_review` 를 함께 안 보므로 시야마다 현재 검출이 여럿이 되어
화면이 그 자리에서 깨진다.** 순서는 이렇다:

    0026  깃발을 더한다            ← 여기. 안 달라진다
    (코드) 읽는 쪽이 둘 다 본다     ← 값이 같다 (sam2 이면서 is_current = 508)
    0027  묶음마다 정규화한다       ← 여전히 둘 다 켜진 것은 508

세 걸음 다 **결과가 안 바뀌는 것**을 확인하며 간다.

## 어느 묶음에 켜는가

이름을 박지 않는다 — **지금 현재 검출을 갖고 있는 묶음**을 찾아서 켠다. 시험
DB 처럼 묶음 이름이 다른 곳에서도 같은 코드가 돌아야 한다.
"""
from django.db import migrations, models


def _turn_on(apps, schema_editor):
    """지금 화면이 보고 있는 묶음에 깃발을 켠다."""
    from collections import Counter
    Detection = apps.get_model("viewer", "Detection")
    RunBatch = apps.get_model("viewer", "RunBatch")

    seen = Counter()
    for d in (Detection.objects.filter(is_current=True)
              .select_related("run").only("id", "run__batch_id")):
        if d.run_id and d.run.batch_id:
            seen[d.run.batch_id] += 1

    if not seen:
        print("    현재 검출이 묶음에 하나도 없다 — 켤 것이 없다")
        return
    if len(seen) > 1:
        # **한 묶음이어야 한다.** 둘이면 화면이 이미 섞인 것을 보고 있었다는
        # 뜻이고, 어느 쪽을 검토 대상으로 삼을지 사람이 정해야 한다.
        rows = ", ".join(f"{RunBatch.objects.get(pk=b).label}={n}"
                         for b, n in seen.most_common())
        raise RuntimeError(
            f"현재 검출이 묶음 여럿에 걸쳐 있다 ({rows}) — 어느 것을 검토 "
            f"대상으로 삼을지 정할 수 없다. prune_detections.py 로 정리하거나 "
            f"사람이 골라야 한다.")

    bid, n = seen.most_common(1)[0]
    RunBatch.objects.filter(pk=bid).update(for_review=True)
    print(f"    검토 대상: {RunBatch.objects.get(pk=bid).label} (현재 검출 {n:,}개)")


def _turn_off(apps, schema_editor):
    """되돌리기 — 칼럼이 사라지므로 값은 의미가 없지만, 되돌아간다는 것을 적어 둔다."""
    apps.get_model("viewer", "RunBatch").objects.update(for_review=False)


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0025_review_belongs_to_batch'),
    ]

    operations = [
        migrations.AddField(
            model_name='runbatch',
            name='for_review',
            # **`db_default` 를 함께 준다.** 파이프라인 이미지는 굽는 주기가
            # 달라 판이 같아질 일이 없고, 옛 이미지가 `RunBatch` 를 새로
            # 만들면 이 칼럼을 아예 안 보낸다 (HANDOFF 3.7).
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.RunPython(_turn_on, _turn_off),
        migrations.AddConstraint(
            model_name='runbatch',
            constraint=models.UniqueConstraint(
                condition=models.Q(('for_review', True)),
                fields=('for_review',),
                name='uniq_batch_for_review'),
        ),
    ]
