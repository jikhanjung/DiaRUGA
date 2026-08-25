"""종명 칸이 도감을 안다 · 검토 화면에서 카드로 (149).

두 가지를 본다. **자리는 다르지만 같은 이야기다** — 동정하는 사람이 한 화면에서
일을 끝내게 하는 것이고, 지금은 화면 사이를 오갈 때마다 무엇을 보고 있었는지
잃는다.

## 1. 종명 ↔ 도감

`species_seen()`(이미 쓴 이름)만으로는 **처음 적는 사람에게 아무것도 못 준다** —
종명이 0건이면 목록도 빈다. 도감은 반입만 되어 있으면 처음부터 차 있다.

## 2. 검토 화면 → 개체 카드

118 이 카탈로그에서 시야로 가는 길을 냈는데 **반대 방향이 없었다.** 개체를 두고
하는 말은 카탈로그에서 적기로 해 놓고(0036), 검토하다 그 자리로 가려면 화면을
따로 열어 번호로 다시 찾아야 했다.

## 되살려서 잡히는가

- 1번 — `_atlas_name_rows` 의 `binomial` 비었을 때 건너뛰기를 빼면 실패한다.
  `Navicula`(속까지) 와 못 읽는 항목이 종명 칸의 값으로 나가면 **119 가 갈라
  놓은 둘을 화면이 도로 섞는다**
- 2번 — 값으로 모으는 것을 빼면 실패한다. 같은 이름이 도감 둘에 실려 있고,
  그대로 내면 자동완성 목록에 같은 값이 두 번 놓인다
- 4번 — `row["plate"]` 가 `plate_url` 없는 자리를 고르면 실패한다. 한국 도감
  201건이 PDF 쪽 없이 앉아 있고, 눌러서 404 가 나면 "아직 안 구웠다" 로 읽힌다
- 6번 — `atlas_for_names` 를 `binomial__in` 으로 되돌리면 실패한다. SQLite 는
  글자를 그대로 맞춰 첫 글자를 달리 친 것을 못 찾는다
- 7번 — 카드마다 도감을 물으면 실패한다. 한 판이 120장이라 질의가 120번 난다(105)
- 11번 — 파편을 펴 주는 줄을 빼면 실패한다. **파편은 기본으로 감춰져 있어**
  눌러서 온 사람에게 빈 자리가 보인다
- 13번 — 쪽을 안 옮기면 실패한다. 한 판이 120장이라 셋째 쪽의 개체는 "없다" 가
  된다
"""
from unittest.mock import patch

from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from . import factories as fx
from .base import DiaRUGATestCase
from .. import data
from ..models import Atlas, AtlasEntry, AtlasPlacement, RunBatch


def make_atlas():
    """도감 둘. **실제로 갈리는 자리만 세운다** (P15 · 119).

    - 같은 이름이 도감 둘에 실린 것 (`Melosira ambigua`)
    - PDF 도판 쪽이 없는 자리 (한국 도감 201건)
    - 이명법이 없는 항목 — 속까지만 내려간 것과 못 읽는 것
    """
    a = Atlas.objects.create(key="schmidt", title="A. Schmidt, Atlas",
                             short="Schmidt Atlas", sort_order=1)
    k = Atlas.objects.create(key="korean", title="한국동식물도감 제9권",
                             short="한국 도감", sort_order=0)

    e1 = AtlasEntry.objects.create(
        atlas=a, seq=1, name="Melosira ambigua (GRUN.) O. F. MÜLLER",
        genus="Melosira", binomial="Melosira ambigua", rank="species")
    AtlasPlacement.objects.create(entry=e1, seq=0, plate=3, figures="1",
                                  volume="Band1", pdf_page=22,
                                  pdf_plate_page=23)
    # 같은 이름이 한국 도감에도 있다 — **자동완성 목록에 두 번 놓이면 안 된다**
    e2 = AtlasEntry.objects.create(
        atlas=k, seq=1, name="Melosira ambigua", genus="Melosira",
        binomial="Melosira ambigua", rank="species")
    AtlasPlacement.objects.create(entry=e2, seq=0, plate=21, book_page=147)

    # PDF 도판 쪽이 없는 자리만 가진 항목 (한국 도감 201건)
    e3 = AtlasEntry.objects.create(
        atlas=k, seq=2, name="Cocconeis placentula EHRENBERG",
        genus="Cocconeis", binomial="Cocconeis placentula", rank="species")
    AtlasPlacement.objects.create(entry=e3, seq=0, plate=9, book_page=151)

    # 이명법이 없는 둘 — 속까지만 내려간 것과 못 읽는 것 (119 가 가른 자리)
    e4 = AtlasEntry.objects.create(
        atlas=a, seq=2, name="Melosira sp.", genus="Melosira",
        binomial="", rank="genus_only")
    AtlasPlacement.objects.create(entry=e4, seq=0, plate=8, pdf_page=15,
                                  pdf_plate_page=16)
    e5 = AtlasEntry.objects.create(
        atlas=a, seq=3, name="Melosira cyclopиm", genus="Melosira",
        binomial="", rank="unreadable")
    AtlasPlacement.objects.create(entry=e5, seq=0, plate=9, pdf_page=17,
                                  pdf_plate_page=18)
    return a, k


class AtlasSuggestTest(DiaRUGATestCase):
    """자동완성이 무엇을 내는가."""

    def setUp(self):
        super().setUp()
        make_atlas()
        self.c = Client()

    def rows(self, q):
        r = self.c.get(reverse("atlas_suggest"), {"q": q})
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()["rows"]

    # 1) 이명법이 없는 항목은 값으로 안 나간다
    #
    # **값 목록을 통째로 못 박는다.** "속명이 안 들어 있다" 만 보면 그 자리를
    # `binomial or name` 으로 되돌려도 통과한다 — 그때 나가는 값은
    # `Melosira sp.` 라서 속명 검사에 안 걸린다. 실패할 수 없는 시험이 된다.
    def test_이명법이_없는_항목은_안_낸다(self):
        vals = [r["value"] for r in self.rows("Melosira")]
        # 넷 중 이명법을 든 것은 하나뿐이다 — 나머지 셋(`sp.` · 못 읽는 것)은
        # **119 가 갈라 놓은 쪽**이라 종명 칸의 값이 아니다.
        self.assertEqual(vals, ["Melosira ambigua"],
                         f"이명법이 없는 항목이 값으로 나갔다: {vals}")

    # 2) 같은 이름이 도감 둘에 실려도 값은 하나다
    def test_같은_이름을_한_번만_낸다(self):
        rows = [r for r in self.rows("ambigua")
                if r["value"] == "Melosira ambigua"]
        self.assertEqual(len(rows), 1, "같은 값이 목록에 두 번 놓인다")
        # 어느 도감에 있는지는 함께 말한다 — 값이 하나라고 출처를 잃으면 안 된다
        self.assertCountEqual(rows[0]["atlases"], ["한국 도감", "Schmidt Atlas"])

    # 3) 한 글자로는 안 찾는다 — 2천 행의 절반이 걸려 목록이 뜻을 잃는다
    def test_한_글자로는_안_찾는다(self):
        self.assertEqual(self.rows("M"), [])

    # 4) PDF 도판 쪽이 없으면 띄울 자리를 안 고른다
    def test_도판_쪽이_없으면_자리를_안_고른다(self):
        rows = self.rows("Cocconeis")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["plate"],
                          "PDF 쪽이 없는 자리를 도판으로 골랐다 — 눌러서 404 다")
        # 표제어는 그대로 걸린다 — **없는 것과 못 짚는 것은 다른 말이다**
        self.assertEqual(rows[0]["value"], "Cocconeis placentula")

    # 4-b) 도판이 있는 쪽은 주소와 경로를 함께 낸다
    def test_도판이_있으면_주소와_경로를_낸다(self):
        pl = self.rows("ambigua")[0]["plate"]
        self.assertEqual(pl["plate_url"], "/atlas/schmidt/band1/23/")
        self.assertEqual(pl["plate_rel"], "atlas/schmidt/band1/p0023.png")


class CatalogAtlasTest(DiaRUGATestCase):
    """카탈로그 화면이 도감을 잇는가."""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=3)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def setUp(self):
        super().setUp()
        make_atlas()
        self.c = Client()
        self.url = reverse("catalog", args=["rs23"])
        self.rows = data.candidate_rows("rs23")

    def name(self, i, species):
        """개체 하나에 종명을 적어 둔다."""
        fx.add_review(self.w.vp, self.rows[i]["key"],
                      image=self.rows[i]["image_id"], species=species)

    def get(self, **q):
        r = self.c.get(self.url, q)
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.content.decode()

    # 5) 적어 둔 종명의 도판 단추가 뜬다
    def test_적힌_종명의_도판이_뜬다(self):
        self.name(0, "Melosira ambigua")
        html = self.get()
        self.assertIn('data-plate="atlas/schmidt/band1/p0023.png"', html)
        self.assertIn("/atlas/schmidt/band1/23/", html)

    # 6) 대소문자를 달리 적어도 찾는다
    def test_대소문자를_안_가린다(self):
        self.name(0, "melosira AMBIGUA")
        self.assertIn('data-plate="atlas/schmidt/band1/p0023.png"', self.get())

    # 7) 카드가 늘어도 도감 질의는 안 는다 (105)
    #
    # **수를 못 박지 않는다** — 자리를 함께 뜨느라 두 번 나가고(항목·자리),
    # 거기에 수를 박으면 질의를 하나 합치는 것만으로 시험이 깨진다. 걸러야 할
    # 것은 **카드 수를 따라 느는 것**이다.
    def test_카드가_늘어도_도감_질의는_안_는다(self):
        def n_atlas_queries():
            with CaptureQueriesContext(connection) as ctx:
                self.get()
            return len([q for q in ctx.captured_queries
                        if "atlasentry" in q["sql"].lower()])

        self.name(0, "Melosira ambigua")
        one = n_atlas_queries()
        self.name(1, "Melosira ambigua")
        self.name(2, "Cocconeis placentula")
        self.assertEqual(n_atlas_queries(), one,
                         "카드가 느니 도감 질의도 늘었다 — 카드마다 되묻고 있다")

    # 8) 도감에 없는 이름이면 단추가 안 뜬다 — **가두지는 않는다**
    def test_도감에_없는_이름도_적힌다(self):
        self.name(0, "Eucampia antarctica")
        html = self.get()
        self.assertIn("Eucampia antarctica", html, "도감에 없다고 종명을 지웠다")
        self.assertNotIn("data-plate=\"atlas/", html)


class CatalogHighlightTest(DiaRUGATestCase):
    """검토 화면이 짚어 온 개체를 카탈로그가 받는가 (#4)."""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=3)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def setUp(self):
        super().setUp()
        self.c = Client()
        self.url = reverse("catalog", args=["rs23"])
        self.rows = data.candidate_rows("rs23")

    def get(self, **q):
        r = self.c.get(self.url, q)
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.content.decode()

    def card_of(self, html, key):
        """그 개체의 카드 한 조각. 없으면 빈 문자열."""
        i = html.find(f'data-key="{key}"')
        if i < 0:
            return ""
        return html[max(0, i - 400):i + 200]

    # 9) 짚어 온 카드에 표시가 붙는다
    def test_짚어_온_카드에_표시가_붙는다(self):
        row = self.rows[1]
        html = self.get(obj=row["key"], img=row["image_id"])
        self.assertIn("hl", self.card_of(html, row["key"]))
        # 다른 카드에는 안 붙는다 — 붙으면 표시가 아무 말도 안 하는 것이다
        self.assertNotIn("catcard hl", self.card_of(html, self.rows[0]["key"]))

    # 10) 못 찾으면 왜 없는지 적는다
    def test_못_찾으면_왜_없는지_적는다(self):
        html = self.get(obj="no-such-key", img=self.rows[0]["image_id"])
        self.assertIn("카탈로그에 없습니다", html)
        # **화면이 서기는 한다** — 표시는 곁들이는 것이지 서는 조건이 아니다(118)
        self.assertIn("catcard", html)

    # 11) 파편이면 펴 준다 — 기본으로 감춰져 있다
    def test_파편이면_펴_준다(self):
        row = self.rows[2]
        fx.add_review(self.w.vp, row["key"], image=row["image_id"],
                      label="round_frag")
        # 그냥 열면 안 보인다 (파편은 기본으로 감춘다)
        self.assertNotIn(f'data-key="{row["key"]}"', self.get())
        # 짚어 오면 보인다
        html = self.get(obj=row["key"], img=row["image_id"])
        self.assertIn("hl", self.card_of(html, row["key"]))

    # 12) 지운 개체를 짚어 오면 「지운 것」 을 열고 그렇게 말한다
    def test_지운_개체는_지운_것을_연다(self):
        row = self.rows[0]
        fx.add_review(self.w.vp, row["key"], image=row["image_id"],
                      removed=True)
        html = self.get(obj=row["key"], img=row["image_id"])
        self.assertIn("「지운 것」 을 열었습니다", html)
        self.assertIn("hl", self.card_of(html, row["key"]))

    # 13) 그 카드가 있는 쪽을 연다
    #
    # **카탈로그의 차례로 짚는다.** `candidate_rows` 의 차례로 집으면 그것이
    # 마침 첫 쪽에 놓여 **쪽을 안 옮겨도 통과한다** — 실제로 그렇게 짰다가
    # 되살려 보고 알았다(카탈로그는 번호 차례라 순서가 다르다).
    @patch("viewer.views.CATALOG_PER_PAGE", 1)
    def test_그_카드가_있는_쪽을_연다(self):
        crows = data.catalog_rows("rs23")
        self.assertGreater(len(crows), 1, "카드가 하나면 쪽이 갈리지 않는다")
        row, first = crows[-1], crows[0]
        html = self.get(obj=row["key"], img=row["image_id"])
        self.assertIn(f'data-key="{row["key"]}"', html,
                      "짚어 온 카드가 있는 쪽을 안 열었다")
        self.assertNotIn(f'data-key="{first["key"]}"', html,
                         "첫 쪽을 그대로 냈다")

    # 14) 검토 화면이 카탈로그로 가는 재료를 싣는다
    #
    # **눌러서 실제로 가는지는 여기서 못 본다** — 우클릭 메뉴는 JS 가 만든다
    # (`browser/` 가 볼 일이다). 이 겹은 재료가 거기까지 가는지만 본다.
    def test_검토_화면이_카탈로그_주소를_싣는다(self):
        gid = self.w.viewpoints[0].idx
        r = self.c.get(reverse("group", args=["rs23", gid]))
        self.assertEqual(r.status_code, 200, r.content[:300])
        html = r.content.decode()
        self.assertIn('CATALOG_URL = "/d/rs23/catalog/"', html)
        self.assertIn("이 개체 카드로", html)
