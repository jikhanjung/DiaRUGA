#!/usr/bin/env python
"""북평분지의 층을 말과 맞춘다 — 지역 `BP` · 지점 `BP09` · 시료 `0901`.

**한 번 쓰고 버리는 스크립트다.** 남겨 두는 이유는 무엇을 왜 바꿨는지가
`--dry-run` 으로 다시 읽히기 때문이다.

두 가지를 고친다.

1. **지역 코드 `BP09` → `BP`.** 지역 이름 자리에 노두 코드가 앉아 있었다.
   육상은 폴더에 지역이 없어서(`BP09-0901` 은 `<지점>-<시료>` 다) 파이프라인이
   앞 토막을 지역으로 읽은 결과다. `BP10`·`BP11` 노두가 들어오면 같은 지역
   아래로 모여야 한다.
2. **`BP09-0901 (1)` 을 지점 `BP09` 에 붙인다.** 관찰은 같은 시료이므로 같은
   지점에 서야 한다. 앞으로 들어오는 것은 `group_focus_series.sample_fields()`
   가 물려받게 했고, 이미 들어와 있는 이 한 장만 손으로 옮긴다.

지도는 이 이름을 안 본다 — `korea.APPROX_SITES` 가 비어 있고 좌표가 `Site`
에 직접 들어 있다(37.28 · 129.06). 코드를 바꿔도 마커는 그대로다.

    deploy/host/dbsync.sh fix_bp09.py
    deploy/host/dbrun.sh  fix_bp09.py --dry-run
    deploy/host/dbrun.sh  fix_bp09.py --apply
"""
import argparse
import os
import re
import sys
from pathlib import Path

# 컨테이너 안에서는 코드가 `/app` 이다 — 자기 옆의 `web/` 을 보게 짜면
# `No module named 'diarugaweb'` 로 죽는다 (check_db.py 와 같은 머리).
APP = Path(os.environ.get("DIARUGA_APP", Path(__file__).resolve().parent))
sys.path.insert(0, str(APP / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")

import django                                                       # noqa: E402
django.setup()

from django.db import transaction                                   # noqa: E402
from viewer.models import Core, Site, Slide                         # noqa: E402

SITE_OLD, SITE_NEW = "BP09", "BP"
LOC_CODE = "BP09"

# 관찰 접미사. **`Slide.sibling_observations()` 를 부르지 않고 여기서 다시
# 푼다** — 그 메서드는 아직 배포 안 된 판에 있고, 이 스크립트는 지금 도는
# 컨테이너(옛 `/app`) 안에서 돌아야 한다. 고칠 코드가 도는지부터 확인할 것.
OBS_SUFFIX = re.compile(r"\s*\((\d+)\)\s*$")


def base_name(name: str) -> str:
    return OBS_SUFFIX.sub("", name or "").strip()


def sibling_with_core(slide):
    """같은 시료의 다른 관찰 중 지점이 붙어 있는 것. 번호가 작은 쪽을 따른다."""
    base = base_name(slide.name)
    if not base:
        return None
    for s in (Slide.objects.filter(name__startswith=base)
              .exclude(pk=slide.pk).exclude(core__isnull=True)
              .select_related("core").order_by("obs_no", "id")):
        if base_name(s.name) == base:
            return s
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="바꿀 것만 보인다")
    g.add_argument("--apply", action="store_true", help="실제로 바꾼다")
    args = ap.parse_args()

    plan, warn = [], []

    site = Site.objects.filter(code=SITE_OLD).first()
    if site is None:
        warn.append(f"지역 {SITE_OLD} 이 없다 — 이미 고쳤나?")
    elif Site.objects.filter(code=SITE_NEW).exists():
        warn.append(f"지역 {SITE_NEW} 이 이미 있다 — 손으로 볼 것")
        site = None
    else:
        plan.append(f"지역 {site.code} → {SITE_NEW}  (이름 {site.name!r} · "
                    f"권역 {site.area} · 좌표 {site.lat},{site.lon} 는 그대로)")

    loc = Core.objects.filter(code=LOC_CODE).first()
    if loc is None:
        warn.append(f"지점 {LOC_CODE} 이 없다")
    orphans = list(Slide.objects.filter(core__isnull=True).order_by("name"))
    attach = []
    for sl in orphans:
        # 같은 시료의 다른 관찰이 이미 붙어 있는 지점을 따른다 — 화면의
        # `기존 코어에 붙이기` 가 미리 골라 주는 것과 같은 근거다
        sib = sibling_with_core(sl)
        if sib:
            attach.append((sl, sib))
            plan.append(f"{sl.name!r} → 지점 {sib.core.code} "
                        f"(같은 시료 {sib.name!r} 이 거기 있다)")
        else:
            warn.append(f"{sl.name!r} 은 지점이 없고 물려받을 관찰도 없다")

    print("== 바꿀 것 ==")
    for p in plan:
        print("  " + p)
    if not plan:
        print("  (없다)")
    if warn:
        print("== 봐야 할 것 ==")
        for w in warn:
            print("  " + w)

    if args.dry_run:
        print("\n--dry-run 이라 아무것도 안 썼다")
        return 0

    with transaction.atomic():
        if site is not None:
            site.code = SITE_NEW
            site.save(update_fields=["code"])
        for sl, sib in attach:
            sl.core = sib.core
            sl.save(update_fields=["core"])
    print(f"\n적용했다 — 지역 {1 if site else 0}건 · 붙이기 {len(attach)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
