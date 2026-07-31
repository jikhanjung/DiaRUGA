#!/usr/bin/env python3
"""DB 사본을 backup/ 에 타임스탬프를 붙여 뜬다.

    python backup_db.py
    python backup_db.py --note before-refilter    # 파일명에 꼬리말을 붙인다
    python backup_db.py --keep 20                 # 오래된 것부터 지운다

**`cp diatom.db` 로는 안 된다.** WAL 모드라 최근 쓰기가 `-wal` 파일에 있고, 그냥
복사하면 불완전한 사본이 나온다. SQLite 의 backup API 는 잠금을 잡고 일관된 사본을
만든다(쓰는 중에도 안전하다).

DB 는 gitignore 다. 사람의 교정(재생성 불가)이 DB 에만 있는 동안은 이것이 유일한
안전망이므로, 큰 작업 전에 한 번씩 돌린다. review/*.json 내보내기(P02 §5-5)가
갖춰지면 그쪽이 감사 기록을 맡는다.
"""
import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _env(key, default):
    """환경변수 → .env → 기본값.

    settings.py 에도 같은 것이 있다. 일부러 나눠 뒀다 — 이 스크립트는 **다른 것이
    전부 망가졌을 때 쓰는 마지막 안전망**이라, Django 를 임포트하지 않고 혼자
    돌아야 한다. 열 줄 중복이 그 값을 한다.
    """
    if key in os.environ:
        return os.environ[key]
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    except OSError:
        pass
    return default


# DB 는 배포 위치(/srv/diatom)로 나가 있을 수 있다 — .env 의 DIATOM_DB 를 따른다.
DB = Path(_env("DIATOM_DB", str(ROOT / "diatom.db")))
# 사본은 커지므로(3 GB 넘었다) 큰 디스크에 둘 수 있게 뺀다.
OUT = Path(_env("DIATOM_BACKUP_DIR", str(ROOT / "backup")))

TABLES = ("slide", "viewpoint", "frame", "detection", "candidate",
          "objectreview", "viewpointreview", "run")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", default="", help="파일명 꼬리말")
    ap.add_argument("--keep", type=int, default=0,
                    help="최근 N개만 남긴다 (0 이면 안 지운다)")
    ap.add_argument("--db", default=str(DB))
    args = ap.parse_args()

    src_path = Path(args.db)
    if not src_path.exists():
        raise SystemExit(f"DB 가 없다: {src_path}")

    OUT.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tail = f"_{args.note}" if args.note else ""
    out = OUT / f"diatom_{stamp}{tail}.db"

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst = sqlite3.connect(out)
    with dst:
        src.backup(dst)
    src.close()

    # 사본은 파일 하나로 딱 떨어져야 한다. backup 은 journal 모드까지 복사하므로
    # 그대로 두면 WAL 로 남아, 읽을 때마다 -shm 이 생기고 옮길 때 딸려 다녀야
    # 하는 파일이 늘어난다. 보관용은 DELETE 모드가 맞다.
    dst.execute("PRAGMA journal_mode=DELETE")

    # 사본이 실제로 읽히는지 확인한다 — 뜨기만 하고 깨진 것을 모르면 뜻이 없다
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    counts = {}
    for t in TABLES:
        try:
            counts[t] = dst.execute(f"select count(*) from viewer_{t}").fetchone()[0]
        except sqlite3.Error:
            counts[t] = None
    dst.close()

    # 옮겨 다닐 필요 없는 부산물은 치운다
    for ext in ("-wal", "-shm"):
        stray = out.with_name(out.name + ext)
        if stray.exists():
            stray.unlink()

    mb = out.stat().st_size / 1e6
    # 사본 디렉토리는 저장소 밖일 수 있다 (DIATOM_BACKUP_DIR)
    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f"{shown}  {mb:.1f} MB  integrity={ok}")
    print("  " + " · ".join(f"{t} {n}" for t, n in counts.items() if n is not None))
    if ok != "ok":
        print("사본이 깨졌다 — 지우지 말고 원인을 확인하라", file=sys.stderr)
        return 1

    if args.keep:
        old = sorted(OUT.glob("diatom_*.db"))[: -args.keep] if args.keep else []
        for p in old:
            p.unlink()
        if old:
            print(f"  오래된 사본 {len(old)}개 지웠다 (최근 {args.keep}개 유지)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
