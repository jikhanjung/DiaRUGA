"""동정(종명)이 검토 화면의 저장에 살아남는가 (개체 카탈로그 3단계).

**여기가 이 기능에서 제일 위험한 자리다.** `/review` POST 는 그 `(이미지, 묶음)`
의 교정 행 중 **payload 에 없는 것을 지운다** — "뷰어는 늘 전체를 보낸다" 가
전제이기 때문이다. 그런데 검토 화면은 종명을 모른다. 그래서 종명만 채운 행은
사람이 **"검토 완료" 만 한 번 눌러도 통째로 사라진다.** 예외도 경고도 안 난다.

017 · 027 · 053 이 전부 그 삭제 줄에서 났고, 두 번은 실제로 운영 자료를 잃었다
(14건 · 37건). 종명은 사람이 현미경을 보며 적는 것이라 **재생성 불가**다.

그래서 규칙은 하나다 — **`/review` 는 종명이 든 행을 지우지 않는다.** 그 화면이
대표하지 않는 것을 지우면 안 된다. `geom_edited` 가 같은 문제를 겪은 자리이고
같은 처리를 받는데, 이쪽은 **늘** 얹는다: `/review` 는 어느 판에서도 종명을
보내지 않는다.

**그러면서 청소는 계속 돼야 한다** — 아무 표시도 안 남은 행은 여전히 지워져야
"교정 전체 초기화" 가 예전처럼 동작한다. 안전망이 청소를 막으면 빈 행이 쌓이고,
그것을 세는 자리(`check_db.py`)가 전부 어긋난다.
"""
import json

from django.test import Client
from django.urls import reverse

from . import factories as fx
from .base import DiaRUGATestCase
from ..models import ObjectReview


class SpeciesSurvivesReviewTest(DiaRUGATestCase):
    """검토 화면이 종명을 밟고 지나가지 않는가."""

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=3)

    def setUp(self):
        self.c = Client()
        self.key = self.w.keys()[0]
        self.det = self.w.detection()

    def post(self, expect=200, **over):
        """검토 화면이 보내는 것과 같은 payload. **종명은 안 들어 있다** —
        그 화면은 종명을 모른다."""
        p = {"stem": self.w.stem(), "slug": self.w.slug, "gid": self.w.vp.idx,
             "done": False, "removed": [], "accepted": [],
             "labels": {}, "notes": {}}
        p.update(over)
        r = self.c.post(reverse("save_review"), data=json.dumps(p),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return r

    def put_species(self, key=None, species="Eucampia antarctica", **extra):
        """개체 카탈로그 화면이 만드는 것과 같은 행."""
        obj, _ = ObjectReview.objects.get_or_create(
            image=self.det.image, batch=self.det.batch, mask_key=key or self.key,
            defaults={"viewpoint": self.w.vp, "bind_method": "exact"})
        obj.species = species
        for k, v in extra.items():
            setattr(obj, k, v)
        obj.save()
        return obj

    # --- 사고 재현 ---------------------------------------------------------

    def test_검토_완료만_눌러도_종명이_남는다(self):
        """**이 시험이 이 기능의 이유다.** 종명만 채운 행은 삭제·되살림·유형·
        코멘트가 전부 비어 있어, 안전망이 없으면 빈 payload 한 번에 사라진다."""
        self.put_species()
        self.post(done=True)
        o = ObjectReview.objects.filter(mask_key=self.key).first()
        self.assertIsNotNone(o, "종명만 있는 행이 지워졌다")
        self.assertEqual(o.species, "Eucampia antarctica")

    def test_같은_시야의_다른_개체를_고쳐도_남는다(self):
        """사람이 검토를 실제로 하는 모습 — 옆 개체에 분류를 붙인다."""
        self.put_species()
        other = self.w.keys()[1]
        self.post(labels={other: "rod"})
        self.assertEqual(
            ObjectReview.objects.get(mask_key=self.key).species,
            "Eucampia antarctica")

    def test_여러_번_저장해도_남는다(self):
        """한 번 살아남는 것과 계속 살아남는 것은 다르다."""
        self.put_species()
        for _ in range(3):
            self.post(done=True)
        self.assertTrue(
            ObjectReview.objects.filter(mask_key=self.key).exists())

    # --- 다른 칸과 함께 있을 때 ---------------------------------------------

    def test_유형을_지워도_종명은_남는다(self):
        """유형(`label`)은 검토 화면이 아는 칸이라 payload 가 비면 지워지는 것이
        맞다. **종명은 그 화면이 대표하지 않으므로 따라 지워지면 안 된다.**"""
        self.put_species(label="round")
        self.post()
        o = ObjectReview.objects.get(mask_key=self.key)
        self.assertEqual(o.label, "", "유형은 화면이 대표하는 칸이라 비워야 한다")
        self.assertEqual(o.species, "Eucampia antarctica")

    def test_검토_화면이_지운_개체도_종명을_들고_있는다(self):
        """지운 것도 학습의 음성 표본이다 (P02 §2.7) — 무엇을 지웠는지가 종명과
        함께 남아야 그 판단을 되짚을 수 있다."""
        self.put_species()
        self.post(removed=[self.key])
        o = ObjectReview.objects.get(mask_key=self.key)
        self.assertTrue(o.removed)
        self.assertEqual(o.species, "Eucampia antarctica")

    def test_유형과_코멘트를_함께_보내도_종명이_안_밀린다(self):
        self.put_species()
        self.post(labels={self.key: "rod"}, notes={self.key: "가장자리가 넘쳤다"})
        o = ObjectReview.objects.get(mask_key=self.key)
        self.assertEqual((o.label, o.note, o.species),
                         ("rod", "가장자리가 넘쳤다", "Eucampia antarctica"))

    # --- 청소는 계속 돼야 한다 ----------------------------------------------

    def test_종명이_없는_빈_행은_여전히_지워진다(self):
        """**안전망이 청소를 막으면 안 된다.** 아무 표시도 안 남은 행이 쌓이면
        "교정 전체 초기화" 가 안 되고, 그 행들을 세는 자리가 전부 어긋난다."""
        self.post(labels={self.key: "rod"})
        self.assertTrue(ObjectReview.objects.filter(mask_key=self.key).exists())
        self.post()
        self.assertFalse(ObjectReview.objects.filter(mask_key=self.key).exists())

    def test_종명을_비우면_그_행도_지워진다(self):
        """카탈로그 화면에서 종명을 지운 뒤에는 검토 저장이 그 행을 청소해도
        된다 — 더는 지킬 것이 없다."""
        self.put_species()
        self.post(done=True)
        ObjectReview.objects.filter(mask_key=self.key).update(species="")
        self.post(done=True)
        self.assertFalse(ObjectReview.objects.filter(mask_key=self.key).exists())

    # --- 범위가 새지 않는가 -------------------------------------------------

    def test_다른_시야의_종명에는_안_닿는다(self):
        """삭제 범위가 `(이미지, 묶음)` 인 것과 같은 이야기다 — 안전망도 그
        범위 안에서만 얹혀야 하고, 밖의 행은 애초에 이 payload 가 대표하지
        않는다."""
        w2 = fx.make_world(slug="rs23-b", n_candidates=2)
        det2 = w2.detection()
        ObjectReview.objects.create(
            viewpoint=w2.vp, image=det2.image, batch=det2.batch,
            mask_key=w2.keys()[0], bind_method="exact",
            species="Chaetoceros sp.")
        self.put_species()
        self.post(done=True)
        self.assertEqual(ObjectReview.objects.filter(
            species="Chaetoceros sp.").count(), 1)


class DrawnSpeciesSurvivesTest(DiaRUGATestCase):
    """**사람이 그린 개체의 종명** — 저장 길이 다르다 (`_save_drawn`).

    그린 개체는 `batch=None` 이라 위의 삭제 줄이 안 닿는다. 대신 `drawn` 목록이
    그 범위를 대표하고, 목록에 없는 것을 지운다. 그 갈래도 종명을 밟지 않아야
    한다 — 그린 개체야말로 사람이 "여기 규조각이 있다" 고 말한 것이다.
    """

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=2)

    def setUp(self):
        self.c = Client()
        self.det = self.w.detection()
        self.mkey = "m1a2b3c4d"

    def post(self, expect=200, **over):
        p = {"stem": self.w.stem(), "slug": self.w.slug, "gid": self.w.vp.idx,
             "done": False, "removed": [], "accepted": [],
             "labels": {}, "notes": {}}
        p.update(over)
        r = self.c.post(reverse("save_review"), data=json.dumps(p),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return r

    def draw(self):
        return [{"key": self.mkey, "polygon": [50, 60, 80, 60, 80, 80, 50, 80],
                 "cls": "round", "note": ""}]

    def test_다시_저장해도_종명이_남는다(self):
        self.post(drawn=self.draw())
        ObjectReview.objects.filter(mask_key=self.mkey).update(
            species="Eucampia antarctica")
        self.post(drawn=self.draw())
        self.assertEqual(
            ObjectReview.objects.get(mask_key=self.mkey).species,
            "Eucampia antarctica")

    def test_그리기를_모르는_옛_탭은_안_건드린다(self):
        """`drawn` 이 아예 없으면 손대지 않는다 — 이미 있는 규칙이고, 종명도
        그 아래에서 함께 지켜진다."""
        self.post(drawn=self.draw())
        ObjectReview.objects.filter(mask_key=self.mkey).update(
            species="Eucampia antarctica")
        self.post()
        self.assertEqual(
            ObjectReview.objects.get(mask_key=self.mkey).species,
            "Eucampia antarctica")
