"""두 쪽 보기의 **배치** — 이름이 부딪히면 조용히 작아진다 (131).

3겹(테스트 클라이언트)은 200 과 글자만 본다. **이 고장은 거기서 안 잡힌다** —
`base.html` 이 이미 `.bookspread` 를 쓰고 있어서(P11 묶기 팝업 · `position: fixed`
· `max-width: 520px`) 같은 이름을 빌리면 펼침이 화면 구석에 520px 로 박힌다.
HTML 은 멀쩡하고 예외도 경고도 없다. **`getComputedStyle` 로만 보인다.**

CLAUDE.md 가 `.tools { display: none }` 으로 같은 자리를 두 번 겪었다고 적어
두었고, 이것이 세 번째다.
"""
import json
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from .base import BrowserTestCase
from ..base import write_image


class AtlasSpreadLayoutTest(BrowserTestCase):

    def make_data(self):
        for n in (1, 2, 3, 4):
            write_image(f"atlas/schmidt/band1/p{n:04d}.png", size=(400, 560))
        root = Path(settings.DATA_ROOT) / "atlas"
        root.mkdir(parents=True, exist_ok=True)
        (root / "atlases.json").write_text(json.dumps({
            "dpi": 300, "atlases": {"schmidt": {
                "code": "schmidt", "label": "Schmidt", "left_parity": "even",
                "volumes": [{"code": "band1", "label": "Band 1",
                             "pages": 4, "rendered": 4}]}}}), encoding="utf-8")

    def test_펼침이_제자리에_넓게_놓인다(self):
        page = self.open(reverse("atlas_page", args=["schmidt", "band1", 2])
                         + "?spread=1")
        page.wait_for_selector(".bookspread img", state="visible", timeout=10_000)
        m = page.evaluate("""() => {
          const sp = document.querySelector('.bookspread');
          const L = document.querySelector('.leaf.left');
          const R = document.querySelector('.leaf.right');
          const s = getComputedStyle(sp);
          const b = e => e.getBoundingClientRect();
          return {pos: s.position,
                  w: Math.round(b(sp).width),
                  main: Math.round(b(document.querySelector('main')).width),
                  lw: Math.round(b(L).width), rw: Math.round(b(R).width),
                  gap: Math.round(b(R).left - b(L).right),
                  sameRow: Math.abs(b(L).top - b(R).top) < 2};
        }""")
        # **`fixed` 면 base 의 팝업 규칙을 입은 것이다.**
        self.assertEqual(m["pos"], "static", "펼침이 팝업 규칙을 입었다")
        self.assertGreater(m["w"], m["main"] * 0.8,
                           f"펼침이 좁다 ({m['w']} / {m['main']}) — 이름이 부딪혔나")
        self.assertTrue(m["sameRow"], "두 쪽이 한 줄에 안 놓였다")
        self.assertEqual(m["gap"], 0, "제본 자리가 벌어졌다")

    def test_쪽번호가_바깥_모서리에_붙는다(self):
        """사용자가 정한 규칙 — 왼쪽은 좌상단, 오른쪽은 우상단."""
        page = self.open(reverse("atlas_page", args=["schmidt", "band1", 2])
                         + "?spread=1")
        page.wait_for_selector(".leaf.right .pgno", state="visible", timeout=10_000)
        m = page.evaluate("""() => {
          const b = e => e.getBoundingClientRect();
          const L = document.querySelector('.leaf.left'),
                R = document.querySelector('.leaf.right');
          const ln = L.querySelector('.pgno'), rn = R.querySelector('.pgno');
          return {leftIn: Math.round(b(ln).left - b(L).left),
                  leftFromRight: Math.round(b(L).right - b(ln).right),
                  rightIn: Math.round(b(R).right - b(rn).right),
                  rightFromLeft: Math.round(b(rn).left - b(R).left),
                  texts: [ln.textContent.trim(), rn.textContent.trim()]};
        }""")
        self.assertLess(m["leftIn"], m["leftFromRight"],
                        "왼쪽 쪽 번호가 좌상단이 아니다")
        self.assertLess(m["rightIn"], m["rightFromLeft"],
                        "오른쪽 쪽 번호가 우상단이 아니다")
        self.assertEqual(m["texts"], ["p.2", "p.3"])
