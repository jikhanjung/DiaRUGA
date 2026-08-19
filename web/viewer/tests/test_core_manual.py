"""코어 자료를 사람이 넣는다 (P17 5단계).

여기서 잡는 것은 **적어 놓은 대로 실제로 막히는가**다.

- 반입 항목에 손으로 넣으면 다음 반입에 지워진다 → 아예 못 하게 했는가
- 항목의 속성을 고치는 일이 그 항목의 점을 건드리는가 (116)
- 미리 보기와 저장이 **같은 파서**를 지나는가 (둘로 갈리면 "보기에서는 되는데
  저장하면 다르다" 가 생긴다)
- 화면에서 막은 것을 **서버가 다시 보는가** (화면에서 막는 것은 막는 것이 아니다)
"""
from django.urls import reverse

from .base import DiaRUGATestCase
from .. import manage_data as md
from ..models import CorePoint, CoreSeries, Locality, Site


def _loc(site_code="RS14", loc_code="GC04"):
    site = Site.objects.create(code=site_code, area="ant")
    return Locality.objects.create(site=site, code=loc_code, kind="core")


def _series(loc, key, *, source="manual", points=()):
    cs = CoreSeries.objects.create(locality=loc, key=key, label=key.upper(),
                                   unit="개/g", source=source)
    CorePoint.objects.bulk_create(
        [CorePoint(series=cs, depth_mm=mm, value=v) for mm, v in points])
    return cs


class ParseTest(DiaRUGATestCase):
    """`parse_points` — 붙여넣기를 읽는 **규칙은 여기 하나뿐이다.**"""

    def test_탭_쉼표_빈칸을_다_받는다(self):
        """엑셀에서 두 칸을 긁으면 탭이다. 손으로 적으면 쉼표나 빈칸이다."""
        got = md.parse_points("0\t120\n4,135.5\n8 98")
        self.assertEqual(got["rows"], {0: 120.0, 40: 135.5, 80: 98.0})
        self.assertEqual(got["skipped"], [])

    def test_cm_를_mm_정수로_든다(self):
        got = md.parse_points("0.1 1\n36.2 2")
        self.assertEqual(sorted(got["rows"]), [1, 362])

    def test_머리글과_빈줄과_주석을_건너뛴다(self):
        got = md.parse_points("깊이\t개수\n\n# 메모\n0\t120")
        self.assertEqual(got["rows"], {0: 120.0})
        # **버린 줄을 센다.** 조용히 건너뛰면 왜 안 들어왔는지 알 수 없다
        self.assertEqual(len(got["skipped"]), 1)
        self.assertIn("1행", got["skipped"][0])

    def test_칸이_하나면_버린다(self):
        got = md.parse_points("120")
        self.assertEqual(got["rows"], {})
        self.assertEqual(len(got["skipped"]), 1)

    def test_음수_깊이를_버린다(self):
        got = md.parse_points("-4 120\n0 130")
        self.assertEqual(got["rows"], {0: 130.0})
        self.assertIn("음수", got["skipped"][0])

    def test_같은_깊이_같은_값은_한_번만(self):
        """반입기(`read_block`)와 같은 규칙이다."""
        got = md.parse_points("16 141\n16,141")
        self.assertEqual(got["rows"], {160: 141.0})
        self.assertEqual(got["clash"], [])

    def test_같은_깊이에_다른_값이면_말한다(self):
        """**어느 쪽이 맞는지 사람이 정한다.**"""
        got = md.parse_points("16 141\n16 99")
        self.assertEqual(len(got["clash"]), 1)

    def test_너무_많으면_멈춘다(self):
        text = "\n".join(f"{i} 1" for i in range(md.MAX_PASTE_LINES + 50))
        got = md.parse_points(text)
        self.assertEqual(len(got["rows"]), md.MAX_PASTE_LINES)
        self.assertTrue(any("줄까지" in s for s in got["skipped"]))


class PreviewTest(DiaRUGATestCase):
    """미리 보기. **아무것도 안 쓴다** — 누르기 전에 무엇이 일어날지만 본다."""

    def setUp(self):
        super().setUp()
        self.loc = _loc()
        self.cs = _series(self.loc, "chaetoceros", points=[(0, 1.0), (100, 2.0)])

    def test_새로_들어올_것과_덮을_것을_가른다(self):
        ok, pv = md.preview_points(self.loc, "chaetoceros", "0 9\n200 3")
        self.assertTrue(ok)
        self.assertEqual((pv["n_new"], pv["n_over"], pv["n_have"]), (1, 1, 2))
        # 갈아치우기를 고르면 사라지는 수도 미리 말한다 (063)
        self.assertEqual(pv["n_gone"], 1)

    def test_아무것도_안_쓴다(self):
        md.preview_points(self.loc, "chaetoceros", "0 9\n200 3")
        self.assertEqual(CorePoint.objects.filter(series=self.cs).count(), 2)
        self.assertEqual(self.cs.points.get(depth_mm=0).value, 1.0)

    def test_반입_항목은_거절한다(self):
        _series(self.loc, "opal", source="import", points=[(0, 1.0)])
        ok, pv = md.preview_points(self.loc, "opal", "0 9")
        self.assertFalse(ok)
        self.assertIn("반입한 항목", pv["error"])


class SaveTest(DiaRUGATestCase):
    """저장. **항목 하나만 건드리는 좁은 문이다.**"""

    def setUp(self):
        super().setUp()
        self.loc = _loc()
        self.cs = _series(self.loc, "chaetoceros", points=[(0, 1.0), (100, 2.0)])

    def _vals(self):
        return dict(CorePoint.objects.filter(series=self.cs)
                    .values_list("depth_mm", "value"))

    def test_덮되_나머지는_둔다(self):
        ok, m = md.save_points(self.loc, "chaetoceros", "0 9\n200 3",
                               replace=False)
        self.assertTrue(ok, m)
        # 200 cm 는 2000 mm 다 — DB 는 mm 로 든다 (`CorePoint` 머리말)
        self.assertEqual(self._vals(), {0: 9.0, 100: 2.0, 2000: 3.0})

    def test_갈아치우면_나머지가_사라진다(self):
        ok, m = md.save_points(self.loc, "chaetoceros", "0 9", replace=True)
        self.assertTrue(ok, m)
        self.assertEqual(self._vals(), {0: 9.0})

    def test_다른_항목은_안_건드린다(self):
        other = _series(self.loc, "other", points=[(0, 7.0)])
        md.save_points(self.loc, "chaetoceros", "0 9", replace=True)
        self.assertEqual(other.points.count(), 1)

    def test_반입_항목에는_못_넣는다(self):
        cs = _series(self.loc, "opal", source="import", points=[(0, 1.0)])
        ok, m = md.save_points(self.loc, "opal", "0 9", replace=True)
        self.assertFalse(ok)
        self.assertIn("반입한 항목", m)
        self.assertEqual(cs.points.get(depth_mm=0).value, 1.0)

    def test_값이_엇갈리면_아무것도_안_쓴다(self):
        """**서버가 다시 검사한다** — 미리 보기를 안 거친 요청이 들어올 수 있다."""
        ok, m = md.save_points(self.loc, "chaetoceros", "0 9\n0 8", replace=True)
        self.assertFalse(ok)
        self.assertEqual(self._vals(), {0: 1.0, 100: 2.0})

    def test_읽을_점이_하나도_없으면_안_쓴다(self):
        ok, m = md.save_points(self.loc, "chaetoceros", "깊이 개수", replace=True)
        self.assertFalse(ok)
        self.assertEqual(len(self._vals()), 2)


class SeriesEditTest(DiaRUGATestCase):
    """항목의 속성. **점과 다른 문이다** (116)."""

    def setUp(self):
        super().setUp()
        self.loc = _loc()

    def test_만든_것은_언제나_수동이다(self):
        ok, m = md.create_series(self.loc, {"key": "chaetoceros",
                                            "label": "Chaetoceros 개체수",
                                            "unit": "개/g"})
        self.assertTrue(ok, m)
        cs = CoreSeries.objects.get(locality=self.loc, key="chaetoceros")
        self.assertEqual(cs.source, "manual")

    def test_대문자로_적어도_소문자로_들어간다(self):
        """기계 이름이라 대소문자를 가릴 이유가 없다. **화면의 `pattern` 도
        같은 것을 받는다** — 폼이 막는데 서버가 받으면 둘이 다른 말을 한다."""
        ok, m = md.create_series(self.loc, {"key": "Chaetoceros", "label": "C"})
        self.assertTrue(ok, m)
        self.assertTrue(CoreSeries.objects.filter(key="chaetoceros").exists())

    def test_이름표_규칙을_지킨다(self):
        """`key` 는 주소에 실린다 — 아무 글자나 받으면 링크가 깨진다."""
        for bad in ("9x", "쇄설물", "a b", "", "-x", "a-b"):
            ok, _ = md.create_series(self.loc, {"key": bad, "label": "x"})
            self.assertFalse(ok, f"{bad!r} 이 통과했다")
        self.assertEqual(CoreSeries.objects.count(), 0)

    def test_같은_이름표는_두_번_못_만든다(self):
        md.create_series(self.loc, {"key": "a", "label": "A"})
        ok, m = md.create_series(self.loc, {"key": "a", "label": "A"})
        self.assertFalse(ok)
        self.assertEqual(CoreSeries.objects.count(), 1)

    def test_속성을_고쳐도_점은_그대로다(self):
        cs = _series(self.loc, "a", points=[(0, 1.0), (100, 2.0)])
        ok, m = md.update_series(self.loc, "a", {"label": "새 이름", "unit": "%"})
        self.assertTrue(ok, m)
        cs.refresh_from_db()
        self.assertEqual(cs.label, "새 이름")
        self.assertEqual(cs.points.count(), 2)

    def test_반입_항목은_못_고친다(self):
        _series(self.loc, "opal", source="import", points=[(0, 1.0)])
        ok, m = md.update_series(self.loc, "opal", {"label": "x"})
        self.assertFalse(ok)
        self.assertIn("반입한 항목", m)
        self.assertTrue(CoreSeries.objects.filter(key="opal").exists())

    def test_반입_항목은_지울_수는_있다(self):
        """**지우는 것은 고치는 것과 다르다.** 고치면 다음 반입이 덮어 헛일이
        되지만 지우는 것은 다시 반입하면 돌아온다. 그리고 막아 두면 반입 자료가
        붙은 지점을 영영 못 지운다(지우기 문턱이 코어 자료를 센다)."""
        _series(self.loc, "opal", source="import", points=[(0, 1.0)])
        ok, m = md.delete_series(self.loc, "opal")
        self.assertTrue(ok, m)
        self.assertIn("다시 반입하면", m)
        self.assertEqual(CoreSeries.objects.count(), 0)

    def test_지우면_점도_간다(self):
        _series(self.loc, "a", points=[(0, 1.0), (100, 2.0)])
        ok, m = md.delete_series(self.loc, "a")
        self.assertTrue(ok, m)
        # 몇 점이 함께 갔는지 말한다 (063)
        self.assertIn("2개", m)
        self.assertEqual(CorePoint.objects.count(), 0)


class ManualViewTest(DiaRUGATestCase):
    """문 둘. **POST 전용이다** — 주소를 누르는 것만으로 지워지면 안 된다."""

    def setUp(self):
        super().setUp()
        self.loc = _loc()
        self.series_url = reverse("core_series_edit", args=["RS14", "GC04"])
        self.points_url = reverse("core_points_edit", args=["RS14", "GC04"])

    def test_GET_은_안_받는다(self):
        for u in (self.series_url, self.points_url):
            self.assertEqual(self.client.get(u).status_code, 405)

    def test_만들고_넣고_지운다(self):
        r = self.client.post(self.series_url, {"act": "create", "key": "ch",
                                               "label": "Chaetoceros"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("msg=", r["Location"])
        self.client.post(self.points_url, {"key": "ch", "points": "0 9\n4 8"})
        self.assertEqual(CorePoint.objects.count(), 2)
        self.client.post(self.series_url, {"act": "delete", "key": "ch"})
        self.assertEqual(CoreSeries.objects.count(), 0)

    def test_미리_보기는_화면을_돌려주고_안_쓴다(self):
        _series(self.loc, "ch")
        r = self.client.post(self.points_url,
                             {"key": "ch", "points": "0 9", "act": "preview"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("새로 들어오는 점", r.content.decode())
        self.assertEqual(CorePoint.objects.count(), 0)

    def test_노두에는_안_만들어진다(self):
        """화면이 이미 안 내지만 **화면에서 막는 것은 막는 것이 아니다.**"""
        site = Site.objects.create(code="BP", area="kr")
        Locality.objects.create(site=site, code="BP09", kind="outcrop")
        r = self.client.post(reverse("core_series_edit", args=["BP", "BP09"]),
                             {"act": "create", "key": "a", "label": "A"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("err=", r["Location"])
        self.assertEqual(CoreSeries.objects.count(), 0)

    def test_점이_없어도_넣는_자리가_화면에_있다(self):
        """**항목을 만들면 축이 없다**(점이 0개다). 그때 넣는 자리가 사라지면
        첫 점을 넣을 방법이 없어진다 — 새 코어를 세우는 순서가 그 순서다."""
        _series(self.loc, "ch")
        html = self.client.get(reverse("core", args=["RS14", "GC04"])).content.decode()
        self.assertIn('class="csedit"', html)
        self.assertIn('name="points"', html)

    def test_반입_항목은_고르는_자리에_안_나온다(self):
        _series(self.loc, "opal", source="import", points=[(0, 1.0)])
        _series(self.loc, "ch", points=[(0, 1.0)])
        from .. import data
        ctx = data.locality_detail("RS14", "GC04")
        self.assertEqual([cs["key"] for cs in ctx["manual_series"]], ["ch"])


class LocalityDeleteThresholdTest(DiaRUGATestCase):
    """지점을 지울 때 코어 자료를 센다 (063).

    **실제로 당한 자리다.** `RS19-GC17` 을 지웠더니 27개 항목 10,795점이
    예외도 경고도 없이 함께 사라졌다 — `CorePoint` 가 `CASCADE` 이고
    **새 코어는 시료가 0개라** 문턱이 그냥 열렸다.
    """

    def setUp(self):
        super().setUp()
        self.loc = _loc()

    def test_코어_자료가_있으면_막는다(self):
        _series(self.loc, "opal", source="import",
                points=[(0, 1.0), (100, 2.0)])
        obj, why = md.deletable("locality", self.loc.pk)
        self.assertTrue(why, "시료가 0개라도 코어 자료가 있으면 막아야 한다")
        self.assertIn("2", why[-1])          # 점 수를 적는다
        ok, m = md.delete("locality", self.loc.pk)
        self.assertFalse(ok)
        self.assertTrue(Locality.objects.filter(pk=self.loc.pk).exists())

    def test_수동_항목은_다시_만들_수_없다고_적는다(self):
        _series(self.loc, "ch", source="manual", points=[(0, 1.0)])
        _, why = md.deletable("locality", self.loc.pk)
        self.assertIn("다시 만들 수 없습니다", why[-1])

    def test_반입만_있으면_그_말은_안_적는다(self):
        _series(self.loc, "opal", source="import", points=[(0, 1.0)])
        _, why = md.deletable("locality", self.loc.pk)
        self.assertNotIn("다시 만들 수 없습니다", why[-1])

    def test_항목을_치우면_지워진다(self):
        """막기만 하고 치울 길이 없으면 지점이 영영 안 지워진다."""
        _series(self.loc, "opal", source="import", points=[(0, 1.0)])
        md.delete_series(self.loc, "opal")
        ok, m = md.delete("locality", self.loc.pk)
        self.assertTrue(ok, m)

    def test_코어_자료가_없으면_예전대로다(self):
        ok, m = md.delete("locality", self.loc.pk)
        self.assertTrue(ok, m)
