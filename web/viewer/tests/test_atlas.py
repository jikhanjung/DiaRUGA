"""도감 표 셋과 2단계 반입 (P15 · 128 · 130).

시험 목록이 곧 **이 자리가 조용히 틀릴 수 있는 곳**이다.

1. **반입이 멱등이다** — 두 번 돌려도 같다. 색인이 고쳐질 때마다 다시 돌리는
   것이 이 표의 전제라(P15 4.2), 이것이 깨지면 행이 불어난다
2. **통째로 갈아치운다** — 색인에서 빠진 항목이 DB 에 남으면 안 된다
3. **자기 검산이 실제로 잡는다** — 넣은 것이 JSON 과 다르면 되돌린다.
   실패할 수 없는 검사는 없는 것보다 나쁘다
4. **빈 것을 0 으로 채우지 않는다** — 도판이 없는 항목의 `plate` 는 `null` 이다.
   0 으로 앉으면 "Plate 0" 이라는 없는 자리가 자료가 된다 (P15 9절)
5. **`check_db` 11번이 안 맞는 속을 센다** — 심어 놓고 걸리는지, 치우면
   풀리는지 둘 다 본다 (P15 8.2)
6. **저장소에 든 진짜 JSON 이 그대로 들어온다** — 픽스처만 통과하는 반입이
   되지 않게, 실제로 나갈 파일로 한 번 돌린다
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from .base import DiaRUGATestCase
from ..models import Atlas, AtlasEntry, AtlasPlacement, ClassDef

_ROOT = Path(__file__).resolve().parents[3]
_PATH = _ROOT / "ops" / "import_atlas.py"


def _load(name):
    """`ops/` 의 스크립트를 모듈로 들인다 (`test_check_db_grade_pose` 와 같다)."""
    path = _ROOT / "ops" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def doc(entries, key="test-atlas"):
    return {"atlas": {"key": key, "title": "시험용 도감", "short": "시험",
                      "source": "md/x.md", "source_sha256": "0" * 64,
                      "note": "", "sort_order": 0},
            "entries": entries}


def entry(seq, name, genus, placements=None, **kw):
    e = {"seq": seq, "item_no": "", "name": name, "genus": genus,
         "binomial": kw.get("binomial", name), "rank": kw.get("rank", "species"),
         "infra": None, "authority": None, "genus_guess": False,
         "extra": kw.get("extra", {}), "line": 1,
         "placements": placements if placements is not None else [PLACE]}
    return e


def place(**kw):
    p = {"plate": None, "plate_label": "", "figures": "", "book_page": None,
         "pdf_page": None, "pdf_plate_page": None, "volume": "", "note": ""}
    p.update(kw)
    return p


PLACE = place(plate=21, pdf_page=46, book_page=145)


class AtlasImportTest(DiaRUGATestCase):

    def setUp(self):
        self.mod = _load("import_atlas")

    def put(self, d, order=0):
        return self.mod.put(d, order)

    def test_넣고_또_넣어도_같다(self):
        d = doc([entry(1, "Melosira ambigua", "Melosira"),
                 entry(2, "Melosira distans", "Melosira")])
        self.put(d)
        self.put(d)
        self.assertEqual(Atlas.objects.count(), 1)
        self.assertEqual(AtlasEntry.objects.count(), 2)
        self.assertEqual(AtlasPlacement.objects.count(), 2)

    def test_색인에서_빠진_항목은_DB_에서도_빠진다(self):
        self.put(doc([entry(1, "A a", "A"), entry(2, "B b", "B")]))
        self.put(doc([entry(1, "A a", "A")]))
        self.assertEqual(AtlasEntry.objects.count(), 1)
        # 자리도 함께 간다 (CASCADE). 남으면 어느 항목의 것인지 모르는 행이 된다
        self.assertEqual(AtlasPlacement.objects.count(), 1)

    def test_빈_것을_0_으로_안_채운다(self):
        # 한국 도감 항목 680 이 이 모양이다 — 도판도 PDF 쪽도 없다
        self.put(doc([entry(1, "Surirella tenera", "Surirella",
                            [place(book_page=370)])]))
        p = AtlasPlacement.objects.get()
        self.assertIsNone(p.plate)
        self.assertIsNone(p.pdf_page)
        self.assertEqual(p.book_page, 370)

    def test_한_항목이_자리를_여럿_갖는다(self):
        # Schmidt 254건이 그렇고 최다 11이다 — 표를 가른 이유가 이것이다
        self.put(doc([entry(1, "Achnanthes brevipes", "Achnanthes", [
            place(plate=417, pdf_page=168, pdf_plate_page=169, volume="Band4"),
            place(plate=418, pdf_page=170, pdf_plate_page=171, volume="Band4",
                  figures="1—8"),
        ])]))
        e = AtlasEntry.objects.get()
        self.assertEqual(e.placements.count(), 2)
        # 차례가 색인에 적힌 순서대로다
        self.assertEqual([p.plate for p in e.placements.all()], [417, 418])

    def test_자리의_주석이_도판_번호를_뒤집는다(self):
        # Verzeichnis 21건 — `plate` 는 색인대로 두고 주석이 뒤집는다
        self.put(doc([entry(1, "Auliscus pauper", "Auliscus", [
            place(plate=240, pdf_page=204, pdf_plate_page=205, volume="Band2",
                  note="Tafel 아님 · 권 뒤 Verzeichnis(색인) 쪽에서 왔다")])]))
        p = AtlasPlacement.objects.get()
        self.assertEqual(p.plate, 240)
        self.assertIn("Tafel 아님", p.note)
        # **쪽은 성하다** — 도판을 여는 것은 그대로다
        self.assertEqual(p.pdf_page, 204)

    def test_검산이_어긋난_것을_잡는다(self):
        d = doc([entry(1, "A a", "A"), entry(2, "B b", "B")])
        atlas, _, _ = self.put(d)
        self.assertEqual(self.mod.verify(atlas, d), [])
        # 되살려서 본다 — 자리 하나가 없어지면 걸려야 한다
        AtlasPlacement.objects.first().delete()
        self.assertTrue(any("자리" in b for b in self.mod.verify(atlas, d)))
        # 표제어가 바뀌어도 걸려야 한다 (인용이 원문과 어긋나는 자리다)
        atlas.entries.filter(seq=1).update(name="A aa")
        self.assertTrue(any("표제어" in b for b in self.mod.verify(atlas, d)))

    def test_저장소의_JSON_이_그대로_들어온다(self):
        src = _ROOT / "atlas"
        files = sorted(src.glob("*.json"))
        self.assertTrue(files, "atlas/*.json 이 저장소에 없다 (1단계를 돌린다)")
        total_e = total_p = 0
        for i, f in enumerate(files):
            d = json.loads(f.read_text(encoding="utf-8"))
            atlas, ne, np_ = self.put(d, i)
            self.assertEqual(self.mod.verify(atlas, d), [], f.name)
            total_e += ne
            total_p += np_
        self.assertEqual(AtlasEntry.objects.count(), total_e)
        self.assertEqual(AtlasPlacement.objects.count(), total_p)
        # 도감 셋 · 표제어 2,059 가 P15 2절의 수다
        self.assertEqual(Atlas.objects.count(), 3)
        self.assertEqual(total_e, 2059)


class CheckAtlasTest(DiaRUGATestCase):
    """`check_db.py` 11번 — 안 맞는 속을 세는가."""

    def setUp(self):
        self.imp = _load("import_atlas")
        self.chk = _load("check_db")
        self.chk.problems.clear()
        # **픽스처의 is_taxon 분류를 전부 담은 도감**을 세운다 — 하나만 담으면
        # 나머지가 늘 걸려 "치우면 풀린다" 를 볼 수가 없다
        self.taxa = list(ClassDef.objects.filter(is_taxon=True, active=True))
        self.assertTrue(self.taxa, "is_taxon 분류가 픽스처에 있어야 한다")
        self.imp.put(doc([entry(i + 1, f"{c.label} sp", c.label)
                          for i, c in enumerate(self.taxa)]), 0)

    def run_check(self):
        self.chk.problems.clear()
        self.chk.check_atlas()
        return {name for name, _n, _why in self.chk.problems}

    def test_도감에_없는_속이면_걸리고_맞추면_풀린다(self):
        self.assertNotIn("분류(is_taxon)의 속이 도감에 없다", self.run_check())

        c = self.taxa[0]
        was = c.label
        # 한국 도감의 옛 표기다. `Chaetoceras`(홍조류) 와 `Chaetoceros`(규조)는
        # 둘 다 실재하는 속이라 **한 글자가 계를 가른다** (P15 5.2)
        c.label = "Chaetoceras"
        c.save(update_fields=["label"])
        self.assertIn("분류(is_taxon)의 속이 도감에 없다", self.run_check())

        c.label = was
        c.save(update_fields=["label"])
        self.assertNotIn("분류(is_taxon)의 속이 도감에 없다", self.run_check())

    def test_도감이_안_들어와_있으면_건너뛴다(self):
        Atlas.objects.all().delete()
        self.assertEqual(self.run_check(), set())
