"""검토 완료를 **묶음마다** 남긴다 (073).

`ViewpointReview` 가 시야마다 한 줄이었다. 그 줄의 `done` 은 "여기는 다 봤다"
인데, **무엇을 다 봤는지**가 빠져 있다. `sam2-전수` 를 검토하고 붙인 완료
표시가 `yolo-3차` 로 갈아탄 화면에도 그대로 붙어, **아직 아무도 안 본 검출이
"검토 완료" 로 보였다.** 그 시야는 "다음 미검토" 가 건너뛰어 다시 열리지 않는다.

## 무엇을 어디에 두는가

`ObjectReview` 와 같은 가름이다(P09 5.2).

- `done` → **묶음마다** (`(viewpoint, batch)` 가 열쇠)
- `note` → **시야마다** (`batch=NULL` 인 행 하나)

코멘트를 함께 묶음에 매달면 묶음을 갈 때마다 사람이 쓴 글이 사라진다.
**재생성 불가한 자료다.**

## 옛 줄을 어느 묶음으로 보내는가

`0025` 가 교정을 옮길 때 쓴 것과 같은 기준이다 — **그 시야의 `ObjectReview`
가 든 묶음**, 없으면 지금 검토 대상 묶음. 지금까지의 검토는 전부 `sam2-전수`
아래에서 이루어졌으므로 실제로는 하나로 모인다.

코멘트가 있던 줄은 **둘로 갈린다** — 완료는 그 묶음 줄에, 코멘트는 새로 만드는
`batch=NULL` 줄에. 어느 쪽도 잃지 않는다.
"""
from django.db import migrations, models
import django.db.models.deletion


def _split(apps, schema_editor):
    VR = apps.get_model("viewer", "ViewpointReview")
    OR = apps.get_model("viewer", "ObjectReview")
    RunBatch = apps.get_model("viewer", "RunBatch")

    cur = (RunBatch.objects.filter(for_review=True)
           .values_list("id", flat=True).first())
    # 시야 → 그 시야의 교정이 든 묶음 (여럿이면 행이 가장 많은 것)
    owner = {}
    counts = {}
    for vp_id, b_id in OR.objects.filter(batch__isnull=False).values_list(
            "viewpoint_id", "batch_id"):
        counts[(vp_id, b_id)] = counts.get((vp_id, b_id), 0) + 1
    for (vp_id, b_id), n in counts.items():
        if n > owner.get(vp_id, (None, 0))[1]:
            owner[vp_id] = (b_id, n)

    notes, moved, kept = 0, 0, 0
    for r in VR.objects.all():
        b = owner.get(r.viewpoint_id, (cur, 0))[0]
        if r.note:
            # 코멘트는 시야의 것 — 묶음 없는 줄로 뺀다
            VR.objects.create(viewpoint_id=r.viewpoint_id, batch=None,
                              done=False, note=r.note)
            notes += 1
        if b is None:
            # **묶음을 정할 수 없다** (검토 대상도 없고 교정도 없는 DB). 완료
            # 표시는 어느 묶음의 것인지 말할 수 없어 버린다 — 다시 누르면 된다.
            # 코멘트는 위에서 이미 묶음 없는 줄로 옮겨 두었다: 사람이 쓴 글은
            # 버리지 않는다.
            r.delete()
            kept += 1
            continue
        r.batch_id = b
        r.note = ""
        r.save(update_fields=["batch", "note"])
        moved += 1
    print(f"    검토 완료 {moved:,}줄을 묶음으로 · 코멘트 {notes:,}줄을 따로 뺐다"
          + (f" · 묶음을 못 정한 줄 {kept:,}" if kept else ""))


def _merge(apps, schema_editor):
    """되돌리기 — 시야마다 한 줄로 합친다. **완료가 하나라도 있으면 완료다.**"""
    VR = apps.get_model("viewer", "ViewpointReview")
    by_vp = {}
    for r in VR.objects.all().order_by("id"):
        cur = by_vp.get(r.viewpoint_id)
        if cur is None:
            by_vp[r.viewpoint_id] = r
            continue
        cur.done = cur.done or r.done
        cur.note = cur.note or r.note
        cur.save(update_fields=["done", "note"])
        r.delete()
    n = 0
    for r in by_vp.values():
        if r.batch_id is not None:
            r.batch = None
            r.save(update_fields=["batch"])
            n += 1
    print(f"    시야마다 한 줄로 합쳤다 ({len(by_vp):,}줄 · 묶음을 뗀 것 {n:,})")


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0027_normalize_is_current'),
    ]

    operations = [
        # **먼저 판을 넓힌다.** 유일 제약(OneToOne)이 살아 있으면 코멘트 줄을
        # 만드는 순간 죽는다 — 자료를 옮기기 전에 자리를 만들어야 한다.
        migrations.AlterField(
            model_name="viewpointreview",
            name="viewpoint",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reviews", to="viewer.viewpoint"),
        ),
        migrations.AddField(
            model_name="viewpointreview",
            name="batch",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="viewpoint_reviews", to="viewer.runbatch"),
        ),
        migrations.RunPython(_split, _merge),
        migrations.AddConstraint(
            model_name="viewpointreview",
            constraint=models.UniqueConstraint(
                condition=models.Q(("batch__isnull", False)),
                fields=("viewpoint", "batch"), name="uniq_vpreview_batch"),
        ),
        migrations.AddConstraint(
            model_name="viewpointreview",
            constraint=models.UniqueConstraint(
                condition=models.Q(("batch__isnull", True)),
                fields=("viewpoint",), name="uniq_vpreview_note"),
        ),
    ]
