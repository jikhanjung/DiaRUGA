"""도감 도판 화면 — 조용히 다른 것을 내는 자리들 (129).

이 화면은 **DB 를 안 본다**(`viewer/atlas.py`). 파일이 곧 자료라 고장이
예외로 안 나고 **다른 그림·빈 화면**으로 난다. 여기 세운 것은 전부 짜면서
실제로 밟은 자리다.

## 되살려서 잡히는가

- 1번 — `rawimg` 를 `{% thumb rel 0 %}` 로 되돌리면 실패한다. `image` 뷰가
  `w` 를 **있으면 축소본**으로 읽고 `max(32, …)` 로 바닥을 깔아서, `w=0` 은
  원본이 아니라 **32px** 가 된다. 예외가 안 나고 그림만 작아진다
- 2번 — `_jpeg` 의 `content_type` 을 `"image/jpeg"` 로 되돌리면 실패한다.
  PNG 를 JPEG 라고 말하는 응답이라 브라우저가 눈치껏 그려 **화면으로는 안
  드러난다** — 내려받아야 안다
- 3번·4번 — 뷰에서 `?n=` 갈래를 빼면 실패한다. 격자 첫 판이 그대로 200 이라
  **사람은 갔다고 믿는다**
- 5번 — `CODE` 정규식을 느슨하게 하면 실패한다
- 6번 — `atlas.page()` 의 `n not in nums` 를 빼면 실패한다. 안 구운 쪽이
  200 으로 뜨고 그림만 안 나와 **원본에 그 쪽이 없다**고 읽힌다
- 7번 — 자리가 통째로 없을 때 500 이 나면 실패한다
"""
from pathlib import Path

from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase, write_image


def seed(root: Path):
    """도감 하나 · 권 하나 · 쪽 둘. 목록 파일까지 굽는 스크립트와 같은 모양으로."""
    for n in (68, 69):
        write_image(f"atlas/schmidt/band1/p{n:04d}.png", size=(40, 56))
    (root / "atlas").mkdir(parents=True, exist_ok=True)
    (root / "atlas" / "atlases.json").write_text(
        '{"dpi": 300, "atlases": {"schmidt": {"code": "schmidt",'
        ' "label": "A. Schmidt, Atlas der Diatomaceenkunde",'
        ' "volumes": [{"code": "band1", "label": "Band 1", "pages": 308,'
        ' "rendered": 2}]}}}', encoding="utf-8")


class AtlasPageTests(DiaRUGATestCase):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.root = Path(__import__("django.conf", fromlist=["settings"])
                         .settings.DATA_ROOT)
        seed(self.root)

    # 1) 원본 주소에는 폭이 없어야 한다
    def test_raw_url_has_no_width(self):
        html = self.c.get(reverse("atlas_page",
                                  args=["schmidt", "band1", 69])).content.decode()
        self.assertIn("원본 PNG", html)
        raw = [ln for ln in html.splitlines() if "원본 PNG</a>" in ln]
        self.assertTrue(raw, "원본 링크가 없다")
        self.assertNotIn("w=", raw[0],
                         "원본 링크에 폭이 붙었다 — w=0 은 32px 축소본이 된다")

    # 2) PNG 를 PNG 라고 말한다
    def test_png_served_as_png(self):
        r = self.c.get(reverse("image"), {"p": "atlas/schmidt/band1/p0069.png"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")

    # 3) 쪽 번호로 곧장 간다 — 색인이 그 번호를 들고 온다
    def test_jump_to_page(self):
        r = self.c.get(reverse("atlas_volume", args=["schmidt", "band1"]),
                       {"n": "68"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"],
                         reverse("atlas_page", args=["schmidt", "band1", 68]))

    # 4) 못 간 것을 말한다 — 조용히 격자를 내면 갔다고 믿는다
    def test_jump_to_missing_page_says_so(self):
        r = self.c.get(reverse("atlas_volume", args=["schmidt", "band1"]),
                       {"n": "99999"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("99999", r.content.decode())
        self.assertIn("없습니다", r.content.decode())

    # 5) 주소에서 온 값으로 디렉토리를 만든다 — 못 박혀 있어야 한다
    def test_codes_are_pinned(self):
        from viewer import atlas as A
        for bad in ("../../etc", "Schmidt", "band 1", "", "a" * 40, "sch/midt"):
            self.assertIsNone(A.volume(bad, "band1"), f"통과했다: {bad!r}")
            self.assertIsNone(A.page("schmidt", bad, 68), f"통과했다: {bad!r}")

    # 6) 안 구운 쪽은 404 다 — 빈 그림이 아니다
    def test_unrendered_page_is_404(self):
        r = self.c.get(reverse("atlas_page", args=["schmidt", "band1", 70]))
        self.assertEqual(r.status_code, 404)

    # 7) 자리가 없어도 화면은 선다
    def test_missing_root_still_renders(self):
        import shutil
        shutil.rmtree(self.root / "atlas")
        r = self.c.get(reverse("atlas"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("아직 하나도 안 떠", r.content.decode())

    # 8) 목록 파일이 없으면 폴더로 물러나되 화면은 선다 (굽는 중)
    def test_manifest_missing_falls_back(self):
        (self.root / "atlas" / "atlases.json").unlink()
        r = self.c.get(reverse("atlas"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("schmidt", r.content.decode())

    # 9) 머리줄의 문이 모든 화면에 있다 (사용자 2026-08-18)
    def test_header_link_everywhere(self):
        for url in (reverse("index"), reverse("atlas")):
            self.assertIn(reverse("atlas"), self.c.get(url).content.decode(),
                          f"{url} 에 도감 문이 없다")


class AtlasLinkTests(DiaRUGATestCase):
    """색인 → 도판 링크. **변환이 한 자리에만 있어야 한다** (129 · 옆 세션 합의).

    색인 자료는 권을 원문 표기(`"Band4"`)로 들고 있고 경로는 소문자다. 세
    화면이 각자 `.lower()` 하면 넷째 도감에서 갈린다 — `naming.py` 와 같은 줄.

    되살려서 잡히는가: `vol_code` 가 `.lower()` 를 안 하면 1번이, `None → main`
    을 안 하면 2번이, `page_url` 이 없는 쪽에도 주소를 안 내면 4번이 실패한다.
    """
    def setUp(self):
        super().setUp()
        from django.conf import settings
        seed(Path(settings.DATA_ROOT))

    def test_volume_code_lowercased(self):
        from viewer import atlas as A
        self.assertEqual(A.vol_code("Band4"), "band4")

    def test_null_volume_is_main(self):
        from viewer import atlas as A
        for v in (None, "", "   "):
            self.assertEqual(A.vol_code(v), "main")

    def test_link_from_index_placement(self):
        from viewer import atlas as A
        self.assertEqual(A.page_url("schmidt", "Band1", 68),
                         reverse("atlas_page", args=["schmidt", "band1", 68]))
        self.assertEqual(A.page_url("korean", None, 74),
                         reverse("atlas_page", args=["korean", "main", 74]))

    def test_link_does_not_check_disk(self):
        # 안 구운 쪽에도 주소는 난다 — 그 화면이 404 로 말한다. 링크마다
        # 디스크를 짚으면 검색 결과 한 판에 수백 번이 된다.
        from viewer import atlas as A
        self.assertTrue(A.page_url("schmidt", "Band1", 9999))
        self.assertFalse(A.has_page("schmidt", "Band1", 9999))
        self.assertTrue(A.has_page("schmidt", "Band1", 68))

    def test_bad_placement_gives_no_link(self):
        from viewer import atlas as A
        for bad in (None, "", "abc", 0, -3):
            self.assertEqual(A.page_url("schmidt", "Band1", bad), "")
