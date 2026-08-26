"""출현 기록 반입 — P20 2단계.

1. **`source` 단위로 통째로 갈아치운다** — 다른 source 의 기록은 안 건드린다
2. **`Reference` 는 upsert 다** — `Atlas` 처럼 지우지 않는다
3. **못 보던 (저자, 연도) 는 멈춘다** — `REF_KEY` 를 벗어나면 조용히 넘어가지
   않는다
4. **자기 검산이 실제로 잡는다**
5. **저장소에 든 진짜 JSON 이 그대로 들어온다**
6. **`check_db` 12번이 가리키는 자리가 성립하는가를 본다**
"""
import importlib.util
import json
import sys
from pathlib import Path

from .base import DiaRUGATestCase
from ..models import Atlas, Occurrence, Reference

_ROOT = Path(__file__).resolve().parents[3]


def _load(name):
    path = _ROOT / "ops" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def doc(occs, refs=None, source="test-src"):
    refs = refs if refs is not None else [
        {"ref": "정 영호 외", "year": "1967", "records": len(occs), "cite": "", "note": ""}]
    return {"source": {"atlas": source}, "references": refs, "occurrences": occs}


def occ(binomial, ref="정 영호 외", year="1967", **kw):
    o = {"item_no": "", "binomial": binomial, "region_raw": "", "region": "",
         "ref": ref, "year": year, "note": ""}
    o.update(kw)
    return o


class ImportOccurrenceTest(DiaRUGATestCase):

    def setUp(self):
        self.mod = _load("import_occurrence")

    def put(self, d):
        return self.mod.put(d)

    def test_넣고_또_넣어도_같다(self):
        d = doc([occ("Melosira ambigua"), occ("Melosira distans")])
        self.put(d)
        self.put(d)
        self.assertEqual(Reference.objects.count(), 1)
        self.assertEqual(Occurrence.objects.count(), 2)

    def test_source_단위로만_갈아치운다(self):
        self.put(doc([occ("A a")], source="src1"))
        self.put(doc([occ("B b"), occ("C c")], source="src2"))
        self.assertEqual(Occurrence.objects.filter(source="src1").count(), 1)
        self.assertEqual(Occurrence.objects.filter(source="src2").count(), 2)
        # src2 를 다시 넣어도 src1 은 그대로다
        self.put(doc([occ("D d")], source="src2"))
        self.assertEqual(Occurrence.objects.filter(source="src1").count(), 1)
        self.assertEqual(Occurrence.objects.filter(source="src2").count(), 1)

    def test_Reference_는_upsert_다(self):
        # 두 source 가 같은 문헌을 인용해도 Reference 행은 하나다
        self.put(doc([occ("A a")], source="src1"))
        self.put(doc([occ("B b")], source="src2"))
        self.assertEqual(Reference.objects.count(), 1)
        self.assertEqual(Occurrence.objects.count(), 2)

    def test_못_보던_문헌이면_멈춘다(self):
        d = doc([occ("A a", ref="아무개", year="1900")],
                refs=[{"ref": "아무개", "year": "1900", "records": 1,
                       "cite": "", "note": ""}])
        with self.assertRaises(SystemExit):
            self.put(d)

    def test_검산이_어긋난_것을_잡는다(self):
        d = doc([occ("A a"), occ("B b")])
        source, _, _ = self.put(d)
        self.assertEqual(self.mod.verify(source, d), [])
        Occurrence.objects.filter(binomial="A a").delete()
        self.assertTrue(any("출현 기록" in b for b in self.mod.verify(source, d)))

    def test_저장소의_JSON_이_그대로_들어온다(self):
        src = _ROOT / "atlas" / "occurrence"
        files = sorted(src.glob("*.json"))
        self.assertTrue(files, "atlas/occurrence/*.json 이 저장소에 없다 (1단계를 돌린다)")
        total_o = 0
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            source, nr, no = self.put(d)
            self.assertEqual(self.mod.verify(source, d), [], f.name)
            total_o += no
        self.assertEqual(Occurrence.objects.count(), total_o)
        # 한국 도감 1단계(P20) 의 수 — 문헌 열다섯 · 출현 기록 924
        self.assertEqual(Reference.objects.count(), 15)
        self.assertEqual(total_o, 924)


class CheckOccurrenceTest(DiaRUGATestCase):
    """`check_db.py` 12번 — 가리키는 자리가 성립하는가."""

    def setUp(self):
        self.imp = _load("import_occurrence")
        self.chk = _load("check_db")
        self.chk.problems.clear()

    def run_check(self):
        self.chk.problems.clear()
        self.chk.check_occurrence()
        return {name for name, _n, _why in self.chk.problems}

    def test_비어_있으면_건너뛴다(self):
        self.assertEqual(self.run_check(), set())

    def test_source_오타를_잡는다(self):
        # source 는 실재하는 Atlas.key 나 Reference.key 를 가리켜야 한다
        Atlas.objects.create(key="src1", title="시험 도감", short="시험")
        self.imp.put(doc([occ("A a")], source="src1"))
        self.assertNotIn("출현 기록의 source 가 도감·문헌 어디도 아니다", self.run_check())
        Occurrence.objects.update(source="typo-src")
        self.assertIn("출현 기록의 source 가 도감·문헌 어디도 아니다", self.run_check())

    def test_출현_기록이_없는_문헌을_잡는다(self):
        self.imp.put(doc([occ("A a")], source="src1"))
        self.assertNotIn("출현 기록이 하나도 없는 문헌", self.run_check())
        Occurrence.objects.all().delete()
        self.assertIn("출현 기록이 하나도 없는 문헌", self.run_check())
