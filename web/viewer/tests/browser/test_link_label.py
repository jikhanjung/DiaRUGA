"""묶인 개체는 분류를 함께 받는다 — 화면 쪽 (사용자 요청 2026-08-10).

서버가 번지게 하는 것은 `test_object_link.LinkLabelSpreadTest` 가 본다. 여기서
보는 것은 **화면이 그 사실을 받아 들이는가**이고, 그건 3겹에서 안 보인다.

두 가지인데 **뒤엣것이 더 무섭다.**

1. 판을 넘기면 번진 분류가 보인다 — 새로고침을 안 기다린다 (102 덧 2 와 같은 자리)
2. **그 판의 다음 저장이 도로 지우지 않는다** — 화면의 `labels` 는 열릴 때 받은
   것이라 번진 분류를 모른다. 뷰어는 늘 전체를 보내므로, 모르는 채로 저장이
   나가면 서버가 "표시가 사라진 행" 으로 보고 지운다. 예외도 경고도 없이,
   **다른 판에서 뭔가를 지운 순간** 앞서 정한 분류가 사라진다
"""
from django.urls import reverse

from .base import BrowserTestCase
from .. import factories as fx
from ...models import Image, ObjectLink, ObjectLinkMember, ObjectReview, RunBatch


class LinkLabelSpreadBrowserTest(BrowserTestCase):

    def make_data(self):
        fx.make_classes()
        self.w = fx.make_world(slug=f"rs23-{self.uniq}",
                               site_code=f"RS{self.uniq}",
                               n_frames=3, n_candidates=2)
        self.extra = fx.add_frame_detections(self.w.vp)
        self.batch = RunBatch.objects.get(label="sam2-시험")
        self.stack_img = Image.objects.get(viewpoint=self.w.vp, kind="stack")
        self.frame, self.frame_img, _ = self.extra[0]

        # 합성본과 첫 프레임의 같은 자리를 한 개체로 묶어 둔다 — 픽스처가 판마다
        # 같은 자리에 후보를 세우므로 `mask_key` 가 그대로 맞는다.
        self.key = self.w.keys()[0]
        link = ObjectLink.objects.create(viewpoint=self.w.vp, batch=self.batch)
        for i, img in enumerate((self.stack_img, self.frame_img)):
            ObjectLinkMember.objects.create(
                link=link, image=img, batch=self.batch, mask_key=self.key,
                is_rep=(i == 0), geom={"bbox_xywh": [40, 50, 60, 40]})

    def open_review(self):
        page = self.open(reverse("group", args=[self.w.slug, self.w.vp.idx]))
        page.wait_for_selector(".detview .box")
        return page

    def shot(self, detkey):
        el = self.page.query_selector(f'.shot[data-detkey="{detkey}"]')
        self.assertIsNotNone(el, f"캐러셀에 {detkey} 판이 없다")
        el.scroll_into_view_if_needed()
        return el

    def pick(self, detkey):
        el = self.shot(detkey)
        el.hover()
        self.page.wait_for_timeout(350)
        el.click()
        self.page.wait_for_timeout(400)
        # **사진을 화면 안으로 되돌린다.** 캐러셀을 누르느라 스크롤이 내려가
        # 있으면 이미지 좌표로 짚은 클릭이 창 밖으로 떨어진다 — 우클릭 메뉴가
        # 안 열려서 "메뉴가 없다" 로 읽힌다 (test_carousel_preview 와 같다).
        self.masks_svg().scroll_into_view_if_needed()
        self.page.wait_for_timeout(150)

    def label_first_as_rod(self):
        """합성본에서 첫 개체를 고르고 봉상(w)으로 지정한다."""
        self.click_image(40 + 60 // 2, 50 + 40 // 2)
        self.page.keyboard.press("w")
        self.page.wait_for_timeout(900)          # 지연 저장 + 응답

    def classes_of_boxes(self):
        return self.page.evaluate(
            """() => [...document.querySelectorAll('.detview .box')]
                 .map(e => e.className)""")

    def test_판을_넘기면_번진_분류가_보인다(self):
        self.open_review()
        self.label_first_as_rod()
        self.assertEqual(
            ObjectReview.objects.get(image=self.frame_img,
                                     mask_key=self.key).label, "rod",
            "서버가 안 번지게 했다 — 이 시험의 전제가 틀렸다")

        self.pick(self.frame.name)
        rods = [c for c in self.classes_of_boxes() if "rod" in c]
        self.assertTrue(rods,
                        "묶인 판으로 넘어왔는데 봉상으로 안 보인다 — "
                        f"새로고침해야 나오는 상태다: {self.classes_of_boxes()}")

    def test_그_판에서_저장해도_번진_분류가_안_지워진다(self):
        """**이것이 진짜 위험한 쪽이다.** 화면이 모르는 채로 전체를 보낸다."""
        self.open_review()
        self.label_first_as_rod()

        # 묶인 판으로 넘어가 **다른** 개체를 지운다 → 그 판의 저장이 나간다
        self.pick(self.frame.name)
        self.context_menu_at(160 + 70 // 2, 130 + 50 // 2)   # 둘째 후보
        self.page.get_by_text("오검출로 삭제", exact=False).first.click()
        self.page.wait_for_timeout(1000)

        row = ObjectReview.objects.filter(image=self.frame_img,
                                          mask_key=self.key).first()
        self.assertIsNotNone(
            row, "그 판에서 뭔가를 지웠더니 번진 분류 행이 통째로 사라졌다")
        self.assertEqual(row.label, "rod",
                         "그 판의 다음 저장이 번진 분류를 도로 지웠다")

