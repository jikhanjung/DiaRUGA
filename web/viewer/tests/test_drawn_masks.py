"""사람이 그린 마스크를 받는다 (P09 3단계 — 서버).

**엔진이 마스크를 아예 안 낸 자리**는 지금까지 손댈 방법이 없었다. 거기가
재현율의 나머지 절반이고, 학습으로 보면 **가장 값진 양성 표본**이다.

그린 개체는 `batch=NULL` · `source="manual"` 이다 — 엔진에 대한 판단이 아니라
**이미지에 대한 사실**이라 어느 회차에도 안 속한다(P09 5.2). 그래서 묶음을
갈아타도 안 사라진다.

여기서 지키는 것 셋.

1. **없는 것과 빈 것이 다르다** — 그리기를 모르는 옛 탭의 저장 한 번이 그린
   개체를 전부 지우면 안 된다. 배포 중에는 그런 탭이 반드시 있다
2. **서버가 기하를 다시 잰다** — 클라이언트가 보낸 면적을 믿으면 브라우저마다
   다른 숫자가 DB 에 앉는다
3. **못 받을 것은 오류로 말한다** — 조용히 고쳐 앉히면 사람이 보낸 것과 다른
   것이 저장된다
"""
import json

from django.test import Client
from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx
from .. import data
from ..models import ObjectReview, RunBatch

BOX = [400, 300, 60, 40]
POLY = [400, 300, 460, 300, 460, 340, 400, 340]
KEY = "m7f3a91c2"


class DrawnMaskTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=3)

    def setUp(self):
        self.c = Client()

    def post(self, expect=200, **over):
        p = {"stem": self.w.stem(), "slug": self.w.slug, "gid": self.w.vp.idx,
             "done": False, "removed": [], "accepted": [],
             "labels": {}, "notes": {}}
        p.update(over)
        r = self.c.post(reverse("save_review"), data=json.dumps(p),
                        content_type="application/json")
        self.assertEqual(r.status_code, expect, r.content[:300])
        return r

    def draw(self, key=KEY, poly=None, cls="rod", note=""):
        return {"key": key, "polygon": poly or POLY, "cls": cls, "note": note}

    # --- 만들어지는가 ------------------------------------------------------

    def test_그린_개체가_저장된다(self):
        self.post(drawn=[self.draw(note="엔진이 놓쳤다")])
        o = ObjectReview.objects.get(mask_key=KEY)
        self.assertEqual(o.source, "manual")
        self.assertIsNone(o.batch_id, "그린 개체가 회차에 묶였다")
        self.assertEqual(o.label, "rod")
        self.assertEqual(o.note, "엔진이 놓쳤다")
        self.assertEqual(o.image_id, self.w.detection().image_id)

    def test_상자는_서버가_폴리곤에서_만든다(self):
        """**클라이언트가 보낸 상자를 안 받는다.** 폴리곤이 원본이다."""
        self.post(drawn=[self.draw()])
        self.assertEqual(ObjectReview.objects.get(mask_key=KEY).geom["bbox"],
                         BOX)

    def test_다시_보내면_고쳐진다(self):
        """뷰어는 늘 전체를 보낸다 — 같은 키가 두 행이 되면 안 된다."""
        self.post(drawn=[self.draw(cls="rod")])
        self.post(drawn=[self.draw(cls="round", note="다시 봤다")])
        o = ObjectReview.objects.get(mask_key=KEY)
        self.assertEqual(ObjectReview.objects.filter(mask_key=KEY).count(), 1)
        self.assertEqual(o.label, "round")
        self.assertEqual(o.note, "다시 봤다")

    # --- 없는 것과 빈 것 ---------------------------------------------------

    def test_drawn_이_없으면_손대지_않는다(self):
        """**그리기를 모르는 옛 탭이 그린 개체를 지우면 안 된다.**

        배포 중에는 그런 탭이 반드시 있다 — 판을 올리는 동안 사람이 열어 둔
        화면은 옛 JS 를 들고 있고, "검토 완료" 한 번이면 저장이 나간다.
        """
        self.post(drawn=[self.draw()])
        self.post(done=True)                      # drawn 을 아예 안 보낸다
        self.assertTrue(ObjectReview.objects.filter(mask_key=KEY).exists(),
                        "옛 탭의 저장이 그린 개체를 지웠다")

    def test_빈_목록은_지운다(self):
        """"그린 것이 하나도 없다" 는 말이다 — 지우는 정상 경로다."""
        self.post(drawn=[self.draw()])
        self.post(drawn=[])
        self.assertFalse(ObjectReview.objects.filter(mask_key=KEY).exists())

    def test_지우면_행이_사라진다_removed_가_아니다(self):
        """**사람이 그리다 만 것을 음성 표본으로 남기면 안 된다** (P09 5.10).

        "여기 규조각 없다" 를 다음 회차에 가르치게 된다 — 사람은 자기 실수를
        지운 것이지 그 자리가 배경이라고 말한 것이 아니다.
        """
        self.post(drawn=[self.draw()])
        self.post(drawn=[])
        self.assertEqual(ObjectReview.objects.filter(source="manual").count(), 0)

    # --- 엔진 교정과 안 섞이는가 -------------------------------------------

    def test_엔진_교정_저장이_그린_개체를_안_지운다(self):
        """삭제 범위가 `(image, batch)` 인데 그린 개체는 `batch=NULL` 이다."""
        self.post(drawn=[self.draw()])
        self.post(labels={self.w.keys()[0]: "rod"})     # drawn 없이 엔진 교정만
        self.assertTrue(ObjectReview.objects.filter(mask_key=KEY).exists())

    def test_묶음을_갈아타도_안_사라진다(self):
        """어느 회차에도 안 속하므로 회차가 바뀌어도 그대로 있어야 한다."""
        self.post(drawn=[self.draw()])
        other, _ = RunBatch.objects.get_or_create(kind="detect", label="yolo-다음")
        det = self.w.detection()
        det.run.batch = other
        det.run.save(update_fields=["batch"])
        self.post(labels={self.w.keys()[0]: "rod"})
        self.assertTrue(ObjectReview.objects.filter(mask_key=KEY).exists())

    # --- 못 받을 것은 오류로 ----------------------------------------------

    def test_키_규칙을_어기면_거절한다(self):
        for bad in ("400_300_60_40", "mZZZZZZZZ", "m123", "", "m7f3a91c2x"):
            with self.subTest(key=bad):
                self.post(expect=409, drawn=[self.draw(key=bad)])
        self.assertEqual(ObjectReview.objects.count(), 0)

    def test_점이_모자라면_거절한다(self):
        self.post(expect=409, drawn=[self.draw(poly=[400, 300, 460, 300])])
        self.assertEqual(ObjectReview.objects.count(), 0)

    def test_이미지_밖이면_거절한다(self):
        """밖에 있는 개체는 그릴 수도 잴 수도 없고, 학습 자료로 나가면
        좌표가 뒤집힌 라벨이 된다."""
        far = [9000, 9000, 9060, 9000, 9060, 9040, 9000, 9040]
        self.post(expect=409, drawn=[self.draw(poly=far)])
        self.assertEqual(ObjectReview.objects.count(), 0)

    def test_거절하면_아무것도_안_바뀐다(self):
        """**한 개체가 틀리면 그 저장 전체가 아무것도 안 한다.** 반쯤 저장하면
        사람은 무엇이 들어갔는지 알 수 없다."""
        self.post(drawn=[self.draw()])
        self.post(expect=409, drawn=[self.draw(cls="round"),
                                     self.draw(key="틀린키")])
        self.assertEqual(ObjectReview.objects.get(mask_key=KEY).label, "rod",
                         "거절했는데 앞 개체가 고쳐졌다")

    # --- 화면에 나오는가 ---------------------------------------------------

    def test_그린_개체가_화면에_나온다(self):
        """2단계가 낸 길로 나온다 — `Candidate` 가 없어도 그린다."""
        self.post(drawn=[self.draw()])
        d = data.detection_for_viewpoint(self.w.vp)
        me = next((c for c in d["candidates"] if data.cand_key(c) == KEY), None)
        self.assertIsNotNone(me, "그린 개체가 화면에 안 나온다")
        self.assertTrue(me["orphan"])
        self.assertEqual(me["source"], "manual")
        self.assertEqual(me["cls"], "rod")

    def test_지표를_서버가_잰다(self):
        """**클라이언트가 보낸 면적을 안 믿는다** — 브라우저마다 다른 숫자가
        DB 에 앉는다. 그리고 잰 값은 저장하지 않는다: 폴리곤이 원본이고 4단계에서
        기하가 바뀌면 낡기 때문이다."""
        self.post(drawn=[self.draw()])
        d = data.detection_for_viewpoint(self.w.vp)
        me = next(c for c in d["candidates"] if data.cand_key(c) == KEY)
        self.assertEqual(me["area_px"], 60 * 40)
        self.assertAlmostEqual(me["fill_ratio"], 1.0, places=2)
        self.assertIsNotNone(me["area_um2"])
        # 픽셀이 있어야 나오는 것은 비어 있다 — 화면이 왜 비었는지 적는다
        self.assertIsNone(me["texture"])

    # --- 집계에 잡히는가 ---------------------------------------------------

    def test_그린_개체가_목록_숫자에_잡힌다(self):
        """**화면에는 보이는데 숫자에는 없는 상태**를 남기지 않는다.

        후보 기반 SQL 이 `Candidate` 가 없는 개체를 못 보므로, 사람이 찾아낸
        규조각이 밀도에서 통째로 빠진다 — 그리고 그 숫자가 보고서에 실린다.
        """
        before = data._summary_by_sql(self.w.slide)
        self.post(drawn=[self.draw(cls="rod")])
        after = data._summary_by_sql(self.w.slide)

        self.assertEqual(after["n_detected"], before["n_detected"] + 1,
                         "그린 개체가 개수에 안 잡혔다")
        self.assertEqual(after["per_cls"]["rod"], before["per_cls"]["rod"] + 1,
                         "분류별 수에 안 잡혔다")
        self.assertEqual(after["n_labeled"], before["n_labeled"] + 1)

    def test_그린_개체는_자동_검출_수에_안_섞인다(self):
        """**엔진 성적을 잘못 읽게 된다.** 사람이 만든 것은 엔진이 낸 것이 아니다."""
        before = data._summary_by_sql(self.w.slide)
        self.post(drawn=[self.draw()])
        after = data._summary_by_sql(self.w.slide)
        self.assertEqual(after["n_auto"], before["n_auto"])

    def test_지우면_숫자도_돌아온다(self):
        before = data._summary_by_sql(self.w.slide)["n_detected"]
        self.post(drawn=[self.draw()])
        self.post(drawn=[])
        self.assertEqual(data._summary_by_sql(self.w.slide)["n_detected"], before)

    def test_그린_개체의_분류가_labels_지도에_안_실린다(self):
        """**화면이 받은 것을 그대로 되돌려 보낸다** — JS 가 `lab-<uid>` 를 읽어
        `labels` 로 보내는 것이 그 모양이다.

        그린 개체의 분류가 거기 실리면 그 키가 `labels` 로 돌아오는데, 그 키는
        `batch=NULL` 이라 엔진 쪽 `known` 집합에 없다 → **저장이 409 로 막힌다.**
        한 번 그리고 나면 그 시야를 더 이상 저장할 수 없게 된다.

        분류·코멘트는 `drawn` 이 통째로 나른다.
        """
        self.post(drawn=[self.draw(cls="rod", note="놓친 것")])
        d = data.detection_for_viewpoint(self.w.vp)

        self.assertNotIn(KEY, d["labels"], "그린 개체가 labels 지도에 실렸다")
        self.assertNotIn(KEY, d["notes"], "그린 개체가 notes 지도에 실렸다")

        # 화면이 받은 그대로 되돌려 보낸다 — 막히면 안 된다
        self.post(labels=d["labels"], notes=d["notes"],
                  drawn=[self.draw(cls="rod", note="놓친 것")])
        self.assertEqual(ObjectReview.objects.get(mask_key=KEY).label, "rod")
