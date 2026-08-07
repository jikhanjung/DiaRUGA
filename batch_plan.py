#!/usr/bin/env python3
"""새 자료를 어느 묶음에 어떤 순서로 채울지 — **폴러가 읽는다** (079).

    python batch_plan.py            # 사람이 읽는 표
    python batch_plan.py --args     # 폴러가 먹는 줄 (탭으로 가른다)

`RunBatch.recipe` 가 `segment_diatoms.py` 의 인자를 담고 있고, 여기서는 그것을
**순서대로** 펴 준다. 순서는 `data.batches_to_run()` 이 정한다 — 검토 중인
묶음이 먼저, 나머지는 최근 것부터.

**셸에서 조리법을 해석하지 않는다.** 파이썬이 한 줄로 만들어 주고 셸은 그대로
넘긴다 — JSON 을 셸에서 뜯으면 따옴표와 공백에서 반드시 깨진다.

`dbrun.sh` 로 도는 다른 스크립트들과 같은 머리를 쓴다 (`check_db.py` 참고).
"""
import argparse
import os
import shlex
import sys
from pathlib import Path

import django

APP = Path(os.environ.get("DIARUGA_APP", Path(__file__).resolve().parent / "web"))
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from viewer import data                                              # noqa: E402

# 조리법 열쇠 → `segment_diatoms.py` 의 인자. 없는 열쇠는 그냥 건너뛴다 —
# 조리법에 새 항목이 생겨도 옛 파이프라인이 죽지 않아야 한다.
FLAGS = {
    "backend": "--backend", "scale": "--scale",
    "points_per_side": "--points-per-side",
    "min_um": "--min-um", "max_um": "--max-um",
    "weights": "--weights", "yolo_conf": "--yolo-conf",
    "yolo_imgsz": "--yolo-imgsz",
}
SWITCHES = {"all_images": "--all-images"}


def argv_for(recipe: dict) -> list[str]:
    out = []
    for k, flag in FLAGS.items():
        v = recipe.get(k)
        if v is not None:
            out += [flag, str(v)]
    for k, flag in SWITCHES.items():
        if recipe.get(k):
            out.append(flag)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--args", action="store_true",
                    help="폴러용: '<이름>\\t<인자들>' 을 줄마다")
    a = ap.parse_args()

    rows = data.batches_to_run()
    if a.args:
        for r in rows:
            if not r["ready"]:
                continue
            print(f"{r['batch'].label}\t{shlex.join(argv_for(r['recipe']))}")
        return 0

    if not rows:
        print("자동으로 채울 묶음이 없다 — 조리법(recipe)이 적힌 묶음이 없다.")
        return 0
    print(f"{'순서':<4} {'묶음':<16} {'상태':<6} 인자")
    for i, r in enumerate(rows, 1):
        mark = "◉" if r["batch"].for_review else " "
        state = "OK" if r["ready"] else "못 돌림"
        print(f"{i:<4} {mark} {r['batch'].label:<14} {state:<6} "
              f"{shlex.join(argv_for(r['recipe']))}")
        if not r["ready"]:
            print(f"       └─ {r['why']}")
        if r["recipe"].get("weights_guessed"):
            print("       └─ 가중치는 이행이 **추측한** 값이다 — 확인할 것")
    return 0


if __name__ == "__main__":
    sys.exit(main())
