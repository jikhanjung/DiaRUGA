"""검토 완료가 남은 통과분에 서명한다 (`materialize_passed` · 2026-08-11).

지금까지 "이건 규조각이 맞다" 는 판단은 **행의 부재로만** 기록됐다. 사람이
틀린 것을 지우고 완료를 누르면 남은 것이 곧 맞다고 본 것인데 DB 에는 아무것도
안 남아, 학습 자료의 양성 표본이 암묵적이고 개체 수에 통과분이 안 잡혔다.

여기서 지키는 것:

1. 완료를 눌러야 선다 (그냥 저장으로는 안 선다)
2. **사람이 지운 것·판단한 것은 안 건드린다**
3. 서명한 행이 **다음 저장의 청소에 안 지워진다** — 화면은 `confirmed` 를 모른다
4. 두 번 눌러도 늘지 않는다
5. 시야의 **모든 판**에 선다 (완료 표시가 시야 단위라 그 주장도 시야 단위다)
"""
import json

from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx
from ..models import DiatomObject, ObjectReview


class ConfirmPassedTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_frames=3, n_candidates=3)

    def setUp(self):
        self.c = Client()
        self.det = self.w.detection()
        # **통과분만 본다.** 픽스처는 탈락 후보도 하나 세우는데, 서명은
        # 통과분에만 선다(되살리는 것은 사람이 눌러서 하는 일이다).
        self.keys = sorted(c.mask_key for c in self.det.candidates.all()
                           if c.passed)
        self.reject = next(c.mask_key for c in self.det.candidates.all()
                           if not c.passed)

    def post(self, expect=200, **over):
        p = {"stem": self.w.stem(), "slug": self.w.slug, "gid": self.w.vp.idx,
             "done": False, "removed": [], "accepted": [],
             "labels": {}, "notes": {}}
        p.update(over)
        r = self.c.post(reverse("save_review"), data=json.dumps(p),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return json.loads(r.content)

    def confirmed(self):
        return set(ObjectReview.objects.filter(confirmed=True)
                   .values_list("mask_key", flat=True))

    def test_완료를_눌러야_선다(self):
        self.post()
        self.assertEqual(self.confirmed(), set(), "완료도 안 눌렀는데 섰다")
        out = self.post(done=True)
        self.assertEqual(self.confirmed(), set(self.keys))
        self.assertEqual(out.get("confirmed"), len(self.keys))
        self.assertNotIn(self.reject, self.confirmed(),
                         "탈락 후보에 서명했다 — 되살리는 것은 사람이 한다")

    def test_지운_것에는_안_선다(self):
        gone = self.keys[0]
        self.post(done=True, removed=[gone])
        self.assertNotIn(gone, self.confirmed(), "지운 마스크에 서명했다")
        self.assertIn(self.keys[1], self.confirmed())

    def test_사람이_판단한_행은_안_건드린다(self):
        """분류를 붙인 행은 이미 사람의 것이다 — 서명이 그 위에 덮이면 안 된다."""
        self.post(done=True, labels={self.keys[0]: "rod"})
        row = ObjectReview.objects.get(mask_key=self.keys[0])
        self.assertEqual(row.label, "rod")
        self.assertFalse(row.confirmed,
                         "이미 판단이 있는 행에까지 서명을 얹었다")

    def test_다음_저장의_청소가_안_지운다(self):
        """**화면은 `confirmed` 를 모른다.** payload 에 안 실리므로 얹어 두지
        않으면 다음 저장이 "표시가 사라진 행" 으로 보고 지운다."""
        self.post(done=True)
        n = len(self.confirmed())
        self.assertEqual(n, len(self.keys))
        self.post()                      # 아무것도 안 담긴 평범한 저장
        self.assertEqual(len(self.confirmed()), n, "청소가 서명을 지웠다")

    def test_두_번_눌러도_안_는다(self):
        self.post(done=True)
        n_rows = ObjectReview.objects.count()
        n_obj = DiatomObject.objects.count()
        out = self.post(done=True)
        self.assertEqual(ObjectReview.objects.count(), n_rows)
        self.assertEqual(DiatomObject.objects.count(), n_obj)
        self.assertIsNone(out.get("confirmed"), "두 번째에도 새로 세웠다")

    def test_시야의_모든_판에_선다(self):
        """완료 표시는 `(시야, 묶음)` 단위라 그 주장도 시야 단위다 — 프레임
        넷 중 하나만 서명되면 안 된다."""
        fx.add_frame_detections(self.w.vp)
        self.post(done=True)
        imgs = set(ObjectReview.objects.filter(confirmed=True)
                   .values_list("image_id", flat=True))
        self.assertGreater(len(imgs), 1, "한 판에만 섰다")

    def test_개체가_함께_선다(self):
        """서명한 마스크는 개체를 갖는다 — 그래야 프레임에 겹쳐 잡힌 것을
        하나로 세는 층이 통과분 위에도 얹힌다."""
        self.post(done=True)
        for row in ObjectReview.objects.filter(confirmed=True):
            self.assertIsNotNone(row.diatom_object_id)
            self.assertTrue(row.is_rep, "1:1 개체인데 대표가 아니다")
