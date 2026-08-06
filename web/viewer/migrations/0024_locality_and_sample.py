"""층을 말과 맞춘다 — `Core` → `Locality`(지점), 그 아래 `Sample`(시료).

    권역   한국 · 남극                       Site.area
     └ 지역   BP(북평분지) · RS23            Site
        └ 지점   BP09(노두) · GC03(시추코어)  Locality   ← 예전 Core
           └ 시료   0901 · 71cm              Sample     ← 새로 생긴 층
              └ 관찰   (1) · (2)             Slide

**자동 생성본을 그대로 쓰면 안 됐다.** Django 는 `Core` 를 지우고 `Locality` 를
빈 채로 만드는 순서를 냈다 — 그대로 돌리면 지점 다섯과 모든 관찰의 소속이
통째로 날아간다. 그래서 손으로 순서를 잡았다:

    새 표를 만들고 → **자료를 옮기고** → 그 다음에 옛 칸을 걷는다.

`RunPython` 이 가운데 있어야 하는 이유가 그것이다. 되돌리기(`reverse`)도 함께
적어 둔다 — 배포 게이트가 막히면 판을 되돌려야 하는데, 그때 자료가 없으면
되돌린 판이 빈 화면을 낸다.

## 시료를 어떻게 만드나

관찰 행이 들고 있던 `(core, depth_cm)` 에서 만든다. 같은 지점·같은 위치의 관찰
여럿은 **한 시료 행을 공유해야 한다** — 그것이 이 이사의 요점이다.

- 시추코어: 코드는 `71cm`, 위치는 `depth_cm`
- 노두: 깊이가 없으므로 **폴더 이름의 뒤 토막**이 코드다 (`BP09-0901` → `0901`),
  위치는 지점 번호가 되풀이되는 자리를 뗀 값 (`naming.sample_no_from`)

지점 유형(`kind`)은 그 지점에 달린 관찰들의 `sample_kind` 에서 올린다. 실측에서
지점 다섯 곳 전부 한 가지로 모였다(2026-08-06) — 섞여 있으면 노두를 이긴 것으로
본다: 노두는 사람이 손으로 골라 넣은 값이라 자동값보다 근거가 세다.
"""
import django.db.models.deletion
from django.db import migrations, models


def to_locality_and_sample(apps, schema_editor):
    """`Core` → `Locality`, 관찰의 소속 → `Sample`."""
    Core = apps.get_model("viewer", "Core")
    Locality = apps.get_model("viewer", "Locality")
    Sample = apps.get_model("viewer", "Sample")
    Slide = apps.get_model("viewer", "Slide")

    # 마이그레이션은 앱 코드를 임포트해도 되지만(모델이 아니라 순수 문자열 규칙
    # 이다) 규칙이 나중에 바뀌면 지난 마이그레이션의 뜻이 달라진다. 그래서
    # **여기서 쓰는 것만 그대로 베껴 온다** — 마이그레이션은 그때의 규칙으로
    # 고정되어야 한다.
    def sample_no_from(loc_code, sample_code):
        if not sample_code or not sample_code.isdigit():
            return None
        head = "".join(c for c in (loc_code or "") if c.isdigit())
        rest = (sample_code[len(head):]
                if head and sample_code.startswith(head) else sample_code)
        return int(rest) if rest.isdigit() and rest else int(sample_code)

    def base_name(name):
        import re
        return re.sub(r"\s*\((\d+)\)\s*$", "", name or "").strip()

    # 1) 지점. 유형은 그 아래 관찰들의 `sample_kind` 에서 올린다.
    old_to_new = {}
    for core in Core.objects.all():
        kinds = set(core.slides.values_list("sample_kind", flat=True))
        kind = "outcrop" if "outcrop" in kinds else "core"
        loc = Locality.objects.create(
            site_id=core.site_id, code=core.code, kind=kind,
            # 옛 `Core.kind` 는 자유 문자열(`gravity core`)이었다. 새 `kind` 는
            # 두 갈래라 이름이 겹치므로 `collect_kind` 로 옮긴다.
            collect_kind=core.kind or "", lat=core.lat, lon=core.lon,
            water_depth_m=core.water_depth_m, collected_at=core.collected_at,
            note=core.note or "")
        old_to_new[core.pk] = loc

    # 2) 시료. **같은 지점·같은 위치의 관찰들이 한 행을 공유한다.**
    made = {}
    for slide in Slide.objects.all().order_by("id"):
        if not slide.core_id:
            continue                     # 소속이 없던 관찰은 그대로 둔다
        loc = old_to_new[slide.core_id]
        if slide.depth_cm is not None:
            code = f"{slide.depth_cm:g}cm"
            depth, no = slide.depth_cm, None
        else:
            # 노두. 폴더 이름의 뒤 토막이 시료 코드다 (`BP09-0901` → `0901`).
            base = base_name(slide.name)
            code = base.rsplit("-", 1)[-1].strip() if "-" in base else base
            depth, no = None, sample_no_from(loc.code, code)
        key = (loc.pk, code)
        sample = made.get(key)
        if sample is None:
            sample = made[key] = Sample.objects.create(
                locality=loc, code=code, depth_cm=depth, sample_no=no)
        slide.sample = sample
        slide.save(update_fields=["sample"])


def back_to_core(apps, schema_editor):
    """되돌리기. 판을 되돌려야 할 때 빈 화면이 나오면 안 된다."""
    Core = apps.get_model("viewer", "Core")
    Locality = apps.get_model("viewer", "Locality")
    Slide = apps.get_model("viewer", "Slide")

    back = {}
    for loc in Locality.objects.all():
        back[loc.pk] = Core.objects.create(
            site_id=loc.site_id, code=loc.code, kind=loc.collect_kind or "",
            lat=loc.lat, lon=loc.lon, water_depth_m=loc.water_depth_m,
            collected_at=loc.collected_at, note=loc.note or "")
    for slide in Slide.objects.select_related("sample__locality").all():
        if not slide.sample_id:
            continue
        sm = slide.sample
        slide.core = back[sm.locality_id]
        slide.depth_cm = sm.depth_cm
        slide.sample_kind = sm.locality.kind
        slide.save(update_fields=["core", "depth_cm", "sample_kind"])


class Migration(migrations.Migration):

    dependencies = [("viewer", "0023_slide_observation")]

    operations = [
        # --- 1) 새 표를 만든다 -------------------------------------------
        migrations.CreateModel(
            name="Locality",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32)),
                ("kind", models.CharField(
                    choices=[("core", "시추코어"), ("outcrop", "노두")],
                    db_default="core", default="core", max_length=12)),
                ("collect_kind", models.CharField(blank=True, max_length=64)),
                ("lat", models.FloatField(blank=True, null=True)),
                ("lon", models.FloatField(blank=True, null=True)),
                ("water_depth_m", models.FloatField(blank=True, null=True)),
                ("collected_at", models.DateField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("site", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="localities", to="viewer.site")),
            ],
            options={"verbose_name": "지점", "ordering": ["site", "code"]},
        ),
        migrations.CreateModel(
            name="Sample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=64)),
                ("depth_cm", models.FloatField(blank=True, null=True)),
                ("sample_no", models.PositiveIntegerField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("locality", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="samples", to="viewer.locality")),
            ],
            options={"verbose_name": "시료",
                     "ordering": ["locality", "depth_cm", "sample_no", "code"]},
        ),
        migrations.AddField(
            model_name="slide",
            name="sample",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="slides", to="viewer.sample"),
        ),

        # --- 2) 자료를 옮긴다. **옛 칸을 걷기 전이다** ---------------------
        migrations.RunPython(to_locality_and_sample, back_to_core),

        # --- 3) 그 다음에 옛 것을 걷는다 -----------------------------------
        migrations.RemoveIndex(model_name="slide",
                               name="viewer_slid_core_id_690347_idx"),
        migrations.RemoveField(model_name="slide", name="core"),
        migrations.RemoveField(model_name="slide", name="depth_cm"),
        migrations.RemoveField(model_name="slide", name="sample_kind"),
        # **제약을 먼저 뗀다.** SQLite 는 칼럼을 지울 때 표를 통째로 다시 만드는데,
        # `uniq_core_code` 가 아직 `site` 를 가리키고 있으면 그 새 표를 그리다가
        # `NewCore has no field named 'site'` 로 죽는다.
        migrations.RemoveConstraint(model_name="core", name="uniq_core_code"),
        migrations.RemoveField(model_name="core", name="site"),
        migrations.DeleteModel(name="Core"),

        # --- 4) 제약과 인덱스은 자료가 다 앉은 뒤에 건다 --------------------
        migrations.AlterModelOptions(
            name="slide",
            options={"ordering": ["sample", "obs_no", "name"],
                     "verbose_name": "관찰"}),
        migrations.AddIndex(
            model_name="slide",
            index=models.Index(fields=["sample", "obs_no"],
                               name="viewer_slid_sample__ed9cac_idx")),
        migrations.AddConstraint(
            model_name="locality",
            constraint=models.UniqueConstraint(fields=("site", "code"),
                                               name="uniq_locality_code")),
        migrations.AddIndex(
            model_name="sample",
            index=models.Index(fields=["locality", "depth_cm"],
                               name="viewer_samp_localit_55866c_idx")),
        migrations.AddConstraint(
            model_name="sample",
            constraint=models.UniqueConstraint(fields=("locality", "code"),
                                               name="uniq_sample_code")),
    ]
