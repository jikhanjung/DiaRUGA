"""판정 규칙 (`judge.py`). **1겹 — DB 도 픽스처도 필요 없다.**

`judge.py` 는 import 가 하나도 없다(P02 6단계에서 그렇게 떼어냈다). 검출 직후
(`segment_diatoms.py`)와 문턱 재조정(`refilter.py`)이 **같은 함수**를 쓰므로,
여기가 흔들리면 "다시 걸렀더니 결과가 달라졌다" 가 조용히 생긴다.

**값을 못 박는 것이 목적이 아니다.** 문턱 기본값은 사람이 바꾼다 — 여기서 미는
것은 **규칙의 모양**이다: 어느 관문이 먼저 오는가, 경계에서 어느 쪽인가,
중첩 정리가 무엇을 버리는가.
"""
from django.test import SimpleTestCase

import judge


def rec(**kw):
    """판정을 통과하는 원형 개체 하나. 시험이 필요한 칸만 흔든다.

    **통과하는 것에서 출발해 하나씩 망가뜨린다.** 반대로 하면 "왜 떨어졌는지"
    가 여러 개일 수 있어 무엇을 시험한 것인지 알 수 없다.
    """
    r = {"shape_ok": True, "major_um": 30.0, "texture": 3000.0,
         "elongation": 1.1, "ellipse_iou": 0.90, "solidity": 0.95,
         "bbox_xywh": [0, 0, 100, 100], "area_px": 5000}
    r.update(kw)
    return r


class ClassifyTest(SimpleTestCase):
    """`classify(r, args) -> (분류, 탈락사유)`."""

    def setUp(self):
        self.th = judge.Thresholds()

    def test_기본_개체는_원형으로_통과한다(self):
        self.assertEqual(judge.classify(rec(), self.th), ("round", None))

    def test_봉상은_신장비로_갈린다(self):
        r = rec(elongation=3.0, ellipse_iou=0.80, solidity=0.90)
        self.assertEqual(judge.classify(r, self.th), ("rod", None))

    # --- 관문의 순서 ------------------------------------------------------

    def test_형태측정불가가_가장_먼저다(self):
        """**순서가 뜻을 갖는다.** 형태를 못 재면 나머지 값은 믿을 게 못 된다."""
        r = rec(shape_ok=False, major_um=9999.0, texture=0.0)
        self.assertEqual(judge.classify(r, self.th), (None, "형태측정불가"))

    def test_크기가_텍스처보다_먼저다(self):
        r = rec(major_um=5.0, texture=0.0)
        self.assertEqual(judge.classify(r, self.th)[1], "장축범위밖")

    def test_크기는_bbox_가_아니라_타원_장축으로_본다(self):
        """bbox 긴 변은 비스듬히 누운 물체에서 실제보다 커진다 — 그것만 보면
        4 µm 짜리가 10 µm 관문을 통과한다 (judge.py 머리말)."""
        r = rec(major_um=5.0, bbox_xywh=[0, 0, 4000, 4000])
        self.assertEqual(judge.classify(r, self.th)[1], "장축범위밖")

    # --- 경계값 ----------------------------------------------------------

    def test_크기_관문은_양끝을_포함한다(self):
        for major in (self.th.min_um, self.th.max_um):
            with self.subTest(major=major):
                self.assertEqual(judge.classify(rec(major_um=major), self.th),
                                 ("round", None))
        for major in (self.th.min_um - 0.01, self.th.max_um + 0.01):
            with self.subTest(major=major):
                self.assertEqual(judge.classify(rec(major_um=major), self.th)[1],
                                 "장축범위밖")

    def test_텍스처는_문턱_미만일_때만_떨어진다(self):
        """`<` 이지 `<=` 가 아니다 — 문턱과 같으면 통과한다."""
        r = rec(texture=self.th.round_texture_min)
        self.assertEqual(judge.classify(r, self.th), ("round", None))

    def test_원형과_봉상_사이에_빈_구간이_있다(self):
        """`round_max_elong`(1.4) 과 `rod_min_elong`(2.0) 사이는 어느 쪽도 아니다.

        **붙여 놓지 않은 것이 설계다** — 애매한 신장비를 억지로 한쪽에 넣지 않는다.
        """
        r = rec(elongation=1.7)
        self.assertEqual(judge.classify(r, self.th)[1], "신장비범위밖")

    def test_신장비_상한을_넘으면_봉상이_아니다(self):
        r = rec(elongation=self.th.rod_max_elong + 0.1)
        self.assertEqual(judge.classify(r, self.th)[1], "신장비범위밖")

    # --- 원형만의 areolae 관문 --------------------------------------------

    def test_원형은_areolae_를_따로_본다(self):
        """원형 통과분은 형태 지표가 텍스처와 무관하게 평평했다 — 형태로
        가려낼 수 없으므로 areolae 세기 자체를 관문으로 둔다 (judge.py)."""
        th = self.th
        # 전체 텍스처 관문(1000)은 넘지만 원형 관문(1500)에는 못 미친다.
        r = rec(texture=(th.texture_min + th.round_texture_min) / 2)
        self.assertEqual(judge.classify(r, th)[1], "원형areolae부족")

    def test_봉상에는_areolae_관문이_없다(self):
        """같은 텍스처라도 봉상은 통과한다 — 관문이 원형에만 걸려 있다."""
        th = self.th
        tex = (th.texture_min + th.round_texture_min) / 2
        r = rec(texture=tex, elongation=3.0, ellipse_iou=0.80, solidity=0.90)
        self.assertEqual(judge.classify(r, th), ("rod", None))

    def test_원형_areolae_관문은_끌_수_있다(self):
        """`round_texture_min` 이 0 이면 그 관문이 없는 것과 같다."""
        th = judge.Thresholds(round_texture_min=0)
        r = rec(texture=th.texture_min + 1)
        self.assertEqual(judge.classify(r, th), ("round", None))

    # --- 빈 값 -----------------------------------------------------------

    def test_없는_값은_관문을_건너뛴다(self):
        """`major_um`·`texture` 가 None 이면 그 관문을 안 본다 — 값이 없는 것과
        값이 나쁜 것은 다르다."""
        r = rec(major_um=None, texture=None)
        self.assertEqual(judge.classify(r, self.th), ("round", None))


class ThresholdsTest(SimpleTestCase):

    def test_주지_않은_것은_기본값이다(self):
        th = judge.Thresholds(texture_min=2000.0)
        self.assertEqual(th.texture_min, 2000.0)
        self.assertEqual(th.min_um, judge.DEFAULTS["min_um"])

    def test_as_dict_가_FIELDS_전부를_낸다(self):
        self.assertEqual(set(judge.Thresholds().as_dict()), set(judge.FIELDS))

    def test_같은_값이면_같다(self):
        self.assertEqual(judge.Thresholds(min_um=5), judge.Thresholds(min_um=5))
        self.assertNotEqual(judge.Thresholds(min_um=5), judge.Thresholds(min_um=6))


class DedupeTest(SimpleTestCase):
    """중첩 마스크 정리.

    SAM2 AMG 는 격자 포인트마다 다중 스케일 마스크를 내 최대 6단계까지 중첩된다.
    **NMS 로는 못 잡는다** — 작은 것이 큰 것 안에 들면 IoU 가 오히려 작아진다
    (실측 중앙값 0.07).
    """

    @staticmethod
    def box(x, y, w, h, area=None, texture=1000.0):
        return {"bbox_xywh": [x, y, w, h], "area_px": area or (w * h),
                "texture": texture}

    def test_겹치지_않으면_전부_남는다(self):
        rs = [self.box(0, 0, 10, 10), self.box(100, 100, 10, 10)]
        self.assertEqual(len(judge.dedupe(rs)), 2)

    def test_집합체를_버리고_개별_물체를_남긴다(self):
        """**큰 쪽을 남기면 덩어리가 내부 규조각을 전부 삼킨다.**

        자식 2개 이상이 부모 면적의 절반 이상을 설명하면 개별 물체가 아니다.
        """
        parent = self.box(0, 0, 100, 100, area=10000)
        kids = [self.box(0, 0, 50, 90, area=4500),
                self.box(50, 0, 50, 90, area=4500)]
        out = judge.dedupe([parent] + kids)
        self.assertNotIn(parent, out)
        self.assertEqual(len(out), 2)

    def test_자식이_하나면_부모를_안_버린다(self):
        """하나짜리는 "안에 든 것" 이지 집합체가 아니다."""
        parent = self.box(0, 0, 100, 100, area=10000)
        kid = self.box(0, 0, 90, 90, area=8100)
        out = judge.dedupe([parent, kid])
        self.assertIn(parent, out)

    def test_자식들이_작으면_부모를_안_버린다(self):
        """자식 셋이 있어도 합이 절반에 못 미치면 부모가 개별 물체다."""
        parent = self.box(0, 0, 100, 100, area=10000)
        kids = [self.box(i * 10, 0, 10, 10, area=100) for i in range(3)]
        self.assertIn(parent, judge.dedupe([parent] + kids))

    def test_거의_같은_마스크는_텍스처가_높은_쪽을_남긴다(self):
        low = self.box(0, 0, 100, 100, texture=500.0)
        high = self.box(1, 1, 100, 100, texture=9000.0)
        out = judge.dedupe([low, high])
        self.assertEqual(out, [high])


class ApplyTest(SimpleTestCase):

    def test_통과분과_탈락분을_가른다(self):
        good = rec()
        bad = rec(major_um=1.0, bbox_xywh=[500, 500, 10, 10])
        kept, rejected = judge.apply([good, bad], judge.Thresholds())
        self.assertEqual(kept, [good])
        self.assertEqual(rejected, [bad])
        self.assertEqual(bad["reject"], "장축범위밖")
        self.assertIsNone(bad["cls"])

    def test_중첩정리로_떨어진_것은_분류를_남긴다(self):
        """판정을 통과한 뒤 정리된 것이라 `cls` 가 남는다 — 학습 자료에서
        "판정은 통과했으나 겹쳤다" 와 "판정에서 떨어졌다" 는 다른 표본이다."""
        parent = rec(bbox_xywh=[0, 0, 100, 100], area_px=10000)
        kids = [rec(bbox_xywh=[0, 0, 50, 90], area_px=4500),
                rec(bbox_xywh=[50, 0, 50, 90], area_px=4500)]
        kept, rejected = judge.apply([parent] + kids, judge.Thresholds())

        self.assertEqual(len(kept), 2)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reject"], "중첩정리")
        self.assertEqual(rejected[0]["cls"], "round")

    def test_빈_묶음도_받는다(self):
        self.assertEqual(judge.apply([], judge.Thresholds()), ([], []))


class CollapseBoxesTest(SimpleTestCase):
    """`collapse_boxes` — **판정 전에** 같은 bbox 를 하나로 접는다 (077).

    DB 의 열쇠가 `mask_key`(= bbox 문자열)라 같은 자리는 한 행밖에 못 들어간다.
    예전에는 **판정한 뒤** 넣으면서 버렸고, 그래서 판정이 본 집합(34개)과 저장된
    집합(33개)이 달라졌다 — 저장된 판정을 다시 계산해도 안 맞는 상태가 된다.

    실측으로 `yolo-3차` 검출 1,799개 중 18개가 하나씩 잃었고 **판정이 어긋난
    8개가 전부 그 안에** 있었다.
    """

    def test_같은_bbox_는_하나로_접힌다(self):
        a = rec(area_px=5000)
        b = rec(area_px=4000)
        out, n = judge.collapse_boxes([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(n, 1)

    def test_면적이_큰_쪽을_남긴다(self):
        """같은 자리를 가리키는 둘 중에서는 마스크가 더 많이 잡힌 쪽이 근거가 많다."""
        small = rec(area_px=4000, texture=9999.0)
        big = rec(area_px=5000, texture=1.0)
        out, _ = judge.collapse_boxes([small, big])
        self.assertEqual(out[0]["area_px"], 5000)
        # 순서를 뒤집어도 같은 답이어야 한다 — **결정적**이라는 것이 요점이다
        out2, _ = judge.collapse_boxes([big, small])
        self.assertEqual(out2[0]["area_px"], 5000)

    def test_자리가_다르면_안_접는다(self):
        a = rec(bbox_xywh=[0, 0, 100, 100])
        b = rec(bbox_xywh=[0, 1, 100, 100])
        out, n = judge.collapse_boxes([a, b])
        self.assertEqual((len(out), n), (2, 0))

    def test_소수점은_열쇠와_같은_규칙으로_깎는다(self):
        """`mask_key` 가 `int()` 로 깎으므로 여기서도 그래야 한다 —
        안 맞으면 접힌 줄 알고도 DB 에서 또 부딪힌다."""
        a = rec(bbox_xywh=[10.0, 20.0, 30.0, 40.0])
        b = rec(bbox_xywh=[10.4, 20.4, 30.4, 40.4])
        out, n = judge.collapse_boxes([a, b])
        self.assertEqual((len(out), n), (1, 1))

    def test_순서를_지킨다(self):
        """접은 것이 원래 자리에 남아야 뒤의 `id` 매김이 안 흔들린다."""
        a = rec(bbox_xywh=[0, 0, 10, 10])
        b = rec(bbox_xywh=[50, 50, 10, 10])
        c = rec(bbox_xywh=[0, 0, 10, 10], area_px=9999)
        out, _ = judge.collapse_boxes([a, b, c])
        self.assertEqual([r["bbox_xywh"][0] for r in out], [0, 50])
        self.assertEqual(out[0]["area_px"], 9999)

    def test_접고_나면_판정과_저장이_같은_집합을_본다(self):
        """**이것이 이 함수의 존재 이유다.**

        접기 전에는 `apply` 가 둘을 보고 하나로 다른 하나를 누르는데, DB 에는
        한 행만 들어가 그 판단을 되짚을 수 없다.
        """
        a = rec(area_px=5000)
        b = rec(area_px=4000)
        kept, rejected = judge.apply([a, b], judge.Thresholds())
        keys = {tuple(r["bbox_xywh"]) for r in kept + rejected}
        self.assertEqual(len(kept) + len(rejected), 2)
        self.assertEqual(len(keys), 1, "같은 열쇠 둘이 판정을 받았다")

        out, _ = judge.collapse_boxes([a, b])
        kept2, rejected2 = judge.apply(out, judge.Thresholds())
        self.assertEqual(len(kept2) + len(rejected2), 1,
                         "접은 뒤에는 판정받은 수와 저장될 수가 같아야 한다")
