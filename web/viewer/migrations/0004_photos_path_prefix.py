"""사진을 photos/<촬영일>/<슬라이드>/ 아래로 옮긴다 (P03).

사진이 저장소 안(`260729/`)에서 큰 디스크(`/data3/diatom/photos/`)로 나갔다.
뿌리는 `DATA_ROOT` 환경변수가 가리키므로 DB 가 알 필요가 없지만, 그 위의 칸이
바뀐 것은 DB 에 든 상대경로에 남아 있다.

**촬영일 층을 남기는 이유.** NAS 가 `DiatomPhotos/<촬영일>/<슬라이드>/` 구조다.
평탄하게 펴서 슬라이드만 남기면 같은 슬라이드를 다시 촬영했을 때 이름이 부딪힌다
(초점을 다시 잡거나 시야를 더 찍는 일은 충분히 있다). NAS 구조를 그대로 비추면
그 문제가 없고, 스캔·인제스트도 상대경로 하나를 키로 쓰면 되어 단순해진다.

경로를 담는 칼럼은 여섯인데 셋만 손댄다. `Stack.*_path` 는 `stacked/` 로 시작해
바뀔 것이 없다.
"""
from django.db import migrations

OLD = "260729/"
NEW = "photos/260729/"

TARGETS = [
    ("Slide", "image_dir"),
    ("Frame", "path"),
    ("Detection", "image_path"),
]


def _swap(apps, old, new):
    for model_name, field in TARGETS:
        model = apps.get_model("viewer", model_name)
        # 접두사가 맞는 행만 — 이미 옮겨졌거나 새로 만든 DB 면 아무 일도 없다
        qs = model.objects.filter(**{f"{field}__startswith": old})
        for obj in qs.iterator():
            setattr(obj, field, new + getattr(obj, field)[len(old):])
            obj.save(update_fields=[field])


def forward(apps, schema_editor):
    _swap(apps, OLD, NEW)


def backward(apps, schema_editor):
    _swap(apps, NEW, OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("viewer", "0003_core_site_alter_slide_options_slide_depth_cm_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
