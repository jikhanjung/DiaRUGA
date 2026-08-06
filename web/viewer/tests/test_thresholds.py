"""문턱 다루기 중 **DB 를 안 타는 부분** (`thresholds.py`).

`preview`·`apply_values` 는 검출 자료를 읽으므로 2겹이다. 여기서 보는 것은
`clean_values`(입력 검사)와 `class_counts_from`(세기)이다.

`clean_values` 는 **설계가 담긴 함수다** — "주지 않은 문턱은 현재 값을 그대로
쓴다"(CLAUDE.md). 전부 기본값으로 되돌리는 것이 아니라, **하나 바꾸려다 나머지가
조용히 초기화되는 것을 막는** 것이다. 그 성질이 뒤집히면 예외도 경고도 없이
검출·문턱 이력과 어긋난다.
"""
from django.test import SimpleTestCase

import judge
from ..thresholds import class_counts_from, clean_values


def base():
    """"현재 값" 자리. 기본값과 일부러 다르게 둔다 — 같으면 "base 를 썼는가" 와
    "기본값으로 되돌렸는가" 를 구별할 수 없다."""
    b = dict(judge.DEFAULTS)
    b["texture_min"] = 2222.0
    b["round_texture_min"] = 3333.0
    return b


class CleanValuesTest(SimpleTestCase):

    def test_주지_않은_것은_base_그대로다(self):
        """**이것이 이 함수의 요점이다.**"""
        b = base()
        out = clean_values({"min_um": 12.0}, b)
        self.assertEqual(out["min_um"], 12.0)
        self.assertEqual(out["texture_min"], 2222.0)
        self.assertEqual(out["round_texture_min"], 3333.0)

    def test_기본값으로_되돌리지_않는다(self):
        """빈 입력이면 base 와 똑같이 나와야 한다 — `judge.DEFAULTS` 가 아니라."""
        b = base()
        self.assertEqual(clean_values({}, b), b)
        self.assertNotEqual(clean_values({}, b)["texture_min"],
                            judge.DEFAULTS["texture_min"])

    def test_base_를_고치지_않는다(self):
        """부르는 쪽의 dict 를 건드리면 되돌리기가 안 된다."""
        b = base()
        before = dict(b)
        clean_values({"min_um": 12.0}, b)
        self.assertEqual(b, before)

    def test_문자열_숫자도_받는다(self):
        """폼에서 오는 값은 문자열이다."""
        out = clean_values({"min_um": "12.5"}, base())
        self.assertEqual(out["min_um"], 12.5)

    def test_모르는_칸은_무시한다(self):
        out = clean_values({"없는문턱": 5, "min_um": 12.0}, base())
        self.assertNotIn("없는문턱", out)
        self.assertEqual(set(out), set(judge.FIELDS))

    # --- 거절하는 것 ------------------------------------------------------

    def test_숫자가_아니면_거절한다(self):
        for v in ("열두", None, [], {}):
            with self.subTest(v=v):
                with self.assertRaises(ValueError):
                    clean_values({"min_um": v}, base())

    def test_범위를_벗어나면_거절한다(self):
        for v in (-1, 1e6 + 1):
            with self.subTest(v=v):
                with self.assertRaises(ValueError):
                    clean_values({"min_um": v}, base())

    def test_뒤집힌_구간을_거절한다(self):
        """`min > max` 면 아무것도 안 통과한다 — 화면이 텅 비고 사람은 문턱이
        아니라 검출을 의심한다."""
        with self.assertRaises(ValueError):
            clean_values({"min_um": 200.0, "max_um": 100.0}, base())
        with self.assertRaises(ValueError):
            clean_values({"rod_min_elong": 30.0, "rod_max_elong": 2.0}, base())

    def test_한쪽만_줘도_구간을_본다(self):
        """`max_um` 만 낮춰서 뒤집히는 경우 — base 와 합친 뒤에 검사해야 잡힌다."""
        b = base()
        b["min_um"] = 50.0
        with self.assertRaises(ValueError):
            clean_values({"max_um": 20.0}, b)

    def test_양끝이_같은_것은_받는다(self):
        """`min == max` 는 빈 구간이 아니다 — `classify` 가 양끝을 포함한다."""
        out = clean_values({"min_um": 30.0, "max_um": 30.0}, base())
        self.assertEqual((out["min_um"], out["max_um"]), (30.0, 30.0))

    def test_0_은_받는다(self):
        """`round_texture_min=0` 은 "그 관문을 끈다" 는 뜻이라 유효하다."""
        out = clean_values({"round_texture_min": 0}, base())
        self.assertEqual(out["round_texture_min"], 0.0)


class ClassCountsFromTest(SimpleTestCase):
    """`preview()` 결과에서 센다. **판정을 다시 걸지 않는다.**

    예전에는 전체를 다시 판정해서 `judge.apply` 가 시야 수의 두 배로 찍혔다
    (검출 74개에 148번).
    """

    def test_통과분만_센다(self):
        per_det = {
            1: {"verdict": {"a": "round", "b": "rod", "c": None}},
            2: {"verdict": {"d": "round", "e": None}},
        }
        self.assertEqual(class_counts_from(per_det), {"round": 2, "rod": 1})

    def test_빈_것은_빈_dict_다(self):
        self.assertEqual(class_counts_from({}), {})
        self.assertEqual(class_counts_from({1: {"verdict": {}}}), {})

    def test_전부_탈락이면_아무것도_안_센다(self):
        per_det = {1: {"verdict": {"a": None, "b": None}}}
        self.assertEqual(class_counts_from(per_det), {})
