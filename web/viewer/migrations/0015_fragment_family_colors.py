"""파편을 제 본체와 같은 색 가족으로 묶는다.

전에는 넷이 서로 다른 색이었다 — 봉상 파랑 217° · 봉상 파편 보라 258° ·
원형 초록 150° · 원형 파편 청록 180°. 네 가지를 **따로 외워야** 했고, 화면에서
"이건 봉상 쪽인가 원형 쪽인가" 가 색으로 안 읽혔다.

이제 색상은 본체를 따르고 **진하기로 본체와 파편을 가른다.**

    봉상      70,140,255   진한 파랑
    봉상 파편 120,195,255  옅은 파랑 (같은 217°)
    원형      60,220,120   진한 초록
    원형 파편 140,235,170  옅은 초록 (같은 150°)

**너무 옅게는 안 잡았다.** 마스크는 밝은 규조각 위에 42% 로 얹히므로, 흰색에
가까워지면 "마스크가 안 걸린 것" 과 구분이 안 된다. 가장 어두운 성분을 120·140
위로 두어 색은 남기되 본체보다 확실히 연하게만 했다.

**배지 색도 마스크 색을 따라간다.** 파편 둘이 `frag` 하나를 같이 쓰고 있어서
색으로 가를 수가 없었다. 원형의 배지 키가 `on` 이었던 것도 고친다 — `on` 은
"합성됨"·"N개 검출" 이 쓰는 일반 배지라 분류가 얹혀 있을 자리가 아니다.

색상환의 보라 258°·청록 180° 가 비었다. 속을 더 넣을 때 쓸 자리다.
"""
from django.db import migrations

NEW = {
    "rod_frag":   {"color": "120,195,255", "badge": "rodf"},
    "round_frag": {"color": "140,235,170", "badge": "rndf"},
    "round":      {"color": "60,220,120",  "badge": "rnd"},
}
OLD = {
    "rod_frag":   {"color": "160,120,255", "badge": "frag"},
    "round_frag": {"color": "60,205,205",  "badge": "frag"},
    "round":      {"color": "60,220,120",  "badge": "on"},
}


def apply(rows):
    def run(apps, schema_editor):
        model = apps.get_model("viewer", "ClassDef")
        for key, vals in rows.items():
            model.objects.filter(key=key).update(**vals)
    return run


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0014_classdef_chaetoceros"),
    ]

    operations = [migrations.RunPython(apply(NEW), apply(OLD))]
