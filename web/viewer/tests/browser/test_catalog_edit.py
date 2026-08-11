"""개체 카탈로그에 **실제로 쳐 넣어 본다.**

3겹(`tests/test_catalog_page.py`)은 서버가 무엇을 받으면 무엇을 하는지까지 본다.
여기서 보는 것은 그 밖이다 — **화면이 실제로 그것을 보내는가, 그리고 보낸 뒤에
화면이 사람이 친 글자를 지키는가.**

이 시험이 있는 이유가 구체적이다. 세 칸을 잇달아 채우면 **먼저 보낸 요청의
응답이 나중에 친 글자를 덮었다** — 종명을 저장한 응답이 돌아오면서 그 사이에 친
코멘트를 서버가 아는 빈 값으로 되돌렸다. 화면에는 "저장됨" 이 적혀 있고,
새로고침하면 코멘트만 없다.

**3겹으로는 안 잡힌다.** 서버는 받은 것을 정확히 저장했고 200 을 냈다. 고장은
브라우저 안에서만 났다 — 045 가 브라우저 겹을 만든 바로 그 종류다.
"""
from django.urls import reverse

from .base import BrowserTestCase
from .. import factories as fx
from ...models import DiatomObject, ObjectReview, RunBatch


class CatalogEditTest(BrowserTestCase):

    def make_data(self):
        fx.make_classes()
        self.w = fx.make_world(slug=f"rs23-{self.uniq}",
                               site_code=f"RS{self.uniq}", n_candidates=3)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def open_catalog(self):
        return self.open(reverse("catalog", args=[self.w.slide.slug]))

    def first_card(self, page):
        return page.locator(".catcard").first

    def test_세_칸을_잇달아_채워도_다_남는다(self):
        """**이 시험이 이 파일의 이유다.** 응답이 겹치는 그 자리를 그대로 밟는다."""
        page = self.open_catalog()
        card = self.first_card(page)
        card.locator(".species").fill("Eucampia antarctica")
        card.locator(".cls").select_option("rod")
        card.locator(".note").fill("가장자리가 넘쳤다")
        page.locator("body").click(position={"x": 5, "y": 5})
        page.wait_for_timeout(1800)

        page.reload(wait_until="load")
        card = self.first_card(page)
        self.assertEqual(card.locator(".species").input_value(),
                         "Eucampia antarctica")
        self.assertEqual(card.locator(".cls").input_value(), "rod")
        self.assertEqual(card.locator(".note").input_value(), "가장자리가 넘쳤다")

    def test_저장하는_동안_더_쳐도_안_덮인다(self):
        """응답이 오는 사이에 사람이 더 친다. **보낸 뒤로 바뀐 칸은 안 건드린다.**"""
        page = self.open_catalog()
        card = self.first_card(page)
        card.locator(".species").fill("Euc")
        card.locator(".species").blur()
        card.locator(".species").fill("Eucampia antarctica")
        page.wait_for_timeout(2000)

        page.reload(wait_until="load")
        self.assertEqual(self.first_card(page).locator(".species").input_value(),
                         "Eucampia antarctica")

    def test_옆_카드를_안_건드린다(self):
        """`/review` 는 범위를 갈아치우지만 여기는 짚은 개체 하나만 고친다."""
        page = self.open_catalog()
        cards = page.locator(".catcard")
        cards.nth(1).locator(".species").fill("Chaetoceros sp.")
        cards.nth(1).locator(".species").blur()
        page.wait_for_timeout(1200)
        cards.nth(0).locator(".species").fill("Eucampia antarctica")
        cards.nth(0).locator(".species").blur()
        page.wait_for_timeout(1500)

        page.reload(wait_until="load")
        cards = page.locator(".catcard")
        self.assertEqual(cards.nth(1).locator(".species").input_value(),
                         "Chaetoceros sp.")
        self.assertEqual(cards.nth(0).locator(".species").input_value(),
                         "Eucampia antarctica")

    def test_비우면_그_줄이_사라진다(self):
        page = self.open_catalog()
        card = self.first_card(page)
        card.locator(".species").fill("Eucampia antarctica")
        card.locator(".species").blur()
        page.wait_for_timeout(1500)
        self.assertTrue(DiatomObject.objects.filter(species__gt="").exists())

        card.locator(".species").fill("")
        card.locator(".species").blur()
        page.wait_for_timeout(1500)
        self.assertFalse(DiatomObject.objects.filter(species__gt="").exists())

    def test_그림을_누르면_그_시야로_간다(self):
        """크롭 화면과 같은 자리로 간다. **그림과 g번호 둘 다** — 그림만 링크면
        말풍선으로만 알 수 있어서, 있는 줄 모르고 안 쓴다."""
        page = self.open_catalog()
        card = self.first_card(page)
        want = f"/d/{self.w.slide.slug}/g/0/"
        self.assertTrue(card.locator(".pic").get_attribute("href").endswith(want))
        self.assertTrue(
            card.locator(".meta .togroup").get_attribute("href").endswith(want))
        card.locator(".meta .togroup").click()
        page.wait_for_load_state("load")
        self.assertIn(want, page.url)

    def test_적다_말고_뒤로_가도_안_잃는다(self):
        """**글자 칸은 900ms 쉬거나 자리를 떠야 보낸다.** 그 사이에 페이지가
        사라지면 방금 적은 종명이 없던 일이 된다 — 저장됐다는 표시도 못 봤으니
        사람은 적은 줄 안다.

        **링크를 누르는 것은 이 갈래가 아니다.** 누르면 칸이 먼저 blur 되어
        그때 이미 보내진다(처음엔 그것을 시험이라고 적었는데, 떠날 때 마저
        보내는 코드를 빼도 통과했다 — 실패할 수 없는 시험이었다).

        빈 자리는 **blur 가 안 나는 이동**이다: 뒤로 가기 · 주소창 · 탭 닫기.
        그때는 `pagehide` 밖에 안 오고, `keepalive` 가 없으면 요청이 문서와
        함께 죽는다.
        """
        # 뒤로 갈 곳을 만들어 둔다 — 시야 목록에서 카탈로그로 들어온 것처럼.
        self.open(reverse("dataset", args=[self.w.slide.slug]))
        page = self.open_catalog()
        card = self.first_card(page)
        card.locator(".species").type("Eucampia antarctica", delay=10)
        # 디바운스가 돌기 전에 뒤로 간다. blur 는 안 난다.
        page.go_back(wait_until="load")
        page.wait_for_timeout(1500)

        self.assertEqual(
            list(DiatomObject.objects.values_list("species", flat=True)),
            ["Eucampia antarctica"])

    def test_저장되면_카드가_그렇게_말한다(self):
        """아무 표시도 없으면 사람이 같은 일을 다시 한다."""
        page = self.open_catalog()
        card = self.first_card(page)
        card.locator(".species").fill("Eucampia antarctica")
        card.locator(".species").blur()
        page.wait_for_timeout(1200)
        self.assertIn("saved", card.get_attribute("class"))


class CatalogReadOnlyTest(BrowserTestCase):
    """**되는 것처럼 보이면 안 된다** (051).

    저장만 잠그고 화면을 살려 두면 사람이 한 판을 헛동정하고, 새로고침하면
    통째로 사라진다. 그래서 **반응하는 자리를 전부 센다.**
    """

    def make_data(self):
        fx.make_classes()
        self.w = fx.make_world(slug=f"rs23-{self.uniq}",
                               site_code=f"RS{self.uniq}", n_candidates=2,
                               state="processing")
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def test_세_칸이_다_안_눌린다(self):
        page = self.open(reverse("catalog", args=[self.w.slide.slug]))
        card = page.locator(".catcard").first
        for sel in (".species", ".cls", ".note"):
            self.assertTrue(card.locator(sel).is_disabled(), sel)

    def test_쳐_넣어도_아무것도_안_저장된다(self):
        """`disabled` 를 브라우저가 실제로 막는가 — CSS 로 감춘 것과 다르다."""
        page = self.open(reverse("catalog", args=[self.w.slide.slug]))
        card = page.locator(".catcard").first
        # `fill` 은 disabled 를 못 채운다 — JS 로 값을 밀어 넣고 이벤트까지 쏜다.
        card.locator(".species").evaluate("""e => {
            e.value = '몰래';
            e.dispatchEvent(new Event('input', {bubbles: true}));
            e.dispatchEvent(new Event('change', {bubbles: true}));
            e.dispatchEvent(new Event('blur', {bubbles: true}));
        }""")
        page.wait_for_timeout(1500)
        self.assertFalse(DiatomObject.objects.filter(species="몰래").exists())

    def test_왜_못_적는지_보인다(self):
        page = self.open(reverse("catalog", args=[self.w.slide.slug]))
        self.assertTrue(page.is_visible(".note.warn"))
        self.assertIn("자동 처리가 아직 끝나지 않았습니다",
                      page.inner_text(".note.warn"))
