#!/usr/bin/env python
"""노두 현장 사진을 화면에 쓸 크기로 줄인다. NAS 공유의 원본을 제자리에서 바꾼다.

**원본을 건드리는 스크립트다** (사용자 허가 2026-08-06). 그래서:

- `--dry-run` 이 기본이다. 실제로 쓰려면 `--apply` 를 준다
- **줄이기 전에 사본을 뜬다** (`--backup-dir`, 기본 `/data3/DiaRUGA/backup/
  outcrop-original`). 이미 있는 파일은 덮지 않는다 — 두 번 돌려도 줄인 것이
  원본 자리에 앉지 않는다
- 이미 충분히 작으면 **건드리지 않는다.** 다시 돌릴 때마다 JPEG 을 재압축하면
  볼 때마다 조금씩 뭉개진다
- 새 파일을 옆에 쓰고 검증한 뒤 제자리로 옮긴다(`.part` → 이름). 반쯤 쓴
  파일이 제 이름을 달면 화면이 깨진 그림을 낸다 (`backup_db.py` 와 같은 규칙)

5568x3712 · 12 MB 짜리를 그대로 두면 "원본 열기" 가 NAS 에서 12 MB 를 끌어온다.
장축 2400px 이면 화면에서 확대해 보기에 넉넉하고 1 MB 아래로 떨어진다.

    python shrink_outcrop.py                 # 무엇을 할지만 보인다
    python shrink_outcrop.py --apply
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

from PIL import Image

DEFAULT_DIR = os.environ.get("DIARUGA_OUTCROP_DIR",
                             "/nfs/temp-share/DiaRUGA/outcrop")
DEFAULT_BACKUP = "/data3/DiaRUGA/backup/outcrop-original"
EXT = (".jpg", ".jpeg", ".png")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--backup-dir", default=DEFAULT_BACKUP)
    ap.add_argument("--max-side", type=int, default=2400,
                    help="긴 변 픽셀 (기본 2400)")
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--apply", action="store_true", help="실제로 바꾼다")
    args = ap.parse_args()

    root, backup = Path(args.dir), Path(args.backup_dir)
    if not root.is_dir():
        raise SystemExit(f"폴더가 없다: {root}")

    files = sorted(f for f in root.iterdir()
                   if f.is_file() and f.suffix.lower() in EXT)
    if not files:
        print("줄일 것이 없다")
        return 0

    total_before = total_after = 0
    for f in files:
        before = f.stat().st_size
        total_before += before
        try:
            with Image.open(f) as im:
                w, h = im.size
                if max(w, h) <= args.max_side:
                    print(f"  건너뜀 {f.name} — 이미 {w}x{h}")
                    total_after += before
                    continue
                scale = args.max_side / max(w, h)
                size = (round(w * scale), round(h * scale))
                if not args.apply:
                    print(f"  {f.name}: {w}x{h} {before/1e6:.1f} MB "
                          f"-> {size[0]}x{size[1]}")
                    total_after += before
                    continue
                backup.mkdir(parents=True, exist_ok=True)
                dst = backup / f.name
                if not dst.exists():
                    shutil.copy2(f, dst)
                out = im.convert("RGB").resize(size, Image.LANCZOS)
        except OSError as e:
            print(f"  못 읽음 {f.name}: {e}")
            total_after += before
            continue

        # 옆에 쓰고 확인한 뒤에 제자리로. 반쯤 쓴 파일이 제 이름을 달면 안 된다.
        tmp = f.with_suffix(f.suffix + ".part")
        out.save(tmp, "JPEG", quality=args.quality, optimize=True,
                 progressive=True)
        with Image.open(tmp) as chk:
            chk.verify()
        after = tmp.stat().st_size
        tmp.replace(f)
        total_after += after
        print(f"  {f.name}: {w}x{h} {before/1e6:.1f} MB "
              f"-> {size[0]}x{size[1]} {after/1e6:.2f} MB "
              f"({100 * after / before:.0f}%)")

    print(f"\n{len(files)}장 · {total_before/1e6:.1f} MB "
          f"-> {total_after/1e6:.1f} MB")
    if not args.apply:
        print("--dry-run 이라 아무것도 안 썼다 (--apply 를 줄 것)")
    else:
        print(f"원본 사본: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
