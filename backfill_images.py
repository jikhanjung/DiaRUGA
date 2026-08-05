#!/usr/bin/env python3
"""`Image` 를 채우고 검출·교정을 거기에 맨다 (P06 3단계).

    deploy/host/dbsync.sh backfill_images.py     # 저장소 -> /srv
    deploy/host/dbrun.sh  backfill_images.py     # 세어만 본다 (기본)
    deploy/host/dbrun.sh  backfill_images.py --apply
    deploy/host/dbrun.sh  backfill_images.py --verify   # 채워진 뒤 앞뒤가 맞는가

**넓히는 중이라 아무것도 지우지 않는다.** `Detection.target`·`frame` 과
`Stack.focused_path` 는 그대로 두고 `image` 만 채운다 — 판을 되돌리면 옛 코드가
그대로 돈다(P06 §1). 조이는 것은 5단계다.

## 무엇을 만드는가

| kind | 어디서 | 수 |
|---|---|---|
| `frame` | `Frame.path` | 1,318 |
| `stack` | `Stack.focused_path` | 317 |
| `depth` | `Stack.depth_path` | 317 |

열쇠는 `path` 다(파일 하나에 행 하나). 그래서 **몇 번을 돌려도 같다** —
`get_or_create(path=…)` 이고, 이미 맨 것은 건너뛴다.

## 교정은 어느 이미지에 매는가

**그 시야의 현재 검출이 보고 있던 이미지**다. 교정은 사람이 화면을 보고 만든
것이고, 화면이 그리는 것이 현재 검출(`is_current`)이기 때문이다. 실측으로 교정이
있는 시야는 전부 현재 검출이 하나씩 있다(둘인 곳도, 없는 곳도 없다).

**여기서 `image` 를 채우는 것이 곧 "어느 이미지를 보고 한 판단인가" 를 처음으로
기록하는 일이다.** 지금까지는 시야마다 볼 이미지가 한 장이라 물을 필요가 없었다.

## 돌리기 전에

- **`backup_db.py --note before-image-backfill`** — 교정 6,700여 건을 만진다
- **폴러를 세운다.** 1분마다 도는데, 도중에 새 검출이 들어오면 그것만 `image` 가
  빈 채 남는다. 멱등이라 다시 돌리면 되지만 "왜 하나가 비었나" 를 뒤에 가서
  묻게 된다
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import django

# 이 스크립트는 저장소 밖(`/srv/DiaRUGA/scripts`)에 복사해 두고 컨테이너 안에서
# 돈다. 그때 Django 코드가 어디 있는지는 `DIARUGA_APP` 이 알려 준다 — 이미지 안의
# `/app` 이고, 뷰어 컨테이너가 쓰는 바로 그 코드다. 저장소에서 그냥 돌리면 자기
# 옆의 `web/` 을 본다. `check_db.py` 와 같은 머리다.
APP = Path(os.environ.get("DIARUGA_APP") or Path(__file__).resolve().parent)
sys.path.insert(0, str(APP / "web"))
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                       # noqa: E402
from viewer.models import (Detection, Frame, Image,      # noqa: E402
                           ObjectReview, Slide, Stack)


def plan():
    """무엇을 만들고 무엇을 맬지. 쓰지 않는다."""
    want = []          # (path, kind, viewpoint_id, frame_id, stack_id, w, h)
    for f in Frame.objects.all().only("id", "path", "viewpoint_id",
                                      "width", "height"):
        want.append((f.path, "frame", f.viewpoint_id, f.id, None,
                     f.width, f.height))
    for s in Stack.objects.all().only("id", "viewpoint_id", "focused_path",
                                      "depth_path"):
        want.append((s.focused_path, "stack", s.viewpoint_id, None, s.id,
                     None, None))
        if s.depth_path:
            want.append((s.depth_path, "depth", s.viewpoint_id, None, s.id,
                         None, None))
    return want


def make_images(want, apply_it):
    """`Image` 행을 만든다. `path` 가 열쇠라 몇 번을 돌려도 같다.

    돌려주는 `by_path` 는 **만들 것까지 포함한다**(안 쓸 때는 id 가 `None`).
    그래야 세어만 볼 때도 "몇 개가 매질 것인가" 가 참말이 된다 — 있는 것만
    돌려주면 첫 실행에서 모든 검출이 "이미지를 못 찾았다" 로 나온다.
    """
    have = dict(Image.objects.values_list("path", "id"))
    new = [w for w in want if w[0] not in have]
    if apply_it and new:
        Image.objects.bulk_create([
            Image(path=p, kind=k, viewpoint_id=vp, frame_id=fid,
                  stack_id=sid, width=w, height=h)
            for p, k, vp, fid, sid, w, h in new
        ], batch_size=500)
        have = dict(Image.objects.values_list("path", "id"))
    else:
        have.update({w[0]: None for w in new})
    return have, len(new)


def link_detections(by_path, apply_it):
    """검출을 이미지에 맨다 — `image_path` 로 찾는다.

    **`target`·`frame` 을 근거로 쓰지 않는다.** 그 둘이 없애려는 대상이고,
    `image_path` 는 검출이 실제로 연 파일이라 더 직접적이다.
    """
    todo, missing = [], []
    for d in Detection.objects.filter(image__isnull=True).only("id", "image_path"):
        if d.image_path in by_path:
            todo.append((d.id, by_path[d.image_path]))
        else:
            missing.append(d.image_path)
    if apply_it:
        for did, iid in todo:
            Detection.objects.filter(pk=did).update(image_id=iid)
    return len(todo), missing


def link_reviews(by_path, apply_it):
    """교정을 **그 시야의 현재 검출이 보던 이미지**에 맨다.

    검출이 아직 안 매여 있어도(세어만 볼 때) 답이 나와야 하므로 현재 검출의
    `image_path` 를 거쳐 찾는다 — `image_id` 를 거치면 첫 실행에서 전부
    고아로 보인다.
    """
    cur = {}
    for d in (Detection.objects.filter(is_current=True)
              .only("viewpoint_id", "image_path")):
        if d.image_path in by_path:
            cur[d.viewpoint_id] = by_path[d.image_path]
    todo, orphan = [], []
    for o in (ObjectReview.objects.filter(image__isnull=True)
              .only("id", "viewpoint_id")):
        if o.viewpoint_id in cur:
            todo.append((o.id, cur[o.viewpoint_id]))
        else:
            orphan.append(o.viewpoint_id)
    if apply_it:
        for oid, iid in todo:
            ObjectReview.objects.filter(pk=oid).update(image_id=iid)
    return len(todo), orphan


def verify():
    """채운 뒤 앞뒤가 맞는가. **`check_db.py` 와 같은 성격이다** — 예외가 안 나고
    그냥 틀린 상태를 잡는다."""
    bad = 0

    def report(label, n, total, extra=""):
        nonlocal bad
        ok = n == 0
        bad += 0 if ok else 1
        mark = "OK" if ok else f"!! {n}"
        print(f"   {label:44} {mark}{extra}")

    print("=== Image 백필 검증 ===")
    print(f"   이미지 {Image.objects.count():,} "
          f"(프레임 {Image.objects.filter(kind='frame').count():,} · "
          f"합성본 {Image.objects.filter(kind='stack').count():,} · "
          f"깊이맵 {Image.objects.filter(kind='depth').count():,})")
    report("image 가 빈 검출", Detection.objects.filter(image__isnull=True).count(),
           Detection.objects.count())
    report("image 가 빈 교정", ObjectReview.objects.filter(image__isnull=True).count(),
           ObjectReview.objects.count())
    # 옛 칸과 새 칸이 같은 것을 가리키는가 — 조이기 전에 이것이 맞아야 한다
    n = sum(1 for d in Detection.objects.filter(image__isnull=False)
            .select_related("image").only("image_path", "image__path")
            if d.image.path != d.image_path)
    report("image.path 와 image_path 가 어긋난 검출", n, 0)
    n = sum(1 for d in Detection.objects.filter(image__isnull=False)
            .select_related("image").only("target", "image__kind")
            if (d.target == "frame") != (d.image.kind == "frame"))
    report("target 과 image.kind 가 어긋난 검출", n, 0)
    n = Detection.objects.filter(image__kind="depth").count()
    report("깊이맵에 붙은 검출", n, 0)
    n = sum(1 for o in ObjectReview.objects.filter(image__isnull=False)
            .select_related("image").only("viewpoint_id", "image__viewpoint_id")
            if o.image.viewpoint_id != o.viewpoint_id)
    report("교정과 이미지의 시야가 어긋난 것", n, 0)
    # 5단계에서 열쇠가 될 조합이 지금 이미 유일한가
    seen = Counter(ObjectReview.objects.filter(image__isnull=False)
                   .values_list("image_id", "mask_key"))
    report("(image, mask_key) 가 겹치는 교정",
           sum(c - 1 for c in seen.values() if c > 1), 0,
           "  ← 5단계 유일 제약이 설 수 있는가")
    print("앞뒤가 맞는다." if not bad else f"어긋난 검사 {bad}개 — 위를 볼 것")
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(description="Image 를 채우고 검출·교정을 맨다")
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다")
    ap.add_argument("--verify", action="store_true", help="검증만 한다")
    ap.add_argument("--force", action="store_true",
                    help="처리 중인 슬라이드가 있어도 진행한다")
    args = ap.parse_args()

    if args.verify:
        return verify()

    # 파이프라인이 도는 중이면 새 검출이 `image` 없이 들어온다. 멱등이라
    # 되돌릴 일은 아니지만, 반쯤 채워진 상태를 만들 이유가 없다.
    busy = list(Slide.objects.exclude(state="done").values_list("slug", flat=True))
    if busy and not args.force:
        print(f"처리 중인 슬라이드가 있다: {', '.join(busy[:5])}")
        print("  폴러를 세우고 다시 돌린다 (--force 로 넘길 수 있다)")
        return 1

    want = plan()
    kinds = Counter(k for _, k, *_ in want)
    print(f"이미지가 될 것 {len(want):,} "
          f"(프레임 {kinds['frame']:,} · 합성본 {kinds['stack']:,} · "
          f"깊이맵 {kinds['depth']:,})")

    with transaction.atomic():
        by_path, n_new = make_images(want, args.apply)
        n_det, missing = link_detections(by_path, args.apply)
        n_rev, orphan = link_reviews(by_path, args.apply)

        print(f"  새 이미지        {n_new:,}")
        print(f"  맬 검출          {n_det:,} / {Detection.objects.count():,}")
        print(f"  맬 교정          {n_rev:,} / {ObjectReview.objects.count():,}")
        if missing:
            print(f"  !! 이미지를 못 찾은 검출 {len(missing)}개: {missing[:3]}")
        if orphan:
            print(f"  !! 현재 검출이 없어 못 맨 교정의 시야 {len(set(orphan))}개")
        if not args.apply:
            print("\n세어만 봤다. 실제로 쓰려면 --apply")
            transaction.set_rollback(True)
            return 0

    print("\n채웠다. 이어서:  backfill_images.py --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
