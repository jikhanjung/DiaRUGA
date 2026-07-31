#!/usr/bin/env python3
"""NAS 를 훑어 어떤 슬라이드가 있고 무엇이 새것인지 보고한다. **읽기 전용이다.**

    python scan_nas.py
    python scan_nas.py --json /tmp/scan.json

DB 도 파일도 건드리지 않는다. 반입은 `ingest_nas.py` 가 한다.

**왜 나누는가.** NAS 디렉토리는 사람이 만든 것이라 예외가 많다 — 촬영 중인 폴더,
이름 규칙에서 벗어난 폴더, XML 이 빠진 사진. 먼저 읽기 전용으로 훑어 "무엇이 있고
무엇이 안 맞는가" 를 보고 나서 반입한다. diatom 은 사람의 교정이 재생성 불가라
이 순서가 더 중요하다. (형제 프로젝트의 EPMA 반입도 같은 갈래다.)

## NAS 구조

    /nfs/temp-share/DiatomPhotos/<촬영일>/<슬라이드>/Snap-NNNNN.jpg
                                                    Snap-NNNNN.jpg_metadata.xml

로컬은 이 구조를 그대로 비춘다: `<DATA_ROOT>/photos/<촬영일>/<슬라이드>/`.
그래서 상대경로 하나가 곧 키다.

## 촬영이 끝났는지 어떻게 아는가

**촬영 중인 폴더를 건드리면 안 된다.** 절반만 가져가면 그룹핑이 시야를 잘못 묶고,
그 위에 검출과 교정이 쌓인 뒤에 되돌리는 것은 훨씬 비싸다.

NFS 에서 inotify 는 믿을 수 없으므로(P01 §1) 폴링으로 본다. **파일 개수와 가장 최근
mtime 이 일정 시간 그대로면 끝난 것으로 본다.** 완벽하지는 않다 — 촬영자가 오래
쉬었다 다시 찍으면 중간에 끝난 것으로 볼 수 있다. 그래서 `--quiet-min` 을 넉넉히
잡고, 그래도 잘못 잡히면 `Slide.state` 로 사람이 되돌릴 수 있게 해 둔다.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diatomweb.settings")
django.setup()

from django.conf import settings                                    # noqa: E402
from viewer.models import Slide                                     # noqa: E402

# 로컬에서 사진이 놓이는 자리. NAS 의 <촬영일>/<슬라이드> 를 이 아래에 그대로 편다.
PHOTOS = "photos"


def nas_root() -> Path:
    return Path(os.environ.get("DIATOM_NAS_PHOTOS",
                               "/nfs/temp-share/DiatomPhotos"))


def is_mounted(path: Path) -> bool:
    """NFS 가 실제로 붙어 있는가.

    빠지면 그 자리는 그냥 빈 로컬 디렉토리가 된다. 그것을 "새 슬라이드가 하나도
    없다" 로 읽으면 조용히 아무것도 안 하게 된다 — 고장이 정상처럼 보인다.
    """
    try:
        mounts = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    target = str(path.resolve())
    for line in mounts:
        p = line.split()
        if len(p) >= 3 and p[2].startswith("nfs") and (
                target == p[1] or target.startswith(p[1] + "/")):
            return True
    return False


def survey(slide_dir: Path) -> dict:
    """폴더 하나를 재 본다. NAS 왕복을 한 번만 하도록 한 번에 모은다."""
    jpgs, xmls, newest, total = 0, 0, 0.0, 0
    with os.scandir(slide_dir) as it:
        for e in it:
            if not e.is_file():
                continue
            st = e.stat()
            newest = max(newest, st.st_mtime)
            total += st.st_size
            low = e.name.lower()
            if low.endswith(".jpg") or low.endswith(".jpeg"):
                jpgs += 1
            elif low.endswith("_metadata.xml"):
                xmls += 1
    return {"jpgs": jpgs, "xmls": xmls, "bytes": total,
            "newest_mtime": newest,
            "quiet_min": round((time.time() - newest) / 60, 1) if newest else None}


def scan(quiet_min: float = 20.0) -> dict:
    """NAS 의 슬라이드 폴더를 전부 훑고 DB 와 대조한다."""
    root = nas_root()
    if not is_mounted(root):
        raise SystemExit(f"NAS 가 마운트되어 있지 않다: {root}\n"
                         f"  빈 디렉토리를 '새것 없음' 으로 읽으면 안 된다 — 멈춘다.")

    known = set(Slide.objects.values_list("image_dir", flat=True))

    rows = []
    for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for slide_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
            rel = f"{date_dir.name}/{slide_dir.name}"
            local = f"{PHOTOS}/{rel}"
            s = survey(slide_dir)
            if s["jpgs"] == 0:
                state = "empty"
            elif local in known:
                state = "known"
            elif s["quiet_min"] is not None and s["quiet_min"] < quiet_min:
                state = "uploading"
            else:
                state = "new"
            rows.append({"rel": rel, "local": local, "state": state,
                         "nas_path": str(slide_dir), **s})
    return {"nas_root": str(root), "quiet_min": quiet_min, "slides": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet-min", type=float, default=20.0,
                    help="마지막 파일이 이 시간(분) 이상 조용해야 촬영이 끝난 것으로 본다")
    ap.add_argument("--json", dest="json_file", help="결과를 JSON 으로 저장")
    args = ap.parse_args()

    res = scan(args.quiet_min)
    rows = res["slides"]
    by = {}
    for r in rows:
        by.setdefault(r["state"], []).append(r)

    label = {"new": "새 슬라이드", "known": "이미 있음",
             "uploading": "촬영 중(조용해지길 기다림)", "empty": "사진 없음"}
    print(f"NAS {res['nas_root']} · 슬라이드 폴더 {len(rows)}개")
    for state in ("new", "uploading", "known", "empty"):
        got = by.get(state) or []
        if not got:
            continue
        print(f"\n{label[state]} — {len(got)}개")
        for r in got:
            xml = "" if r["xmls"] >= r["jpgs"] else f"  ** XML {r['xmls']}/{r['jpgs']}"
            print(f"  {r['rel']:<40} 사진 {r['jpgs']:>4}  "
                  f"{r['bytes'] / 1e6:>7.1f} MB  조용 {r['quiet_min']}분{xml}")

    # XML 이 모자라면 배율이 기본값으로 조용히 떨어진다 (004 에서 한 번 당했다)
    short = [r for r in rows if r["state"] in ("new", "known")
             and r["xmls"] < r["jpgs"]]
    if short:
        print(f"\n** XML 이 모자란 폴더 {len(short)}개 — 배율(µm/px)을 못 읽으면 "
              f"기본값으로 조용히 떨어진다", file=sys.stderr)

    if args.json_file:
        Path(args.json_file).write_text(json.dumps(res, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
        print(f"\nJSON: {args.json_file}")

    print(f"\n새로 반입할 것 {len(by.get('new') or [])}개"
          f" (반입은 ingest_nas.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
