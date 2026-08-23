"""한국 도감의 쪽을 대응표에서 채우는 자리 (147).

색인은 **도판이 PDF 몇 쪽인지 적는 칸이 아예 없고** 481~680 은 `PDF p.` 도
안 따라왔다. 그래서 `atlas/korean_pages.toml` 에 잰 것을 두고
`tools/parse_atlas.py` 가 읽어 채운다. **여기서 나는 고장은 예외가 아니다** —
화면이 엉뚱한 쪽을 열거나 없는 쪽을 연다.

## 되살려서 잡히는가

- 1번 — 채우는 갈래를 빼면 실패한다. 색인에 `PDF p.` 가 없는 항목이
  `pdf_page=None` 으로 남아 **화면에 해설 링크가 아예 안 뜬다**(그 전 상태다)
- 2번 — 발췌본 밖을 거르는 `1 <= n <= pages` 를 빼면 실패한다. 항목 680 은
  책 p.370 인데 발췌본이 369(PDF 270)에서 끝나 **PDF 271 이 생긴다.**
  없는 쪽이라 화면이 빈 그림을 내고, 그것이 "원본에 그 쪽이 없다" 로 읽힌다
  (`AtlasPlacement` 머리말의 "빈 것을 채우지 않는다" 가 이 자리다)
- 3번 — `pdf_plate_page` 를 안 붙이면 실패한다. 512자리 전부 NULL 이던 그
  상태이고, 한국 도감만 도판으로 못 이었다
- 4번 — 색인이 적어 온 값을 덮게 바꾸면 실패한다. 대응표는 **없는 것을
  채우는** 표이지 색인을 고치는 표가 아니다
- 5번 — `check_korean` 의 옵셋 검산을 빼면 실패한다. 표가 낡아도 조용히
  지나가고, 그때부터 **모든 쪽이 한 칸씩 밀린다**
"""
import sys
from pathlib import Path

from django.test import SimpleTestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import parse_atlas  # noqa: E402


def md(*rows: str) -> str:
    """`parse_korean` 이 먹는 최소한의 색인 꼴."""
    return "## 종별 상세\n\n" + "\n".join(rows) + "\n"


def entry(no: int, name: str, sub: str) -> str:
    return f"**{no}. *{name}***\n<sub>{sub}</sub>  "


class KoreanPageMapTests(SimpleTestCase):
    def parse(self, *rows: str) -> dict:
        entries, _ = parse_atlas.parse_korean(md(*rows))
        return {e["item_no"]: e["placements"][0] for e in entries}

    def test_해설_쪽을_대응표에서_채운다(self):
        """1번 — 색인에 `PDF p.` 가 없어도 책 p. 에서 얻는다."""
        p = self.parse(entry(481, "Gyrosigma balticum", "pl. 57 · 책 p.291"))
        self.assertEqual(p["481"]["pdf_page"], 291 - 99)

    def test_발췌본_밖은_안_채운다(self):
        """2번 — 항목 680. 셈만 하면 PDF 271 인데 그런 쪽은 없다."""
        p = self.parse(entry(680, "Surirella tenera", "책 p.370"))
        self.assertIsNone(p["680"]["pdf_page"])

    def test_도판_쪽이_붙는다(self):
        """3번 — `pl.` 이 대응표의 PDF 쪽으로 간다."""
        p = self.parse(entry(481, "Gyrosigma balticum", "pl. 57 · 책 p.291"))
        self.assertEqual(p["481"]["pdf_plate_page"], 190)

    def test_색인이_적어_온_값을_안_덮는다(self):
        """4번 — 대응표는 없는 것을 채우는 표다."""
        p = self.parse(entry(238, "Asteromphalus hepaticus",
                             "pl. 31 · 책 p.174 · PDF p.76"))
        self.assertEqual(p["238"]["pdf_page"], 76)   # 175-99 = 76 이 아니라 색인 값

    def test_옵셋이_어긋나면_말한다(self):
        """5번 — 표가 낡으면 여기서 걸린다. 알려진 둘(#238·#424)은 뺀다."""
        entries, _ = parse_atlas.parse_korean(
            md(entry(500, "Navicula sp", "pl. 57 · 책 p.300 · PDF p.150")))
        bad = parse_atlas.check_korean(entries)
        self.assertTrue(any("옵셋" in b for b in bad), bad)

        entries, _ = parse_atlas.parse_korean(
            md(entry(238, "Asteromphalus hepaticus",
                     "pl. 31 · 책 p.174 · PDF p.76")))
        self.assertEqual(parse_atlas.check_korean(entries), [])
