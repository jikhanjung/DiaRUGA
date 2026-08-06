"""폴더 이름 규칙 (`naming.py`). **규칙이 여기 하나뿐이라는 것이 요점이다.**

뷰어·파이프라인·마이그레이션이 전부 이 파일을 본다. 규칙이 갈라지면 같은 폴더가
두 자리에 다르게 앉는다.

**그리고 이 축은 함께 올려야 한다** (057). 슬러그·경로 같은 "값의 모양" 규칙은
**파이프라인이 만들고 뷰어가 쓴다** — 코드만 고치고 이미지를 안 올리면 옛 규칙이
계속 값을 만들고, 규칙을 어긴 값이 DB 에 앉으면 그 값을 읽는 화면이 전부 죽는다.
"""
from django.test import SimpleTestCase

from ..naming import base_name, parse_folder, parse_obs_no, sample_no_from


class ObsSuffixTest(SimpleTestCase):
    """관찰 접미사 `(1)`·`(2)` — 시료 하나를 달리 관찰한 것."""

    def test_접미사를_읽는다(self):
        self.assertEqual(parse_obs_no("BP09-0901 (1)"), 1)
        self.assertEqual(parse_obs_no("BP09-0901 (12)"), 12)

    def test_없으면_0_이다(self):
        """**`0` 을 저장하고 화면에서만 감춘다** — 비워 두면 "아직 안 읽은 것" 과
        "접미사가 없던 것" 이 구별되지 않는다."""
        self.assertEqual(parse_obs_no("BP09-0901"), 0)
        self.assertEqual(parse_obs_no(""), 0)
        self.assertEqual(parse_obs_no(None), 0)

    def test_글자_접미사는_안_읽는다(self):
        """**폴더에는 숫자만 받는다** (사용자 방침). 글자를 받으면 슬러그가
        뭉개져 서로 다른 관찰이 같은 슬러그로 부딪히고, `update_or_create(slug=…)`
        라 한쪽이 다른 쪽을 덮어쓴다."""
        self.assertEqual(parse_obs_no("BP09-0901 (산처리)"), 0)

    def test_끝에_있는_것만_읽는다(self):
        self.assertEqual(parse_obs_no("BP09 (1)-0901"), 0)

    def test_base_name_은_접미사를_뗀다(self):
        self.assertEqual(base_name("BP09-0901 (1)"), "BP09-0901")
        self.assertEqual(base_name("BP09-0901"), "BP09-0901")
        self.assertEqual(base_name("  BP09-0901 (2)  "), "BP09-0901")

    def test_같은_시료의_관찰들이_같은_base_를_갖는다(self):
        """`base_name` 의 존재 이유가 이것이다 — 관찰들이 공유하는 이름."""
        names = ["BP09-0901", "BP09-0901 (1)", "BP09-0901 (2)"]
        self.assertEqual(len({base_name(n) for n in names}), 1)


class SampleNoTest(SimpleTestCase):
    """`BP09` + `0901` → `1`. 지점 번호가 되풀이되는 자리를 뗀다."""

    def test_되풀이되는_자리를_뗀다(self):
        self.assertEqual(sample_no_from("BP09", "0901"), 1)
        self.assertEqual(sample_no_from("BP09", "0912"), 12)

    def test_되풀이가_없으면_전체를_읽는다(self):
        """규칙을 벗어난 이름 — **정렬은 되어야 한다.**"""
        self.assertEqual(sample_no_from("BP09", "1234"), 1234)

    def test_숫자가_아니면_None_이다(self):
        for loc, s in (("BP09", "abc"), ("BP09", ""), ("BP09", None)):
            with self.subTest(sample=s):
                self.assertIsNone(sample_no_from(loc, s))

    def test_지점_코드가_비어도_죽지_않는다(self):
        self.assertEqual(sample_no_from("", "0901"), 901)
        self.assertEqual(sample_no_from(None, "0901"), 901)


class ParseFolderTest(SimpleTestCase):
    """**가르는 표시는 `cm` 이 있느냐다.** 있으면 앞 토막이 지역, 없으면 지점."""

    # --- 남극 (시추코어) --------------------------------------------------

    def test_남극_폴더를_가른다(self):
        d = parse_folder("RS23-GC03 71cm")
        self.assertEqual(d["site_code"], "RS23")
        self.assertEqual(d["loc_code"], "GC03")
        self.assertEqual(d["loc_kind"], "core")
        self.assertEqual(d["depth_cm"], 71.0)
        self.assertIsNone(d["sample_no"])

    def test_시료_이름은_화면에_그대로_쓰는_모양이다(self):
        """`71.0cm` 이 아니라 `71cm` 다 — 숫자로 다시 만들면 폴더와 안 맞아 보인다."""
        self.assertEqual(parse_folder("RS23-GC03 71cm")["sample_code"], "71cm")
        self.assertEqual(parse_folder("RS23-GC03 71.0cm")["sample_code"], "71cm")
        self.assertEqual(parse_folder("RS23-GC03 116.5cm")["sample_code"], "116.5cm")

    def test_대소문자와_공백을_받아_준다(self):
        for folder in ("rs23-gc03 71cm", "RS23-GC03  71 cm", "RS23-GC03 71CM"):
            with self.subTest(folder=folder):
                d = parse_folder(folder)
                self.assertEqual((d["site_code"], d["loc_code"]), ("RS23", "GC03"))

    def test_관찰_접미사가_붙어도_앞쪽을_읽는다(self):
        d = parse_folder("RS23-GC03 71cm (2)")
        self.assertEqual(d["loc_code"], "GC03")
        self.assertEqual(d["obs_no"], 2)

    # --- 육상 (노두) ------------------------------------------------------

    def test_육상_폴더를_가른다(self):
        d = parse_folder("BP09-0901")
        self.assertEqual(d["loc_code"], "BP09")
        self.assertEqual(d["loc_kind"], "outcrop")
        self.assertEqual(d["sample_code"], "0901")
        self.assertEqual(d["sample_no"], 1)
        self.assertIsNone(d["depth_cm"])

    def test_육상의_지역은_지점_코드에서_숫자를_떼어_얻는다(self):
        """폴더에 지역이 없다. **비워 두는 쪽이 더 나쁘다** — 지역이 없는
        슬라이드는 어느 권역 탭에도 안 나와 화면에서 사라진다(`BP09-0901 (1)`)."""
        self.assertEqual(parse_folder("BP09-0901")["site_code"], "BP")
        self.assertEqual(parse_folder("ABC12-1203")["site_code"], "ABC")

    def test_두_체계를_cm_으로_가른다(self):
        """같은 모양이라도 `cm` 이 있으면 남극, 없으면 육상이다."""
        self.assertEqual(parse_folder("BP09-0901")["loc_kind"], "outcrop")
        self.assertEqual(parse_folder("BP-09 71cm")["loc_kind"], "core")

    # --- 아무 규칙에도 안 맞을 때 ------------------------------------------

    def test_모르는_이름은_전부_None_이다(self):
        """**그때는 부르는 쪽이 아무것도 쓰지 않는다** — 사람이 채운 것을
        자동값이 지우면 안 된다 (063 에서 당했다)."""
        for folder in ("", None, "그냥 폴더", "123", "-"):
            with self.subTest(folder=folder):
                d = parse_folder(folder)
                self.assertIsNone(d["site_code"])
                self.assertIsNone(d["loc_code"])
                self.assertIsNone(d["sample_code"])

    def test_모르는_이름에서도_관찰_번호는_읽는다(self):
        self.assertEqual(parse_folder("그냥 폴더 (3)")["obs_no"], 3)

    def test_늘_같은_칸을_낸다(self):
        """부르는 쪽이 `.get()` 없이 짚을 수 있어야 한다."""
        want = {"site_code", "loc_code", "loc_kind", "sample_code",
                "depth_cm", "sample_no", "obs_no"}
        for folder in ("RS23-GC03 71cm", "BP09-0901", "모르는 것", ""):
            with self.subTest(folder=folder):
                self.assertEqual(set(parse_folder(folder)), want)


class SlugShapeTest(SimpleTestCase):
    """**057 이 난 자리다.** 괄호가 든 슬러그 하나로 뷰어 전체가 500 이었다.

    `urls.py` 가 `<slug:slug>` 로 받으므로 슬러그가 그 문자 집합을 벗어나면
    **링크를 만들다 죽는다**(`NoReverseMatch`). 들어오는 값이 404 가 되는 것과
    나가는 값을 못 만드는 것은 고장의 크기가 다르다.

    슬러그를 만드는 것은 파이프라인 쪽(`group_focus_series.slide_slug`)이라 여기
    1겹에서는 **이름에서 온 조각이 그 규칙을 지키는지**까지만 본다.
    """

    # Django 의 `<slug:…>` 컨버터가 받는 것.
    SLUG_OK = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"

    def test_폴더에서_읽은_코드에_슬러그가_못_받는_문자가_없다(self):
        folders = ["RS23-GC03 71cm", "BP09-0901", "WAP13-GC47 450cm",
                   "RS23-GC03 116.5cm (2)"]
        for folder in folders:
            d = parse_folder(folder)
            for field in ("site_code", "loc_code"):
                with self.subTest(folder=folder, field=field):
                    v = d[field] or ""
                    bad = [c for c in v if c not in self.SLUG_OK]
                    self.assertEqual(bad, [], f"{field}={v!r} 에 {bad} 가 있다")

    def test_괄호가_든_이름은_코드로_새지_않는다(self):
        """접미사는 `obs_no` 로 가고 코드에는 안 남는다 — 057 의 괄호가
        슬러그로 흘러든 경로가 이것이었다."""
        d = parse_folder("BP09-0901 (1)")
        self.assertEqual(d["loc_code"], "BP09")
        self.assertNotIn("(", d["loc_code"])
        self.assertEqual(d["obs_no"], 1)
