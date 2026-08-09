#!/usr/bin/env python3
"""검토 진척을 슬라이드별로 보여준다 — 2차 검토(직접 그리기 포함)의 진척계.

    python review_progress.py

권역별로 묶어 완료/전체와 직접 그린 개체 수를 센다. 남극은 2026-08-09 에
완료 표시를 걷고 다시 보는 중이라(reset_review_done.py), 여기 붙는 완료가
곧 2차 검토다. 직접 그린 개체는 batch IS NULL 로 저장부터 구분돼 있다(P09).
"""
import os
import sys
from pathlib import Path

import django

# 이 스크립트는 저장소 밖(/srv/DiaRUGA/scripts)에 복사해 두고 컨테이너 안에서
# 돌릴 수도 있다. 그때 Django 코드가 어디 있는지는 DIARUGA_APP 이 알려 준다.
APP = Path(os.environ.get("DIARUGA_APP") or Path(__file__).resolve().parent)
sys.path.insert(0, str(APP / "web"))
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db.models import Count, Q                                # noqa: E402

from viewer.models import ObjectReview, Slide, ViewpointReview        # noqa: E402

AREA_LABEL = {"ant": "남극 (2차 검토 — 직접 그리기 포함, 08-09 재시작)",
              "kr": "한국"}


def main():
    slides = (Slide.objects
              .select_related("sample__locality__site")
              .annotate(vps=Count("viewpoints", distinct=True))
              .order_by("sample__locality__site__area", "slug"))

    done_by_slide = dict(
        ViewpointReview.objects.filter(done=True, batch__for_review=True)
        .values_list("viewpoint__slide")
        .annotate(n=Count("id")).values_list("viewpoint__slide", "n"))

    drawn_by_slide = dict(
        ObjectReview.objects.filter(batch__isnull=True)
        .values_list("viewpoint__slide")
        .annotate(n=Count("id")).values_list("viewpoint__slide", "n"))

    area = None
    tot = {"vps": 0, "done": 0, "drawn": 0}
    for s in slides:
        a = s.sample.locality.site.area if s.sample else "?"
        if a != area:
            area = a
            print(f"\n{AREA_LABEL.get(a, a)}")
            print(f"  {'슬라이드':30s} {'검토':>9s} {'그린 개체':>8s}")
        done = done_by_slide.get(s.id, 0)
        drawn = drawn_by_slide.get(s.id, 0)
        mark = "완료" if done == s.vps and s.vps else f"{done}/{s.vps}"
        print(f"  {s.slug:32s} {mark:>8s} {drawn or '-':>8}")
        tot["vps"] += s.vps
        tot["done"] += done
        tot["drawn"] += drawn

    print(f"\n전체 검토 {tot['done']}/{tot['vps']} · 직접 그린 개체 {tot['drawn']}건")


if __name__ == "__main__":
    main()
