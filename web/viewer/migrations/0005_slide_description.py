"""슬라이드에 사람이 적는 설명 칸을 둔다.

`state_note` 는 자동 처리가 쓰는 칸이라(그룹핑 여유, 검출 대기 시야 수) 사람이
적은 것이 덮어써진다. 성격이 다르므로 갈라 둔다.

지역명·좌표 칸(`Site.region`·`lat`·`lon`, `Core.lat`·`lon`·`water_depth_m` …)은
P02 때 이미 만들어 두고 비워 뒀다 — "코드만으로는 단정할 수 없어 사람이 채운다" 는
판단이었다. 이번에 그 칸들을 채울 화면이 생긴다.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0004_photos_path_prefix"),
    ]

    operations = [
        migrations.AddField(
            model_name="slide",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
