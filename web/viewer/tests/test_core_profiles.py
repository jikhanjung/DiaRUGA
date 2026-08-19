"""코어 자료 — 축·반입·매핑표 (P17 2·3단계).

**되살려서 잡히는 것만 적는다** (064). 여기 있는 것은 실제로 물릴 자리들이다:

- 관찰이 없는 코어는 축이 안 섰다. `RS14-GC04`·`RS19-GC17` 이 그 상태로
  들어온다 — 자료를 다 넣어 놓고도 화면이 빈다.
- 재반입이 사람이 넣은 항목을 덮으면 다시 만들 수 없다.
- 깊이 단위를 잘못 읽으면 **예외 없이** 프로파일이 코어 맨 위에 뭉친다.
  `RS14-GC04` 의 `MS`·`Opal` 이 실제로 머리글과 단위가 다르다.
"""
import csv
import importlib.util
import sys
import tempfile
import tomllib
from pathlib import Path

from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx
from .. import data
from ..models import CorePoint, CoreSeries, Locality, Site

_ROOT = Path(__file__).resolve().parents[3]
_MAPPING = _ROOT / "coredata" / "mapping.toml"


def _load(rel: str, name: str):
    """저장소의 스크립트를 모듈로 들인다 (`test_check_db_grade_pose` 와 같은 문)."""
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _series(loc, key, *, source="import", default_on=False, points=()):
    cs = CoreSeries.objects.create(locality=loc, key=key, label=key.upper(),
                                   unit="%", source=source,
                                   default_on=default_on)
    CorePoint.objects.bulk_create(
        [CorePoint(series=cs, depth_mm=mm, value=v) for mm, v in points])
    return cs


def _bare_locality(site_code="RS14", loc_code="GC04"):
    """**관찰이 하나도 없는 지점.** 새 코어가 들어오는 모습 그대로다."""
    site = Site.objects.create(code=site_code, area="ant")
    return Locality.objects.create(site=site, code=loc_code, kind="core")


class CoreSeriesReadTest(DiaRUGATestCase):
    """`data.core_series()` — 목록과 범위."""

    def test_범위를_cm_로_낸다(self):
        loc = _bare_locality()
        _series(loc, "opal", points=[(0, 48.5), (200, 44.0), (3620, 41.0)])
        (row,) = data.core_series(loc)
        self.assertEqual(row["n"], 3)
        # DB 는 mm, 화면은 cm. 바꾸는 자리가 이 함수 하나다.
        self.assertEqual(row["min_cm"], 0)
        self.assertEqual(row["max_cm"], 362)

    def test_점이_없는_항목은_범위가_None_이다(self):
        """**0 으로 두지 않는다** — 0 cm 에서 잰 것과 구별이 안 된다."""
        loc = _bare_locality()
        _series(loc, "opal")
        (row,) = data.core_series(loc)
        self.assertEqual(row["n"], 0)
        self.assertIsNone(row["min_cm"])
        self.assertIsNone(row["max_cm"])


class CoreAxisTest(DiaRUGATestCase):
    """축의 근거 (P17 6절). **시료와 코어 자료 둘 중 하나만 있어도 선다.**"""

    def test_관찰이_없어도_자료가_있으면_축이_선다(self):
        loc = _bare_locality()
        _series(loc, "opal", points=[(0, 48.5), (3620, 41.0)])
        ctx = data.locality_detail("RS14", "GC04")
        self.assertIsNotNone(ctx["axis"], "코어 자료만으로도 축이 서야 한다")
        self.assertGreaterEqual(ctx["axis"]["bottom"], 362)
        self.assertEqual(ctx["rows"], [])

    def test_자료도_관찰도_없으면_축이_안_선다(self):
        loc = _bare_locality()
        ctx = data.locality_detail("RS14", "GC04")
        self.assertIsNone(ctx["axis"])

    def test_점이_없는_항목은_축을_안_잡는다(self):
        """이름만 만들어 둔 항목. `max_cm` 이 `None` 이라 비교에서 죽던 자리다."""
        loc = _bare_locality()
        _series(loc, "opal")
        ctx = data.locality_detail("RS14", "GC04")
        self.assertIsNone(ctx["axis"])

    def test_자료가_없어도_시료가_있으면_축이_선다(self):
        """넓히기 전부터 되던 것. **되돌아가지 않는지 본다.**"""
        fx.make_world(slug="rs23", depth_cm=71.0)
        ctx = data.locality_detail("RS23", "GC03")
        self.assertIsNotNone(ctx["axis"])

    def test_더_깊은_쪽이_축을_잡는다(self):
        """시료는 71 cm 인데 자료가 362 cm 까지 있으면 축은 362 를 덮어야 한다."""
        w = fx.make_world(slug="rs23", depth_cm=71.0)
        _series(w.locality, "opal", points=[(0, 48.5), (3620, 41.0)])
        ctx = data.locality_detail("RS23", "GC03")
        self.assertGreaterEqual(ctx["axis"]["bottom"], 362)


class CorePageTest(DiaRUGATestCase):
    """화면. **자료가 어느 갈래로 가는지를 본다** (086)."""

    def test_관찰이_없는_코어_페이지가_뜬다(self):
        loc = _bare_locality()
        _series(loc, "opal", default_on=True,
                points=[(0, 48.5), (3620, 41.0)])
        r = self.client.get(reverse("core", args=["RS14", "GC04"]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        # **글자로 짚지 않는다** — `base.html` 의 CSS 주석에 "코어 자료" 가
        # 들어 있어서 어느 화면에서나 걸린다. 렌더된 블록을 본다.
        self.assertIn('class="cslist"', html)
        self.assertIn("OPAL", html)
        # 축이 섰으므로 "축을 그릴 수 없습니다" 가 뜨면 안 된다
        self.assertNotIn("축을 그릴 수 없습니다", html)

    def test_아무것도_없으면_편집하러_보내지_않는다(self):
        """관찰이 없는 코어에 "정보 편집에서 깊이를 채우세요" 는 갈 곳이 없다."""
        _bare_locality()
        r = self.client.get(reverse("core", args=["RS14", "GC04"]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("아직 관찰도 코어 자료도 없습니다", html)
        self.assertNotIn("정보 편집에서 깊이를 채우면", html)

    def test_노두에는_안_뜬다(self):
        """노두에는 cm 축이 없다 — 그 자리는 현장 사진이 쓴다."""
        w = fx.make_world(slug="bp09", site_code="BP", loc_code="BP09",
                          kind="outcrop", area="kr", sample_code="0901")
        r = self.client.get(reverse("core", args=["BP", "BP09"]))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('class="cslist"', r.content.decode())


class ImportCoredataTest(DiaRUGATestCase):
    """`ops/import_coredata.py` — **자기 출처만 갈아치운다** (P17 3.1)."""

    def setUp(self):
        super().setUp()
        self.mod = _load("ops/import_coredata.py", "import_coredata_under_test")
        self.loc = _bare_locality()
        self.dir = Path(tempfile.mkdtemp(prefix="diaruga-test-coredata-"))

    def _write(self, name="RS14-GC04", series=(), points=()):
        with (self.dir / f"{name}.series.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["key", "label", "unit", "default_on", "sort_order",
                        "origin"])
            w.writerows(series)
        with (self.dir / f"{name}.points.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["key", "depth_mm", "value"])
            w.writerows(points)

    def test_반입한다(self):
        self._write(series=[["opal", "Opal", "%", "1", "50", "x.xlsx::Opal"]],
                    points=[["opal", 0, 48.5], ["opal", 3620, 41.0]])
        rc = self.mod.load_one("RS14", "GC04",
                               self.dir / "RS14-GC04.series.csv",
                               self.dir / "RS14-GC04.points.csv", False)
        self.assertEqual(rc, 0)
        cs = CoreSeries.objects.get(locality=self.loc, key="opal")
        self.assertTrue(cs.default_on)
        self.assertEqual(cs.points.count(), 2)

    def test_다시_돌려도_두_벌이_안_된다(self):
        args = ("RS14", "GC04", self.dir / "RS14-GC04.series.csv",
                self.dir / "RS14-GC04.points.csv", False)
        self._write(series=[["opal", "Opal", "%", "1", "50", "x"]],
                    points=[["opal", 0, 48.5]])
        self.mod.load_one(*args)
        self.mod.load_one(*args)
        self.assertEqual(CoreSeries.objects.filter(locality=self.loc).count(), 1)
        self.assertEqual(CorePoint.objects.count(), 1)

    def test_사람이_넣은_항목은_안_덮는다(self):
        """**이것이 `source` 를 가른 이유다.** 063 과 같은 줄."""
        _series(self.loc, "chaetoceros", source="manual",
                points=[(0, 120.0), (500, 88.0)])
        self._write(series=[["opal", "Opal", "%", "1", "50", "x"]],
                    points=[["opal", 0, 48.5]])
        self.mod.load_one("RS14", "GC04",
                          self.dir / "RS14-GC04.series.csv",
                          self.dir / "RS14-GC04.points.csv", False)
        kept = CoreSeries.objects.get(locality=self.loc, key="chaetoceros")
        self.assertEqual(kept.source, "manual")
        self.assertEqual(kept.points.count(), 2)

    def test_dry_run_은_아무것도_안_쓴다(self):
        self._write(series=[["opal", "Opal", "%", "1", "50", "x"]],
                    points=[["opal", 0, 48.5]])
        rc = self.mod.load_one("RS14", "GC04",
                               self.dir / "RS14-GC04.series.csv",
                               self.dir / "RS14-GC04.points.csv", True)
        self.assertEqual(rc, 0)
        self.assertEqual(CoreSeries.objects.count(), 0)

    def test_지점이_없으면_만들지_않고_멈춘다(self):
        self._write(name="RS99-GC01",
                    series=[["opal", "Opal", "%", "0", "50", "x"]],
                    points=[["opal", 0, 48.5]])
        rc = self.mod.load_one("RS99", "GC01",
                               self.dir / "RS99-GC01.series.csv",
                               self.dir / "RS99-GC01.points.csv", False)
        self.assertEqual(rc, 1)
        self.assertFalse(Locality.objects.filter(code="GC01").exists())

    def test_항목에_없는_key_가_점에_있으면_멈춘다(self):
        self._write(series=[["opal", "Opal", "%", "0", "50", "x"]],
                    points=[["opal", 0, 48.5], ["ms_whole", 0, 8.2]])
        rc = self.mod.load_one("RS14", "GC04",
                               self.dir / "RS14-GC04.series.csv",
                               self.dir / "RS14-GC04.points.csv", False)
        self.assertEqual(rc, 1)
        self.assertEqual(CoreSeries.objects.count(), 0)


class _FakeSheet:
    """`read_block` 이 엑셀에서 쓰는 것은 `iter_rows` 하나뿐이다."""

    def __init__(self, rows):
        self.rows = rows

    def iter_rows(self, min_row=1, values_only=True):
        return iter(self.rows[min_row - 1:])


class ExtractTest(DiaRUGATestCase):
    """`tools/coredata_extract.py` 의 순수 부분. **xlsx 없이 돈다.**"""

    def setUp(self):
        super().setUp()
        self.mod = _load("tools/coredata_extract.py", "coredata_extract_under_test")

    def test_cm_는_열_배로_들어간다(self):
        self.assertEqual(self.mod._to_mm(36.2, "cm"), 362)
        self.assertEqual(self.mod._to_mm(3609, "mm"), 3609)

    def test_글자_칸은_안_읽는다(self):
        """`TYPE`(`gM`)·`Munsell C Hue`(`0.6Y`)가 이 갈래로 걸린다."""
        self.assertIsNone(self.mod._num("gM"))
        self.assertIsNone(self.mod._num("0.6Y"))
        self.assertIsNone(self.mod._num(None))
        self.assertEqual(self.mod._num("48.5"), 48.5)

    def test_값이_없는_깊이는_점을_안_만든다(self):
        ws = _FakeSheet([("깊이", "값"), (0, 1.0), (1, None), (2, 3.0)])
        got = self.mod.read_block(ws, {
            "sheet": "T", "header_row": 1, "depth_col": 1, "depth_unit": "cm",
            "columns": [[2, "v", "V", ""]]})
        self.assertEqual(got["v"], {0: 1.0, 20: 3.0})

    def test_같은_깊이_같은_값은_한_번만_들어간다(self):
        """`RS14-GC04` 의 `MS` 가 221~260 cm 40점을 값까지 똑같이 겹쳐 들고 있다."""
        ws = _FakeSheet([("깊이", "값"), (0, 1.0), (1, 2.0), (0, 1.0)])
        got = self.mod.read_block(ws, {
            "sheet": "MS", "header_row": 1, "depth_col": 1, "depth_unit": "cm",
            "columns": [[2, "v", "V", ""]]})
        self.assertEqual(got["v"], {0: 1.0, 10: 2.0})

    def test_같은_깊이에_다른_값이면_멈춘다(self):
        """**어느 쪽이 맞는지 스크립트가 고를 수 없다.** 사람이 정할 일이다."""
        ws = _FakeSheet([("깊이", "값"), (0, 1.0), (0, 9.0)])
        with self.assertRaises(ValueError):
            self.mod.read_block(ws, {
                "sheet": "MS", "header_row": 1, "depth_col": 1,
                "depth_unit": "cm", "columns": [[2, "v", "V", ""]]})


class MappingTableTest(DiaRUGATestCase):
    """매핑표 자체를 검사한다.

    **머리글이 틀려 있는 자리를 사람이 확인해서 적어 둔 것이 이 표다** (P17 1.1).
    누가 "머리글대로 고치자" 며 되돌리면 프로파일이 조용히 어긋난다 — 예외도
    경고도 없다. 그래서 **확인해 둔 사례를 검사로 박는다.**
    """

    def setUp(self):
        super().setUp()
        with _MAPPING.open("rb") as f:
            self.conf = tomllib.load(f)
        self.cores = {f"{c['site']}-{c['locality']}": c for c in self.conf["core"]}

    def _block(self, core, sheet, depth_col=None):
        for b in self.cores[core]["block"]:
            if b["sheet"] == sheet and (depth_col is None
                                        or b["depth_col"] == depth_col):
                return b
        self.fail(f"{core} 에 {sheet} 블록이 없다")

    def test_RS14_의_MS_는_머리글이_mm_라도_cm_다(self):
        """값이 1~362 이고 코어가 362 cm 다. mm 로 읽으면 맨 위 36 cm 에 뭉친다."""
        self.assertEqual(self._block("RS14-GC04", "MS", 1)["depth_unit"], "cm")
        self.assertEqual(self._block("RS14-GC04", "MS", 4)["depth_unit"], "cm")

    def test_RS14_의_Opal_은_머리글이_m_라도_cm_다(self):
        self.assertEqual(self._block("RS14-GC04", "Opal")["depth_unit"], "cm")

    def test_XRF_만_진짜_mm_다(self):
        """값이 1~3609 이고 그것이 360.9 cm 다."""
        self.assertEqual(self._block("RS14-GC04", "XRF")["depth_unit"], "mm")

    def test_코어_길이가_적혀_있다(self):
        """단위를 잘못 읽으면 열 배로 어긋난다 — 반입기가 이 값으로 자기를 본다."""
        self.assertEqual(self.cores["RS14-GC04"]["expect_max_cm"], 362)
        self.assertEqual(self.cores["RS19-GC17"]["expect_max_cm"], 599)

    def test_켤_항목이_실제로_있는_key_다(self):
        """오타면 화면이 아무것도 안 켠 채 뜬다 — 예외가 안 난다."""
        for name, core in self.cores.items():
            keys = {c[1] for b in core["block"] for c in b["columns"]}
            missing = set(core.get("default_on", [])) - keys
            self.assertFalse(missing, f"{name}: default_on 에 없는 key {missing}")

    def test_규조_자료와_함께_보는_넷이_켜져_있다(self):
        """사용자 방침 2026-08-19 — MS · 함수율 · Opal · TOC."""
        on = set(self.cores["RS14-GC04"]["default_on"])
        self.assertEqual(on, {"ms_whole", "wc", "opal", "toc"})
        # RS19 에는 Opal 시트가 없다. 없는 것을 켤 수는 없다.
        self.assertEqual(set(self.cores["RS19-GC17"]["default_on"]),
                         {"ms_whole", "wc", "toc"})

    def test_key_가_코어_안에서_안_겹친다(self):
        for name, core in self.cores.items():
            keys = [c[1] for b in core["block"] for c in b["columns"]]
            self.assertEqual(len(keys), len(set(keys)), f"{name}: key 중복")
