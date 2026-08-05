# 한 시료에 관찰을 여럿 둔다 — 폴더 접미사 `(1)`·`(2)`, 사람이 붙이는 이름표,
# 그리고 목록 숨김·집계 제외.
#
# **칸을 더하기만 한다 — 조이지 않는다.** 넷 다 `db_default` 를 들고 있어서 이
# 칼럼을 모르는 옛 파이프라인 이미지의 INSERT 도 그대로 통과한다. 그래서 뷰어
# 판만 먼저 올려도 폴러가 안 선다.
#
# **다만 순서는 있다 — 마이그레이션이 먼저, 새 파이프라인 판이 나중이다.**
# 거꾸로 가면 `obs_no` 를 넣는 새 그룹핑이 그 칼럼 없는 DB 를 만나 죽는다.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0022_image_is_the_key'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='slide',
            options={'ordering': ['core', 'depth_cm', 'obs_no', 'name']},
        ),
        migrations.AddField(
            model_name='slide',
            name='exclude_from_totals',
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name='slide',
            name='hide_in_list',
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name='slide',
            name='obs_label',
            field=models.CharField(blank=True, db_default='', default='', max_length=10),
        ),
        migrations.AddField(
            model_name='slide',
            name='obs_no',
            field=models.PositiveSmallIntegerField(db_default=0, default=0),
        ),
    ]
