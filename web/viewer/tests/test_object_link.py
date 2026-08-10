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


class LinkRejectedCandidateTest(DiaRUGATestCase):
    """탈락 후보를 묶으면 되살아난다 (102 · 사용자 요청).

    P11 §4 는 "탈락 후보는 1판에서 뺀다 — 묶기(정체)와 되살리기(판정)를 한
    팝업에서 겹치면 저장 의미가 복잡해진다" 로 미뤄 뒀다. 실제로 쓰다 보니
    **그 프레임에서 가장 좋은 마스크가 문턱에서 떨어져 있는 일**이 있어서
    열었다 — 다만 "고르면 되살아난다" 를 화면이 먼저 말하고, 서버가 행 하나만
    좁게 세운다.
    """

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_frames=3, n_candidates=2)
        cls.batch = RunBatch.objects.get(label="sam2-시험")
        cls.stack_img = Image.objects.get(viewpoint=cls.w.vp, kind="stack")
        cls.frame_img = Image.objects.filter(viewpoint=cls.w.vp,
                                             kind="frame").order_by("pk").first()
        # 프레임에 **탈락한** 후보 하나 (passed=False)
        from ..models import Candidate, Detection, Run
        from .factories import IMG_H, IMG_W
        run = Run.objects.create(kind="detect", batch=cls.batch,
                                 slide=cls.w.slide, status="done")
        det = Detection.objects.create(
            viewpoint=cls.w.vp, image=cls.frame_img,
            image_path=cls.frame_img.path, width=IMG_W, height=IMG_H,
            scale=1.0, um_per_pixel=0.1, run=run, is_current=True)
        cls.rej = Candidate.objects.create(
            detection=det, raw_id=0, mask_key="40_50_60_40",
            bbox_x=40, bbox_y=50, bbox_w=60, bbox_h=40,
            center_x=70, center_y=70, area_px=1200, area_um2=6.0,
            major_um=6.0, minor_um=4.0, long_side_um=6.0, short_side_um=4.0,
            aspect_ratio=1.5, fill_ratio=0.6, shape_ok=True, circularity=0.8,
            convexity=0.9, solidity=0.9, elongation=1.5, ellipse_iou=0.85,
            texture=100.0, predicted_iou=0.9, stability_score=0.9,
            polygon=[40, 50, 100, 50, 100, 90, 40, 90],
            passed=False, reject="텍스처부족")

    def setUp(self):
        from django.test import Client
        self.c = Client()
        self.url = f"/d/{self.w.slide.slug}/g/{self.w.vp.idx}/link"

    def post(self, members):
        import json as _json
        return self.c.post(self.url, _json.dumps({"members": members}),
                           content_type="application/json")

    def members(self):
        return [
            {"image": self.stack_img.pk, "mask_key": self.w.keys()[0],
             "rep": True},
            {"image": self.frame_img.pk, "mask_key": "40_50_60_40",
             "rep": False},
        ]

    def test_탈락_후보를_묶으면_되살아난다(self):
        r = self.post(self.members())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()["revived"], 1)
        row = ObjectReview.objects.get(image=self.frame_img,
                                       mask_key="40_50_60_40")
        self.assertTrue(row.accepted, "되살아나지 않았다")
        self.assertFalse(row.removed)
        # 묶음에도 멤버로 섰다
        self.assertEqual(ObjectLink.objects.get().members.count(), 2)

    def test_통과분만_묶으면_되살릴_것이_없다(self):
        """되살리기가 **탈락분에서만** 일어나는가 — 통과분까지 손대면
        `accepted` 가 뜻을 잃는다(사람이 되살린 것이 아니다)."""
        from ..models import Candidate
        # 프레임에 통과 후보를 하나 더 세운다 — 탈락분과 같은 검출에
        # **`mask_key` 만으로 짚지 않는다** — 팩토리의 합성본 후보가 같은 키를
        # 쓸 수 있다(실제로 그래서 MultipleObjectsReturned 가 났다). 이 시험이
        # 세운 프레임 쪽 탈락분에서 검출을 얻는다.
        det = self.rej.detection
        Candidate.objects.create(
            detection=det, raw_id=1, mask_key="200_200_50_50",
            bbox_x=200, bbox_y=200, bbox_w=50, bbox_h=50,
            center_x=225, center_y=225, area_px=1250, area_um2=6.2,
            major_um=5.0, minor_um=5.0, long_side_um=5.0, short_side_um=5.0,
            aspect_ratio=1.0, fill_ratio=0.6, shape_ok=True, circularity=0.9,
            convexity=0.9, solidity=0.9, elongation=1.0, ellipse_iou=0.9,
            texture=3000.0, predicted_iou=0.9, stability_score=0.9,
            polygon=[200, 200, 250, 200, 250, 250, 200, 250],
            passed=True, cls="round")
        ms = self.members()
        ms[1]["mask_key"] = "200_200_50_50"          # 통과분으로 바꾼다
        r = self.post(ms)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()["revived"], 0, "통과분을 되살렸다")
        self.assertFalse(
            ObjectReview.objects.filter(mask_key="200_200_50_50").exists(),
            "통과분에 교정 행을 만들었다")

    def test_이미_붙어_있는_분류는_안_덮는다(self):
        """되살리기는 다른 축의 판단을 건드리지 않는다."""
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image=self.frame_img, batch=self.batch,
            mask_key="40_50_60_40", label="rod", note="사람이 적었다",
            geom={"bbox_xywh": [40, 50, 60, 40]})
        r = self.post(self.members())
        self.assertEqual(r.status_code, 200, r.content[:300])
        row = ObjectReview.objects.get(image=self.frame_img,
                                       mask_key="40_50_60_40")
        self.assertTrue(row.accepted)
        self.assertEqual(row.label, "rod", "분류가 덮였다")
        self.assertEqual(row.note, "사람이 적었다", "코멘트가 덮였다")

    def test_지운_탈락분은_여전히_거절한다(self):
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image=self.frame_img, batch=self.batch,
            mask_key="40_50_60_40", removed=True,
            geom={"bbox_xywh": [40, 50, 60, 40]})
        r = self.post(self.members())
        self.assertEqual(r.status_code, 400)
        self.assertIn("지운", r.json()["error"])


class LinkLabelSpreadTest(DiaRUGATestCase):
    """묶인 개체는 **분류를 함께 받는다** (사용자 요청 2026-08-10).

    묶음은 "이 판들의 이것이 같은 개체다" 라는 말이다. 그런데 분류는 판마다
    따로 앉아 있어서, 한 판에서 봉상이라고 정해도 나머지는 그대로였다 —
    사람이 판 수만큼 같은 판단을 되풀이해야 하고, 되풀이하다 하나를 빠뜨리면
    **묶음 안에서 분류가 어긋난다**(학습 자료에서는 모순이다).

    여기서 지키는 것:

    1. 한 판에서 정하면 나머지 판에 같은 분류가 앉는다
    2. **물리는 것도 번진다** — 한 판만 지정이 남아 있으면 안 된다
    3. 분류 말고는 안 건드린다 — 삭제·되살림·코멘트는 판마다 따로 하는 판단이다
    4. 묶이지 않은 개체는 아무 데도 안 번진다
    """

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_frames=3, n_candidates=2)
        cls.batch = RunBatch.objects.get(label="sam2-시험")
        cls.extra = fx.add_frame_detections(cls.w.vp)
        cls.stack_img = Image.objects.get(viewpoint=cls.w.vp, kind="stack")
        cls.f1_img = cls.extra[0][1]
        cls.f2_img = cls.extra[1][1]

    def setUp(self):
        from django.test import Client
        self.c = Client()
        self.key = self.w.keys()[0]
        self.other = self.w.keys()[1]
        # 합성본·프레임 둘을 한 개체로 묶는다. 픽스처가 판마다 같은 자리에
        # 후보를 세우므로 `mask_key` 가 그대로 맞는다.
        self.link = ObjectLink.objects.create(viewpoint=self.w.vp,
                                              batch=self.batch)
        for i, img in enumerate((self.stack_img, self.f1_img, self.f2_img)):
            ObjectLinkMember.objects.create(
                link=self.link, image=img, batch=self.batch,
                mask_key=self.key, is_rep=(i == 0),
                geom={"bbox_xywh": [40, 50, 60, 40]})

    def save(self, labels, image=None, **over):
        import json as _json
        payload = {"stem": self.w.stem(), "slug": self.w.slide.slug,
                   "gid": self.w.vp.idx, "done": False,
                   "removed": [], "accepted": [], "notes": {},
                   "labels": labels,
                   "image": image or self.stack_img.pk}
        payload.update(over)
        from django.urls import reverse
        r = self.c.post(reverse("save_review"), _json.dumps(payload),
                        content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def label_of(self, img):
        row = ObjectReview.objects.filter(image=img, mask_key=self.key).first()
        return row.label if row else None

    # --- 1. 번진다 ----------------------------------------------------------

    def test_한_판에서_정하면_나머지_판도_같은_분류다(self):
        self.save({self.key: "rod"})
        self.assertEqual(self.label_of(self.stack_img), "rod")
        self.assertEqual(self.label_of(self.f1_img), "rod",
                         "묶인 판에 분류가 안 번졌다")
        self.assertEqual(self.label_of(self.f2_img), "rod")

    def test_화면에_알려_준다(self):
        """다른 판의 상태는 화면이 열릴 때 받은 것이라, 안 알려 주면 그 판의
        다음 저장이 도로 지운다 — 뷰어는 늘 전체를 보낸다."""
        out = self.save({self.key: "rod"})
        linked = out.get("linked") or {}
        self.assertIn(str(self.f1_img.pk), linked)
        self.assertEqual(linked[str(self.f1_img.pk)][self.key], "rod")
        self.assertNotIn(str(self.stack_img.pk), linked,
                         "내가 보낸 판까지 되돌려줄 이유가 없다")

    def test_프레임에서_정해도_합성본으로_번진다(self):
        """방향이 없다 — 어느 판에서 정하든 묶음 전체가 같아진다."""
        self.save({self.key: "round"}, image=self.f1_img.pk,
                  stem=self.f1_img.path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
        self.assertEqual(self.label_of(self.stack_img), "round")
        self.assertEqual(self.label_of(self.f2_img), "round")

    # --- 2. 물리는 것도 번진다 ---------------------------------------------

    def test_지정을_물리면_다른_판에서도_지워진다(self):
        self.save({self.key: "rod"})
        self.save({})
        self.assertIsNone(self.label_of(self.f1_img),
                          "한 판만 지정이 남았다 — 묶음 안에서 어긋난다")
        self.assertFalse(
            ObjectReview.objects.filter(image=self.f1_img,
                                        mask_key=self.key).exists(),
            "표시가 하나도 없는 빈 껍데기가 남았다")

    def test_다른_표시가_있으면_행은_남는다(self):
        """분류만 지운다 — 그 판에서 따로 한 판단은 그대로여야 한다."""
        self.save({self.key: "rod"})
        row = ObjectReview.objects.get(image=self.f1_img, mask_key=self.key)
        row.note = "이 판이 제일 선명하다"
        row.save()

        self.save({})
        row.refresh_from_db()
        self.assertEqual(row.label, "")
        self.assertEqual(row.note, "이 판이 제일 선명하다",
                         "분류를 물리면서 남의 코멘트를 지웠다")

    # --- 3·4. 넘지 않는 선 --------------------------------------------------

    def test_삭제는_안_번진다(self):
        """묶음은 정체(같은 개체)에 대한 말이고, 오검출 판정은 판마다 다르다 —
        한 프레임에서만 흐릿하게 잡힌 것을 지울 수 있어야 한다."""
        self.save({}, removed=[self.key])
        self.assertTrue(ObjectReview.objects
                        .get(image=self.stack_img, mask_key=self.key).removed)
        row = ObjectReview.objects.filter(image=self.f1_img,
                                          mask_key=self.key).first()
        self.assertTrue(row is None or not row.removed,
                        "삭제가 다른 판으로 번졌다")

    def test_안_묶인_개체는_안_번진다(self):
        self.save({self.other: "rod"})
        self.assertIsNone(self.label_of(self.f1_img))
        self.assertFalse(ObjectReview.objects
                         .filter(image=self.f1_img, mask_key=self.other)
                         .exists())
