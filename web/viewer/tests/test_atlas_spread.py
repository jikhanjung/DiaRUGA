"""두 쪽 보기 — 짝이 한 칸 밀리는 고장 (131).

**그림은 나오고 짝만 틀린다.** 예외도 경고도 없어서, 사람이 해설과 도판을
나란히 보다가 "이 도감은 원래 이렇게 안 맞나" 로 읽는다. 그래서 도감마다
세운다.

## 왼쪽이 어느 홀짝인지는 자료로 갈랐다

| 도감 | 근거 | 왼쪽 |
|---|---|---|
| Schmidt | 도판면(p.69)의 Tafel 번호 `26` 이 **우상단** → 홀수가 오른쪽 | 짝수 |
| 한국 | 색인의 `책 p.172 · PDF p.73` — 책 짝수면(verso)이 PDF 홀수다 | 홀수 |
| 동남극 | 아래 가운데 `- 73 -` 가 PDF p.2 — 책 홀수면(recto)이 PDF 짝수다 | 홀수 |

## 되살려서 잡히는가

- 1·2번 — `left_parity` 를 한쪽으로 못 박으면 실패한다
- 3번 — 짝의 한쪽만 보고 펼침을 만들면 실패한다(69 로 들어가도 68–69 여야 한다)
- 4번 — 없는 쪽에 빈 칸을 그리면 실패한다. 표지가 혼자 서는 자리인데 옆에
  회색 네모를 두면 사람이 **안 구운 쪽**으로 읽는다
- 5번 — 앞뒤 주소에서 `?spread=1` 을 빼면 실패한다. 한 장 보기로 튕겨 나가서
  **넘길 때마다 보기가 바뀐다**
"""
import json
from pathlib import Path

from django.conf import settings
from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase, write_image


def seed_book(parity: str, atlas="schmidt", vol="band1", pages=range(1, 7)):
    for n in pages:
        write_image(f"atlas/{atlas}/{vol}/p{n:04d}.png", size=(40, 56))
    root = Path(settings.DATA_ROOT) / "atlas"
    root.mkdir(parents=True, exist_ok=True)
    mf = root / "atlases.json"
    data = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {
        "dpi": 300, "atlases": {}}
    data["atlases"][atlas] = {
        "code": atlas, "label": atlas, "left_parity": parity,
        "volumes": [{"code": vol, "label": vol, "pages": len(list(pages)),
                     "rendered": len(list(pages))}]}
    mf.write_text(json.dumps(data), encoding="utf-8")


class SpreadTests(DiaRUGATestCase):
    def setUp(self):
        super().setUp()
        self.c = Client()

    # 1) Schmidt — 짝수가 왼쪽 (해설면 왼쪽 · 도판면 오른쪽)
    def test_even_left_atlas(self):
        from viewer import atlas as A
        seed_book("even")
        s = A.spread("schmidt", "band1", 4)
        self.assertEqual((s["left"]["n"], s["right"]["n"]), (4, 5))

    # 2) 한국·동남극 — 홀수가 왼쪽
    def test_odd_left_atlas(self):
        from viewer import atlas as A
        seed_book("odd", atlas="korean", vol="main")
        s = A.spread("korean", "main", 4)
        self.assertEqual((s["left"]["n"], s["right"]["n"]), (3, 4))

    # 3) 짝의 어느 쪽으로 들어와도 같은 펼침이다
    def test_either_page_gives_same_spread(self):
        from viewer import atlas as A
        seed_book("even")
        a, b = A.spread("schmidt", "band1", 4), A.spread("schmidt", "band1", 5)
        self.assertEqual((a["left"]["n"], a["right"]["n"]),
                         (b["left"]["n"], b["right"]["n"]))

    # 4) 짝이 없는 쪽은 혼자 선다 — 빈 칸을 그리지 않는다
    def test_lone_page_has_no_empty_slot(self):
        from viewer import atlas as A
        seed_book("even")
        s = A.spread("schmidt", "band1", 1)
        self.assertIsNone(s["left"], "p.1 의 짝(p.0)은 없다")
        self.assertEqual(s["right"]["n"], 1)
        html = self.c.get(reverse("atlas_page", args=["schmidt", "band1", 1]),
                          {"spread": "1"}).content.decode()
        self.assertIn("alone", html)
        self.assertEqual(html.count('class="leaf'), 1)

    # 5) 넘겨도 두 쪽 보기가 유지된다
    def test_navigation_keeps_spread(self):
        seed_book("even")
        html = self.c.get(reverse("atlas_page", args=["schmidt", "band1", 4]),
                          {"spread": "1"}).content.decode()
        import re
        nav = re.findall(r'href="(/atlas/schmidt/band1/\d+/[^"]*)"', html)
        moves = [u for u in nav if u.rstrip("/").split("/")[-1] != "4"]
        self.assertTrue(moves, "앞뒤로 갈 주소가 없다")
        self.assertTrue(any("spread=1" in u for u in moves),
                        "넘기는 주소가 한 장 보기로 튕긴다")

    # 6) 앞뒤는 펼침 단위로 옮긴다 — 한 쪽씩 가면 같은 펼침을 두 번 본다
    def test_moves_by_spread_not_by_page(self):
        from viewer import atlas as A
        seed_book("even")
        s = A.spread("schmidt", "band1", 4)          # 4–5
        self.assertEqual(s["next"], 6, "다음은 6 이다 — 5 로 가면 같은 펼침이다")
        nxt = A.spread("schmidt", "band1", s["next"])
        # 쪽이 여섯뿐이라 마지막 펼침은 6 혼자다. **짝이 없는 것과 없는 쪽에
        # 빈 칸을 그리는 것은 다르다** — 여기서는 앞의 것만 본다.
        self.assertEqual(nxt["left"]["n"], 6)
        self.assertIsNone(nxt["right"])
        self.assertEqual(A.spread("schmidt", "band1", 4)["prev"], 3)

    # 7) 목록에 값이 없으면 홀수-왼쪽으로 본다 (굽는 쪽이 표에 없는 도감을 거절한다)
    def test_default_parity(self):
        from viewer import atlas as A
        seed_book("")
        self.assertEqual(A.left_parity("schmidt"), "odd")
