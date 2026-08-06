"""시야 하나에 **현재 검출이 여럿**일 때 (P09 1단계).

합성본에 하나 + 프레임마다 하나다. YOLO 는 합성본이 아니라 원본 프레임을 보므로
`yolo-3차` 를 current 로 올리면 그 모양이 된다 — 실측으로 시야 452개에 프레임
검출 1,310개, 합성본 검출 314개다(P09 4.1).

**운영 DB 에는 아직 그 상태가 없다.** 그래서 "시야마다 이미지가 하나" 를 전제한
코드가 지금 전부 통과한다. 여기서 그 전제를 깨 놓고 본다 — 갈아타는 날 한꺼번에
드러나면 잃는 것이 재생성 불가한 교정이다.

세 가지를 못 박는다.

1. 화면이 **그 이미지의 검출**을 본다 (아무거나가 아니라)
2. **다른 이미지의 교정이 얹혀 보이지 않는다** — 합성본과 프레임은 같은 시야라
   좌표계가 같아서 `mask_key` 가 실제로 맞는다. 45%가 겹친다는 실측이 있다
3. 저장이 **그 이미지에만** 걸린다 — 마지막 줄이 범위를 갈아치우므로 여기가
   틀리면 017·027·053 과 같은 자리가 된다
"""
import json

from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx
from .. import data
from ..models import ObjectReview


class MultiImageViewpointTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_frames=3, n_candidates=3)
        cls.extra = fx.add_frame_detections(cls.w.vp)

    def setUp(self):
        self.c = Client()
        self.vp = self.w.vp
        self.stack_det = self.w.detection()
        self.frame, self.frame_img, self.frame_det = self.extra[0]

    def post(self, payload, expect=200):
        r = self.c.post(reverse("save_review"), data=json.dumps(payload),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return r

    def full(self, **over):
        p = {"stem": self.w.stem(), "slug": self.w.slug, "gid": self.vp.idx,
             "done": False, "removed": [], "accepted": [],
             "labels": {}, "notes": {}}
        p.update(over)
        return p

    # --- 픽스처가 진짜 그 상태인가 -----------------------------------------

    def test_현재_검출이_여럿이다(self):
        dets = data.current_detections(self.vp)
        self.assertEqual(len(dets), 4, "합성본 1 + 프레임 3")
        kinds = sorted(d.image.kind for d in dets)
        self.assertEqual(kinds, ["frame", "frame", "frame", "stack"])

    # --- 대표 이미지 (집계가 세는 것) --------------------------------------

    def test_대표는_합성본이다(self):
        """**집계는 시야마다 하나에서 낸다** (P09 5.3).

        다 세면 같은 규조각이 4.6번 세어져 밀도가 그만큼 부푼다.
        """
        rep = data.representative_detection(self.vp)
        self.assertEqual(rep.image.kind, "stack")
        self.assertEqual(rep.pk, self.stack_det.pk)

    def test_합성본이_없으면_그_프레임이_대표다(self):
        w = fx.make_world(slug="single", with_stack=False, n_frames=1)
        rep = data.representative_detection(w.vp)
        self.assertEqual(rep.image.kind, "frame")

    # --- 어느 이미지의 검출을 그리는가 --------------------------------------

    def test_이미지를_주면_그_이미지의_검출을_낸다(self):
        d = data.detection_for_viewpoint(self.vp, image=self.frame_img)
        self.assertEqual(d["image"], self.frame_img.path)

    def test_안_주면_대표_이미지의_것이다(self):
        d = data.detection_for_viewpoint(self.vp)
        self.assertEqual(d["image"], self.stack_det.image.path)

    # --- 교정이 새어 들지 않는가 -------------------------------------------

    def test_합성본_교정이_프레임_화면에_안_얹힌다(self):
        """**같은 좌표계라 `mask_key` 가 실제로 맞는다** — 우연이 아니다.

        픽스처가 두 검출에 같은 bbox 를 쓰므로 키가 그대로 겹친다. 거르지 않으면
        합성본에서 "지웠다" 고 한 것이 프레임 화면에서도 지워져 보인다.
        """
        k = self.w.keys()[0]
        self.assertIn(k, [c.mask_key for c in self.frame_det.candidates.all()],
                      "픽스처 전제가 깨졌다 — 키가 안 겹치면 시험이 무의미하다")

        fx.add_review(self.vp, k, removed=True)      # 합성본 위의 판단

        on_stack = data.detection_for_viewpoint(self.vp)
        on_frame = data.detection_for_viewpoint(self.vp, image=self.frame_img)
        self.assertEqual(on_stack["n_removed"], 1,
                         "합성본에서는 지워져 보여야 한다")
        self.assertEqual(on_frame["n_removed"], 0,
                         "합성본 교정이 프레임 화면에 얹혔다")
        self.assertIn(k, [data.cand_key(c) for c in on_frame["candidates"]],
                      "프레임 화면에서는 살아 있는 개체로 보여야 한다")

    # --- 저장이 그 이미지에만 걸리는가 --------------------------------------

    def test_프레임에_저장하면_프레임_이미지에_앉는다(self):
        k = self.w.keys()[0]
        self.post(self.full(image=self.frame_img.pk, labels={k: "rod"}))
        obj = ObjectReview.objects.get(mask_key=k, label="rod")
        self.assertEqual(obj.image_id, self.frame_img.pk)

    def test_프레임_저장이_합성본_교정을_안_지운다(self):
        """마지막 줄이 범위를 갈아치운다 — **여기가 017·027·053 의 자리다.**"""
        k = self.w.keys()[0]
        on_stack = fx.add_review(self.vp, k, removed=True)

        self.post(self.full(image=self.frame_img.pk))   # 프레임에 빈 목록

        self.assertTrue(ObjectReview.objects.filter(pk=on_stack.pk).exists(),
                        "프레임 화면의 저장이 합성본 교정을 지웠다")

    def test_합성본_저장이_프레임_교정을_안_지운다(self):
        k = self.w.keys()[0]
        self.post(self.full(image=self.frame_img.pk, labels={k: "rod"}))
        on_frame = ObjectReview.objects.get(image=self.frame_img)

        self.post(self.full(image=self.stack_det.image_id))   # 합성본에 빈 목록

        self.assertTrue(ObjectReview.objects.filter(pk=on_frame.pk).exists(),
                        "합성본 화면의 저장이 프레임 교정을 지웠다")

    def test_이미지를_안_주면_대표에_앉는다(self):
        """옛 화면(배포 중에 열려 있던 탭)이 그렇다 — 예전과 결과가 같다."""
        k = self.w.keys()[0]
        self.post(self.full(labels={k: "rod"}))
        self.assertEqual(ObjectReview.objects.get(mask_key=k, label="rod")
                         .image_id, self.stack_det.image_id)

    # --- 짚은 것이 이 시야의 것인가 -----------------------------------------

    def test_남의_이미지를_짚으면_거절한다(self):
        """**조용히 대표에 앉히지 않는다.** 사람이 보고 있던 것과 다른 자리에
        판단이 쌓이면 무엇을 검토했는지 알 수 없게 된다.
        """
        other = fx.make_world(slug="남의것", n_frames=1)
        r = self.post(self.full(image=other.detection().image_id,
                                labels={self.w.keys()[0]: "rod"}), expect=409)
        self.assertIn("현재 검출이 없다", r.json()["error"])
        self.assertEqual(ObjectReview.objects.count(), 0)

    def test_다른_이미지의_키는_받지_않는다(self):
        """`mask_key` 는 프레임끼리 45% 겹친다 — 통과하면 엉뚱한 행이 남는다."""
        alien = "9999_9999_10_10"
        self.post(self.full(image=self.frame_img.pk, removed=[alien]),
                  expect=409)
        self.assertEqual(ObjectReview.objects.count(), 0)
