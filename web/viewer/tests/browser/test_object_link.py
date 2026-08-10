"""같은 개체 묶기 — **실제로 눌러서** 배선을 본다 (P11 2단계).

3겹(endpoint 시험)은 서버 검증까지만 본다. 여기서 보는 것: 우클릭 메뉴에
항목이 나오는가 · 팝업이 뜨고 미리 고르기가 찍혀 있는가 · 저장이 DB 에
남는가 · 다시 열면 "묶음 열기" 가 되는가. 이벤트 배선 고장은 이것으로만
잡힌다 (CLAUDE.md).
"""
from django.urls import reverse

from .base import BrowserTestCase
from .. import factories as fx
from ...models import (Candidate, Detection, Image, ObjectLink,
                       ObjectReview, Run, RunBatch)


class ObjectLinkBrowserTest(BrowserTestCase):

    def make_data(self):
        fx.make_classes()
        # 합성본 + 프레임 3장. 검출은 합성본(팩토리)과 프레임 둘에 세운다 —
        # 캐러셀이 성립해야 묶을 상대가 있다.
        self.w = fx.make_world(slug=f"rs23-{self.uniq}",
                               site_code=f"RS{self.uniq}",
                               n_frames=3, n_candidates=2)
        batch = RunBatch.objects.get(label="sam2-시험")
        run = Run.objects.create(kind="detect", batch=batch,
                                 slide=self.w.slide, status="done")
        self.frame_imgs = list(Image.objects.filter(
            viewpoint=self.w.vp, kind="frame").order_by("pk"))
        for img in self.frame_imgs[:2]:
            det = Detection.objects.create(
                viewpoint=self.w.vp, image=img, image_path=img.path,
                width=fx.IMG_W, height=fx.IMG_H, scale=1.0, um_per_pixel=0.1,
                run=run, is_current=True)
            # 합성본의 첫 후보(40,50,60,40)와 같은 자리 — IoU 1.0 이라
            # 미리 고르기 규칙(≥0.5 · 간격 ≥0.3)에 걸려 ✓ 가 찍혀 있어야 한다
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

    def open_group(self):
        return self.open(reverse("group", args=[self.w.slide.slug,
                                                self.w.vp.idx]))

    def menu_item(self, menu, text):
        for el in menu.query_selector_all("button, .mi"):
            if text in (el.inner_text() or ""):
                return el
        return None

    def test_묶고_다시_열면_묶음_열기다(self):
        page = self.open_group()
        # 합성본 첫 후보(중심 70,70) 위에서 우클릭
        menu = self.context_menu_at(70, 70)
        self.assertIsNotNone(menu, "우클릭 메뉴가 안 열렸다")
        item = self.menu_item(menu, "동일 개체 묶기")
        self.assertIsNotNone(item, "묶기 항목이 메뉴에 없다")
        item.click()
        page.wait_for_selector(".linkpanel", state="visible", timeout=3000)

        # 프레임 두 줄이 미리 골라져 있어야 한다 (IoU 1.0 · 간격 큼)
        picked = page.query_selector_all(".linkpanel .scell.on:not(.anchor)")
        self.assertEqual(len(picked), 2,
                         "미리 고르기가 안 찍혔다 (IoU 1.0 인데)")

        # 저장
        btn = page.query_selector(".linkpanel .lfoot .btn")
        self.assertIn("3장", btn.inner_text())
        btn.click()
        page.wait_for_selector(".linkpanel", state="detached", timeout=3000)

        link = ObjectLink.objects.get()
        self.assertEqual(link.members.count(), 3)
        rep = link.members.get(is_rep=True)
        self.assertEqual(rep.image.kind, "stack", "기본 대표는 닻(합성본)이다")

        # **사슬 배지가 새로고침 없이 선다** (3단계) — 저장 성공 갈래가
        # build() 를 다시 부른다.
        self.assertIsNotNone(self.page.query_selector(".box.linked"),
                             "묶었는데 사슬 배지가 없다")

        # 같은 자리에서 다시 열면 "묶음 열기"
        menu = self.context_menu_at(70, 70)
        self.assertIsNotNone(self.menu_item(menu, "묶음 열기"),
                             "묶은 뒤에도 '묶기' 로 나온다")

    def test_없음을_고르면_그_판은_빠진다(self):
        page = self.open_group()
        menu = self.context_menu_at(70, 70)
        self.menu_item(menu, "동일 개체 묶기").click()
        page.wait_for_selector(".linkpanel", state="visible", timeout=3000)
        # 첫 프레임 줄의 (없음) 을 누른다
        page.query_selector_all(".linkpanel .lnone")[0].click()
        page.wait_for_timeout(150)
        btn = page.query_selector(".linkpanel .lfoot .btn")
        self.assertIn("2장", btn.inner_text())
        btn.click()
        page.wait_for_selector(".linkpanel", state="detached", timeout=3000)
        self.assertEqual(ObjectLink.objects.get().members.count(), 2)

    def test_별로_대표를_옮긴다(self):
        page = self.open_group()
        menu = self.context_menu_at(70, 70)
        self.menu_item(menu, "동일 개체 묶기").click()
        page.wait_for_selector(".linkpanel", state="visible", timeout=3000)
        # 프레임 쪽(닻 아닌) 선택 칸의 별을 누른다
        star = page.query_selector(
            ".linkpanel .scell.on:not(.anchor) .lstar")
        self.assertIsNotNone(star, "선택 칸에 별이 없다")
        star.click()
        page.wait_for_timeout(150)
        page.query_selector(".linkpanel .lfoot .btn").click()
        page.wait_for_selector(".linkpanel", state="detached", timeout=3000)
        rep = ObjectLink.objects.get().members.get(is_rep=True)
        self.assertEqual(rep.image.kind, "frame", "별을 옮겼는데 대표가 닻이다")

    def test_판이_하나면_메뉴에_항목이_없다(self):
        """묶을 상대가 없는 화면 — 죽은 항목을 내보이지 않는다."""
        w2 = fx.make_world(slug=f"solo-{self.uniq}", site_code=f"SO{self.uniq}",
                           n_frames=1, n_candidates=2)
        self.open(reverse("group", args=[w2.slide.slug, w2.vp.idx]))
        menu = self.context_menu_at(70, 70)
        self.assertIsNotNone(menu)
        self.assertIsNone(self.menu_item(menu, "동일 개체"),
                          "판이 하나인데 묶기 항목이 나온다")

    def test_저장이_한_번_미끄러진_그린_마스크도_묶인다(self):
        """실사용 g25 의 사고 (2026-08-10). 마스크를 그렸는데 /review 저장이
        한 번 실패하면 — 옛 코드는 `savePending` 을 이미 꺼 둔 채라 다시
        시도하지 않았고, 그 마스크는 **화면에는 있는데 DB 에는 영영 없었다.**
        묶기 POST 는 모르는 열쇠라며 "이 화면의 마스크가 아니다" 로 거절했다.

        고침 둘을 함께 본다: 실패가 `savePending` 을 되살리는 것, 그리고 묶기
        팝업이 열릴 때 그 밀린 저장을 먼저 밀어내는 것.
        """
        page = self.open_group()

        # /review 를 한 번만 떨어뜨린다 — 연결이 순간 끊긴 상황
        state = {"failed": 0}
        def wreck(route):
            if state["failed"] == 0:
                state["failed"] += 1
                route.abort()
            else:
                route.continue_()
        page.route("**/review", wreck)

        # 빈 자리에 마스크를 그린다 (draw 도구 → 점 셋 → 첫 점으로 닫기)
        page.click('#tools-stack button[data-act="draw"]')
        page.wait_for_timeout(150)
        for x, y in ((400, 300), (470, 300), (470, 360)):
            self.click_image(x, y)
        self.click_image(400, 300)
        page.wait_for_timeout(900)          # 지연 저장이 나가고 — 떨어진다
        self.assertEqual(state["failed"], 1, "저장 실패를 만들지 못했다")

        # 그린 마스크(중심께)에서 우클릭 → 묶기 → 프레임 후보는 없을 테니
        # 합성본 근처의 엔진 후보 하나를 프레임에서 고르는 대신, 그냥
        # 미리 골라진 것 없이 닻+없음이면 저장이 안 되므로 —
        # 엔진 후보(70,70) 위에서 여는 편이 확실하다: 닻은 엔진 마스크,
        # 다른 판 후보가 미리 골라져 있고, **팝업 열기가 밀린 저장을 먼저
        # 밀어낸다** 는 것이 이 시험의 요점이다.
        menu = self.context_menu_at(70, 70)
        self.menu_item(menu, "동일 개체 묶기").click()
        page.wait_for_selector(".linkpanel", state="visible", timeout=3000)
        page.wait_for_timeout(600)          # saveGate(재시도 저장)가 돌 시간
        page.query_selector(".linkpanel .lfoot .btn").click()
        page.wait_for_selector(".linkpanel", state="detached", timeout=3000)

        # 묶음이 섰고 — 그린 마스크도 (재시도 덕에) DB 에 있다
        self.assertEqual(ObjectLink.objects.count(), 1)
        drawn = ObjectReview.objects.filter(batch__isnull=True,
                                            source="manual")
        self.assertEqual(drawn.count(), 1,
                         "실패했던 저장이 재시도되지 않았다 — 그린 마스크가 DB 에 없다")

        # **일부러 떨어뜨린 요청의 콘솔 오류는 이 시험의 조건이지 고장이 아니다.**
        # 그 한 줄만 걸러 낸다 — 통째로 비우면 진짜 JS 오류까지 덮는다.
        self.errors = [e for e in self.errors
                       if "ERR_FAILED" not in e or "/review" not in e
                       if not e.startswith("console.error: Failed to load resource")]
