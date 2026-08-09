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
from ..models import (Image, ObjectLink, ObjectLinkMember, ObjectReview,
                      RunBatch)


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


class SaveLinkEndpointTest(DiaRUGATestCase):
    """묶음 저장 endpoint (P11 2단계).

    **서버가 다시 검사한다** — 화면에서 막는 것은 막는 것이 아니다(027).
    여기서 어겨 보는 것: 남의 시야 이미지 · 없는 마스크 · 지운 마스크 ·
    대표 0/2개 · 멤버 1개 · 다른 묶음에 이미 속한 마스크.
    """

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_frames=3, n_candidates=2)
        cls.batch = RunBatch.objects.get(label="sam2-시험")
        # 프레임에도 같은 묶음의 검출을 세운다 — 캐러셀·묶기가 성립하는 모양
        from ..models import Detection, Run
        run = Run.objects.create(kind="detect", batch=cls.batch,
                                 slide=cls.w.slide, status="done")
        cls.frame_imgs = list(Image.objects.filter(viewpoint=cls.w.vp,
                                                   kind="frame").order_by("pk"))
        from .factories import IMG_W, IMG_H
        from ..models import Candidate
        for img in cls.frame_imgs[:2]:
            det = Detection.objects.create(
                viewpoint=cls.w.vp, image=img, image_path=img.path,
                width=IMG_W, height=IMG_H, scale=1.0, um_per_pixel=0.1,
                run=run, is_current=True)
            Candidate.objects.create(
                detection=det, raw_id=0, mask_key="40_50_60_40",
                bbox_x=40, bbox_y=50, bbox_w=60, bbox_h=40,
                center_x=70, center_y=70, area_px=1200, area_um2=6.0,
                major_um=6.0, minor_um=4.0, long_side_um=6.0,
                short_side_um=4.0, aspect_ratio=1.5, fill_ratio=0.6,
                shape_ok=True, circularity=0.8, convexity=0.9, solidity=0.9,
                elongation=1.5, ellipse_iou=0.85, texture=3000.0,
                predicted_iou=0.9, stability_score=0.9,
                polygon=[40, 50, 100, 50, 100, 90, 40, 90],
                passed=True, cls="rod")
        cls.stack_img = Image.objects.get(viewpoint=cls.w.vp, kind="stack")

    def setUp(self):
        from django.test import Client
        self.c = Client()
        self.url = f"/d/{self.w.slide.slug}/g/{self.w.vp.idx}/link"

    def post(self, body):
        import json as _json
        return self.c.post(self.url, _json.dumps(body),
                           content_type="application/json")

    def good_members(self):
        return [
            {"image": self.stack_img.pk, "mask_key": "40_50_60_40",
             "rep": True},
            {"image": self.frame_imgs[0].pk, "mask_key": "40_50_60_40",
             "rep": False},
        ]

    def test_묶고_기하가_스스로_선다(self):
        r = self.post({"members": self.good_members()})
        self.assertEqual(r.status_code, 200, r.content[:200])
        link = ObjectLink.objects.get()
        self.assertEqual(link.viewpoint, self.w.vp)
        m = link.members.get(is_rep=True)
        # **기하는 서버가 뜬다** — 화면이 보낸 것을 믿지 않는다
        self.assertEqual(m.geom["bbox_xywh"], [40, 50, 60, 40])
        self.assertTrue(m.geom["polygon"])

    def test_고치면_갈아끼운다(self):
        self.post({"members": self.good_members()})
        link = ObjectLink.objects.get()
        ms = self.good_members()
        ms.append({"image": self.frame_imgs[1].pk,
                   "mask_key": "40_50_60_40", "rep": False})
        r = self.post({"link_id": link.pk, "members": ms})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(ObjectLink.objects.count(), 1)
        self.assertEqual(link.members.count(), 3)

    def test_푼다(self):
        self.post({"members": self.good_members()})
        link = ObjectLink.objects.get()
        r = self.post({"act": "unlink", "link_id": link.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ObjectLink.objects.count(), 0)

    def test_남의_시야_이미지는_거절한다(self):
        other = fx.make_world(slug="wap13", site_code="WAP13",
                              loc_code="GC47", sample_code="116cm",
                              depth_cm=116.0)
        stranger = Image.objects.filter(viewpoint=other.vp).first()
        ms = self.good_members()
        ms[1]["image"] = stranger.pk
        r = self.post({"members": ms})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ObjectLink.objects.count(), 0)

    def test_없는_마스크는_거절한다(self):
        ms = self.good_members()
        ms[1]["mask_key"] = "1_1_1_1"
        self.assertEqual(self.post({"members": ms}).status_code, 400)

    def test_지운_마스크는_거절한다(self):
        """오검출로 지운 것을 묶으면 "오검출이면서 실재한다" 가 된다."""
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image=self.frame_imgs[0], batch=self.batch,
            mask_key="40_50_60_40", removed=True,
            geom={"bbox_xywh": [40, 50, 60, 40]})
        r = self.post({"members": self.good_members()})
        self.assertEqual(r.status_code, 400)
        self.assertIn("지운", r.json()["error"])

    def test_대표가_없거나_둘이면_거절한다(self):
        for reps in ((False, False), (True, True)):
            ms = self.good_members()
            ms[0]["rep"], ms[1]["rep"] = reps
            with self.subTest(reps=reps):
                self.assertEqual(self.post({"members": ms}).status_code, 400)

    def test_혼자인_묶음은_거절한다(self):
        r = self.post({"members": self.good_members()[:1]})
        self.assertEqual(r.status_code, 400)

    def test_이미_묶인_마스크는_409_다(self):
        self.post({"members": self.good_members()})
        ms = [
            {"image": self.frame_imgs[0].pk, "mask_key": "40_50_60_40",
             "rep": True},                          # ← 이미 첫 묶음의 멤버
            {"image": self.frame_imgs[1].pk, "mask_key": "40_50_60_40",
             "rep": False},
        ]
        r = self.post({"members": ms})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(ObjectLink.objects.count(), 1)

    def test_사람이_그린_마스크도_묶인다(self):
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image=self.frame_imgs[1], batch=None,
            mask_key="7_7_30_30", source="manual",
            geom={"bbox_xywh": [7, 7, 30, 30],
                  "polygon": [7, 7, 37, 7, 37, 37, 7, 37]})
        ms = self.good_members()
        ms.append({"image": self.frame_imgs[1].pk, "mask_key": "7_7_30_30",
                   "rep": False})
        r = self.post({"members": ms})
        self.assertEqual(r.status_code, 200, r.content[:200])
        m = ObjectLink.objects.get().members.get(mask_key="7_7_30_30")
        self.assertIsNone(m.batch_id)

    def test_GET_은_안_받는다(self):
        self.assertEqual(self.c.get(self.url).status_code, 405)
