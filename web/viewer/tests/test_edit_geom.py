"""엔진이 낸 마스크를 사람이 고친다 (P09 4단계 — 서버).

**`Candidate` 는 안 건드린다.** 고친 기하는 교정 행의 `geom` 에만 산다 —
검출 이력에서 엔진이 낸 것과 사람이 손댄 것을 못 가르게 되면 회차 비교가
무의미해지고, 재검출하면 어차피 사라진다 (P09 5.6).

`geom_edited` 는 **회차별 수렴 지표**다. "사람이 손댄 비율" 이 줄면 그것이
수렴이고, 기하만 조용히 덮으면 그 수를 못 센다 (P09 1).

여기서 지키는 것 셋.

1. **키가 안 바뀐다** — bbox 가 바뀌는데 키가 따라 바뀌면 옛 행이 지워지고
   새 행이 서서 분류·코멘트·이력이 끊긴다
2. **지표를 다시 잰다** — 안 재면 옛 모양의 면적·장축이 새 마스크 옆에 적힌다
3. **되돌릴 수 있다** — 빈 폴리곤이 "엔진 것으로" 다
"""
import json

from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx
from .. import data
from ..models import ObjectReview

# 픽스처 첫 개체는 (40,50,60,40). 그것을 절반으로 줄인 모양.
TIGHT = [50, 60, 80, 60, 80, 80, 50, 80]


class EditGeomTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=3)

    def setUp(self):
        self.c = Client()
        self.key = self.w.keys()[0]

    def post(self, expect=200, **over):
        p = {"stem": self.w.stem(), "slug": self.w.slug, "gid": self.w.vp.idx,
             "done": False, "removed": [], "accepted": [],
             "labels": {}, "notes": {}}
        p.update(over)
        r = self.c.post(reverse("save_review"), data=json.dumps(p),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return r

    def shown(self, key=None):
        d = data.detection_for_viewpoint(self.w.vp)
        key = key or self.key
        return next((c for c in d["candidates"] + d["removed_candidates"]
                     if data.cand_key(c) == key), None)

    # --- 고쳐지는가 --------------------------------------------------------

    def test_고친_기하가_저장된다(self):
        self.post(edits={self.key: TIGHT})
        o = ObjectReview.objects.get(mask_key=self.key)
        self.assertTrue(o.geom_edited)
        self.assertEqual(o.geom["polygon"], TIGHT)
        self.assertEqual(o.geom["bbox"], [50, 60, 30, 20])

    def test_Candidate_는_안_바뀐다(self):
        """**검출 이력이 사람 손을 타면 안 된다** (P09 5.6)."""
        before = self.w.detection().candidates.get(mask_key=self.key)
        was = (list(before.polygon), before.bbox_x, before.bbox_y,
               before.area_px)
        self.post(edits={self.key: TIGHT})
        after = self.w.detection().candidates.get(mask_key=self.key)
        self.assertEqual((list(after.polygon), after.bbox_x, after.bbox_y,
                          after.area_px), was)

    def test_키가_안_바뀐다(self):
        """bbox 가 바뀌는데 키가 따라가면 **옛 행이 지워지고 새 행이 선다** —
        분류·코멘트·이력이 끊긴다."""
        self.post(labels={self.key: "rod"}, notes={self.key: "가장자리가 넘쳤다"})
        self.post(edits={self.key: TIGHT},
                  labels={self.key: "rod"}, notes={self.key: "가장자리가 넘쳤다"})

        self.assertEqual(ObjectReview.objects.count(), 1)
        o = ObjectReview.objects.get()
        self.assertEqual(o.mask_key, self.key, "키가 바뀌었다")
        self.assertEqual(o.label, "rod")
        self.assertEqual(o.note, "가장자리가 넘쳤다")

    def test_저장_직후에_안_지워진다(self):
        """고친 기하도 **표시**다. `keys` 에 안 들어가면 같은 저장의 마지막 줄이
        "표시가 사라진 행" 으로 보고 지운다."""
        self.post(edits={self.key: TIGHT})
        self.assertTrue(ObjectReview.objects.filter(mask_key=self.key).exists())

    # --- 화면이 고친 것을 보여주는가 ---------------------------------------

    def test_화면이_고친_기하를_그린다(self):
        self.post(edits={self.key: TIGHT})
        c = self.shown()
        self.assertEqual(c["polygon"], TIGHT)
        self.assertEqual(c["bbox_xywh"], [50, 60, 30, 20])
        self.assertTrue(c["geom_edited"])

    def test_지표를_다시_잰다(self):
        """안 재면 **옛 모양의 면적·장축이 새 마스크 옆에 적힌다.**"""
        before = self.shown()
        self.post(edits={self.key: TIGHT})
        after = self.shown()
        self.assertNotEqual(after["area_px"], before["area_px"])
        self.assertEqual(after["area_px"], 30 * 20)
        self.assertIsNotNone(after["area_um2"])

    def test_텍스처는_엔진_값을_그대로_둔다(self):
        """픽셀이 있어야 나오는 값이라 여기서 못 잰다 — 버리면 정보만 잃는다.
        섞였다는 사실은 `geom_edited` 가 말한다."""
        before = self.shown()
        self.post(edits={self.key: TIGHT})
        self.assertEqual(self.shown()["texture"], before["texture"])

    # --- 되돌릴 수 있는가 --------------------------------------------------

    def test_빈_폴리곤은_엔진_것으로_되돌린다(self):
        self.post(edits={self.key: TIGHT})
        self.post(edits={self.key: []})

        o = ObjectReview.objects.get(mask_key=self.key)
        self.assertFalse(o.geom_edited)
        cand = self.w.detection().candidates.get(mask_key=self.key)
        self.assertEqual(o.geom["polygon"], list(cand.polygon))
        c = self.shown()
        self.assertEqual(c["polygon"], list(cand.polygon))
        self.assertIsNone(c.get("geom_edited"))

    def test_되돌릴_엔진_개체가_없으면_거절한다(self):
        """고아에는 되돌릴 원본이 없다 — 지우면 그릴 것이 없어진다."""
        det = self.w.detection()
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image=det.image, batch=det.batch,
            mask_key="900_900_50_50", bind_method="orphan",
            geom={"bbox": [900, 900, 50, 50],
                  "polygon": [900, 900, 950, 900, 950, 950]})
        self.post(expect=409, edits={"900_900_50_50": []})

    # --- 못 받을 것은 오류로 ----------------------------------------------

    def test_점이_모자라면_거절한다(self):
        self.post(expect=409, edits={self.key: [50, 60, 80, 60]})
        self.assertEqual(ObjectReview.objects.count(), 0)

    def test_이미지_밖이면_거절한다(self):
        far = [9000, 9000, 9060, 9000, 9060, 9040, 9000, 9040]
        self.post(expect=409, edits={self.key: far})
        self.assertEqual(ObjectReview.objects.count(), 0)

    def test_그리기와_같은_검사를_지난다(self):
        """검사가 갈라지면 **한쪽으로만 들어오는 값**이 생긴다."""
        bad = [50, 60, 80, 60]
        self.post(expect=409, edits={self.key: bad})
        self.post(expect=409, drawn=[{"key": "m0a1b2c3", "polygon": bad,
                                      "cls": "", "note": ""}])
