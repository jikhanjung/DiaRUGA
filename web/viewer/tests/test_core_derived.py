"""관찰에서 세어 오는 항목 (P17 6단계).

**저장하지 않는다.** 검출 수는 이미 DB 에 있다 — 관찰마다 `n_counted` 가 있고
시료마다 깊이가 있다. 테이블에 또 넣으면 두 벌이 되고, **교정을 하나 고치는
순간 어긋난다.** 여기서 잡는 것은 그 셈이 목록·합계와 같은 규칙을 쓰는가다.
"""
from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx
from .. import data
from ..models import CoreSeries, Locality, Site


def _keys(ctx):
    return {cs["key"]: cs for cs in ctx["series"] if cs["source"] == "derived"}


class DerivedTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()

    def test_관찰에서_검출_수를_센다(self):
        fx.make_world(slug="rs23", depth_cm=71.0, n_viewpoints=2,
                      n_candidates=3)
        ctx = data.locality_detail("RS23", "GC03")
        d = _keys(ctx)
        self.assertIn("d_counted", d)
        self.assertEqual(d["d_counted"]["n"], 1)
        self.assertEqual(d["d_counted"]["min_cm"], 71.0)

    def test_저장되지_않는다(self):
        """테이블에 또 넣으면 교정을 고치는 순간 어긋난다."""
        fx.make_world(slug="rs23", depth_cm=71.0)
        data.locality_detail("RS23", "GC03")
        self.assertEqual(CoreSeries.objects.count(), 0)

    def test_같은_깊이의_관찰은_더한다(self):
        """관찰은 시료 하나를 달리 처리해 본 것이라 동등하다 — 대표를 몰래
        고르지 않는다 (063). 대신 시야당 값을 함께 낸다."""
        w = fx.make_world(slug="a", depth_cm=100.0, n_viewpoints=2,
                          n_candidates=2)
        fx.make_world(slug="b", depth_cm=100.0, sample_code="100cm-2",
                      n_viewpoints=3, n_candidates=2)
        ctx = data.locality_detail("RS23", "GC03")
        rows = {r["slug"]: r for r in ctx["rows"]}
        want = rows["a"]["n_counted"] + rows["b"]["n_counted"]
        views = rows["a"]["n_groups"] + rows["b"]["n_groups"]
        ctx2 = data.locality_detail("RS23", "GC03",
                                    series_keys=["d_counted", "d_per_view"])
        got = {p["key"]: [pt["v"] for s in p["segments"] for pt in s]
               for p in ctx2["profiles"]}
        self.assertEqual(got["d_counted"], [float(want)])
        self.assertEqual(got["d_per_view"], [round(want / views, 3)])

    def test_숨긴_관찰도_센다(self):
        """`hidden` 은 보기 상태다 — 숫자가 보기 토글을 따라 흔들리면 안 된다."""
        w = fx.make_world(slug="rs23", depth_cm=71.0, n_candidates=3)
        before = _keys(data.locality_detail("RS23", "GC03"))["d_counted"]
        w.slide.hide_in_list = True
        w.slide.save(update_fields=["hide_in_list"])
        after = _keys(data.locality_detail("RS23", "GC03"))["d_counted"]
        self.assertEqual(after["n"], before["n"])

    def test_집계_제외는_뺀다(self):
        """`excluded` 는 자료의 성질이다 — 목록 합계와 같은 규칙."""
        w = fx.make_world(slug="rs23", depth_cm=71.0, n_candidates=3)
        w.slide.exclude_from_totals = True
        w.slide.save(update_fields=["exclude_from_totals"])
        ctx = data.locality_detail("RS23", "GC03")
        self.assertEqual(_keys(ctx), {})

    def test_깊이가_없으면_안_센다(self):
        """노두 시료의 위치는 거리가 아니라 순서다 — cm 축에 못 얹는다."""
        fx.make_world(slug="bp09", site_code="BP", loc_code="BP09",
                      kind="outcrop", area="kr", sample_code="0901")
        ctx = data.locality_detail("BP", "BP09")
        self.assertEqual(_keys(ctx), {})

    def test_분류마다_하나씩_생긴다(self):
        """`counted_classes()` 를 따른다 — 파편·미분류는 거기서 이미 빠져 있다."""
        fx.make_world(slug="rs23", depth_cm=71.0, n_candidates=3)
        d = _keys(data.locality_detail("RS23", "GC03"))
        want = {"d_" + c["key"] for c in data.counted_classes()}
        self.assertTrue(want <= set(d), f"빠진 것: {want - set(d)}")
        self.assertIn("d_chaetoceros", d)
        # 파편은 안 나온다
        self.assertNotIn("d_round_frag", d)

    def test_기본으로는_안_켠다(self):
        """켜지는 넷은 MS·함수율·Opal·TOC 다 (사용자 방침 2026-08-19)."""
        fx.make_world(slug="rs23", depth_cm=71.0, n_candidates=3)
        ctx = data.locality_detail("RS23", "GC03")
        self.assertFalse(any(cs["default_on"] for cs in _keys(ctx).values()))
        self.assertEqual(ctx["profiles"], [])

    def test_고르면_그려진다(self):
        fx.make_world(slug="rs23", depth_cm=71.0, n_candidates=3)
        r = self.client.get(reverse("core", args=["RS23", "GC03"]),
                            {"series": "d_counted"})
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn('class="cslane"', html)
        self.assertIn("검출 수", html)

    def test_사람이_고치는_목록에는_안_나온다(self):
        """저장돼 있지 않으니 고칠 것도 지울 것도 없다."""
        fx.make_world(slug="rs23", depth_cm=71.0, n_candidates=3)
        ctx = data.locality_detail("RS23", "GC03")
        self.assertEqual(ctx["manual_series"], [])

    def test_사람이_같은_이름표를_못_쓴다(self):
        """같은 `key` 가 둘이면 화면이 어느 쪽을 그리는지가 정렬에 달린다."""
        from .. import manage_data as md
        site = Site.objects.create(code="RS14", area="ant")
        loc = Locality.objects.create(site=site, code="GC04", kind="core")
        ok, m = md.create_series(loc, {"key": "d_counted", "label": "x"})
        self.assertFalse(ok)
        self.assertEqual(CoreSeries.objects.count(), 0)
