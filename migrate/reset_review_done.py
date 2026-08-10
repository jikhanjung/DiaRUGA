#!/usr/bin/env python3
"""검토 완료 표시를 걷는다 — 2차 검토(직접 그리는 마스크 포함)를 시작하기 위해.

    python reset_review_done.py --area ant             # 무엇이 걷히는지만 보여준다
    python reset_review_done.py --area ant --apply     # 실제로 걷는다
    python reset_review_done.py --slide rs23 --apply   # 슬라이드 하나만

교정(ObjectReview)과 시야 코멘트(note)는 건드리지 않는다 — 검토 대상 묶음
(for_review)에 붙은 완료 체크(ViewpointReview.done)만 False 로 돌린다.
걷고 나면 목록의 검토 수와 "다음 미검토" 가 2차 검토의 진척계가 된다.

2026-08-09, 사용자 요청 — 직접 그리는 마스크(P09)가 생겨 남극 시료를 다시
보기로 했다. 회차를 따로 구분하지는 않는다(사용자 판단).
"""
import argparse
import os
import sys
from pathlib import Path

import django

# 이 스크립트는 저장소 밖(/srv/DiaRUGA/scripts)에 복사해 두고 컨테이너 안에서
# 돌릴 수도 있다. 그때 Django 코드가 어디 있는지는 DIARUGA_APP 이 알려 준다 —
# 이미지 안의 /app 이고, 뷰어 컨테이너가 쓰는 바로 그 코드다.
# **저장소에서는 한 단계 위가 뿌리다** (스크립트가 pipeline/·ops/·migrate/
# 안에 있다). `/srv/DiaRUGA/scripts` 처럼 저장소 밖에서 돌 때는 그 짐작이
# 안 맞으므로 `DIARUGA_APP` 이 알려 준다 — 컨테이너에서는 이미지 안의 /app 이다.
APP = Path(os.environ.get("DIARUGA_APP")
          or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402

from viewer.models import ViewpointReview                            # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--area", choices=["ant", "kr"], help="권역째로 (ant=남극, kr=한국)")
    g.add_argument("--slide", help="슬라이드 slug 하나만")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 걷는다 (없으면 보여주기만)")
    args = ap.parse_args()

    qs = ViewpointReview.objects.filter(done=True, batch__for_review=True)
    if args.area:
        qs = qs.filter(viewpoint__slide__sample__locality__site__area=args.area)
    else:
        qs = qs.filter(viewpoint__slide__slug=args.slide)
        if not qs.exists():
            sys.exit(f"완료 표시가 없다: --slide {args.slide} (slug 를 확인할 것)")

    per_slide = {}
    for slug in qs.values_list("viewpoint__slide__slug", flat=True):
        per_slide[slug] = per_slide.get(slug, 0) + 1
    for slug in sorted(per_slide):
        print(f"  {slug:32s} {per_slide[slug]:4d}")
    total = sum(per_slide.values())
    print(f"  {'합계':32s} {total:4d}")

    if not args.apply:
        print("\n보여주기만 했다. 걷으려면 --apply 를 줄 것.")
        return

    with transaction.atomic():
        changed = qs.update(done=False)
    print(f"\n완료 표시 {changed}건을 걷었다. 교정과 코멘트는 그대로다.")


if __name__ == "__main__":
    main()
