"""슬라이드마다 배율을 사람이 못 박을 수 있게 한다.

`zen_meta` 는 따로 지정하지 않으면 40x 로 가정해 계산한다 — ZEN 이 소프트웨어에서
선택된 대물렌즈를 적어서 실제 광학계와 어긋난 적이 있기 때문이다(devlog 015).
다른 배율로 찍었다면 이 칸으로 알려 준다. 자동으로 알아내려 하지 않는다.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("viewer", "0005_slide_description")]

    operations = [
        migrations.AddField(
            model_name="slide",
            name="um_per_pixel_override",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
