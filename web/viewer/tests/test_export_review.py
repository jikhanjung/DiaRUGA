"""`export_review.py` 의 형식 3 — 시야 하나에 `(이미지, 묶음)` 여럿 (P09 1단계).

**이 파일이 지키는 것은 감사 기록이다.** `review/<슬라이드>/g<n>.json` 은 사람이
347 시야를 검토해 만든 재생성 불가 자료를 git 에 남기는 유일한 길이고,
`--check` 로 DB 와 대조하는 도구다. 형식이 담지 못하는 상태가 생기면 그 순간부터
**감사 기록이 조용히 낡는다.**

형식 2 는 시야 하나에 그 짝 하나를 전제했다. 프레임별 검토와 묶음 갈아타기가
그것을 깬다 — 그래서 형식 2 는 깨진 DB 를 만나면 **쓰지 않고 멈췄다.** 형식 3 은
그 짝으로 묶어 담는다.

`export_review.py` 는 **Django 를 임포트하지 않고 sqlite3 로 읽기 전용으로만**
연다(`backup_db.py` 와 같은 자리). 그래서 여기서는 시험 DB 의 파일 경로를 직접
넘겨 부른다 — 시험이 만든 DB 도 결국 sqlite 파일이다.
"""
import importlib.util
import sqlite3
import json
from pathlib import Path
import tempfile

from django.db import connection

from .base import DiaRUGATestCase
from . import factories as fx
from ..models import ObjectReview, RunBatch

_SPEC = importlib.util.spec_from_file_location(
    "export_review",
    Path(__file__).resolve().parents[3] / "export_review.py")
export_review = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(export_review)


class ExportFormat3Test(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_frames=3, n_candidates=3)
        cls.extra = fx.add_frame_detections(cls.w.vp)

    def export(self):
        """지금 시험 DB 를 내보내고 그 시야의 파일을 파싱해 돌려준다.

        **살아 있는 연결을 그대로 넘긴다.** 시험 DB 는 메모리라 파일 경로가
        없는데, `export_review` 는 Django 를 안 쓰고 sqlite3 로 **파일**을 여는
        도구다(`connect()`).

        사본을 떠서 넘기는 쪽이 실제 쓰임(`--db <백업>`)에 가깝지만 **그렇게
        하면 선다** — 시험 하나가 열어 둔 트랜잭션 위에서 backup API 가 잠금을
        기다린다(2분 넘게 안 끝났다). 여기서 시험하려는 것은 `fetch`·`render`
        이지 파일을 여는 일이 아니므로, 그 둘만 부른다.

        `row_factory` 는 되돌린다 — Django 의 뒤 질의가 튜플을 받으리라 믿고
        있어서, 켜 둔 채로 두면 **이 시험이 아니라 다음 시험이 깨진다.**
        """
        raw = connection.cursor().connection
        was = raw.row_factory
        raw.row_factory = sqlite3.Row
        try:
            views = export_review.fetch(raw)
        finally:
            raw.row_factory = was
        v = views[(self.w.slug, self.w.vp.idx)]
        text = export_review.render(v)
        return json.loads(text), text

    # --- 형식이 실제로 갈래를 담는가 ---------------------------------------

    def test_이미지가_여럿이면_묶음이_여럿_나온다(self):
        """형식 2 가 **멈추던** 자리다."""
        stack_img = self.w.detection().image
        frame, frame_img, _ = self.extra[0]
        fx.add_review(self.w.vp, self.w.keys()[0], removed=True)
        fx.add_review(self.w.vp, self.w.keys()[0], image=frame_img, label="rod")

        j, _ = self.export()
        self.assertEqual(j["format"], 3)
        self.assertEqual(j["n_images"], 2, f"묶음이 둘이어야 한다: {j}")
        self.assertEqual(j["n_objects"], 2)

        paths = [g["image"] for g in j["images"]]
        self.assertIn(stack_img.path, paths)
        self.assertIn(frame_img.path, paths)

    def test_합성본이_먼저_온다(self):
        """**차례가 정해져 있어야 diff 가 읽힌다.** DB 의 행 순서가 바뀔 때마다
        파일 전체가 다시 써지면 diff 가 자료 변화를 못 보여 준다."""
        _, frame_img, _ = self.extra[0]
        fx.add_review(self.w.vp, self.w.keys()[0], image=frame_img, label="rod")
        fx.add_review(self.w.vp, self.w.keys()[0], removed=True)

        j, _ = self.export()
        self.assertEqual([g["kind"] for g in j["images"]], ["stack", "frame"])

    def test_같은_이미지에_묶음이_둘이면_따로_담긴다(self):
        """회차를 갈아탄 뒤의 모습 — 같은 이미지에 옛 회차의 교정이 남아 있다.

        형식 2 는 여기서도 멈췄다: 한 파일 안에서 `key` 가 겹쳐 **어느 검출의
        판단인지가 사라진다.**
        """
        det = self.w.detection()
        old, _ = RunBatch.objects.get_or_create(kind="detect", label="옛회차")
        k = self.w.keys()[0]
        fx.add_review(self.w.vp, k, removed=True)          # 이번 회차
        ObjectReview.objects.create(                        # 옛 회차, 같은 키
            viewpoint=self.w.vp, image=det.image, batch=old, mask_key=k,
            label="rod", geom={"bbox": [1, 2, 3, 4]})

        j, _ = self.export()
        self.assertEqual(j["n_images"], 2)
        batches = sorted(g["batch"] for g in j["images"])
        self.assertEqual(batches, ["sam2-시험", "옛회차"])
        for g in j["images"]:
            self.assertEqual([o["key"] for o in g["objects"]], [k],
                             "같은 키가 한 묶음에 몰렸다")

    def test_사람이_그린_개체는_묶음_이름이_빈다(self):
        """`batch=NULL` 은 어느 회차에도 안 속한다 (P09 5.2)."""
        det = self.w.detection()
        ObjectReview.objects.create(
            viewpoint=self.w.vp, image=det.image, batch=None, source="manual",
            mask_key="m0a1b2c3", label="rod", geom={"bbox": [1, 2, 3, 4]})

        j, _ = self.export()
        g = next(g for g in j["images"] if g["batch"] == "")
        self.assertEqual(g["objects"][0]["source"], "manual")

    # --- 안 잃었는가 -------------------------------------------------------

    def test_개체_수가_맞는다(self):
        for i, k in enumerate(self.w.keys()):
            fx.add_review(self.w.vp, k, removed=(i == 0), label="rod")
        j, _ = self.export()
        self.assertEqual(j["n_objects"], len(self.w.keys()))
        self.assertEqual(sum(len(g["objects"]) for g in j["images"]),
                         j["n_objects"])

    def test_기하는_반드시_실린다(self):
        """**`geom` 이 빠진 내보내기는 감사 기록이지 안전망이 아니다** —
        검출이 바뀌면 다시 붙일 근거가 그것뿐이다 (`export_review.py` 머리말).
        """
        fx.add_review(self.w.vp, self.w.keys()[0], removed=True)
        j, _ = self.export()
        o = j["images"][0]["objects"][0]
        self.assertTrue(o["geom"].get("bbox"), f"geom 이 비었다: {o}")
        self.assertTrue(o["geom"].get("polygon"))

    def test_개체는_한_줄로_적힌다(self):
        """`json.dumps(indent=…)` 로 쓰면 폴리곤 좌표까지 쪼개져 개체 하나가
        40줄이 된다 — diff 가 안 읽힌다."""
        fx.add_review(self.w.vp, self.w.keys()[0], removed=True)
        _, text = self.export()
        obj_lines = [ln for ln in text.splitlines()
                     if ln.strip().startswith('{"key"')]
        self.assertEqual(len(obj_lines), 1)
