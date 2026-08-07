"""묶음마다 **어떻게 채우는가**를 적는다 (P10 6단계 · 079).

새 슬라이드가 들어오면 지금은 폴러가 아는 묶음 하나(`DETECT_BATCH`)에만 들어간다.
묶음이 여럿인 것이 기본이 되면서 그것이 문제가 됐다 — `sam2-전수` 를 보다가
`yolo-3차` 로 갈아타면 그 사이에 들어온 슬라이드가 **빈 화면**이다.

`recipe` 는 `segment_diatoms.py` 의 인자를 담는다. **비어 있으면 자동으로 안
돈다** — 끝난 회차를 그대로 두는 것이 기본이고, 묶음이 늘 때마다 GPU 시간이
곱으로 늘기 때문이다.

## 이행에서 채우는 것

**지금까지 실제로 돌린 인자**(`Run.params`)에서 가져온다. 여기서 안 채우면
이행 직후 폴러가 돌 묶음이 하나도 없어지고, 그것은 조용한 멈춤이다.

`weights` 는 076 부터 남기기 시작했으므로 그 전의 YOLO 실행에는 없다. 그때는
지금 기본 가중치를 적고 `weights_guessed` 를 함께 남긴다 — **추측한 값이라고
적어 두지 않으면 나중에 그것을 근거로 삼는다.**
"""
from django.db import migrations, models

# `segment_diatoms.py` 인자 중 조리법에 담는 것. 여기 없는 것은 기본값을 쓴다.
KEYS = ("backend", "scale", "points_per_side", "min_um", "max_um",
        "all_images", "weights", "yolo_conf", "yolo_imgsz")
DEFAULT_WEIGHTS = "models/11m-v1seg-1280.pt"


def _fill(apps, schema_editor):
    RunBatch = apps.get_model("viewer", "RunBatch")
    Run = apps.get_model("viewer", "Run")

    done = []
    for b in RunBatch.objects.filter(kind="detect"):
        if b.recipe:
            continue
        run = (Run.objects.filter(batch=b, kind="detect")
               .exclude(params={}).order_by("-started_at").first())
        if run is None:
            continue
        p = run.params or {}
        recipe = {k: p[k] for k in KEYS if p.get(k) is not None}
        if not recipe.get("backend"):
            continue                    # 무엇으로 돌렸는지 모르면 못 적는다
        if isinstance(recipe.get("weights"), dict):     # 076 형식 {path, sha256…}
            recipe["weights"] = recipe["weights"].get("path") or DEFAULT_WEIGHTS
        if recipe["backend"] == "yolo":
            if not recipe.get("weights"):
                recipe["weights"] = DEFAULT_WEIGHTS
                recipe["weights_guessed"] = True
            # 프레임까지 도는 것이 YOLO 회차의 모양이다(실측: yolo-3차 는 시야
            # 452개에 프레임 검출 1,310개). 옛 실행은 파일 목록을 손으로 만들어
            # 돌려서 이 표시가 안 남았다.
            recipe.setdefault("all_images", True)
        b.recipe = recipe
        b.save(update_fields=["recipe"])
        done.append((b.label, recipe.get("backend"),
                     "가중치 추측" if recipe.get("weights_guessed") else ""))

    if done:
        for label, backend, warn in done:
            print(f"    조리법을 적었다: {label} ({backend}) {warn}")
    else:
        print("    조리법을 적을 묶음이 없다")


def _clear(apps, schema_editor):
    RunBatch = apps.get_model("viewer", "RunBatch")
    n = RunBatch.objects.exclude(recipe={}).update(recipe={})
    print(f"    조리법 {n}개를 비웠다")


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0028_viewpoint_review_batch'),
    ]

    operations = [
        migrations.AddField(
            model_name='runbatch',
            name='recipe',
            field=models.JSONField(blank=True, db_default={}, default=dict),
        ),
        migrations.RunPython(_fill, _clear),
    ]
