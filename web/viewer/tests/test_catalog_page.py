"""개체 카탈로그 화면과 저장 (`/d/<슬러그>/catalog/`).

**URL 을 덮는 것과 갈래를 덮는 것은 다르다** (086). 자료를 전부 합성본으로 세우면
프레임 갈래를 한 번도 안 밟는데, `/crops/`·`/detections/` 가 정확히 그래서
**v0.8.0 이후 내내 500** 이었다. 그래서 여기서는 합성본 갈래와 프레임 갈래를
따로 연다 (`make_world(with_stack=False)` 가 그 반대쪽이다).

저장 쪽에서 지키는 것 셋.

1. **짚은 개체 하나만 고친다** — `/review` 처럼 범위를 갈아치우지 않는다
2. **현재 검출에 없는 키는 안 받는다** — 다른 화면을 보고 보낸 것이다
3. **읽기 전용은 저장을 막는 것으로 안 끝난다** — 화면이 되는 것처럼 보이면
   안 된다 (051 에서 그렇게 37건을 잃었다)
"""
import json

from django.test import Client
from django.urls import reverse

from . import factories as fx
from .base import DiaRUGATestCase
from .. import data
from ..models import ObjectReview, RunBatch


class CatalogPageTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_viewpoints=2, n_candidates=3)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def setUp(self):
        self.c = Client()
        self.url = reverse("catalog", args=["rs23"])

    def get(self, **q):
        r = self.c.get(self.url, q)
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.content.decode()

    def test_열린다(self):
        html = self.get()
        self.assertIn("개체 카탈로그", html)
        self.assertIn("catcard", html)

    def test_번호가_화면에_나온다(self):
        html = self.get()
        no = data.catalog_rows("rs23")[0]["catalog_no"]
        self.assertIn(no, html)

    def test_어느_엔진의_판인지_적힌다(self):
        """번호의 꼬리가 그 코드라서, 적어 둔 번호만 보고도 어느 검출인지 안다."""
        html = self.get()
        self.assertIn("번호 꼬리 · S1", html)
        self.assertIn("sam2-시험", html)

    def test_없는_관찰은_404(self):
        self.assertEqual(self.c.get(reverse("catalog", args=["nope"])).status_code,
                         404)

    # --- 거르개·검색 --------------------------------------------------------

    def test_동정_안_한_것만_거른다(self):
        row = data.catalog_rows("rs23")[0]
        ObjectReview.objects.create(
            viewpoint_id=row["group_id"] and self.w.viewpoints[row["group_id"]].pk
            or self.w.vp.pk,
            image_id=row["image_id"], batch_id=row["batch_id"],
            mask_key=row["key"], bind_method="exact", species="Eucampia sp.")
        named = self.get(cls="named")
        self.assertIn(row["catalog_no"], named)
        self.assertNotIn(row["catalog_no"], self.get(cls="unnamed"))

    def test_번호로_찾는다(self):
        rows = data.catalog_rows("rs23")
        html = self.get(q=rows[0]["catalog_no"])
        self.assertIn(rows[0]["catalog_no"], html)
        self.assertNotIn(rows[-1]["catalog_no"], html)

    def test_대소문자를_안_가린다(self):
        no = data.catalog_rows("rs23")[0]["catalog_no"]
        self.assertIn(no, self.get(q=no.lower()))

    def test_종명으로_찾는다(self):
        row = data.catalog_rows("rs23")[0]
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image_id=row["image_id"],
            batch_id=row["batch_id"], mask_key=row["key"],
            bind_method="exact", species="Eucampia antarctica")
        self.assertIn(row["catalog_no"], self.get(q="eucampia"))

    def test_코멘트로_찾는다(self):
        row = data.catalog_rows("rs23")[0]
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image_id=row["image_id"],
            batch_id=row["batch_id"], mask_key=row["key"],
            bind_method="exact", note="가장자리가 넘쳤다")
        self.assertIn(row["catalog_no"], self.get(q="가장자리"))

    def test_못_찾으면_그렇다고_말한다(self):
        self.assertIn("찾은 개체가 없다", self.get(q="없는종명xyz"))


class FramePageTest(DiaRUGATestCase):
    """합성본이 없는 시야 — **086 이 난 갈래다.** URL 만 덮으면 안 밟힌다."""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=2, with_stack=False)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def test_프레임_갈래도_열린다(self):
        r = Client().get(reverse("catalog", args=["rs23"]))
        self.assertEqual(r.status_code, 200, r.content[:300])
        html = r.content.decode()
        self.assertIn("catcard", html)
        self.assertIn("-f", data.catalog_rows("rs23")[0]["catalog_no"])


class SaveCatalogTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=3)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def setUp(self):
        self.c = Client()
        self.url = reverse("save_catalog", args=["rs23"])
        self.rows = data.catalog_rows("rs23")
        self.r0 = self.rows[0]

    def post(self, expect=200, row=None, **fields):
        row = row or self.r0
        p = {"gid": row["group_id"], "image": row["image_id"], "key": row["key"]}
        p.update(fields)
        r = self.c.post(self.url, data=json.dumps(p),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return json.loads(r.content)

    def shown(self, key):
        return next(x for x in data.catalog_rows("rs23") if x["key"] == key)

    # --- 적히는가 -----------------------------------------------------------

    def test_종명이_저장된다(self):
        self.post(species="Eucampia antarctica")
        self.assertEqual(self.shown(self.r0["key"])["species"],
                         "Eucampia antarctica")

    def test_유형과_코멘트도_저장된다(self):
        self.post(cls="rod", note="가장자리가 넘쳤다")
        r = self.shown(self.r0["key"])
        self.assertEqual((r["cls"], r["note"]), ("rod", "가장자리가 넘쳤다"))

    def test_안_보낸_칸은_안_고친다(self):
        """`None` 은 "안 고친다" 이고 `""` 는 "비운다" 다 — 둘을 같이 다루면
        카드가 안 보내는 칸을 저장이 지운다."""
        self.post(species="Eucampia antarctica", note="메모")
        self.post(cls="rod")
        r = self.shown(self.r0["key"])
        self.assertEqual((r["species"], r["note"]), ("Eucampia antarctica", "메모"))

    def test_빈_문자열은_비운다(self):
        self.post(species="Eucampia antarctica")
        self.post(species="")
        self.assertEqual(self.shown(self.r0["key"])["species"], "")

    def test_다_비우면_그_줄을_지운다(self):
        """표시가 사라진 행을 남기면 "교정 전체 초기화" 가 안 되고 그 행을 세는
        자리가 어긋난다 (`save_review` 와 같은 규칙)."""
        self.post(species="Eucampia antarctica")
        self.assertTrue(ObjectReview.objects.filter(mask_key=self.r0["key"]).exists())
        out = self.post(species="")
        self.assertFalse(out["kept"])
        self.assertFalse(ObjectReview.objects.filter(mask_key=self.r0["key"]).exists())

    # --- 옆 개체를 안 건드리는가 --------------------------------------------

    def test_짚은_개체_하나만_고친다(self):
        """**`/review` 와 다른 점이 이것이다.** 그쪽은 그 (이미지, 묶음) 의 교정
        전체를 갈아치운다 — 017·027·053 이 전부 그 줄에서 났다."""
        other = self.rows[1]
        self.post(row=other, species="Chaetoceros sp.", cls="round")
        self.post(species="Eucampia antarctica")
        r = self.shown(other["key"])
        self.assertEqual((r["species"], r["cls"]), ("Chaetoceros sp.", "round"))

    def test_새로_만든_줄이_기하를_들고_있다(self):
        """**모든 교정 행이 `geom` 을 스스로 든다** (P02 §2.7). 없으면 검출기가
        바뀌었을 때 그릴 것이 없어지고 — 그것이 교정을 `Candidate` 에 안 매는
        이유다 — `check_db.py` 의 "교정이 기하를 갖고 있다" 가 그것을 센다.
        """
        self.post(species="Eucampia antarctica")
        o = ObjectReview.objects.get(mask_key=self.r0["key"])
        self.assertTrue(o.geom.get("bbox"), o.geom)
        self.assertTrue(o.geom.get("polygon"), o.geom)

    def test_삭제_되살림을_안_건드린다(self):
        """그것은 검토 화면이 하는 판단이다."""
        o = ObjectReview.objects.create(
            viewpoint=self.w.vp, image_id=self.r0["image_id"],
            batch_id=self.r0["batch_id"], mask_key=self.r0["key"],
            bind_method="exact", removed=True)
        self.post(species="Eucampia antarctica")
        o.refresh_from_db()
        self.assertTrue(o.removed)

    # --- 받지 않는 것 -------------------------------------------------------

    def test_현재_검출에_없는_키는_409(self):
        out = self.post(409, key="9999_9999_10_10", species="x")
        self.assertIn("현재 검출에 없는", out["error"])

    def test_남의_이미지를_짚으면_409(self):
        """**조용히 대표 이미지에 안 앉힌다** — 사람이 보고 있던 것과 다른 자리에
        판단이 쌓인다 (`save_review` 와 같은 이유)."""
        fx.make_world(slug="rs23-b", n_candidates=2)
        other_img = data.catalog_rows("rs23-b")[0]["image_id"]
        out = self.post(409, image=other_img, species="x")
        self.assertIn("현재 검출이 없다", out["error"])
        self.assertFalse(ObjectReview.objects.filter(species="x").exists())

    def test_모르는_유형은_409(self):
        out = self.post(409, cls="없는분류")
        self.assertIn("모르는 유형", out["error"])

    def test_모르는_시야는_409(self):
        out = self.post(409, gid=999, species="x")
        self.assertIn("모르는 시야", out["error"])
        self.assertFalse(ObjectReview.objects.filter(species="x").exists())

    def test_GET_은_안_받는다(self):
        self.assertEqual(self.c.get(self.url).status_code, 405)


class ReadOnlyTest(DiaRUGATestCase):
    """**읽기 전용은 저장을 막는 것으로 끝나지 않는다** (051).

    화면이 되는 것처럼 보이면 안 된다 — 저장은 잠갔는데 도구가 살아 있어서 한
    시야를 헛검토하고 새로고침하면 판단이 통째로 사라졌다.
    """

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=2, state="processing")
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def test_왜_못_적는지_적혀_있다(self):
        """잠가 놓고 이유를 안 적으면 사람이 같은 일을 몇 번이고 다시 한다 (063)."""
        html = Client().get(reverse("catalog", args=["rs23"])).content.decode()
        self.assertIn("자동 처리가 아직 끝나지 않았습니다", html)

    def test_입력칸이_잠겨_있다(self):
        """**반응하는 자리를 전부 센다** — 종명·유형·코멘트 셋 다."""
        import re
        html = Client().get(reverse("catalog", args=["rs23"])).content.decode()
        tags = re.findall(r"<(?:input|select|textarea)\b[^>]*"
                          r'class="(?:species|cls|note)"[^>]*>', html)
        self.assertTrue(tags, "입력칸을 하나도 못 찾았다 — 시험이 헛돌고 있다")
        for t in tags:
            self.assertIn("disabled", t, t)

    def test_배선을_아예_안_건다(self):
        """`disabled` 만 걸고 배선을 남겨 두면 나중에 누가 그것을 떼는 순간
        조용히 저장이 나간다 — **막는 자리를 하나로 둔다.**"""
        html = Client().get(reverse("catalog", args=["rs23"])).content.decode()
        self.assertIn("var READONLY = true;", html)

    def test_서버가_다시_막는다(self):
        """화면에서 막는 것은 막는 것이 아니다 (063)."""
        row = data.catalog_rows("rs23")[0]
        r = Client().post(
            reverse("save_catalog", args=["rs23"]),
            data=json.dumps({"gid": row["group_id"], "image": row["image_id"],
                             "key": row["key"], "species": "몰래"}),
            content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertFalse(ObjectReview.objects.filter(species="몰래").exists())


class NoCodeTest(DiaRUGATestCase):
    """묶음 코드가 없으면 번호를 못 만든다 — **무엇을 채워야 하는지 적는다.**"""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=2)
        RunBatch.objects.filter(for_review=True).update(code="")

    def test_이유가_화면에_있다(self):
        html = Client().get(reverse("catalog", args=["rs23"])).content.decode()
        self.assertIn("카탈로그 코드가 비어 있어", html)

    def test_그때는_읽기_전용이다(self):
        """번호 없이 동정을 적으면 그 판단을 나중에 무엇으로 부를지가 없다."""
        html = Client().get(reverse("catalog", args=["rs23"])).content.decode()
        self.assertIn("var READONLY = true;", html)
