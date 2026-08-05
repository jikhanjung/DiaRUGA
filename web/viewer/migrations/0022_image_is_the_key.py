"""`Image` 를 열쇠로 못 박는다 — 조이는 단계 (P06 5a).

**여기부터 되돌릴 수 없다.** 2~4단계는 옛 칸(`target`·`frame`)을 그대로 두고
`image` 를 곁들이기만 했다 — 판을 되돌리면 옛 코드가 그대로 돌았다. 이 이행이
그 칸들을 걷는다.

- `Detection.target`·`frame` 제거 — 무엇에 붙은 검출인가는 `image.kind` 가,
  어느 프레임인가는 `image.frame` 이 말한다
- `Detection.image`·`ObjectReview.image` 를 `NOT NULL` 로
- `ObjectReview` 의 유일 제약을 `(viewpoint, mask_key)` 에서
  **`(image, mask_key)`** 로. 옛 열쇠는 **시야마다 볼 이미지가 한 장**일 때만
  성립했는데, 프레임별 검출을 검토하면 깨진다 — 실측으로 시야 452개 중
  203개(45%)에서 `mask_key` 가 프레임끼리 겹친다

**`backfill_images.py --apply` 가 먼저 끝나 있어야 한다.** 아래 `_guard` 가
안 그런 경우 **무엇이 비었는지 적어** 준다 — SQLite 가 내는 말로는 어느 표가
문제인지 알기 어렵다.
"""
import django.db.models.deletion
from django.db import migrations, models


def _guard(apps, schema_editor):
    """`image` 가 빈 행이 남아 있으면 여기서 멈춘다."""
    Detection = apps.get_model("viewer", "Detection")
    ObjectReview = apps.get_model("viewer", "ObjectReview")
    n_det = Detection.objects.filter(image__isnull=True).count()
    n_rev = ObjectReview.objects.filter(image__isnull=True).count()
    if n_det or n_rev:
        raise RuntimeError(
            f"image 가 빈 행이 남아 있다 — 검출 {n_det} · 교정 {n_rev}. "
            "backfill_images.py --apply 를 먼저 돌릴 것 (P06 3단계).")


def _noop(apps, schema_editor):
    """되돌릴 때는 검사할 것이 없다."""


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0021_alter_image_stack'),
    ]

    operations = [
        migrations.RunPython(_guard, _noop),
        migrations.RemoveConstraint(
            model_name='objectreview',
            name='uniq_objreview_key',
        ),
        migrations.RemoveField(
            model_name='detection',
            name='frame',
        ),
        migrations.RemoveField(
            model_name='detection',
            name='target',
        ),
        migrations.AlterField(
            model_name='detection',
            name='image',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='detections', to='viewer.image'),
        ),
        migrations.AlterField(
            model_name='objectreview',
            name='image',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='object_reviews', to='viewer.image'),
        ),
        migrations.AddConstraint(
            model_name='objectreview',
            constraint=models.UniqueConstraint(fields=('image', 'mask_key'), name='uniq_objreview_key'),
        ),
    ]
