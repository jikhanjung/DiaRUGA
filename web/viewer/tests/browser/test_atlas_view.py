"""도판 보는 조작 — 키·확대·쪽으로 가기 (141).

**이 겹으로만 잡힌다.** 3겹(테스트 클라이언트)은 200 과 글자만 본다. 키가
안 듣는 것·확대가 안 걸리는 것·그림이 창을 넘겨 잘리는 것은 전부 HTML 이
멀쩡한 채로 나는 고장이라 거기서 안 보인다 (045 와 같은 줄).

## 되살려서 잡히는가

- 1번 — `_atlasview.html` 의 스크립트를 `DOMContentLoaded` 없이 곧바로 돌리면
  실패한다. 이 조각은 **`#aview` 보다 앞에 놓이므로**(조작 띠가 그림 위에
  있어야 한다) 파싱 중에는 `#aview` 가 아직 없어 `return` 으로 조용히 물러난다
  — 예외도 경고도 없고 **키만 안 듣는다**
- 2번 — 키 갈래에서 `ArrowLeft`/`ArrowRight` 를 빼면 실패한다
- 3번 — `#acanvas` 의 `width/height: 100%` 를 빼면 실패한다. 그림의
  `max-height: 100%` 가 **높이 `auto` 인 부모**에 걸려 안 풀리고, 도판이 원래
  높이 그대로 서서 창을 넘긴다 (실제로 745px 창에 2005px 짜리가 들어 있었다)
- 4번 — 휠 갈래를 빼거나 `transform` 을 안 걸면 실패한다
- 5번 — `atlas_volume` 이 `spread` 를 안 들고 가면 실패한다. 두 쪽으로 읽다
  쪽 번호로 뛰면 **한 장으로 떨어져** 보기를 다시 고르게 된다
- 6번 — 입력칸 갈래(`INPUT|TEXTAREA|SELECT`)를 빼면 실패한다. 쪽 번호를 치는
  중에 `-` 를 누르면 배율이 줄고, 숫자 옆에서 화살표를 누르면 **쪽이 넘어간다**
"""
import json
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from .base import BrowserTestCase
from ..base import write_image


class AtlasViewControlTest(BrowserTestCase):

    def make_data(self):
        # **창보다 큰 도판이어야 한다.** 작은 그림은 `max-height` 가 안 걸려도
        # 그대로 들어가서, 높이 제약이 깨져도 시험이 통과한다 — 처음에
        # 400×560 으로 짰다가 되살려 보고 알았다(실제 도판은 2200×3000쯤이다).
        for n in (1, 2, 3, 4, 5, 6):
            write_image(f"atlas/schmidt/band1/p{n:04d}.png", size=(600, 1600))
        root = Path(settings.DATA_ROOT) / "atlas"
        root.mkdir(parents=True, exist_ok=True)
        (root / "atlases.json").write_text(json.dumps({
            "dpi": 300, "atlases": {"schmidt": {
                "code": "schmidt", "label": "Schmidt", "left_parity": "even",
                "volumes": [{"code": "band1", "label": "Band 1",
                             "pages": 6, "rendered": 6}]}}}), encoding="utf-8")

    def one(self, n=3, spread=False):
        url = reverse("atlas_page", args=["schmidt", "band1", n])
        page = self.open(url + ("?spread=1" if spread else ""))
        page.wait_for_selector("#acanvas img", state="visible", timeout=10_000)
        page.wait_for_timeout(200)
        return page

    # --- 1·2번 ---------------------------------------------------------------

    def test_화살표로_앞뒤_쪽을_넘긴다(self):
        page = self.one(3)
        with page.expect_navigation():
            page.keyboard.press("ArrowRight")
        self.assertIn("/band1/4/", page.url)
        with page.expect_navigation():
            page.keyboard.press("ArrowLeft")
        self.assertIn("/band1/3/", page.url)

    def test_g_는_격자로_s_는_보기를_바꾼다(self):
        page = self.one(3)
        with page.expect_navigation():
            page.keyboard.press("s")
        self.assertIn("spread=1", page.url, "s 가 두 쪽으로 안 갔다")
        with page.expect_navigation():
            page.keyboard.press("g")
        self.assertIn("/band1/?", page.url, "g 가 격자로 안 갔다")

    def test_첫_쪽에서_왼쪽_화살표는_아무_일도_안_한다(self):
        """갈 곳이 없다. **주소를 안 만든다** — 없는 쪽으로 보내면 404 가 된다."""
        page = self.one(1)
        before = page.url
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(300)
        self.assertEqual(page.url, before)

    # --- 3번 -----------------------------------------------------------------

    def test_도판이_창_하나에_들어간다(self):
        """**높이에 맞아야 한다.** 예전에는 폭에 맞춰 늘려 놓아 세로로 넘쳤고,
        한 쪽을 보려면 굴려야 했다. 백분율 높이가 안 풀리는 자리라 HTML 로는
        안 드러난다."""
        page = self.one(3)
        m = page.evaluate("""() => {
          const b = e => e.getBoundingClientRect();
          const v = document.getElementById('aview');
          const im = document.querySelector('#acanvas img');
          return {vh: Math.round(b(v).height), ih: Math.round(b(im).height),
                  doc: document.documentElement.scrollHeight,
                  win: window.innerHeight,
                  inside: b(im).top >= b(v).top - 1 && b(im).bottom <= b(v).bottom + 1};
        }""")
        self.assertTrue(m["inside"], f"도판이 창을 넘겼다 {m}")
        self.assertLessEqual(m["ih"], m["vh"] + 1, f"그림이 창보다 높다 {m}")
        self.assertLessEqual(m["doc"], m["win"] + 2,
                             f"화면이 굴러간다 — 창 하나에 안 들어갔다 {m}")

    # --- 4번 -----------------------------------------------------------------

    def test_휠로_확대하고_맞춤으로_되돌린다(self):
        page = self.one(3)
        # **곱수만 본다.** 원본 PNG 를 물어 왔으면 뒤에 " 원본" 이 붙는다 —
        # 그것은 배율이 아니라 무엇을 그리고 있는가라 여기서 세지 않는다.
        self.assertTrue(page.inner_text("#azoom-lv").startswith("×1.0"))
        box = page.locator("#aview").bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.wheel(0, -600)
        page.wait_for_timeout(200)
        self.assertNotEqual(page.inner_text("#azoom-lv"), "×1.0", "휠이 안 먹었다")
        tr = page.evaluate(
            "getComputedStyle(document.getElementById('acanvas')).transform")
        self.assertNotIn(tr, ("none", "matrix(1, 0, 0, 1, 0, 0)"),
                         "확대가 캔버스에 안 걸렸다")
        page.click("#azoom-fit")
        page.wait_for_timeout(150)
        self.assertTrue(page.inner_text("#azoom-lv").startswith("×1.0"),
                        "맞춤이 안 되돌렸다")

    def test_배율을_퍼센트로_말하지_않는다(self):
        """원본 PNG 의 화소 수를 화면이 모른다 — 모르는 것을 100% 라고 부르면
        그 숫자로 판단하게 된다. **곱수로 말한다** (CLAUDE.md: 이름과 문구가
        어긋나면 둘 중 하나를 고친다)."""
        page = self.one(3)
        self.assertNotIn("%", page.inner_text("#azoom-lv"))
        self.assertIn("×", page.inner_text("#azoom-lv"))

    # --- 5번 -----------------------------------------------------------------

    def test_쪽으로_뛰어도_보던_모양_그대로다(self):
        page = self.one(3, spread=True)
        page.fill("#ajump-n", "5")
        with page.expect_navigation():
            page.click(".ajump button")
        self.assertIn("/band1/5/", page.url)
        self.assertIn("spread=1", page.url, "두 쪽으로 읽다 뛰었는데 한 장이 됐다")

    def test_없는_쪽으로_뛰면_격자가_말한다(self):
        """**조용히 첫 판을 내지 않는다** — 사람이 갔다고 믿는다 (129 · 3번)."""
        page = self.one(3)
        page.fill("#ajump-n", "999")
        with page.expect_navigation():
            page.click(".ajump button")
        self.assertIn("이 권에 없습니다", page.inner_text("main"))

    # --- 6번 -----------------------------------------------------------------

    def test_쪽_번호를_치는_중에는_키가_안_듣는다(self):
        """숫자를 치다 화살표를 누르면 쪽이 넘어가 **치던 번호가 사라진다.**"""
        page = self.one(3)
        page.click("#ajump-n")
        page.keyboard.type("5")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("-")
        page.wait_for_timeout(300)
        self.assertIn("/band1/3/", page.url, "입력칸에서 화살표가 쪽을 넘겼다")
        self.assertTrue(page.inner_text("#azoom-lv").startswith("×1.0"),
                        "입력칸에서 -가 배율을 건드렸다")
