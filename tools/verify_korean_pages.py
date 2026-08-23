#!/usr/bin/env python3
"""`atlas/korean_pages.toml` 을 원본 PDF 에 대고 다시 잰다 (147).

그 표는 **사람이 재서 커밋한 것이다.** 도판 54개가 PDF 몇 쪽인지와 책 쪽에서
PDF 쪽을 얻는 옵셋이 들어 있고, `tools/parse_atlas.py` 가 그것을 읽어 색인에
없는 자리를 채운다. 표가 틀리면 **화면이 엉뚱한 쪽을 연다 — 예외는 안 난다.**

그래서 근거를 문장으로만 두지 않고 다시 돌려 볼 수 있게 했다(126 의
`render_verify.py` 와 같은 자리). `parse_atlas` 는 md 만 읽어 매번 도는 자리라
여기 있는 검산 둘은 못 한다 — **PDF 를 열어야 하고 그것은 NAS 에 있다.**

    python tools/verify_korean_pages.py

## 무엇을 보나

1. **차례와 빠짐** — 도판 번호가 PDF 쪽 차례대로 오르는가, 21~74 에 빈 번호가
   없는가. (`parse_atlas` 도 같은 것을 본다)
2. **옵셋** — 도판이 아닌 쪽의 **인쇄된 쪽번호**가 `PDF + 99` 인가.
   텍스트 레이어가 있는 PDF 41–190 에서만 된다
3. **도판이 제 번호인가** — 도판 쪽 캡션의 항목 번호가 **색인에서 그 도판을
   부르는 항목**과 겹치는가. 번호를 한 자리 잘못 읽으면 여기서 갈린다.
   역시 텍스트 레이어가 있는 쪽만

**PDF 191–270 은 텍스트 레이어가 없어 이 스크립트가 못 본다** — 그 구간(도판
58~74)은 쪽 머리를 렌더해 눈으로 읽었고, 그 사실을 표 머리말이 적어 둔다.
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402

TOML = Path(__file__).resolve().parent.parent / "atlas" / "korean_pages.toml"
INDEX = DIADICTION / "md/korean_flora_diatom_index.md"
ITEM = re.compile(r"^\*\*(\d+)\.\s")
SUB = re.compile(r"^<sub>(.*?)</sub>")


def index_rows() -> list[tuple[int, int | None, int | None]]:
    """색인에서 (항목, pl., 책 p.) 만 뽑는다."""
    out, cur = [], None
    for ln in INDEX.read_text(encoding="utf-8").splitlines():
        m = ITEM.match(ln)
        if m:
            cur = int(m.group(1))
            continue
        m = SUB.match(ln)
        if m and cur is not None:
            pl = re.search(r"pl\.\s*(\d+)", m.group(1))
            bp = re.search(r"책 p\.(\d+)", m.group(1))
            out.append((cur, int(pl.group(1)) if pl else None,
                        int(bp.group(1)) if bp else None))
            cur = None
    return out


def text_of(pdf: Path, page: int) -> str:
    r = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"],
                       capture_output=True, text=True)
    return r.stdout


def main() -> int:
    d = tomllib.loads(TOML.read_text(encoding="utf-8"))
    plates = {int(k): v for k, v in d["plates"].items()}
    off, npages = d["offset"]["book_minus_pdf"], d["source"]["pages"]
    pdf = DIADICTION / d["source"]["pdf"]
    if not pdf.exists():
        print(f"원본 PDF 를 못 찾는다: {pdf}\n"
              f"  NAS 공유가 안 붙었을 수 있다", file=sys.stderr)
        return 2
    bad = 0

    nums = sorted(plates)
    print(f"1. 차례와 빠짐 — 도판 {len(plates)}개 (Plate {nums[0]}–{nums[-1]})")
    if [plates[n] for n in nums] != sorted(plates[n] for n in nums):
        print("   ✗ 번호와 PDF 쪽의 차례가 어긋난다"); bad += 1
    gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in plates]
    if gaps:
        print(f"   ✗ 빠진 번호 {gaps}"); bad += 1
    if not gaps and not bad:
        print("   ✓ 차례대로 오르고 빈 번호가 없다")

    plate_pages = set(plates.values())
    lo = min(plate_pages)
    print(f"\n2. 옵셋 {off} — PDF {lo}–190 의 도판 아닌 쪽")
    ok = miss = 0
    for p in range(lo, 191):
        if p in plate_pages:
            continue
        found = re.findall(r"(?m)^\s*(\d{2,3})\s*$", text_of(pdf, p))
        if any(int(n) == p + off for n in found):
            ok += 1
        else:
            miss += 1
            print(f"   ✗ PDF {p}: 인쇄된 쪽번호가 {p + off} 이 아니다 {found[:3]}")
    print(f"   {'✓' if not miss else '✗'} {ok}쪽이 맞고 {miss}쪽이 어긋난다")
    bad += miss

    cite = collections.defaultdict(set)
    for item, pl, _ in index_rows():
        if pl:
            cite[pl].add(item)
    seen = [n for n in nums if plates[n] <= 190]
    print(f"\n3. 도판이 제 번호인가 — 텍스트 레이어가 있는 {len(seen)}개")
    for n in seen:
        caps = {int(x) for x in re.findall(r"\b(\d{3})\.\s", text_of(pdf, plates[n]))}
        want = cite.get(n, set())
        if not want:
            print(f"   · Plate {n}: 색인이 안 부른다 — 겹쳐 볼 것이 없다")
            continue
        if not caps & want:
            print(f"   ✗ Plate {n} (PDF {plates[n]}): 캡션 {sorted(caps)[:6]} 와 "
                  f"색인 인용 {sorted(want)[:6]} 이 하나도 안 겹친다")
            bad += 1
    print(f"   {'✓ 전부 겹친다' if not bad else ''}")

    hidden = [n for n in nums if plates[n] > 190]
    print(f"\n※ PDF 191–{npages} 은 텍스트 레이어가 없어 2·3 을 못 본다 — "
          f"Plate {hidden[0]}~{hidden[-1]} ({len(hidden)}개).\n"
          f"  그 구간은 쪽 머리를 렌더해 눈으로 읽었다 (표 머리말)")
    print("\n" + ("어긋난 것 없다." if not bad else f"어긋난 것 {bad}건."))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
