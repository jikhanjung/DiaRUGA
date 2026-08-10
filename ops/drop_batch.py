#!/usr/bin/env python3
"""검출 묶음(`RunBatch`)을 통째로 들어낸다. **견주기용으로 쌓아 둔 것만.**

엔진을 견주려고 `--keep-current` 로 나란히 쌓은 검출은 조건이 바뀌면 값이
없어진다 — 알고리즘을 고친 뒤의 것과 고치기 전의 것이 한 묶음에 섞여 있으면
"어느 쪽 숫자인가" 를 말할 수 없다. 그때 묶음을 지우고 다시 뽑는다.

지우는 것: `Candidate` → `Detection` → `Run` → `RunBatch`. 묶음이 남긴 것 전부다.
**`Run` 까지 지운다** — 검출이 사라진 실행만 남으면 관리 화면의 묶음 목록에 빈 묶음이
뜨고, 이력으로도 "무엇을 돌렸는가" 를 못 말한다.

## 막아 둔 것 둘

- **뷰어가 보여줄 검출이 하나라도 있으면 거부한다.** 그것은 뷰어가 보고
  사람이 교정을 붙인 검출이다. 무엇을 보여줄지는 `RunBatch.for_review` 가
  정한다(P10) — 견주기용으로 쌓은 묶음은 그 깃발이 꺼져 있다
  이므로, 하나라도 켜져 있으면 그 묶음은 "쌓아 둔 것" 이 아니다
- **그 개체를 가리키는 교정이 있으면 거부한다.** `ObjectReview.candidate` 는
  `SET_NULL` 이라 교정 행 자체는 살아남지만(진짜 키는 `mask_key` 다), 바인딩이
  조용히 끊긴다. 끊어도 되는지는 사람이 정할 일이라 `--force` 로만 넘어간다

둘 다 지금까지는 걸린 적이 없다. 걸린다면 그 묶음은 지울 것이 아니다.

쓰임:

    python drop_batch.py --list
    python drop_batch.py --batch yolo-1차 --batch yolo-2차          # 미리보기
    python drop_batch.py --batch yolo-1차 --batch yolo-2차 --apply

**큰 작업이다. 앞에 사본을 뜬다** — `dbrun.sh backup_db.py --note before-...`.
DB 를 만지므로 `deploy/host/dbrun.sh` 로 들어간다 (HANDOFF 9.2).
"""
import argparse
import os
import sys
from pathlib import Path

import django

# group_focus_series.py 와 같은 규칙 — 컨테이너 안에서는 /app 의 Django 를 쓴다.
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

from viewer.models import (Candidate, Detection, ObjectReview,      # noqa: E402
                           Run, RunBatch)


def survey(batches):
    """지우면 무엇이 사라지는가. **DB 를 건드리지 않는다.**"""
    dets = Detection.objects.filter(run__batch__in=batches)
    cands = Candidate.objects.filter(detection__in=dets)
    return {
        "detections": dets.count(),
        "candidates": cands.count(),
        "runs": Run.objects.filter(batch__in=batches).count(),
        # 아래 둘이 0 이 아니면 지울 묶음이 아니다
        # **뷰어가 보고 있는 것** — P10 뒤로는 `for_review` 가 정한다.
        # `is_current` 만 세면 정규화 뒤에 모든 묶음이 걸려 아무것도 못 지운다.
        "current": dets.reviewing().count(),
        "bound_reviews": ObjectReview.objects.filter(candidate__in=cands).count(),
    }


def main():
    ap = argparse.ArgumentParser(description="검출 묶음을 통째로 들어낸다")
    ap.add_argument("--batch", action="append", default=[], metavar="이름",
                    help="RunBatch.label. 여러 번 줄 수 있다")
    ap.add_argument("--list", action="store_true", help="묶음 목록만 보인다")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 지운다 (기본은 미리보기)")
    ap.add_argument("--force", action="store_true",
                    help="교정 바인딩이 끊기는 것을 알고도 진행한다")
    args = ap.parse_args()

    if args.list or not args.batch:
        print(f"{'묶음':16s}{'종류':8s}{'실행':>5}{'검출':>7}{'현재':>6}")
        for b in RunBatch.objects.all().order_by("started_at"):
            d = Detection.objects.filter(run__batch=b)
            print(f"{b.label:16s}{b.kind:8s}"
                  f"{Run.objects.filter(batch=b).count():5d}{d.count():7d}"
                  f"{d.reviewing().count():6d}")
        if not args.batch:
            raise SystemExit("\n--batch <이름> 을 줄 것")
        return

    batches = list(RunBatch.objects.filter(label__in=args.batch))
    found = {b.label for b in batches}
    missing = [n for n in args.batch if n not in found]
    if missing:
        raise SystemExit(f"그런 묶음이 없다: {', '.join(missing)}  (--list 로 볼 것)")

    s = survey(batches)
    print(f"지울 묶음 {len(batches)}개 — {', '.join(sorted(found))}")
    print(f"  Candidate {s['candidates']:,} · Detection {s['detections']:,} · "
          f"Run {s['runs']} · RunBatch {len(batches)}")

    # 안전 고리 둘. 여기서 막는 것은 "예외가 안 나고 그냥 틀린 상태" 다.
    stop = []
    if s["current"]:
        stop.append(f"뷰어가 보고 있는 검출이 {s['current']}개 있다 — "
                    f"보고 있는 검출이다. 견주기용으로 쌓은 묶음이 아니다")
    if s["bound_reviews"] and not args.force:
        stop.append(f"이 개체를 가리키는 교정이 {s['bound_reviews']}건 있다 — "
                    f"행은 남지만(mask_key 가 진짜 키다) 바인딩이 끊긴다. "
                    f"알고도 진행하려면 --force")
    if stop:
        print()
        for w in stop:
            print(f"  ** {w}", file=sys.stderr)
        raise SystemExit("거부한다 — 아무것도 지우지 않았다")

    print("  (뷰어가 보는 검출 0개 · 딸린 교정 0건 — 지워도 검토 화면은 그대로다)"
          if not s["bound_reviews"] else "")

    if not args.apply:
        print("\n미리보기다 — 지우려면 --apply")
        print("  그 전에 사본을 뜰 것: "
              "deploy/host/dbrun.sh backup_db.py --note before-drop-batch")
        return

    # 한 트랜잭션이다. 절반만 지워지면 "검출은 없는데 실행은 있는" 묶음이 남고,
    # 그 상태는 화면에서 빈 묶음과 구별되지 않는다.
    with transaction.atomic():
        # Candidate 를 먼저 지운다. Detection 부터 지우면 Django 의 수집기가
        # 74,000 행을 한 번에 끌어올린다 — 나눠서 지우면 그 봉우리가 없다.
        n_c = Candidate.objects.filter(
            detection__run__batch__in=batches).delete()[0]
        n_d = Detection.objects.filter(run__batch__in=batches).delete()[0]
        n_r = Run.objects.filter(batch__in=batches).delete()[0]
        n_b = RunBatch.objects.filter(pk__in=[b.pk for b in batches]).delete()[0]

    print(f"\n지웠다 — Candidate {n_c:,} · Detection {n_d:,} · "
          f"Run {n_r} · RunBatch {n_b}")
    print(f"  남은 검출 {Detection.objects.count():,} · "
          f"현재 {Detection.objects.reviewing().count():,} · "
          f"교정 {ObjectReview.objects.count():,}")


if __name__ == "__main__":
    main()
