#!/usr/bin/env python3
"""검증된 DB 스냅샷을 NAS 로 밀어 둔다 (오프사이트 track).

    python sync_backup_nas.py                   # NAS 에 없는 것을 전부
    python sync_backup_nas.py --newest-only     # 가장 새 것 하나만 (일별 cron)
    python sync_backup_nas.py --keep 30         # NAS 사본을 30개로 유지
    python sync_backup_nas.py --dry-run

**하루에 하나만 건너간다** (cron 은 `--newest-only`). 로컬은 시간별로 뜨지만
오프사이트는 일별 track 이다 — 시간 단위 복구는 로컬이 맡고 이쪽은 가장 오래 남는
사본을 든다. 밀린 것을 다 보내면 `--keep` 이 개수 기준이라 보존 **기간**이 짧아진다:
시간별 스냅샷이 그대로 올라가면 30개가 30일이 아니라 30시간이 된다.

손으로 뜬 `--note` 스냅샷을 오프사이트에 남기려면 그때 **손으로 한 번 돌린다**
(플래그 없이 부르면 밀린 것을 전부 보낸다). 일별 cron 은 그것을 기다려 주지 않는다.

**왜 필요한가.** 이 장비는 개발·운영·백업을 겸한다. `backup_db.py` 의 사본은
전부 `/data3` 안이라 디스크 한 장이 죽으면 사람의 교정 2,400여 건이 같이 간다
(`export_review.py` 가 아직 없어 교정이 DB 에만 있다). NAS 는 물리적으로 별개
장비이므로, 거기 사본을 두면 기계 분리라는 핵심 이득을 얻는다.

**라이브 DB 를 복사하지 않는다** (.guides/web/data-safety.md §4). 도는 WAL DB 를
본체·`-wal`·`-shm` 따로 복사하면 체크포인트와 경합해 찢어진 사본이 나온다.
`backup_db.py` 가 온라인 백업 API 로 떠서 `integrity_check` 를 통과시킨 **단일 파일
스냅샷**만 소비한다. 신선도는 최대 한 주기만큼 뒤처지는데, 그 값이면 싸다.

**수신 후 다시 검증한다** (§2, §4). 가장 오래 남는 사본이 가장 덜 검증된 것이
되는 것 — 그게 정확히 피해야 할 형태다. 그래서 NAS 에 놓은 파일을 열어
`integrity_check` 와 행 수를 다시 본다.

**실패하면 지우지 않는다** (§2). 검증에 실패하면 그 사본에 돌아가지 않는 이름
(`.corrupt`)을 붙여 증거로 남기고, **정리를 건너뛴 채** 0 이 아닌 값으로 끝낸다.
지난 성공 사본이 살아 있어야 한다.

**NAS 가 안 붙었는데 붙은 줄 아는 것을 막는다.** NFS 가 빠지면 `/nfs/temp-share` 는
그냥 빈 로컬 디렉토리가 되고, 거기 쓰면 "오프사이트에 뒀다"고 믿으면서 실은 같은
디스크에 쓰게 된다. `/proc/mounts` 로 실제 마운트인지 확인한다.

**cron 에서는 `timeout` 으로 감쌀 것.** NAS 가 `hard` 마운트라 내려가면 접근하는
프로세스가 무한 대기한다.

    40 4 * * * timeout 600 /home/paleoadmin/venv/diatom/bin/python \
        /home/paleoadmin/projects/diatom/sync_backup_nas.py --newest-only --keep 30 \
        >> /data3/diatom/logs/nas-sync.log 2>&1
"""
import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import db_sentinel

ROOT = Path(__file__).resolve().parent

# 이 표가 있으면 스키마가 살아 있다고 본다 — backup_db.py 와 같은 기준
SMOKE_TABLE = "viewer_objectreview"

# 깃발에 적히는 주인. backup_db.py 와 갈라야 서로의 실패를 안 지운다.
SOURCE = "sync_backup_nas"


def _env(key, default):
    """환경변수 → .env → 기본값. backup_db.py 와 같은 이유로 Django 를 안 쓴다."""
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


def is_real_mount(path: Path) -> bool:
    """path 가 실제 마운트 아래에 있는가.

    NFS 가 빠진 자리에 남은 빈 디렉토리에 쓰는 것을 막는다. 이것이 없으면
    "오프사이트에 뒀다"고 믿으면서 원본과 같은 디스크에 쓰게 된다.
    """
    try:
        mounts = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    target = str(path.resolve())
    for line in mounts:
        parts = line.split()
        if len(parts) < 3:
            continue
        mp, fstype = parts[1], parts[2]
        if fstype.startswith("nfs") and (target == mp or target.startswith(mp + "/")):
            return True
    return False


def verify(db_path: Path):
    """사본을 열어 무결성과 행 수를 본다. (ok, rows, error) 를 돌려준다."""
    try:
        # 읽기 전용으로 연다 — WAL 이 아닌 단일 파일이라 -shm 이 생기지 않는다
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        rows = con.execute(f"select count(*) from {SMOKE_TABLE}").fetchone()[0]
        con.close()
        return ok == "ok", rows, "" if ok == "ok" else ok
    except sqlite3.Error as e:
        return False, None, str(e)


def copy_verified(src: Path, dst_dir: Path):
    """임시 이름으로 옮긴 뒤 검증하고, 통과해야 제 이름을 준다.

    받다 만 파일이 정상 사본처럼 보이는 것을 막는다 — 이름이 붙었으면 검증을
    통과한 것이다.
    """
    tmp = dst_dir / (src.name + ".part")
    final = dst_dir / src.name
    shutil.copyfile(src, tmp)

    ok, rows, err = verify(tmp)
    if not ok or not rows:
        bad = dst_dir / (src.name + ".corrupt")   # 돌아가지 않는 이름 — 정리 대상 밖
        tmp.replace(bad)
        return False, rows, (err or f"{SMOKE_TABLE} 가 비었다"), bad

    tmp.replace(final)
    return True, rows, "", final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", default=_env("DIATOM_BACKUP_DIR",
                                            str(ROOT / "backup")))
    ap.add_argument("--nas", default=_env("DIATOM_NAS_BACKUP_DIR",
                                          "/nfs/temp-share/diatom/backup"))
    # 유지 개수는 조율한 숫자가 아니라 관계다 (data-safety.md §6):
    #   로컬 유지 개수 x 주기 >= 오프사이트 간격.
    # 오프사이트가 하루 간격이고 --newest-only 로 **하루 하나**가 건너가므로,
    # 30 은 곧 30일이다. 값을 늘리는 것은 무손실이다 — 늘려도 지워지는 것이 없다.
    #
    # **--newest-only 를 빼면 이 값의 뜻이 바뀐다.** 시간별 스냅샷이 그대로
    # 올라가므로 30 이 30일이 아니라 30시간이 된다.
    ap.add_argument("--keep", type=int, default=0,
                    help="NAS 사본을 최근 N개로 (0 이면 안 지운다)")
    ap.add_argument("--newest-only", action="store_true",
                    help="가장 새 스냅샷 하나만 보낸다 (일별 cron 이 쓴다)")
    ap.add_argument("--stale-hours", type=float, default=26.0,
                    help="가장 새 로컬 스냅샷이 이보다 오래면 경고 (0 이면 끔)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    local = Path(args.local)
    nas = Path(args.nas)

    snaps = sorted(local.glob("diatom_*.db"))
    if not snaps:
        print(f"로컬 스냅샷이 없다: {local}", file=sys.stderr)
        print("  backup_db.py 를 먼저 돌렸는가?", file=sys.stderr)
        return 1

    # 신선도 — 로컬 백업이 멈췄거나 무결성 게이트에 막혀 있으면 여기서 드러난다.
    # 오프사이트가 조용히 낡아 가는 것을 배포와 무관하게 잡는 신호다 (§4).
    newest_age_h = (time.time() - snaps[-1].stat().st_mtime) / 3600
    if args.stale_hours and newest_age_h > args.stale_hours:
        print(f"경고: 가장 새 로컬 스냅샷이 {newest_age_h:.1f} 시간 전이다 "
              f"({snaps[-1].name}). backup_db.py 가 멈췄는가?", file=sys.stderr)

    if not is_real_mount(nas.parent if not nas.exists() else nas):
        print(f"NAS 가 마운트되어 있지 않다: {nas}", file=sys.stderr)
        print("  빈 디렉토리에 쓰면 원본과 같은 디스크에 쌓인다 — 멈춘다.",
              file=sys.stderr)
        return 1

    if not args.dry_run:
        nas.mkdir(parents=True, exist_ok=True)

    have = {p.name for p in nas.glob("diatom_*.db")} if nas.is_dir() else set()

    if args.newest_only:
        # **하루에 하나만 건너간다.** 로컬은 시간별로 뜨지만 오프사이트는 일별
        # track 이다 — 시간 단위 복구는 로컬이 맡고, 이쪽은 가장 오래 남는 사본을
        # 든다(data-safety.md §1 의 세 갈래).
        #
        # 밀린 것을 따라잡지 않는 것이 요점이다. 다 보내면 NAS 의 --keep 이 개수
        # 기준이라 보존 기간이 그만큼 짧아진다 — 30개가 30일이 아니라 30시간이 된다.
        #
        # 가장 새 것이 이미 가 있으면 할 일이 없다. **더 옛것으로 물러서지
        # 않는다** — 그러면 매번 하나씩 옛 사본을 실어 나르게 된다.
        todo = [] if snaps[-1].name in have else [snaps[-1]]
    else:
        todo = [p for p in snaps if p.name not in have]

    if not todo:
        print(f"NAS 가 최신이다 — 사본 {len(have)}개 ({nas})")
    elif args.dry_run:
        for p in todo:
            print(f"  보낼 것: {p.name}  {p.stat().st_size / 1e6:.1f} MB")
        print(f"\ndry-run — {len(todo)}개. 보내지 않았다.")
        return 0

    sent = failed = 0
    for p in todo:
        ok, rows, err, dst = copy_verified(p, nas)
        if ok:
            sent += 1
            print(f"  {p.name}  {p.stat().st_size / 1e6:.1f} MB  "
                  f"integrity=ok  {SMOKE_TABLE}={rows}")
        else:
            failed += 1
            print(f"  {p.name}  검증 실패 — {err}", file=sys.stderr)
            print(f"    증거를 남겼다: {dst.name}", file=sys.stderr)

    # 깃발은 **사본을 믿을 수 없을 때만** 세운다 (db_sentinel 머리말).
    #
    # NAS 가 안 붙은 것은 여기 넣지 않았다. 그건 자료가 상한 것이 아니라 lane 이
    # 잠깐 없는 것인데, 그것까지 세우면 NAS 점검 한 번에 뷰어가 degraded 가 되고
    # 배포 smoke 가 막힌다. 가장 센 신호(자료가 상했다)가 잡음에 묻히면 안 된다.
    # 오프사이트 가용성은 별도 신호가 맡을 몫이다.
    db = Path(_env("DIATOM_DB", str(ROOT / "diatom.db")))
    if failed:
        # 실패했으면 정리하지 않는다 — 지난 성공 사본이 유일한 안전망일 수 있다
        print(f"\n{failed}개가 검증에 실패했다. 정리를 건너뛴다.", file=sys.stderr)
        if not args.dry_run:
            flag = db_sentinel.raise_fail(
                db, SOURCE, f"NAS 사본 {failed}개가 검증에 실패했다 ({nas})")
            print(f"  깃발을 세웠다: {flag} (/healthz 가 degraded 를 낸다)",
                  file=sys.stderr)
        return 1

    if not args.dry_run and db_sentinel.clear(db, SOURCE):
        print("  지난 실패 깃발을 내렸다")

    if args.keep and not args.dry_run:
        # 정리는 이 스크립트만 한다 (§10). .corrupt 는 glob 에 안 걸려 남는다.
        allc = sorted(nas.glob("diatom_*.db"))
        for old in allc[:-args.keep]:
            old.unlink()
            print(f"  정리: {old.name}")

    total = len(list(nas.glob("diatom_*.db")))
    print(f"\n보냄 {sent}개 · NAS 사본 {total}개 · {nas}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
