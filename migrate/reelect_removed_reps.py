#!/usr/bin/env python3
"""**대표가 지운 판인 개체**의 얼굴을 산 판으로 옮긴다 (151 · 일회성).

    python reelect_removed_reps.py           # 무엇이 걸리는지만 본다
    python reelect_removed_reps.py --apply   # 옮긴다

`v0.17.2` 부터 `save_review` 가 저장할 때마다 이것을 한다(`_reelect_removed_reps`).
그런데 **이미 그렇게 되어 있는 개체는 그 시야를 다시 저장해야 고쳐진다** — 사람이
다시 안 열면 영영 그대로다. 그것을 한 번에 맞추는 자리다.

**같은 함수를 부른다.** 여기서 규칙을 다시 적으면 두 자리가 갈리고, 그러면
운영에서 도는 것과 이 스크립트가 다른 얼굴을 고르게 된다.

**멱등이다** — 대표가 성한 개체는 애초에 안 집는다. 다시 돌려도 된다.
"""
import argparse
import os
import sys
from pathlib import Path

import django

# `ops/check_db.py` 의 머리와 같다 — `/srv/DiaRUGA/scripts` 에서 돌 때 Django
# 코드가 어디 있는지는 `DIARUGA_APP` 이 알려 준다(컨테이너 안의 /app).
APP = Path(os.environ.get("DIARUGA_APP")
          or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
sys.path.insert(0, str(APP / "pipeline"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402
from django.db.models import Count                                  # noqa: E402

from viewer import data                                             # noqa: E402
from viewer.models import DiatomObject, ObjectReview                 # noqa: E402


def targets():
    """대표가 지워졌고 **살아 있는 판이 남아 있는** 개체들."""
    out = []
    for obj in (DiatomObject.objects
                .annotate(n=Count("members")).filter(n__gte=2)
                .filter(members__is_rep=True, members__removed=True)
                .distinct().prefetch_related("members__image")):
        live = [m for m in obj.members.all() if not m.removed]
        if live:
            out.append((obj, live))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 옮긴다")
    args = ap.parse_args()

    hits = targets()
    if not hits:
        print("옮길 것이 없다 — 대표가 지운 판인 개체가 없다.")
        return 0

    print(f"대표가 지운 판인 개체 {len(hits)}개")
    for obj, live in hits:
        rep = next(m for m in obj.members.all() if m.is_rep)
        vp = obj.viewpoint
        print(f"  obj#{obj.pk}  {vp.slide.slug} g{vp.idx}  "
              f"멤버 {obj.members.count()} · 산 판 {len(live)}")
        print(f"     지금 얼굴: img{rep.image_id} {rep.mask_key} (지움)")

    if not args.apply:
        print("\n--apply 를 주면 옮긴다. 그 전에 사본을 뜰 것 "
              "(dbrun.sh backup_db.py --note before-reelect).")
        return 0

    with transaction.atomic():
        # **운영이 쓰는 그 함수를 그대로 부른다** — 규칙을 두 자리에 적지 않는다.
        n = data._reelect_removed_reps([o.pk for o, _ in hits])
    print(f"\n옮겼다 — 개체 {n}개")

    left = targets()
    if left:
        print(f"!! 아직 {len(left)}개가 남았다 — 사람이 볼 것")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
