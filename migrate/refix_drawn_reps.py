#!/usr/bin/env python3
"""그린 개체의 대표(`is_rep`)를 합성본으로 되돌린다 — 번지기가 옮겨 놓은 것.

    python refix_drawn_reps.py            # 무엇이 바뀌는지만 보여준다
    python refix_drawn_reps.py --apply    # 실제로 옮긴다
    python refix_drawn_reps.py --slide 260731_am22-gc10b_25cm --apply

## 왜 있는가 (실사용 2026-08-13)

번지기(106)의 `_spread_drawn` 이 **저장할 때 열려 있던 판**(`src`)을 대표로
삼았다. 08-09 에 합성본에 그린 마스크를 오늘 프레임 판을 열어 둔 채 저장하니
그 프레임이 `src` 가 되고, 합성본이 target 으로 밀리면서 **대표가 조용히
옮겨갔다.** 새 대표는 가장 선명한 프레임도 아니다 — 그때 열려 있던 판일 뿐이다.

`is_rep` 은 *"학습 자료로 뽑을 때, 목록에 보일 때 이 판을 쓴다"* 이므로
(`ObjectReview.is_rep` 머리말) 개체의 얼굴이 **흐린 단일 프레임**이 된다.
예외도 경고도 안 난다: 대표는 개체당 하나라는 제약을 계속 지키므로
`check_db` 8번에도 안 걸리고, 화면은 그냥 다른 크롭을 보여줄 뿐이다.

`data._spread_drawn` 은 고쳤다(대표를 합성본으로 고른다). 이 스크립트는
**그 전에 이미 앉은 값**을 치운다.

## 무엇만 건드리나

`source='manual'` 인 판정 중 **판이 여럿이고 합성본 멤버가 있는데 대표가
합성본이 아닌** 개체만이다. 다음은 손대지 않는다.

- 엔진 개체 — 번지기를 안 타므로 이 고장의 자리가 아니다
- 판이 하나뿐인 개체 — 고를 것이 없다
- 합성본 멤버가 없는 개체 — 싱글턴 시야이거나 아직 안 합친 시야다

**사람이 고른 대표와 번지기가 옮긴 대표를 못 가른다.** `/link` 에서 묶을 때
대표를 사람이 고르는데(`views._Reject` 위쪽 — "대표는 사람이 이 개체의 얼굴로
고른 판이다"), 그 개체에 그린 멤버가 하나라도 있으면 여기 함께 잡힌다.
기록에 "누가 세웠나" 가 없어 스크립트가 정할 수 없다 — **`--apply` 전에 목록을
눈으로 볼 것.** 열 몇 개라 갈린다.

**옮기는 것은 `is_rep` 뿐이다.** 분류·종명·등급·코멘트·기하는 개체와 판정에
그대로 있고 이 스크립트가 읽지도 않는다.
"""
import argparse
import os
import sys
from pathlib import Path

import django

# `dbrun.sh` 로 컨테이너 안에서 돌 수도 있다 — 그때 Django 코드는 /app 이고
# `DIARUGA_APP` 이 그것을 알려 준다 (`ops/check_db.py` 의 머리를 그대로 베꼈다).
APP = Path(os.environ.get("DIARUGA_APP")
           or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402

from viewer.models import DiatomObject, ObjectReview                 # noqa: E402


def wrong_objects(slug=None):
    """대표가 합성본이 아닌 그린 개체들 — `(개체, 합성본 판정, 지금 대표)`.

    **개체 하나씩 본다.** 한 질의로 짜면 "합성본 멤버가 있다" 와 "대표가
    그것이다" 를 한꺼번에 물어야 해서 읽기 어렵고, 대상이 열 몇 개다.
    """
    qs = DiatomObject.objects.filter(members__source="manual").distinct()
    if slug:
        qs = qs.filter(viewpoint__slide__slug=slug)
    out = []
    for obj in qs.prefetch_related("members__image"):
        members = list(obj.members.all())
        if len(members) < 2:
            continue
        stack = next((m for m in members if m.image and m.image.kind == "stack"),
                     None)
        if stack is None or stack.is_rep:
            continue
        out.append((obj, stack, next((m for m in members if m.is_rep), None)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slide", help="슬라이드 slug 하나만")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 옮긴다 (없으면 보여주기만)")
    args = ap.parse_args()

    rows = wrong_objects(args.slide)
    if not rows:
        print("대표가 어긋난 그린 개체가 없다.")
        return

    print(f"{'개체':>6}  {'슬라이드':32s} {'시야':>5}  지금 대표 → 옮길 곳")
    for obj, stack, cur in rows:
        vp = obj.viewpoint
        now = Path(cur.image.path).name if cur and cur.image else "(없다)"
        print(f"{obj.pk:>6}  {vp.slide.slug:32s} g{vp.idx:03d}  "
              f"{now} → {Path(stack.image.path).name}")
    print(f"\n  합계 {len(rows)}개")

    if not args.apply:
        print("\n보여주기만 했다. 옮기려면 --apply 를 줄 것.")
        return

    # **내리고 세우는 것이 한 트랜잭션이어야 한다.** `is_rep` 은 개체당
    # 하나라는 유일 제약이 있어, 중간에 멈추면 대표가 둘이거나 없는 개체가
    # 남는다 — 뒤엣것은 `check_db` 8번이 잡지만 앞엣것은 INSERT 가 막는다.
    moved = 0
    with transaction.atomic():
        for obj, stack, _cur in rows:
            ObjectReview.objects.filter(diatom_object=obj, is_rep=True).update(
                is_rep=False)
            ObjectReview.objects.filter(pk=stack.pk).update(is_rep=True)
            moved += 1
    print(f"\n대표 {moved}개를 합성본으로 옮겼다. 분류·코멘트·기하는 그대로다.")


if __name__ == "__main__":
    main()
