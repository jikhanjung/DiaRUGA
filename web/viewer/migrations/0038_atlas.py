"""도감 표 셋을 세운다 — `Atlas` · `AtlasEntry` · `AtlasPlacement` (P15 · 130).

**더하기만 한다.** 있는 표를 하나도 안 건드리므로 되돌리면 표 셋이 없어질 뿐이다
— 자동 생성 그대로 두어도 되는 드문 자리다(063 이 당한 것은 이름을 바꾼 때였다).

**칸이 셋이 아니라 표가 셋인 이유**는 자리가 항목당 여럿이어서다 — Schmidt
254건이 그렇고 최다 11이다. 근거는 devlog 128 8절.

**자료는 여기 안 들어온다.** 색인 반입은 `ops/import_atlas.py` 가 따로 하고,
그것은 언제든 다시 돌릴 수 있다(P15 4.2). 마이그레이션으로 자료를 넣지 않는
것은 `0037`(분류 한 줄)과 갈리는 자리인데, **저것은 배포마다 같아야 하는
설정이고 이것은 2,059행짜리 사본**이라 그렇다.

**사람이 만든 판정은 이 표에 안 담는다** (P15 4.3) — 학명 유효성은 뒤에
`TaxonName` 으로 따로 온다.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('viewer', '0037_classdef_rhizosolenia'),
    ]

    operations = [
        migrations.CreateModel(
            name='Atlas',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=32, unique=True)),
                ('title', models.CharField(max_length=200)),
                ('short', models.CharField(max_length=40)),
                ('source', models.CharField(blank=True, db_default='', default='', max_length=200)),
                ('source_sha256', models.CharField(blank=True, db_default='', default='', max_length=64)),
                ('note', models.TextField(blank=True, db_default='', default='')),
                ('sort_order', models.IntegerField(db_default=0, default=0)),
            ],
            options={
                'verbose_name_plural': 'atlases',
                'ordering': ['sort_order', 'key'],
            },
        ),
        migrations.CreateModel(
            name='AtlasEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seq', models.PositiveIntegerField()),
                ('item_no', models.CharField(blank=True, db_default='', default='', max_length=16)),
                ('name', models.CharField(max_length=200)),
                ('genus', models.CharField(blank=True, db_default='', default='', max_length=64)),
                ('binomial', models.CharField(blank=True, db_default='', default='', max_length=120)),
                ('rank', models.CharField(choices=[('species', 'species'), ('infraspecies', 'infraspecies'), ('genus_only', 'genus_only'), ('unreadable', 'unreadable')], db_default='species', default='species', max_length=16)),
                ('infra', models.CharField(blank=True, db_default='', default='', max_length=120)),
                ('authority', models.CharField(blank=True, db_default='', default='', max_length=200)),
                ('genus_guess', models.BooleanField(db_default=False, default=False)),
                ('extra', models.JSONField(blank=True, db_default={}, default=dict)),
                ('line', models.PositiveIntegerField(db_default=0, default=0)),
                ('atlas', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='viewer.atlas')),
            ],
            options={
                'ordering': ['atlas', 'seq'],
            },
        ),
        migrations.CreateModel(
            name='AtlasPlacement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seq', models.PositiveSmallIntegerField(db_default=0, default=0)),
                ('plate', models.PositiveIntegerField(blank=True, null=True)),
                ('plate_label', models.CharField(blank=True, db_default='', default='', max_length=16)),
                ('figures', models.CharField(blank=True, db_default='', default='', max_length=120)),
                ('book_page', models.PositiveIntegerField(blank=True, null=True)),
                ('pdf_page', models.PositiveIntegerField(blank=True, null=True)),
                ('pdf_plate_page', models.PositiveIntegerField(blank=True, null=True)),
                ('volume', models.CharField(blank=True, db_default='', default='', max_length=16)),
                ('note', models.TextField(blank=True, db_default='', default='')),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='placements', to='viewer.atlasentry')),
            ],
            options={
                'ordering': ['entry', 'seq'],
            },
        ),
        migrations.AddIndex(
            model_name='atlasentry',
            index=models.Index(fields=['atlas', 'genus'], name='viewer_atla_atlas_i_563ca9_idx'),
        ),
        migrations.AddIndex(
            model_name='atlasentry',
            index=models.Index(fields=['binomial'], name='viewer_atla_binomia_921277_idx'),
        ),
        migrations.AddIndex(
            model_name='atlasentry',
            index=models.Index(fields=['genus'], name='viewer_atla_genus_f3d8b1_idx'),
        ),
        migrations.AddConstraint(
            model_name='atlasentry',
            constraint=models.UniqueConstraint(fields=('atlas', 'seq'), name='atlasentry_unique_seq'),
        ),
        migrations.AddIndex(
            model_name='atlasplacement',
            index=models.Index(fields=['volume', 'pdf_page'], name='viewer_atla_volume_9294f6_idx'),
        ),
        migrations.AddIndex(
            model_name='atlasplacement',
            index=models.Index(fields=['plate'], name='viewer_atla_plate_e9f690_idx'),
        ),
    ]
