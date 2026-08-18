"""도감 검색 화면 — 갈라 말해야 하는 자리들 (131).

DB 는 옆 세션이 넣었고(130) 이 시험은 **화면이 그 자료를 어떻게 말하는가**를
본다. 여기 세운 것은 전부 P15·119 가 "이렇게 말하면 안 된다" 고 적어 둔 자리다.

## 되살려서 잡히는가

- 1번 — `atlas_search` 에서 `binomial__icontains` 를 빼면 실패한다.
  **처음에 짠 것은 실패할 수 없는 시험이었다** — `Melosira ambigua` 로 찾으면
  표제어 `Melosira ambigua (GRUN.) …` 가 이미 그 글자를 품어 `name` 만으로도
  걸렸다. 실제로 갈리는 자리는 **도감이 옛 표기·오기를 쓰는 61건**이다
  (`Sceletonema` ~ `Skeletonema` · `Chaetoceras` ~ `Chaetoceros`, P15 5절)
- 2번 — `_placement_dict` 가 `pdf_page` 없이도 주소를 내면 실패한다. 한국 도감
  201건이 그 자리이고, 눌러서 404 가 나면 **"아직 안 구웠다"** 로 읽힌다
- 3번 — 템플릿에서 `pl.note` 를 빼면 실패한다. `plate` 가 240 인데 그 Tafel 이
  실재하지 않는 자리가 21건이라, 번호만 내면 **없는 것을 있다고 말한다**
- 4번 — `genus_guess` 가 거짓인 행에 "확정" 을 찍으면 실패한다. 표시가 없는데
  잘못 펴진 것이 있다는 것이 119 의 요점이다
- 5번 — `genus_only` 와 `unreadable` 을 한 문구로 합치면 실패한다. **도감이
  속까지만 내려간 것**과 **우리가 못 읽는 것**은 다른 말이다 (P15 8.4)
- 6번 — 빈 결과에 띠를 안 내면 실패한다. 조용히 비면 "도감에 없다" 로 읽힌다
"""
from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase
from ..models import Atlas, AtlasEntry, AtlasPlacement


class AtlasSearchTests(DiaRUGATestCase):
    def setUp(self):
        super().setUp()
        self.c = Client()
        a = Atlas.objects.create(key="schmidt", title="A. Schmidt, Atlas",
                                 short="Schmidt Atlas", sort_order=1)
        k = Atlas.objects.create(key="korean", title="한국동식물도감 제9권",
                                 short="한국 도감", sort_order=0)
        # **표제어와 이명법이 실제로 갈리는 자리** (실측 61건). 도감은 옛
        # 표기·오기를 그대로 쓰고 이명법 칸이 지금 철자를 든다 — 사람은 지금
        # 철자로 찾는다. `Sceletonema` ~ `Skeletonema` 는 P15 5절의 그 짝이다.
        e1 = AtlasEntry.objects.create(
            atlas=k, seq=1, name="Sceletonema costatum (GREV.) CLEVE",
            genus="Sceletonema", binomial="Skeletonema costatum",
            rank="species")
        # 한국 도감은 PDF 쪽을 안 적은 자리가 있다 (201건)
        AtlasPlacement.objects.create(entry=e1, seq=0, plate=21, book_page=147)

        e2 = AtlasEntry.objects.create(
            atlas=a, seq=1, name="Navicula abrupta", genus="Navicula",
            binomial="Navicula abrupta", rank="species", genus_guess=True)
        AtlasPlacement.objects.create(entry=e2, seq=0, plate=3, figures="1",
                                      volume="Band1", pdf_page=22,
                                      pdf_plate_page=23)
        # 주석이 plate 를 뒤집는 자리 (21건)
        AtlasPlacement.objects.create(
            entry=e2, seq=1, plate=240, volume="Band2", pdf_page=99,
            note="Tafel 아님 · 권 뒤 Verzeichnis(색인) 쪽에서 왔다")

        e3 = AtlasEntry.objects.create(
            atlas=a, seq=2, name="Navicula sp.", genus="Navicula",
            binomial="Navicula", rank="genus_only")
        AtlasPlacement.objects.create(entry=e3, seq=0, plate=8, pdf_page=15)
        e4 = AtlasEntry.objects.create(
            atlas=a, seq=3, name="Synedra cyclopиm", genus="Synedra",
            binomial="Synedra", rank="unreadable")
        AtlasPlacement.objects.create(entry=e4, seq=0, plate=9, pdf_page=17)

    def get(self, **q):
        return self.c.get(reverse("atlas"), q).content.decode()

    # 1) 지금 철자로 찾는데 표제어는 옛 표기다 — 이명법을 안 걸면 못 찾는다
    def test_matches_binomial_when_headword_differs(self):
        html = self.get(q="Skeletonema costatum")
        self.assertIn("Sceletonema costatum", html,
                      "지금 철자로 찾았는데 옛 표기 표제어가 안 걸렸다")
        self.assertIn("한국 도감", html)

    # 2) PDF 쪽이 없으면 링크를 안 낸다
    def test_no_link_without_pdf_page(self):
        html = self.get(q="Sceletonema")
        self.assertIn("책 p.147", html)
        self.assertNotIn("해설 p.", html)
        self.assertNotIn("/atlas/korean/main/", html)

    # 3) 주석이 plate 를 뒤집는 자리 — 번호만 내지 않는다
    def test_placement_note_is_shown(self):
        html = self.get(q="Navicula abrupta")
        self.assertIn("Verzeichnis", html)

    # 4) `genus_guess` 는 있는 쪽만 말한다. "확정" 이라는 말을 안 쓴다
    def test_genus_guess_marked_but_never_confirmed(self):
        html = self.get(q="Navicula abrupta")
        self.assertIn("속명 추정", html)
        plain = self.get(q="Sceletonema")
        self.assertNotIn("속명 추정", plain)
        for word in ("확정", "확인됨"):
            self.assertNotIn(word, plain, f"'{word}' 라고 말하면 안 된다 (119)")

    # 5) 속까지만 내려간 것과 못 읽는 것은 다른 말이다
    def test_genus_only_and_unreadable_differ(self):
        # **칩의 글자로 짚는다.** 원문 대조로 하면 "못 읽음" 칩의 툴팁에 든
        # 설명("도감이 속까지만 적은 것과 다른 말이다")에 걸린다 — 시험이
        # 성글면 통과·실패가 엉뚱한 이유로 갈린다.
        self.assertIn(">속까지<", self.get(q="Navicula sp"))
        html = self.get(q="Synedra")
        self.assertIn(">못 읽음<", html)
        self.assertNotIn(">속까지<", html)

    # 6) 빈 결과는 두 가지를 갈라 말한다
    def test_empty_result_says_both(self):
        html = self.get(q="zzzzznotfound")
        self.assertIn("도감에 없는 것", html)
        self.assertIn("표기가 달라", html)

    # 7) 거르는 칩은 페이지 번호를 안 들고 간다
    def test_chips_drop_offset(self):
        html = self.get(q="Navicula", offset="50")
        for line in html.splitlines():
            if 'class="chip' in line and "genus=" in line:
                self.assertNotIn("offset=", line)

    # 8) 도감 차례는 sort_order 다 (코드 정렬이 아니다)
    def test_books_ordered_by_sort_order(self):
        from viewer import data
        self.assertEqual([b["key"] for b in data.atlas_list()],
                         ["korean", "schmidt"])
