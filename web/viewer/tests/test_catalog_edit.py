"""카탈로그의 넓힌 문 — 지우기·되살리기·일괄 (P16 5절).

세 문이 `POST /d/<슬러그>/catalog/save` 하나에 `act` 로 갈려 있다. 여기서 지키는
것은 넷이다.

1. **지운 것은 기본 화면에서 사라지고, `?gone=1` 에서만 난다** — 되살릴 자리가
   없으면 지우기 단추는 되돌릴 수 없는 단추가 된다 (P16 8절)
2. **되돌려서 표시가 안 남으면 그 줄을 지운다** — 사람이 그린 것·묶음 멤버는 남는다
3. **묶인 개체는 못 지운다** — 묶어 놓고 지우면 *오검출이면서 실재한다* 가 된다.
   그리고 **몇 장이 걸렸는지 말한다** (063 — 무엇을 먼저 치울지 모르면 다시 누른다)
4. **일괄은 하나가 걸려도 나머지가 저장된다** — 한 트랜잭션으로 묶으면 39장이
   함께 되돌아가고, 사람은 무엇이 걸렸는지 모른 채 전부 다시 한다

**되살려서 잡히는 것을 보고 나서 "있다" 고 말한다** (064).
"""
import json

from django.test import Client
from django.urls import reverse

from . import factories as fx
from .base import DiaRUGATestCase
from .. import data
from ..models import DiatomObject, ObjectReview, RunBatch


class CatalogRemoveTest(DiaRUGATestCase):
    """지우기·되살리기 (`act=remove|restore`)."""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_viewpoints=1, n_candidates=3)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def setUp(self):
        self.c = Client()
        self.url = reverse("save_catalog", args=["rs23"])
        self.det = self.w.detection()
        self.key = self.w.keys()[0]

    def post(self, act, expect=200, key=None):
        p = {"act": act, "gid": self.w.vp.idx, "image": self.det.image_id,
             "key": key or self.key}
        r = self.c.post(self.url, data=json.dumps(p),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return json.loads(r.content)

    def keys_shown(self, **q):
        return [r["key"] for r in data.catalog_rows("rs23", **q)]

    def test_지우면_카탈로그에서_사라진다(self):
        self.assertIn(self.key, self.keys_shown())
        self.post("remove")
        self.assertNotIn(self.key, self.keys_shown())
        self.assertTrue(ObjectReview.objects.get(
            image=self.det.image_id, mask_key=self.key).removed)

    def test_지운_것은_gone_에서만_난다(self):
        self.post("remove")
        self.assertEqual(self.keys_shown(gone=True), [self.key])
        # **섞어서 내지 않는다** — 기본 화면의 카드 수가 안 늘어난다
        self.assertNotIn(self.key, self.keys_shown())

    def test_되돌리면_다시_보이고_줄이_지워진다(self):
        self.post("remove")
        got = self.post("restore")
        self.assertFalse(got["removed"])
        # 표시가 하나도 안 남았다 — 그 줄은 없어야 한다
        self.assertFalse(got["kept"])
        self.assertFalse(ObjectReview.objects.filter(
            image=self.det.image_id, mask_key=self.key).exists())
        self.assertIn(self.key, self.keys_shown())

    def test_종명이_있으면_되돌려도_줄이_남는다(self):
        """되돌리기가 지우는 것은 **표시가 없는 줄**이지 사람이 적은 것이 아니다."""
        self.c.post(self.url, data=json.dumps(
            {"gid": self.w.vp.idx, "image": self.det.image_id,
             "key": self.key, "species": "Eucampia antarctica"}),
            content_type="application/json")
        self.post("remove")
        got = self.post("restore")
        self.assertTrue(got["kept"])
        row = ObjectReview.objects.get(image=self.det.image_id,
                                       mask_key=self.key)
        self.assertFalse(row.removed)
        self.assertEqual(row.diatom_object.species, "Eucampia antarctica")

    def test_묶인_개체는_못_지운다(self):
        # **묶음은 판이 서로 달라야 한다** — 개체 하나에 이미지마다 한 줄이라는
        # 유일 제약이 있다(`(diatom_object, image)`). 같은 판의 개체 둘을 묶는
        # 자료는 운영에 없다.
        frame = self.w.vp.images.filter(kind="frame").first()
        rows = [fx.add_review(self.w.vp, self.key, image=self.det.image),
                fx.new_review(viewpoint=self.w.vp, image=frame,
                              batch=self.det.batch, mask_key="500_500_20_20",
                              geom={"bbox_xywh": [500, 500, 20, 20],
                                    "polygon": [500, 500, 520, 500,
                                                520, 520, 500, 520]})]
        fx.link_reviews(rows)
        got = self.post("remove", expect=409)
        self.assertFalse(got["ok"])
        # **몇 장이 걸렸는지 말한다** — 무엇을 먼저 치울지 알 수 있어야 한다
        self.assertIn("2", got["error"])
        self.assertIn("묶음", got["error"])
        self.assertFalse(ObjectReview.objects.get(
            image=self.det.image_id, mask_key=self.key).removed)

    def test_현재_검출에_없는_키는_안_받는다(self):
        got = self.post("remove", expect=409, key="9999_9999_5_5")
        self.assertFalse(got["ok"])

    def test_모르는_act_는_400(self):
        r = self.c.post(self.url, data=json.dumps(
            {"act": "누가봐도아닌것", "gid": self.w.vp.idx,
             "image": self.det.image_id, "key": self.key}),
            content_type="application/json")
        self.assertEqual(r.status_code, 400)


class CatalogBulkTest(DiaRUGATestCase):
    """일괄 (`act=bulk`)."""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_viewpoints=2, n_candidates=3)
        RunBatch.objects.filter(for_review=True).update(code="S1")

    def setUp(self):
        self.c = Client()
        self.url = reverse("save_catalog", args=["rs23"])
        self.rows = data.catalog_rows("rs23")

    def item(self, r):
        return {"gid": r["group_id"], "image": r["image_id"], "key": r["key"]}

    def post(self, items, expect=200, **fields):
        r = self.c.post(self.url, data=json.dumps(
            {"act": "bulk", "items": items, "fields": fields}),
            content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        # 400 은 본문이 JSON 이 아니다 (`HttpResponseBadRequest`).
        return json.loads(r.content) if expect != 400 else None

    def now(self):
        """**`mask_key` 는 시야끼리 겹친다** — 좌표에서 나온 이름이라 같은 자리에
        잡힌 개체는 시야가 달라도 이름이 같다. `key` 만으로 표를 만들면 다른
        시야의 행이 덮어써서, **고치지도 않은 행을 보고 통과·실패를 말한다**
        (053 과 같은 줄이다).
        """
        return {(r["group_id"], r["key"]): r for r in data.catalog_rows("rs23")}

    def test_고른_것에_한_번에_앉는다(self):
        items = [self.item(r) for r in self.rows[:3]]
        got = self.post(items, cls="round", grade="A")
        self.assertEqual(got["n_ok"], 3)
        now = self.now()
        for it in items:
            row = now[(it["gid"], it["key"])]
            self.assertEqual(row["cls"], "round")
            self.assertEqual(row["grade"], "A")

    def test_하나가_걸려도_나머지는_저장된다(self):
        """**한 트랜잭션으로 묶지 않는다** — 39장이 함께 되돌아가면 안 된다."""
        good = self.item(self.rows[0])
        bad = {**self.item(self.rows[1]), "key": "9999_9999_5_5"}
        got = self.post([good, bad], cls="rod")
        self.assertEqual(got["n_ok"], 1)
        self.assertEqual(got["n"], 2)
        self.assertTrue(got["results"][0]["ok"])
        self.assertFalse(got["results"][1]["ok"])
        # **실패한 카드를 짚을 수 있어야 한다** — 화면이 그 카드에만 적는다
        self.assertEqual(got["results"][1]["key"], "9999_9999_5_5")
        self.assertEqual(self.now()[(good["gid"], good["key"])]["cls"], "rod")

    def test_파편에_등급을_함께_보내면_그것만_걸린다(self):
        """서버가 다시 검사한다 — 화면에서 막는 것은 막는 것이 아니다."""
        got = self.post([self.item(self.rows[0])], cls="round_frag", grade="A")
        self.assertEqual(got["n_ok"], 0)
        self.assertFalse(got["results"][0]["ok"])

    def test_코멘트는_일괄로_안_간다(self):
        """같은 글을 여러 개체에 붙이는 칸이 아니다 (0036 · P16 3.3)."""
        r0 = self.rows[0]
        got = self.post([self.item(r0)], cls="round", note="한꺼번에")
        self.assertEqual(got["n_ok"], 1)
        self.assertFalse(DiatomObject.objects.filter(note="한꺼번에").exists())

    def test_고른_것이_없으면_400(self):
        self.post([], expect=400, cls="round")

    def test_고칠_칸이_없으면_400(self):
        self.post([self.item(self.rows[0])], expect=400)

    def test_한_판보다_많이_못_보낸다(self):
        one = self.item(self.rows[0])
        self.post([one] * 121, expect=400, cls="round")


class CatalogEditReadOnlyTest(DiaRUGATestCase):
    """**읽기 전용은 저장을 막는 것으로 끝나지 않는다** (051).

    여기서 보는 것은 서버 쪽이다 — 화면이 배선을 안 거는지는 브라우저 시험이 본다.
    """

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_viewpoints=1, n_candidates=2)
        RunBatch.objects.filter(for_review=True).update(code="S1")
        cls.rows = data.catalog_rows("rs23")
        # 검토 대상을 다른 묶음으로 옮긴다 — 이 판은 이제 읽기 전용이다
        fx.add_other_engine(cls.w.vp, label="yolo-3차")
        RunBatch.objects.update(for_review=False)
        RunBatch.objects.filter(label="yolo-3차").update(for_review=True)

    def setUp(self):
        self.c = Client()
        self.url = reverse("save_catalog", args=["rs23"])

    def body(self, **extra):
        r = self.rows[0]
        return json.dumps({"gid": r["group_id"], "image": r["image_id"],
                           "key": r["key"], **extra})

    def test_지우기가_막힌다(self):
        r = self.c.post(self.url, data=self.body(act="remove"),
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertFalse(ObjectReview.objects.filter(removed=True).exists())

    def test_일괄이_아무것도_못_쓴다(self):
        """**항목마다 거절된다** — 일괄은 200 이어도 `n_ok` 가 0 이다.

        검토 대상이 아닌 묶음의 개체는 "현재 검출" 에 없어서 `save_catalog_entry`
        가 짚지 못한다. 화면이 배선을 안 거는 것(051)과 **두 겹으로** 막는다.
        """
        r0 = self.rows[0]
        r = self.c.post(self.url, data=json.dumps(
            {"act": "bulk",
             "items": [{"gid": r0["group_id"], "image": r0["image_id"],
                        "key": r0["key"]}],
             "fields": {"cls": "round"}}),
            content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:300])
        got = json.loads(r.content)
        self.assertEqual(got["n_ok"], 0)
        self.assertFalse(got["results"][0]["ok"])
        self.assertFalse(DiatomObject.objects.filter(label="round").exists())
