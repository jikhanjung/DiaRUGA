"""종명 칸이 도감을 안다 · 검토 화면에서 카드로 — **눌러서 본다** (149).

3겹은 재료가 화면까지 가는지만 본다. **이벤트 배선 고장은 이 겹으로만 잡힌다**
(045). 여기서 보는 것은 넷이다.

1. 치면 자동완성 목록이 실제로 차는가 (`api/atlas/suggest` 까지 갔다 오는가)
2. 도판 단추가 **보이는가** — `[hidden]` 은 특이도 (0,0,1) 이라 클래스 규칙에
   진다. 감추라고 해 놓고 그대로 보이는 자리를 이 저장소가 세 번 겪었고
   (`.tools`·타일·`.row`), 그래서 `getComputedStyle` 로 확인한다
3. 눌러서 미리보기가 뜨는가, Esc 로 닫히는가
4. 검토 화면의 우클릭 메뉴가 실제로 카탈로그로 데려가는가

**도판 PNG 는 여기 없다.** 그래서 그림은 404 로 떨어지는데, 그 갈래도 화면이
말해야 한다("아직 안 떴습니다") — 빈 칸을 남기면 원본에 그 쪽이 없는 것으로
읽힌다.
"""
from django.urls import reverse

from .base import BrowserTestCase
from .. import factories as fx
from ..test_catalog_atlas import make_atlas
from ... import data
from ...models import RunBatch

NAME = "Melosira ambigua"


class CatalogAtlasBrowserTest(BrowserTestCase):

    def make_data(self):
        fx.make_classes()
        self.w = fx.make_world(slug=f"rs23-{self.uniq}",
                               site_code=f"RS{self.uniq}", n_candidates=2)
        RunBatch.objects.filter(for_review=True).update(code="S1")
        make_atlas()
        self.rows = data.candidate_rows(self.w.slide.slug)

    def open_catalog(self, **q):
        page = self.open(reverse("catalog", args=[self.w.slide.slug]))
        page.wait_for_selector(".catcard")
        return page

    def type_name(self, page, text=NAME):
        """첫 카드의 종명 칸에 이름을 치고 **목록이 찰 때까지 기다린다.**

        `fill()` 로 값을 꽂으면 `input` 이 한 번만 나서 사람이 치는 것과 다른
        길을 밟는다. 자동완성은 치는 도중에 떠야 뜻이 있다.

        **시간을 세지 않는다** (전체 시험을 함께 돌리다 한 번 흔들렸다). 지연
        250ms 에 왕복이 얹히는데, 그 합을 상수로 적으면 기계가 바쁠 때 넘친다.
        더 나쁜 것은 **끝난 줄 알고 창을 닫는 것**이다 — 아직 나가 있는 요청이
        끊기면서 콘솔에 오류가 남고, 그것을 이 겹이 실패로 읽는다(그 자국이
        JS 고장과 구별되지 않는다).
        """
        inp = page.query_selector(".catcard .species")
        self.assertIsNotNone(inp, "종명 칸이 없다")
        inp.click()
        page.keyboard.type(text, delay=15)
        page.wait_for_function(
            "() => document.querySelectorAll("
            "'#species-seen option[data-atlas]').length > 0",
            timeout=10_000)
        return inp

    # 1) 치면 목록이 찬다
    def test_치면_도감_이름이_목록에_찬다(self):
        page = self.open_catalog()
        self.assertEqual(
            page.eval_on_selector_all("#species-seen option[data-atlas]",
                                      "els => els.length"), 0,
            "묻기도 전에 도감 이름이 목록에 있다")
        self.type_name(page, "Melos")
        vals = page.eval_on_selector_all(
            "#species-seen option[data-atlas]", "els => els.map(e => e.value)")
        self.assertIn(NAME, vals, f"도감 이름이 목록에 안 찼다: {vals}")

    # 2) 도판 단추가 **보인다**
    def test_도판_단추가_보인다(self):
        page = self.open_catalog()
        btn = page.query_selector(".catcard .plate")
        self.assertEqual(btn.evaluate("e => getComputedStyle(e).display"), "none",
                         "종명을 적기도 전에 도판 단추가 보인다")
        self.type_name(page)
        page.keyboard.press("Tab")          # change · blur 를 낸다
        page.wait_for_selector(".catcard .plate", state="visible", timeout=5_000)
        self.assertNotEqual(
            btn.evaluate("e => getComputedStyle(e).display"), "none",
            "도감에 있는 이름을 적었는데 도판 단추가 안 보인다")

    # 3) 눌러서 뜨고 Esc 로 닫힌다
    def test_눌러서_미리보기가_뜬다(self):
        # 도판 PNG 가 없어 그림이 404 다 — 그 갈래를 일부러 지난다
        self.expect_http_error(404)
        page = self.open_catalog()
        self.type_name(page)
        page.keyboard.press("Tab")
        page.wait_for_selector(".catcard .plate", state="visible", timeout=5_000)
        page.click(".catcard .plate")
        page.wait_for_selector("#cpreview", state="visible", timeout=5_000)
        self.assertTrue(page.is_visible("#cpreview"), "미리보기 판이 안 떴다")
        self.assertIn(NAME, page.inner_text("#cpreview"))
        # **그림이 없으면 그렇다고 말한다** — 빈 칸을 남기면 원본에 그 쪽이
        # 없는 것으로 읽힌다. 그림이 떨어지는 것을 **기다린다**: 판은 누르는
        # 즉시 뜨고 오류는 그 뒤에 온다.
        page.wait_for_selector("#cpreview.failed", timeout=5_000)
        self.assertIn("아직 안 떴습니다", page.inner_text("#cpreview .cap"))
        # 도감 화면으로 가는 길이 판에 있다
        self.assertIn("/atlas/schmidt/band1/23/",
                      page.get_attribute("#cpreview-open", "href"))
        page.keyboard.press("Escape")
        page.wait_for_selector("#cpreview", state="hidden", timeout=5_000)
        self.assertFalse(page.is_visible("#cpreview"), "Esc 로 안 닫혔다")

    # 4) 종명을 지우면 단추도 판도 사라진다
    def test_이름을_지우면_판도_닫힌다(self):
        self.expect_http_error(404)
        page = self.open_catalog()
        self.type_name(page)
        page.keyboard.press("Tab")
        page.wait_for_selector(".catcard .plate", state="visible", timeout=5_000)
        page.click(".catcard .plate")
        page.wait_for_selector("#cpreview", state="visible", timeout=5_000)
        self.assertTrue(page.is_visible("#cpreview"))
        inp = page.query_selector(".catcard .species")
        inp.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        page.keyboard.press("Tab")
        page.wait_for_selector("#cpreview", state="hidden", timeout=5_000)
        self.assertFalse(page.is_visible("#cpreview"),
                         "이름을 지웠는데 옛 이름의 도판이 그대로 떠 있다")
        self.assertEqual(
            page.eval_on_selector(".catcard .plate",
                                  "e => getComputedStyle(e).display"), "none")


class ToCatalogMenuTest(BrowserTestCase):
    """검토 화면 → 개체 카드 (#4)."""

    def make_data(self):
        fx.make_classes()
        self.w = fx.make_world(slug=f"rs23-{self.uniq}",
                               site_code=f"RS{self.uniq}", n_candidates=2)
        RunBatch.objects.filter(for_review=True).update(code="S1")
        self.cand = self.w.detection().candidates.order_by("raw_id").first()

    def menu_item(self, menu, text):
        for el in menu.query_selector_all("button, .mi"):
            if text in (el.inner_text() or ""):
                return el
        return None

    def test_메뉴에서_카드로_간다(self):
        page = self.open(reverse("group", args=[self.w.slide.slug,
                                                self.w.vp.idx]))
        page.wait_for_selector(".detview .box")
        menu = self.context_menu_at(self.cand.center_x, self.cand.center_y)
        self.assertIsNotNone(menu, "우클릭 메뉴가 안 열렸다")
        item = self.menu_item(menu, "이 개체 카드로")
        self.assertIsNotNone(item, "카드로 가는 항목이 메뉴에 없다")
        item.click()
        page.wait_for_selector(".catcard", timeout=10_000)
        # **그 개체의 카드에 표시가 붙어 있어야 한다** — 카드가 여럿이라
        # 그냥 카탈로그로 데려다 놓기만 하면 다시 찾아야 한다 (118 의 반대편)
        self.assertIn("catalog", page.url)
        self.assertIn(f"obj={self.cand.mask_key}", page.url)
        hl = page.query_selector(".catcard.hl")
        self.assertIsNotNone(hl, "짚어 온 카드에 표시가 없다")
        self.assertEqual(hl.get_attribute("data-key"), self.cand.mask_key)
