"""`is_current` 를 **묶음마다** 정규화한다 (P10 2단계).

`Detection.is_current` 의 뜻이 좁아졌다 — 예전에는 "뷰어가 볼 것" 이었고 이제는
**"그 묶음 안에서 이 이미지의 최신 검출"** 이다. 어느 묶음을 볼지는
`RunBatch.for_review` 가 정한다.

자료는 아직 옛 뜻대로 앉아 있다. `yolo-3차` 의 검출 1,799개가 전부
`is_current=False` 인데, 그것은 "뷰어가 안 본다" 는 말이었지 "이 묶음 안에서 낡은
것" 이라는 말이 아니다. 새 뜻으로 옮긴다.

## 화면은 안 달라진다

읽는 쪽은 이미 **`for_review` 와 `is_current` 가 둘 다 켜진 것**을 본다(1단계).
`sam2-전수` 만 검토 대상이므로 `yolo-3차` 를 아무리 켜도 화면이 보는 것은 그대로
508개다. **그것을 확인하고 넘어가는 것이 이 이행의 안전 기준이다.**

이 순서를 지킨 이유는 반대로 하면 그 자리에서 깨지기 때문이다 — 읽는 쪽이 아직
묶음을 안 볼 때 정규화하면 시야마다 검출이 여럿이 되어 화면이 섞인다.

## 무엇을 최신으로 보는가

**`(묶음, 이미지)` 마다 pk 가 가장 큰 것 하나.** `prune_detections.py` 가 남기는
것과 같은 규칙이다("현재 검출이 있으면 그것, 없으면 번호가 큰 것") — 여기서는
묶음 안에 현재가 이미 정해져 있으면 그것을 존중하고, 없을 때만 번호로 고른다.
"""
from django.db import migrations


def _normalize(apps, schema_editor):
    Detection = apps.get_model("viewer", "Detection")

    # (묶음, 이미지) -> 남길 검출 pk
    keep, seen = {}, 0
    for d in (Detection.objects.filter(image__isnull=False)
              .select_related("run")
              .only("id", "image_id", "is_current", "run__batch_id")
              .order_by("id")):
        seen += 1
        b = d.run.batch_id if d.run_id else None
        k = (b, d.image_id)
        cur = keep.get(k)
        if cur is None:
            keep[k] = d
        elif d.is_current and not cur.is_current:
            keep[k] = d              # 이미 정해진 현재를 존중한다
        elif d.is_current == cur.is_current:
            keep[k] = d              # 둘 다 같으면 번호가 큰 쪽 (order_by id)

    want_on = {d.pk for d in keep.values()}
    on = set(Detection.objects.filter(is_current=True)
             .values_list("id", flat=True))

    turn_on = want_on - on
    turn_off = on - want_on
    if turn_on:
        Detection.objects.filter(pk__in=turn_on).update(is_current=True)
    if turn_off:
        Detection.objects.filter(pk__in=turn_off).update(is_current=False)
    print(f"    검출 {seen:,}개 · (묶음,이미지) {len(keep):,}쌍 — "
          f"켠 것 {len(turn_on):,} · 끈 것 {len(turn_off):,}")


def _reverse(apps, schema_editor):
    """되돌리기 — **검토 대상 묶음만 켜 둔다.** 옛 뜻이 그것이었다."""
    Detection = apps.get_model("viewer", "Detection")
    RunBatch = apps.get_model("viewer", "RunBatch")
    rb = RunBatch.objects.filter(for_review=True).values_list("id", flat=True).first()
    if rb is None:
        print("    검토 대상이 없다 — 되돌릴 기준이 없어 그대로 둔다")
        return
    off = Detection.objects.filter(is_current=True).exclude(run__batch_id=rb)
    n = off.count()
    off.update(is_current=False)
    print(f"    검토 대상 밖의 검출 {n:,}개를 껐다")


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0026_batch_for_review'),
    ]

    operations = [migrations.RunPython(_normalize, _reverse)]
