#!/usr/bin/env python3
"""한 묶음 안에서 같은 이미지에 겹쳐 쌓인 검출을 정리한다.

    python prune_detections.py                  # 세어만 본다 (기본)
    python prune_detections.py --apply
    python prune_detections.py --apply --batch yolo-2차

검출은 덮어쓰지 않고 쌓는 것이 원칙이다 — 사람의 교정이 옛 검출을 통해 되짚을
수 있어야 하기 때문이다. 그런데 **같은 묶음 안에서 같은 이미지에 둘씩 쌓인 것은
그런 기록이 아니다.** 다음 두 경로로 생긴 찌꺼기다:

- 빠진 프레임만 다시 돌려도 `--keep-current` 는 이미 끝난 프레임까지 다시 쌓는다
- 첫 시도가 도중에 죽어 다시 돌린 것이 그대로 남았다 (SAM2 #37 → #39)

둘 다 "같은 엔진이 같은 이미지를 같은 설정으로 본 것" 이라 나중 것이 앞의 것을
온전히 대신한다. 남겨 두면 묶음이 실제보다 커 보이고, 화면이 어느 쪽을 그릴지
고르는 규칙에 기대게 된다(`data._engine_pick`).

**묶음을 넘어서는 지우지 않는다.** 서로 다른 엔진이 같은 이미지를 본 것을 나란히
두는 것이 검출 화면의 목적 전부다.

## 무엇을 남기는가

`data._engine_pick` 과 **같은 규칙**이다 — 현재 검출(`is_current`)이 있으면 그것,
없으면 번호가 큰 것. 화면이 그리는 그 하나를 남기고 나머지를 지운다.

현재 검출은 어떤 경우에도 지우지 않는다. 한 이미지에 현재 검출이 둘이면 손대지
않고 알린다 — 그것은 찌꺼기가 아니라 고장이라 사람이 봐야 한다.

교정(`ObjectReview`)은 `mask_key` 로 붙어 있어 `Candidate` 가 지워져도 남는다.
그래도 지우는 것은 지우는 것이다 — `--apply` 전에 `backup_db.py` 를 돌릴 것.
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

import django

# 이 스크립트는 저장소 밖(/srv/DiaRUGA/scripts)에 복사해 두고 컨테이너 안에서
# 돌릴 수도 있다. 그때 Django 코드가 어디 있는지는 DIARUGA_APP 이 알려 준다 —
# 이미지 안의 /app 이고, 뷰어 컨테이너가 쓰는 바로 그 코드다. 저장소에서 그냥
# 돌리면 예전처럼 자기 옆의 web/ 을 본다.
APP = Path(os.environ.get("DIARUGA_APP") or Path(__file__).resolve().parent)
sys.path.insert(0, str(APP / "web"))
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402
from django.db.models import Count                                  # noqa: E402

from viewer.models import Candidate, Detection                      # noqa: E402


def plan(batch_label: str = ""):
    """(지울 것, 손대지 않을 고장) 을 낸다."""
    qs = (Detection.objects.filter(run__isnull=False)
          .select_related("run__batch", "viewpoint__slide"))
    if batch_label:
        qs = qs.filter(run__batch__label=batch_label)

    # 같은 묶음 · 같은 시야 · 같은 이미지. 묶이지 않은 실행은 자기 자신이 묶음이다.
    groups = defaultdict(list)
    for d in qs:
        bkey = ("b", d.run.batch_id) if d.run.batch_id else ("r", d.run_id)
        groups[(bkey, d.viewpoint_id, d.target, d.frame_id)].append(d)

    doomed, conflicts = [], []
    for key, dets in groups.items():
        if len(dets) < 2:
            continue
        cur = [d for d in dets if d.is_current]
        if len(cur) > 1:
            conflicts.append((key, dets))
            continue
        keep = max(dets, key=lambda d: (d.is_current, d.pk))
        doomed.extend(d for d in dets if d.pk != keep.pk)
    return doomed, conflicts


def label_of(d):
    return (d.run.batch.label if d.run.batch_id else f"실행 #{d.run_id}")


def main():
    ap = argparse.ArgumentParser(description="묶음 안의 겹친 검출을 정리한다")
    ap.add_argument("--apply", action="store_true", help="실제로 지운다")
    ap.add_argument("--batch", default="", help="이 묶음만")
    args = ap.parse_args()

    doomed, conflicts = plan(args.batch)

    if conflicts:
        print(f"현재 검출이 둘 이상인 이미지 {len(conflicts)}건 — 손대지 않았다")
        for (bkey, vp, target, fid), dets in conflicts[:10]:
            print(f"  시야 {vp} {target} 프레임 {fid}: "
                  f"{[d.pk for d in dets]}")
        print()

    if not doomed:
        print("겹친 검출이 없다")
        return

    by_batch = defaultdict(list)
    for d in doomed:
        by_batch[label_of(d)].append(d)

    n_cand = Candidate.objects.filter(detection__in=doomed).count()
    print(f"지울 검출 {len(doomed)}건 · 딸린 후보 {n_cand}건")
    for lab, ds in sorted(by_batch.items()):
        slides = sorted({d.viewpoint.slide.slug for d in ds if d.viewpoint})
        print(f"  {lab:<12} {len(ds):>4}건  슬라이드 {len(slides)}개")

    if not args.apply:
        print("\n--apply 를 주지 않아 지우지 않았다")
        return

    with transaction.atomic():
        # 지울 것을 가리키던 `superseded_by` 는 FK 가 SET_NULL 이라 알아서 풀린다.
        # 현재 검출이 딸려 가지 않는 것이 여기 달려 있다.
        n, per = Detection.objects.filter(
            pk__in=[d.pk for d in doomed]).delete()
    print(f"\n지웠다 — 행 {n}건 {dict(per)}")


if __name__ == "__main__":
    main()
