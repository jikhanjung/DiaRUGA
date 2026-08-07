"""커서가 **스치고 지나간 판**이 고른 판의 자리에 앉지 않는가 (074).

캐러셀의 썸네일에 커서를 얹으면 그리기만 바뀐다(미리보기). 그런데 그리기는
전역(`cands`·`rejects`)을 갈아 끼워서 하고, `stash()` 는 그 전역을 **고른
판(`curKey`)의 것**으로 알고 담는다. 그래서 커서가 옆 판을 스친 뒤에 판을
고르면 **두 판의 상태가 뒤바뀐다.**

사람이 본 그대로:

> 합성본이 떠 있고, 첫 프레임 썸네일에 커서를 올리면 그 프레임 검출이 뜬다.
> 다시 합성본 썸네일에 커서를 올리면 합성본 검출이 뜬다. 그런데 **합성본을
> 누르면 첫 프레임의 검출이 뜬다.**

재현해 보니 한 쪽만이 아니라 **서로 바뀐다** — 프레임 자리에 합성본의 30개가,
합성본 자리에 프레임의 3개가 앉았다.

더 나쁜 자리가 하나 더 있다. 지연 저장(400 ms)이 걸린 채로 옆 판을 스치고 다른
판을 누르면 `flushSave()` 가 **스쳐 지나간 판의 개체를 고른 판의 이미지로**
보낸다. `/review` 는 그 이미지의 교정을 통째로 갈아치우므로(027·053 계열)
**본 적 없는 판단이 앉고 있던 것이 지워진다.**
"""
from django.urls import reverse

from .base import BrowserTestCase
from .. import factories as fx
from ...models import ObjectReview


class CarouselPreviewTest(BrowserTestCase):

    def make_data(self):
        fx.make_classes()
        self.w = fx.make_world(slug=f"rs23-{self.uniq}",
                               site_code=f"RS{self.uniq}",
                               n_frames=3, n_candidates=3)
        self.extra = fx.add_frame_detections(self.w.vp)
        self.frame = self.extra[0][0]
        self.frame_img = self.extra[0][1]
        self.stack_det = self.w.detection()

    def open_review(self):
        page = self.open(reverse("group", args=[self.w.slug, self.w.vp.idx]))
        page.wait_for_selector(".detview .box")
        return page

    def shot(self, detkey):
        el = self.page.query_selector(f'.shot[data-detkey="{detkey}"]')
        self.assertIsNotNone(el, f"캐러셀에 {detkey} 판이 없다")
        el.scroll_into_view_if_needed()
        return el

    def drawn(self):
        """지금 그려져 있는 개체들의 자리 — 어느 판의 것인지 이것으로 가른다."""
        return self.page.evaluate(
            """() => [...document.querySelectorAll('.detview .box')]
                 .map(e => e.style.left + '/' + e.style.top)""")

    def pick(self, detkey):
        """**커서를 먼저 얹고, 미리보기가 끝난 뒤에 누른다.**

        사람이 하는 그대로다. 곧바로 누르면 미리보기의 사진 내려받기가 아직
        안 끝나 전역이 안 바뀌어 있고, **고장이 그 사이로 빠져나간다** — 실제로
        이 시험이 고치기 전 코드에서 통과했다.
        """
        el = self.shot(detkey)
        el.hover()
        self.page.wait_for_timeout(350)
        el.click()
        self.page.wait_for_timeout(300)
        self.masks_svg().scroll_into_view_if_needed()
        self.page.wait_for_timeout(120)

    def hover(self, detkey):
        self.shot(detkey).hover()
        self.page.wait_for_timeout(300)

    # --- 판이 뒤바뀌지 않는가 ----------------------------------------------

    def test_스친_판이_고른_판의_자리에_앉지_않는다(self):
        """**사람이 본 그대로의 순서다.**"""
        self.open_review()
        stack = self.drawn()
        self.pick(self.frame.name)
        frame = self.drawn()
        self.assertNotEqual(stack, frame, "두 판의 개체가 같다 — 자료가 틀렸다")

        self.hover("__stack__")
        self.pick(self.frame.name)
        self.assertEqual(self.drawn(), frame,
                         "합성본을 스쳤더니 프레임 자리에 합성본 개체가 앉았다")

        self.hover(self.frame.name)
        self.pick("__stack__")
        self.assertEqual(self.drawn(), stack,
                         "프레임을 스쳤더니 합성본 자리에 프레임 개체가 앉았다")

    def test_스치고_지나가도_그리기는_제자리로_돌아온다(self):
        """커서가 캐러셀을 벗어나면 고른 판으로 돌아와야 한다."""
        page = self.open_review()
        stack = self.drawn()
        self.hover(self.frame.name)
        self.assertNotEqual(self.drawn(), stack, "스쳤는데 안 바뀐다")
        page.mouse.move(20, 20)             # 캐러셀 밖
        page.wait_for_timeout(350)
        self.assertEqual(self.drawn(), stack, "돌아오지 않았다")

    # --- 저장이 엉뚱한 이미지로 가지 않는가 ---------------------------------

    def test_스치며_판을_옮겨도_교정이_제_이미지로_간다(self):
        """교정이 어느 이미지에 앉는지를 끝에서 확인한다.

        **`flushSave` 가 스쳐 지나간 판의 개체를 싣는 창은 여기서 못 짚는다** —
        지연 저장이 400 ms 라 시험이 커서를 옮기기 전에 이미 나간다. 그 자리는
        같은 되돌리기(`unpreviewState`)가 `flushSave` 앞에서 막고 있고, 여기서
        보는 것은 **결과가 제 이미지로 갔는가**다. 못 짚는 것을 짚었다고 적지
        않는다 — 덮은 줄 알게 하는 시험이 없는 것보다 나쁘다(064).
        """
        page = self.open_review()

        # 합성본에서 하나 지운다 — 400 ms 지연 저장이 걸린다
        self.context_menu_at(40 + 60 // 2, 50 + 40 // 2)
        page.get_by_text("오검출로 삭제", exact=False).first.click()
        # 저장이 나가기 전에 옆 판을 스치고 다른 판을 고른다
        self.hover(self.frame.name)
        self.pick(self.frame.name)
        page.wait_for_timeout(900)

        rows = list(ObjectReview.objects.all())
        self.assertEqual(len(rows), 1, f"교정이 하나여야 한다: {rows}")
        self.assertEqual(rows[0].image_id, self.stack_det.image_id,
                         "합성본을 보고 지웠는데 다른 이미지에 앉았다")
        self.assertTrue(rows[0].removed)

    def test_돌아오면_지운_표시가_그대로다(self):
        """스치고 돌아오는 길에서도 사람이 한 일이 남아 있어야 한다."""
        page = self.open_review()
        self.context_menu_at(40 + 60 // 2, 50 + 40 // 2)
        page.get_by_text("오검출로 삭제", exact=False).first.click()
        page.wait_for_timeout(900)

        self.hover(self.frame.name)
        self.pick(self.frame.name)
        self.hover("__stack__")
        self.pick("__stack__")
        self.assertTrue(page.query_selector(".box.gone"),
                        "합성본으로 돌아오니 지운 표시가 사라졌다")
        self.assertEqual(ObjectReview.objects.filter(removed=True).count(), 1)
