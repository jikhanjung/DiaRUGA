#!/usr/bin/env python3
"""이미 남은 실행들을 묶음(`RunBatch`)으로 묶는다.

    python batch_runs.py --list                        # 지금 묶임 상태
    python batch_runs.py --auto --dry-run              # 묶어 보기
    python batch_runs.py --auto
    python batch_runs.py --label yolo-v1seg --runs 58-64

파이프라인은 **슬라이드 단위로 돈다** — 폴러가 새 슬라이드 하나를 받으면 그것만
처리하기 때문이고, 그 단위가 맞다. 그런데 "전체를 한 번 훑었다" 는 작업은 그
실행 여럿으로 흩어져 남는다. 엔진을 견주려면 그 한 번을 한 덩어리로 볼 수
있어야 한다.

앞으로 돌릴 것은 `segment_diatoms.py --batch <이름>` 이 알아서 묶는다. 이
스크립트는 **이미 흩어져 있는 것을 되돌아가 묶을 때** 쓴다.

## `--auto` 가 쓰는 규칙

`(종류, 백엔드, 날짜)` 가 같으면 한 묶음으로 본다. 실측으로 이 규칙이 지금 자료를
정확히 가른다 — SAM2 는 07-31 하루에, YOLO 는 08-03 하루에 몰려 있다.

**규칙이지 진실이 아니다.** 같은 날 두 번 훑었으면 하나로 뭉쳐진다. 실제로
07-31 의 sam2 묶음에는 첫 시도(#37)와 그것을 밀어낸 재시도(#39)가 함께 들어
있다. 그래서 `--auto` 로 묶은 것에는 메모에 그 사실을 적는다.
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

from viewer.models import Detection, Run, RunBatch                  # noqa: E402


def parse_runs(spec: str) -> list[int]:
    """`58-64,70` 꼴을 번호 목록으로."""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def describe(runs) -> str:
    n_det = Detection.objects.filter(run__in=runs).count()
    slides = sorted({s for s in Detection.objects.filter(run__in=runs)
                     .values_list("viewpoint__slide__slug", flat=True) if s})
    return (f"실행 {len(runs)} · 검출 {n_det} · 슬라이드 {len(slides)}"
            + (f" ({', '.join(slides)[:60]})" if slides else ""))


def show_list():
    print("묶음")
    for b in RunBatch.objects.all():
        rs = list(b.runs.all())
        print(f"  #{b.pk} {b.label:<26} {b.kind:<9} {describe(rs)}")
        if b.note:
            print(f"       {b.note}")
    loose = Run.objects.filter(batch__isnull=True).order_by("started_at")
    if loose.exists():
        print(f"\n묶이지 않은 실행 {loose.count()}건")
        by = defaultdict(list)
        for r in loose:
            by[(r.kind, (r.params or {}).get("backend"),
                str(r.started_at)[:10])].append(r.pk)
        for k in sorted(by, key=lambda k: (k[2], k[0])):
            print(f"  {k[2]}  {k[0]:<9} {str(k[1] or '-'):<6} "
                  f"{len(by[k]):>2}건  {by[k]}")


def main():
    ap = argparse.ArgumentParser(description="실행을 묶음으로 묶는다")
    ap.add_argument("--list", action="store_true", help="지금 상태만 보인다")
    ap.add_argument("--auto", action="store_true",
                    help="(종류, 백엔드, 날짜)가 같으면 한 묶음으로")
    ap.add_argument("--label", help="손으로 묶을 때 쓸 이름")
    ap.add_argument("--runs", help="손으로 묶을 실행 번호 (58-64,70)")
    ap.add_argument("--note", default="")
    ap.add_argument("--kind", default="",
                    help="묶음의 종류. 실행 종류가 섞여 있을 때 정해 준다")
    ap.add_argument("--kinds", default="detect",
                    help="--auto 가 손댈 종류 (쉼표로, 기본 detect)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.list or not (args.auto or args.label):
        show_list()
        return

    if args.label:
        if not args.runs:
            sys.exit("--label 에는 --runs 가 필요하다")
        runs = list(Run.objects.filter(pk__in=parse_runs(args.runs)))
        if not runs:
            sys.exit("그런 실행이 없다")
        # **종류가 섞여도 된다.** 묶음은 "한 번의 작업" 이고, 그 작업이 여러
        # 종류의 실행으로 남을 수 있다. 실제로 SAM2 전수 처리는 07-31 의
        # `detect` 실행들과, 그보다 먼저 계산해 두었던 260729 세 슬라이드를
        # 들여온 07-30 의 `ingest` 실행(#19)으로 나뉘어 있다. 둘을 갈라 두면
        # "SAM2 로 전체를 한 번 돌렸다" 를 한 화면에 못 본다.
        kinds = {r.kind for r in runs}
        kind = args.kind or (kinds.pop() if len(kinds) == 1 else "")
        if not kind:
            sys.exit(f"종류가 섞여 있다: {sorted(kinds)} — "
                     f"묶음의 종류를 --kind 로 정할 것")
        if len({r.kind for r in runs}) > 1:
            print(f"  종류가 섞여 있다: {sorted({r.kind for r in runs})} "
                  f"→ 묶음은 '{kind}' 로 둔다")
        print(f"'{args.label}' ← {describe(runs)}")
        already = [r.pk for r in runs if r.batch_id]
        if already:
            print(f"  이미 묶여 있는 것 {already} — 옮긴다")
        if args.dry_run:
            print("\n--dry-run 이라 쓰지 않았다")
            return
        with transaction.atomic():
            b, _ = RunBatch.objects.get_or_create(
                kind=kind, label=args.label, defaults={"note": args.note})
            if args.note and b.note != args.note:
                b.note = args.note
                b.save(update_fields=["note"])
            Run.objects.filter(pk__in=[r.pk for r in runs]).update(batch=b)
        print(f"묶었다 (#{b.pk})")
        return

    # --auto
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    groups = defaultdict(list)
    for r in Run.objects.filter(kind__in=kinds, batch__isnull=True) \
                        .order_by("started_at"):
        # 검출을 하나도 안 남긴 실행은 묶지 않는다 — 죽은 시도이고, 묶으면
        # 묶음의 개수가 실제로 처리한 양과 어긋난다.
        if not Detection.objects.filter(run=r).exists():
            continue
        b = (r.params or {}).get("backend") or "-"
        groups[(r.kind, b, str(r.started_at)[:10])].append(r)

    if not groups:
        print("묶을 것이 없다")
        return

    plan = []
    for (kind, backend, day), runs in sorted(groups.items(),
                                             key=lambda kv: kv[0][2]):
        label = f"{backend}-{day}" if backend != "-" else f"{kind}-{day}"
        n_first = sum(1 for r in runs
                      if Detection.objects.filter(run=r, is_current=True).exists())
        note = (f"{day} 의 {backend} {kind} 실행을 (종류·백엔드·날짜)로 묶은 것. "
                f"같은 날 두 번 훑었다면 한 덩어리로 뭉쳐 있다 — "
                f"{len(runs)}건 중 현재 검출을 가진 것은 {n_first}건.")
        plan.append((kind, label, note, runs))
        print(f"{label:<20} {describe(runs)}")
        print(f"   실행 {[r.pk for r in runs]}")

    if args.dry_run:
        print("\n--dry-run 이라 쓰지 않았다")
        return

    with transaction.atomic():
        for kind, label, note, runs in plan:
            b, _ = RunBatch.objects.get_or_create(
                kind=kind, label=label, defaults={"note": note})
            Run.objects.filter(pk__in=[r.pk for r in runs]).update(batch=b)
    print(f"\n{len(plan)}개 묶음으로 묶었다")


if __name__ == "__main__":
    main()
