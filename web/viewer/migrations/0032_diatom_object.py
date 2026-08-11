"""개체와 판정을 가른다 — `ObjectLink`/`ObjectLinkMember`/`ObjectReview` 를 둘로 (P12).

**재생성 불가한 7,914행을 만진다.** 순서는 063 이 정한 그대로다:
**새 자리 → `RunPython` 으로 자료 이동 → 옛 칸 걷기**, 그리고 `reverse` 도 함께
적는다(배포가 막혀 판을 되돌릴 때 빈 화면이 나오면 안 된다).

## 무엇이 어디로 가나

| 옛것 | 새것 |
|---|---|
| `ObjectLink` (4행) | `DiatomObject` — **개명이다.** 새 표를 만들지 않는다 |
| `ObjectLinkMember` (12행) | `ObjectReview.diatom_object` + `is_rep` 로 흡수 |
| `ObjectReview.label`·`species` | `DiatomObject.label`·`species` 로 올린다 |

**개명을 `ObjectReview` 에는 안 쓴다.** 이름이 뜻보다 좁아졌을 뿐이고, 7,914행을
개명 마이그레이션에 태우는 값이 그보다 훨씬 비싸다 (`Core`→`Locality`, 063).

## 되돌릴 때

`unfill` 이 개체의 분류·종명을 판정으로 도로 내리고, 멤버가 둘 이상인 개체만
`ObjectLinkMember` 로 복원한 뒤, **자동으로 만든 1:1 개체를 지운다.** 지우기 전에
`diatom_object` 를 `NULL` 로 먼저 떼는 것이 중요하다 — `CASCADE` 라서 그냥 지우면
판정 행이 함께 사라진다.

**완전한 역이 아니다.** 앞으로 갈 때 묶음 안의 값이 **하나로 합쳐지므로**
(그것이 이 마이그레이션의 목적이다) 되돌려도 판마다 달랐던 값은 안 돌아온다.
실측으로 되돌린 뒤 판정 7,917(원래 7,914) · 분류 1,776(원래 1,774)이다 —
차이는 **묶음 4개 안에서만** 나고, 판단 없이 묶기만 했던 마스크에 세운 껍데기
3건과 그 껍데기가 개체에서 물려받은 분류 2건이다.

`reverse` 를 두는 목적은 **배포를 되돌릴 때 화면이 뜨게 하는 것**이지 완전
복원이 아니다. 진짜 되돌리기는 백업 사본이고, 그쪽이 첫 안전망이다.
"""

from django.db import migrations, models
import django.db.models.deletion


def fill(apps, schema_editor):
    DiatomObject = apps.get_model("viewer", "DiatomObject")
    Member = apps.get_model("viewer", "ObjectLinkMember")
    Review = apps.get_model("viewer", "ObjectReview")
    Candidate = apps.get_model("viewer", "Candidate")

    made_shell = 0
    conflicts = []

    # ── 1. 이미 묶여 있던 것 — 멤버를 판정 행에 잇는다 ──────────────────────
    for obj in DiatomObject.objects.all():
        members = list(Member.objects.filter(link_id=obj.pk))
        rows = []
        for m in members:
            row = Review.objects.filter(image_id=m.image_id,
                                        batch_id=m.batch_id,
                                        mask_key=m.mask_key).first()
            if row is None:
                # **판단 없이 묶기만 한 마스크** — 실측 3건. 판정 행이 없으면
                # 개체에 매달 자리가 없으므로 껍데기를 세운다. 표시가 하나도
                # 없는 행이라 `unfill` 이 이것만 골라 되돌릴 수 있다.
                # 검출의 묶음은 `run` 을 지나 간다 — `Detection` 에 `batch` 가
                # 따로 없다.
                cand = Candidate.objects.filter(
                    detection__image_id=m.image_id,
                    detection__run__batch_id=m.batch_id,
                    mask_key=m.mask_key).first()
                row = Review(viewpoint_id=obj.viewpoint_id,
                             image_id=m.image_id, batch_id=m.batch_id,
                             mask_key=m.mask_key,
                             candidate=cand,
                             bind_method="exact" if cand else "orphan",
                             bind_score=1.0 if cand else None,
                             source="manual" if m.batch_id is None else "engine",
                             geom=m.geom or {})
                made_shell += 1
            row.diatom_object_id = obj.pk
            row.is_rep = bool(m.is_rep)
            rows.append(row)

        # 분류·종명을 개체로 올린다. **사람이 적은 것을 자동으로 덮지 않는다** —
        # 대표가 든 값이 있으면 그것, 없으면 비어 있지 않은 값이 하나일 때만
        # 집는다. 여럿이면 대표 것을 쓰고 무엇을 버렸는지 찍는다 (실측 0건).
        for fld in ("label", "species"):
            vals = [getattr(r, fld, "") or "" for r in rows]
            rep = next((getattr(r, fld, "") or ""
                        for r in rows if r.is_rep), "")
            distinct = {v for v in vals if v}
            if rep:
                pick = rep
            elif len(distinct) == 1:
                pick = distinct.pop()
            else:
                pick = ""
            if len(distinct) > 1:
                conflicts.append((obj.pk, fld, sorted(distinct), pick))
            setattr(obj, fld, pick)
        obj.save(update_fields=["label", "species"])

        for r in rows:
            r.save()

    n_linked = Review.objects.exclude(diatom_object__isnull=True).count()

    # ── 2. 묶이지 않은 판정 — 각자 개체 하나 (1:1) ─────────────────────────
    #
    # **지운 마스크도 받는다.** "규조각이 아니다" 라고 판정한 것에 개체가 서는
    # 것이 어색해 보이지만, 조건부로 두면 지웠다 되살리는 사이에 묶음이 깨지고
    # 읽는 자리 79곳이 전부 갈래를 타야 한다 (P12 · 2026-08-11 결정).
    rest = Review.objects.filter(diatom_object__isnull=True).only(
        "pk", "viewpoint_id", "batch_id", "label", "species")
    n_solo = 0
    for row in rest.iterator(chunk_size=500):
        obj = DiatomObject.objects.create(
            viewpoint_id=row.viewpoint_id, batch_id=row.batch_id,
            label=row.label or "", species=row.species or "")
        Review.objects.filter(pk=row.pk).update(diatom_object=obj, is_rep=True)
        n_solo += 1

    left = Review.objects.filter(diatom_object__isnull=True).count()
    if left:
        raise RuntimeError(f"개체를 못 받은 판정이 {left}건 남았다 — 멈춘다")

    print(f"\n   P12: 개체 {DiatomObject.objects.count()}개 "
          f"(묶음에서 온 판정 {n_linked} · 1:1 로 세운 것 {n_solo})")
    if made_shell:
        print(f"        판단 없이 묶기만 한 마스크에 판정 행 {made_shell}건을 세웠다")
    for pk, fld, vals, pick in conflicts:
        print(f"        !! 개체 {pk} 의 {fld} 가 엇갈렸다: {vals} → '{pick}'")


def unfill(apps, schema_editor):
    DiatomObject = apps.get_model("viewer", "DiatomObject")
    Member = apps.get_model("viewer", "ObjectLinkMember")
    Review = apps.get_model("viewer", "ObjectReview")

    # 1. 분류·종명을 판정으로 도로 내린다
    for obj in DiatomObject.objects.all().iterator(chunk_size=500):
        if obj.label or obj.species:
            Review.objects.filter(diatom_object=obj).update(
                label=obj.label or "", species=obj.species or "")

    # 2. 멤버가 둘 이상인 개체만 묶음으로 복원한다 (1:1 은 P12 가 만든 것이다)
    n_link = 0
    for obj in DiatomObject.objects.all().iterator(chunk_size=500):
        rows = list(Review.objects.filter(diatom_object=obj))
        if len(rows) < 2:
            continue
        for r in rows:
            Member.objects.create(link_id=obj.pk, image_id=r.image_id,
                                  batch_id=r.batch_id, mask_key=r.mask_key,
                                  is_rep=r.is_rep, geom=r.geom or None)
        n_link += 1

    # 3. **떼고 나서 지운다.** `CASCADE` 라 순서를 바꾸면 판정이 함께 사라진다
    solo = [o.pk for o in DiatomObject.objects.all()
            if Review.objects.filter(diatom_object_id=o.pk).count() < 2]
    Review.objects.filter(diatom_object_id__in=solo).update(diatom_object=None)
    DiatomObject.objects.filter(pk__in=solo).delete()

    # 4. 묶기만 하려고 세웠던 빈 껍데기를 걷는다 (이전 전에는 0건이었다)
    n_shell = Review.objects.filter(
        removed=False, accepted=False, label="", note="", species="",
        geom_edited=False, diatom_object__isnull=True).delete()[0]

    print(f"\n   P12 되돌리기: 묶음 {n_link}개 복원 · 1:1 개체 {len(solo)}개 삭제 "
          f"· 빈 껍데기 {n_shell}건 삭제")


class Migration(migrations.Migration):

    dependencies = [("viewer", "0031_catalog_species_and_batch_code")]

    operations = [
        # ── 새 자리 ────────────────────────────────────────────────────────
        migrations.RenameModel(old_name="ObjectLink", new_name="DiatomObject"),
        # 개명하면 인덱스 이름도 따라가야 한다 — 안 맞추면 다음 사람이
        # `makemigrations` 를 돌릴 때마다 이름만 바꾸는 판이 하나 더 난다.
        migrations.RenameIndex(
            model_name="diatomobject",
            new_name="viewer_diat_viewpoi_b72cd6_idx",
            old_name="viewer_obje_viewpoi_a7e604_idx"),
        migrations.AlterField(
            model_name="diatomobject", name="viewpoint",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name="diatom_objects",
                                    to="viewer.viewpoint")),
        migrations.AlterField(
            model_name="diatomobject", name="batch",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.PROTECT,
                                    related_name="diatom_objects",
                                    to="viewer.runbatch")),
        migrations.AddField(
            model_name="diatomobject", name="label",
            field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(
            model_name="diatomobject", name="species",
            field=models.CharField(blank=True, db_default="", default="",
                                   max_length=120)),
        migrations.AddIndex(
            model_name="diatomobject",
            index=models.Index(fields=["viewpoint", "batch"],
                               name="viewer_diat_viewpoi_28ff06_idx")),

        # 판정에 개체 자리를 낸다. **아직 nullable 이다** — 채운 뒤에 조인다
        migrations.AddField(
            model_name="objectreview", name="diatom_object",
            field=models.ForeignKey(null=True,
                                    on_delete=django.db.models.deletion.CASCADE,
                                    related_name="members",
                                    to="viewer.diatomobject")),
        migrations.AddField(
            model_name="objectreview", name="is_rep",
            field=models.BooleanField(db_default=False, default=False)),

        # ── 자료 이동 ──────────────────────────────────────────────────────
        migrations.RunPython(fill, unfill),

        # ── 옛 칸 걷기 ────────────────────────────────────────────────────
        migrations.AlterField(
            model_name="objectreview", name="diatom_object",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name="members",
                                    to="viewer.diatomobject")),
        migrations.RemoveField(model_name="objectreview", name="label"),
        migrations.RemoveField(model_name="objectreview", name="species"),
        migrations.DeleteModel(name="ObjectLinkMember"),

        # ── 제약·인덱스 ───────────────────────────────────────────────────
        migrations.AddConstraint(
            model_name="objectreview",
            constraint=models.UniqueConstraint(
                fields=("diatom_object", "image"),
                name="uniq_objreview_object_image")),
        migrations.AddConstraint(
            model_name="objectreview",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_rep", True)), fields=("diatom_object",),
                name="uniq_objreview_rep")),
        migrations.AddIndex(
            model_name="objectreview",
            index=models.Index(fields=["diatom_object"],
                               name="viewer_obje_diatom__cb5fc4_idx")),
    ]
