#!/usr/bin/env python3
"""묶음의 **조리법**을 보고·비우고·권역을 못 박는다 (2026-08-26).

    python batch_recipe.py --list
    python batch_recipe.py --show yolo-3차
    python batch_recipe.py --clear yolo-3차           # 자동으로 안 돈다
    python batch_recipe.py --areas ant yolo-3차       # 남극만 본다
    python batch_recipe.py --areas '' yolo-3차        # 권역 제한을 걷는다
    python batch_recipe.py --restore yolo-3차 '<json>'

관리 화면(`/manage/`)의 `set_recipe` 와 같은 일을 하는 CLI 다. 화면이 있는데도
두는 이유는 **폴러 쪽 작업이 셸에서 나기 때문**이다 — 조리법을 비우고 다시
얹는 것이 배포·회차 전환의 한 단계라 손으로 클릭할 자리가 아니다.

**비우기 전에 조리법을 찍는다.** `--clear` 는 지우기 전 값을 JSON 한 줄로 내고,
그것을 `--restore` 에 그대로 먹이면 되돌아온다 — 회차를 다시 켤 때 **가중치
경로를 기억에 의존하지 않기 위해서다.**

권역 규칙 자체는 `pipeline/batch_scope.py` 하나에 있다. 여기서는 그 열쇠를
조리법에 적기만 한다.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import django

# **`ops/check_db.py` 의 머리를 그대로 베낀다** (CLAUDE.md). 컨테이너 안에서는
# 코드가 `/app` 이고 이 스크립트만 `/srv/DiaRUGA/scripts` 에서 마운트되므로,
# 자기 옆의 `web/` 을 보게 짜면 `No module named 'diarugaweb'` 로 죽는다.
APP = Path(os.environ.get("DIARUGA_APP")
          or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
# `batch_scope` 는 `pipeline/` 에 있다. `/srv` 는 평평해서 이 줄이 없어도 되지만
# 저장소에서는 디렉토리가 갈려 있어 알려 줘야 한다.
sys.path.insert(0, str(APP / "pipeline"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

import batch_scope                                                  # noqa: E402
from viewer.models import RunBatch                                  # noqa: E402


def find(label: str) -> RunBatch:
    b = RunBatch.objects.filter(kind="detect", label=label).first()
    if b is None:
        raise SystemExit(f"그런 묶음이 없다: {label}")
    return b


def show(b: RunBatch) -> None:
    mark = "◉" if b.for_review else " "
    body = json.dumps(b.recipe or {}, ensure_ascii=False, sort_keys=True)
    print(f"{mark} {b.label:<14} {batch_scope.label_for_plan(b.recipe):<12} {body}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", metavar="묶음")
    ap.add_argument("--clear", metavar="묶음")
    ap.add_argument("--areas", nargs=2, metavar=("권역", "묶음"),
                    help="쉼표로 여럿. 빈 문자열이면 제한을 걷는다")
    ap.add_argument("--restore", nargs=2, metavar=("묶음", "JSON"))
    a = ap.parse_args()

    if a.list or not any([a.show, a.clear, a.areas, a.restore]):
        for b in RunBatch.objects.filter(kind="detect").order_by("id"):
            show(b)
        return 0

    if a.show:
        show(find(a.show))
        return 0

    if a.clear:
        b = find(a.clear)
        if not b.recipe:
            print(f"{b.label} 은 이미 자동으로 안 돈다")
            return 0
        # **되돌릴 값을 먼저 낸다.** 지우고 나서 "가중치가 뭐였더라" 가 되면
        # 회차를 다시 켤 때 추측이 들어간다 (`weights_guessed` 가 그 자국이다).
        old = json.dumps(b.recipe, ensure_ascii=False, sort_keys=True)
        print(f"되돌릴 값 → python batch_recipe.py --restore {b.label} '{old}'")
        b.recipe = {}
        b.save(update_fields=["recipe"])
        print(f"{b.label} 의 조리법을 비웠다 — 자동으로 안 돈다")
        return 0

    if a.areas:
        raw, label = a.areas
        b = find(label)
        if not b.recipe:
            raise SystemExit(f"{b.label} 은 조리법이 없다 — 권역만 적을 수 없다")
        r = dict(b.recipe)
        areas = [x for x in (s.strip() for s in raw.split(",")) if x]
        if areas:
            r[batch_scope.KEY] = areas
        else:
            r.pop(batch_scope.KEY, None)
        b.recipe = r
        b.save(update_fields=["recipe"])
        show(b)
        return 0

    label, body = a.restore
    b = find(label)
    try:
        r = json.loads(body)
    except json.JSONDecodeError as e:
        raise SystemExit(f"JSON 이 아니다: {e}")
    if not isinstance(r, dict):
        raise SystemExit("조리법은 객체여야 한다")
    b.recipe = r
    b.save(update_fields=["recipe"])
    show(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
