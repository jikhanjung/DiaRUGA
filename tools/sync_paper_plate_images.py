#!/usr/bin/env python3
"""논문 도판 크롭을 `/data3/DiaRUGA/atlas/` 로 복사한다 — P23.

`Diadiction/plate/`(NAS)의 크롭은 파일명에 학명이 붙어 있다
(`plate_1991lee_pl1_fig01_Actinocyclus_...png`). DB(`AtlasPlacement.crop_image`)
는 이미 이름을 알고 있으므로 서빙 경로에는 또 싣지 않는다 — 도판 이미지가
`render_atlas_pages.py` 로 `/data3/DiaRUGA/atlas/<도감>/...` 에 구워지는 것과
같은 뿌리 아래, `crops/pl<N>_fig<NN>.png` 로 이름을 떼고 복사한다
(`tools/parse_paper_atlas.py::crop_of()` 가 만드는 경로와 정확히 같아야 한다).

**NAS 를 보므로 호스트에서 돈다**(`render_atlas_pages.py` 와 같은 사정 —
컨테이너는 `/nfs/temp-share` 를 못 본다). `/data3` 는 컨테이너와 호스트가
같이 보므로 새 라우트가 필요 없다 — `/img?p=` 가 그대로 연다.

사용:

    python tools/sync_paper_plate_images.py
    python tools/sync_paper_plate_images.py --only 1991_lee_yeonil_biostratigraphy
    python tools/sync_paper_plate_images.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402
from parse_paper_atlas import PAPER_META  # noqa: E402

PLATE_DIR = DIADICTION / "plate"
OUT = Path(os.environ.get("DIARUGA_ATLAS_ROOT", "/data3/DiaRUGA/atlas"))

NAME_RE = re.compile(r"^plate_(?P<prefix>[a-z0-9]+)_pl(?P<plate>\d+)"
                      r"_fig(?P<fig>[0-9A-Za-z]+)_.*\.png$")


def sync_one(paper: str, meta: dict, dry_run: bool) -> tuple[int, int]:
    prefix = meta["crop_prefix"]
    dest_dir = OUT / meta["atlas_key"] / "crops"
    copied = skipped = 0
    for src in sorted(PLATE_DIR.glob(f"plate_{prefix}_pl*_fig*_*.png")):
        m = NAME_RE.match(src.name)
        if not m or m.group("prefix") != prefix:
            continue
        dest = dest_dir / f"pl{m.group('plate')}_fig{m.group('fig')}.png"
        if dry_run:
            copied += 1
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied += 1
    return copied, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="논문 키 하나만")
    ap.add_argument("--dry-run", action="store_true", help="세기만 한다")
    args = ap.parse_args()

    papers = {k: v for k, v in PAPER_META.items() if v.get("crop_prefix")}
    if args.only:
        papers = {k: v for k, v in papers.items() if k == args.only}
        if not papers:
            print(f"{args.only}: crop_prefix 가 있는 논문이 아니다", file=sys.stderr)
            return 2

    if not PLATE_DIR.exists():
        print(f"NAS 를 못 찾는다: {PLATE_DIR} — 호스트에서 돌 것", file=sys.stderr)
        return 2

    total = 0
    for paper, meta in papers.items():
        n, _ = sync_one(paper, meta, args.dry_run)
        total += n
        print(f"{meta['short']} — {n}개 → "
              f"{OUT / meta['atlas_key'] / 'crops'}{' (dry-run)' if args.dry_run else ''}")
    print(f"\n합계 {total}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
