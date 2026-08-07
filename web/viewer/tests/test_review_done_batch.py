"""검토 완료는 **묶음마다**, 시야 코멘트는 **시야마다** (073).

`ObjectReview` 와 같은 가름이다(P09 5.2) — 무엇에 대한 판단인가로 나눈다.

| 칸 | 무엇에 대한 판단인가 | 속하는 곳 |
|---|---|---|
| `done` | 이 묶음이 낸 검출을 여기서 다 봤다 | **batch** |
| `note` | 이 시야가 이러이러하다 | 시야 — batch 를 갈아도 참이다 |

`done` 을 시야에 매달아 두었더니 `sam2-전수` 를 검토하고 붙인 완료 표시가
`yolo-3차` 화면에도 그대로 붙었다. **아직 아무도 안 본 검출이 "검토 완료" 로
보이고, "다음 미검토" 가 그 시야를 건너뛴다** — 그 시야는 다시 열리지 않는다.

코멘트를 함께 묶음에 매달지 않은 이유는 하나다: **사람이 쓴 글은 재생성
불가다.** 묶음을 갈 때마다 사라지면 안 된다.
"""
from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx
from .. import data, manage_data
from ..models import Detection, RunBatch, ViewpointReview


class ReviewDoneBelongsToBatchTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_viewpoints=2, n_candidates=3)
        cls.vp = cls.w.vp
        cls.yolo = fx.add_other_engine(cls.vp, label="yolo-시험")
        Detection.objects.filter(run=cls.yolo).update(is_current=True)

    def setUp(self):
        self.c = Client()

    def sam(self):
        return RunBatch.objects.get(label="sam2-시험")

    def switch(self, batch):
        ok, msg = manage_data.set_review_batch(batch.pk)
        self.assertTrue(ok, msg)

    def mark_done(self, note=""):
        """화면이 하는 그대로 — 저장이 완료 표시를 함께 나른다."""
        return data.save_review(self.vp, done=True, note=note,
                                removed=set(), accepted=set(),
                                labels={}, notes={},
                                image=None)

    # --- 완료는 묶음을 안 넘어간다 ------------------------------------------

    def test_한_묶음에서_완료해도_다른_묶음은_미검토다(self):
        """**여기가 고장 났던 자리다.**"""
        self.mark_done()
        self.assertTrue(data.review_state(self.vp)[0])

        self.switch(self.yolo.batch)
        self.assertFalse(data.review_state(self.vp)[0],
                         "안 본 묶음인데 검토 완료로 보인다")

    def test_돌아오면_완료가_그대로다(self):
        self.mark_done()
        self.switch(self.yolo.batch)
        self.switch(self.sam())
        self.assertTrue(data.review_state(self.vp)[0], "완료 표시가 사라졌다")

    def test_묶음마다_줄이_따로_선다(self):
        self.mark_done()
        self.switch(self.yolo.batch)
        self.mark_done()
        rows = ViewpointReview.objects.filter(viewpoint=self.vp, done=True)
        self.assertEqual(
            sorted(r.batch.label for r in rows),
            ["sam2-시험", "yolo-시험"])

    # --- 코멘트는 묶음을 넘어간다 ------------------------------------------

    def test_코멘트는_묶음을_갈아도_남는다(self):
        """**사람이 쓴 글이라 재생성 불가다.**"""
        self.mark_done(note="이 시야는 초점이 흐리다")
        self.switch(self.yolo.batch)
        self.assertEqual(data.review_state(self.vp)[1], "이 시야는 초점이 흐리다")

    def test_코멘트는_묶음_없는_줄에_산다(self):
        self.mark_done(note="메모")
        row = ViewpointReview.objects.get(viewpoint=self.vp, batch__isnull=True)
        self.assertEqual(row.note, "메모")
        self.assertFalse(row.done, "코멘트 줄이 완료 표시를 들고 있다")

    def test_코멘트를_비우면_줄이_사라진다(self):
        self.mark_done(note="메모")
        self.mark_done(note="")
        self.assertFalse(ViewpointReview.objects
                         .filter(viewpoint=self.vp, batch__isnull=True).exists())

    # --- 화면이 그렇게 세는가 ----------------------------------------------

    def test_목록_배지가_묶음을_따라간다(self):
        self.mark_done()
        g = {x["id"]: x for x in data.dataset_detail("rs23")["groups"]}
        self.assertTrue(g[self.vp.idx]["reviewed"])

        self.switch(self.yolo.batch)
        g = {x["id"]: x for x in data.dataset_detail("rs23")["groups"]}
        self.assertFalse(g[self.vp.idx]["reviewed"], "배지가 묶음을 넘어갔다")

    def test_완료_수가_묶음을_따라간다(self):
        self.mark_done()
        self.assertEqual(data.dataset_detail("rs23")["reviewed_groups"], 1)
        self.switch(self.yolo.batch)
        self.assertEqual(data.dataset_detail("rs23")["reviewed_groups"], 0)

    def test_다음_미검토가_다시_그_시야를_준다(self):
        """**건너뛰면 그 시야는 다시 안 열린다.** 가장 나쁜 결과다."""
        self.mark_done()
        d = data.group_detail("rs23", self.w.viewpoints[1].idx)
        self.assertNotEqual(d.get("todo_id"), self.vp.idx,
                            "완료한 시야를 또 준다")

        self.switch(self.yolo.batch)
        d = data.group_detail("rs23", self.w.viewpoints[1].idx)
        self.assertEqual(d.get("todo_id"), self.vp.idx,
                         "안 본 묶음인데 미검토 목록에서 빠졌다")

    # --- 한꺼번에 표시하기 --------------------------------------------------

    def test_한꺼번에_표시도_묶음에_찍는다(self):
        n = data.mark_all_reviewed("rs23", done=True)
        self.assertEqual(n["changed"], 2)
        self.assertEqual(len(data.done_viewpoints()), 2)

        self.switch(self.yolo.batch)
        self.assertEqual(len(data.done_viewpoints()), 0,
                         "다른 묶음까지 완료로 찍혔다")

    def test_한꺼번에_되돌려도_코멘트는_남는다(self):
        self.mark_done(note="남아야 한다")
        data.mark_all_reviewed("rs23", done=False)
        self.assertFalse(data.review_state(self.vp)[0])
        self.assertEqual(data.review_state(self.vp)[1], "남아야 한다")


class ReviewDoneScreenTest(DiaRUGATestCase):
    """화면이 실제로 그 값을 그리는가."""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=3)
        cls.yolo = fx.add_other_engine(cls.w.vp, label="yolo-시험")
        Detection.objects.filter(run=cls.yolo).update(is_current=True)

    def test_완료_배지가_묶음을_따라간다(self):
        c = Client()
        data.save_review(self.w.vp, done=True, note="", removed=set(),
                         accepted=set(), labels={}, notes={})
        # **배지의 마크업을 짚는다.** 글자만 찾으면 `base.html` 의 CSS 주석에
        # 있는 같은 글자가 걸린다 — 실제로 그렇게 짰다가 헛통과할 뻔했다.
        badge = '<span class="badge done">✓ 검토</span>'
        body = c.get(reverse("dataset", args=["rs23"])).content.decode()
        self.assertIn(badge, body)

        ok, msg = manage_data.set_review_batch(self.yolo.batch_id)
        self.assertTrue(ok, msg)
        body = c.get(reverse("dataset", args=["rs23"])).content.decode()
        self.assertNotIn(badge, body, "배지가 묶음을 넘어갔다")
