"""교정이 **어느 검출을 보고 한 판단인지**를 들고 있게 한다 (P09 0단계).

`ObjectReview` 에 셋을 더한다.

- **`batch`** — 열쇠에 들어간다. `(image, mask_key)` 였던 유일 제약이
  `(image, batch, mask_key)` 가 된다
- `source` — 사람이 그린 개체인가 (`engine` | `manual`)
- `geom_edited` — 엔진이 낸 기하를 사람이 고쳤는가

## 왜 지금인가

`yolo-3차` 를 current 로 올리기 **전에** 끝나 있어야 한다. 없이 전환하면
`rebind` 가 SAM2 시절의 판단을 YOLO 검출에 IoU 로 옮겨 붙이고, 그것은
되돌릴 수 없다 — 실측(P09 4.4)으로 **`removed` 1,076건이 YOLO 의 통과 후보에
얹힌다.** 사람은 자기가 지우지 않은 것이 지워져 있는 것을 보게 된다.

## 제약이 둘인 이유

**SQLite 는 NULL 끼리 부딪히지 않는다고 본다.** 사람이 그린 개체는 `batch` 가
NULL 이라 `(image, batch, mask_key)` 제약이 **안 잡는다** — 같은 키가 여럿 설 수
있다. 조건을 뒤집은 부분 제약(`uniq_objreview_manual`)을 따로 둔다.

## 되돌릴 수 있는가

**칼럼을 더하기만 한다 — 되돌아간다.** 옛 판의 뷰어는 `batch` 를 모르는 채로
돌고, 유일 제약만 옛 것으로 돌아온다. 다만 되돌린 뒤에 **다른 batch 의 교정이
같은 `(image, mask_key)` 로 둘 이상 있으면 제약을 다시 세우지 못한다** — 그때는
전환을 한 뒤이므로, 되돌리려면 새 batch 의 교정을 먼저 걷어야 한다. 아래
`_unfill` 이 그 상태를 **말로 알려 준다**(SQLite 가 내는 말로는 어느 행이
문제인지 알 수 없다).
"""
from django.db import migrations, models
import django.db.models.deletion


def _fill(apps, schema_editor):
    """기존 교정에 batch 를 채운다 — 전부 그 이미지의 **현재 검출**의 묶음이다.

    지금 교정 7,472건은 모두 `sam2-전수` 를 보고 한 판단이다(회차를 아직 안
    돌렸다). 그래도 이름을 박지 않고 **검출에서 읽는다** — 시험 DB 처럼 묶음
    이름이 다른 곳에서도 같은 코드가 돌아야 한다.
    """
    ObjectReview = apps.get_model("viewer", "ObjectReview")
    Detection = apps.get_model("viewer", "Detection")

    # image_id -> batch_id. 현재 검출이 이미지마다 하나라는 전제가 아니라,
    # **여럿이면 묶음이 갈리는지**를 보고 갈리면 멈춘다.
    by_image = {}
    clash = []
    for d in (Detection.objects.filter(is_current=True)
              .select_related("run")
              .only("image_id", "run__batch_id")):
        b = d.run.batch_id if d.run_id else None
        if d.image_id in by_image and by_image[d.image_id] != b:
            clash.append(d.image_id)
        by_image[d.image_id] = b
    if clash:
        raise RuntimeError(
            f"한 이미지에 묶음이 다른 현재 검출이 여럿이다 — 이미지 "
            f"{sorted(set(clash))[:5]} … {len(set(clash))}개. 어느 묶음의 "
            f"판단인지 정할 수 없으니 먼저 정리할 것.")

    n = miss = 0
    for oid, iid in ObjectReview.objects.values_list("id", "image_id"):
        b = by_image.get(iid)
        if b is None:
            miss += 1
            continue
        ObjectReview.objects.filter(pk=oid).update(batch_id=b)
        n += 1
    if miss:
        # 막지는 않는다 — batch 없는 교정도 스키마가 허용한다(사람이 그린 것과
        # 같은 자리). 다만 조용히 넘어가지 않는다. check_db 8번이 계속 센다.
        print(f"    !! batch 를 못 정한 교정 {miss}건 — 그 이미지에 현재 검출이 "
              f"없거나 그 검출이 묶음에 안 들어 있다")
    print(f"    batch 를 채운 교정 {n:,}건")


def _unfill(apps, schema_editor):
    """되돌리기 — 옛 유일 제약을 다시 세울 수 있는지 먼저 본다."""
    from collections import Counter
    ObjectReview = apps.get_model("viewer", "ObjectReview")
    dup = [k for k, c in Counter(
        ObjectReview.objects.values_list("image_id", "mask_key")).items() if c > 1]
    if dup:
        raise RuntimeError(
            f"`(image, mask_key)` 가 겹치는 교정이 {len(dup)}건 있다 — 되돌리면 "
            f"옛 유일 제약을 세울 수 없다(예: {dup[:3]}). 판을 되돌리려면 새 "
            f"batch 의 교정을 먼저 걷을 것.")


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0024_locality_and_sample'),
    ]

    operations = [
        migrations.AddField(
            model_name='objectreview',
            name='batch',
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.PROTECT,
                                    related_name='object_reviews',
                                    to='viewer.runbatch'),
        ),
        migrations.AddField(
            model_name='objectreview',
            name='source',
            field=models.CharField(choices=[('engine', 'engine'),
                                            ('manual', 'manual')],
                                   db_default='engine', default='engine',
                                   max_length=8),
        ),
        migrations.AddField(
            model_name='objectreview',
            name='geom_edited',
            field=models.BooleanField(db_default=False, default=False),
        ),
        # 자료를 먼저 채우고 제약을 옮긴다. 순서가 거꾸로면 새 제약이 빈 batch
        # 위에 서서 아무것도 안 잡는다.
        migrations.RunPython(_fill, _unfill),
        migrations.RemoveConstraint(
            model_name='objectreview',
            name='uniq_objreview_key',
        ),
        migrations.AddConstraint(
            model_name='objectreview',
            constraint=models.UniqueConstraint(
                condition=models.Q(('batch__isnull', False)),
                fields=('image', 'batch', 'mask_key'),
                name='uniq_objreview_key'),
        ),
        migrations.AddConstraint(
            model_name='objectreview',
            constraint=models.UniqueConstraint(
                condition=models.Q(('batch__isnull', True)),
                fields=('image', 'mask_key'),
                name='uniq_objreview_manual'),
        ),
        migrations.AddIndex(
            model_name='objectreview',
            index=models.Index(fields=['image', 'batch'],
                               name='viewer_obje_image_i_c20d93_idx'),
        ),
        migrations.AddIndex(
            model_name='objectreview',
            index=models.Index(fields=['source'],
                               name='viewer_obje_source_4be8ca_idx'),
        ),
    ]
