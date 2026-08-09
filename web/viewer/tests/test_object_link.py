"""같은 개체 묶음의 스키마 약속 (P11 1단계).

사람이 프레임마다 골라 만든 것이라 **재생성 불가**다 — 약속이 깨지면 교정과
같은 무게로 잃는다. 여기서 지키는 것:

1. **한 이미지에서 하나** — 같은 프레임의 마스크 둘이 같은 개체일 수 없다
2. **한 마스크는 한 묶음에만** — 두 묶음이 같은 마스크를 물면 "이것이 어느
   개체인가" 에 답이 둘이 된다
3. **대표는 둘일 수 없다** — DB 가 막는다 (0개는 저장 쪽 약속 — check_db 가 센다)
4. **RunBatch 를 지우면 묶음이 막는다** (PROTECT) — 조용히 NULL 이 되어
   "어느 검출을 보고 한 판단인지" 를 잃으면 안 된다
"""
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from .base import DiaRUGATestCase
from . import factories as fx
from ..models import Image, ObjectLink, ObjectLinkMember, RunBatch


class ObjectLinkSchemaTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_frames=3, n_candidates=2)
        cls.batch = RunBatch.objects.get(label="sam2-시험")

    def imgs(self):
        return list(Image.objects.filter(viewpoint=self.w.vp, kind="frame")
                    .order_by("pk"))

    def make_link(self, keys=("10_10_50_50", "12_11_50_50")):
        imgs = self.imgs()
        link = ObjectLink.objects.create(viewpoint=self.w.vp, batch=self.batch)
        for i, key in enumerate(keys):
            ObjectLinkMember.objects.create(
                link=link, image=imgs[i], batch=self.batch,
                mask_key=key, is_rep=(i == 0))
        return link

    def test_묶고_대표가_선다(self):
        link = self.make_link()
        self.assertEqual(link.members.count(), 2)
        self.assertEqual(link.members.filter(is_rep=True).count(), 1)

    def test_한_이미지에서_둘은_못_묶는다(self):
        link = self.make_link()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObjectLinkMember.objects.create(
                link=link, image=self.imgs()[0], batch=self.batch,
                mask_key="99_99_20_20")

    def test_한_마스크는_한_묶음에만(self):
        self.make_link()
        other = ObjectLink.objects.create(viewpoint=self.w.vp, batch=self.batch)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObjectLinkMember.objects.create(
                link=other, image=self.imgs()[0], batch=self.batch,
                mask_key="10_10_50_50", is_rep=True)

    def test_대표는_둘일_수_없다(self):
        link = self.make_link()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObjectLinkMember.objects.create(
                link=link, image=self.imgs()[2], batch=self.batch,
                mask_key="30_30_40_40", is_rep=True)

    def test_묶음이_문_RunBatch_는_못_지운다(self):
        """PROTECT — 조용히 NULL 이 되면 어느 검출에 대한 판단인지 잃는다."""
        self.make_link()
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.batch.delete()

    def test_사람이_그린_마스크도_멤버가_된다(self):
        """batch=NULL (P09 5.2 와 같은 뜻) — 짝 제약이 그쪽도 잡는가."""
        imgs = self.imgs()
        link = ObjectLink.objects.create(viewpoint=self.w.vp, batch=self.batch)
        ObjectLinkMember.objects.create(link=link, image=imgs[0], batch=None,
                                        mask_key="5_5_30_30", is_rep=True)
        other = ObjectLink.objects.create(viewpoint=self.w.vp, batch=self.batch)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObjectLinkMember.objects.create(
                link=other, image=imgs[0], batch=None, mask_key="5_5_30_30")

    def test_시야를_지우면_묶음도_간다(self):
        """CASCADE — 시야가 사라지면 그 안의 묶음은 뜻이 없다."""
        self.make_link()
        self.w.vp.delete()
        self.assertEqual(ObjectLink.objects.count(), 0)
