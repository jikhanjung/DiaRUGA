#!/usr/bin/env python3
"""판정 문턱만 바꿔 다시 거른다. SAM2 를 다시 돌리지 않는다.

    python refilter.py --dry-run                        # 지금 문턱 그대로 (변화 확인)
    python refilter.py --round-texture-min 2000 --dry-run
    python refilter.py --round-texture-min 2000         # 적용
    python refilter.py --slide rs23 --texture-min 3000

`segment_diatoms.py` 가 형태·텍스처 지표를 통과분·탈락분 **양쪽에** 기록해 두므로,
문턱만 바꿔 다시 판정하면 된다. 장당 20초짜리 추론 대신 밀리초로 끝난다.

DB 로 옮기면서 달라진 것:

- 통과분·탈락분을 합치는 일이 없어졌다. 한 테이블에 `passed` 칼럼이라 **UPDATE 한 번**이다
- **문턱이 `ThresholdSet` 행으로 남는다.** 예전에는 결과 JSON 마다 복사됐고 다시
  거르면 덮어써져서, "원형 669 → 514 가 언제 무슨 문턱으로 바뀌었나" 에 답할 수 없었다
- 실행이 `Run(kind=refilter)` 에 남는다 — 무슨 문턱으로 개수가 어떻게 변했는지

**주지 않은 문턱은 그 검출이 지금 쓰는 값을 그대로 쓴다.** 전부 기본값으로 되돌리면
`--round-texture-min` 하나 바꾸려다 나머지 열 개가 조용히 초기화된다.

사람의 교정은 건드리지 않는다 — `mask_key` 로 붙어 있고 이 스크립트는 판정만 바꾼다.
지운 개체가 탈락분으로 옮겨가도 뷰어에서는 여전히 지운 것으로 보인다.
"""
import argparse
import os
import socket
import subprocess
import sys
from collections import Counter
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
from django.utils import timezone                                   # noqa: E402

import judge                                                        # noqa: E402
from viewer.models import (Candidate, Detection, Run, Slide,        # noqa: E402
                           ThresholdSet)


def git_version():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=Path(__file__).resolve().parent)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def as_record(c: Candidate) -> dict:
    """판정에 필요한 값만 뽑는다. judge 는 dict 를 받는다."""
    return {
        "_pk": c.pk,
        "bbox_xywh": [c.bbox_x, c.bbox_y, c.bbox_w, c.bbox_h],
        "area_px": c.area_px,
        "shape_ok": c.shape_ok,
        "major_um": c.major_um,
        "texture": c.texture,
        "elongation": c.elongation,
        "ellipse_iou": c.ellipse_iou,
        "solidity": c.solidity,
    }


def threshold_set_for(values: dict) -> ThresholdSet:
    """같은 문턱 조합이면 한 행을 공유한다. 없으면 만든다."""
    found = ThresholdSet.objects.filter(**values).first()
    if found:
        return found
    name = (f"texture {values['texture_min']:g} · "
            f"areolae {values['round_texture_min']:g}")
    return ThresholdSet.objects.create(name=name, note="refilter 가 만들었다",
                                       **values)


def refilter_detection(det: Detection, values: dict, dry_run: bool):
    """검출 하나를 다시 거른다. (전, 후, 사유별 개수, 바뀐 행 수)."""
    cands = list(det.candidates.all())
    before = sum(1 for c in cands if c.passed)

    th = judge.Thresholds(**values)
    kept, rejected = judge.apply([as_record(c) for c in cands], th)

    by_pk = {c.pk: c for c in cands}
    changed = []
    for r in kept:
        c = by_pk[r["_pk"]]
        if not c.passed or c.cls != r["cls"] or c.reject:
            c.passed, c.cls, c.reject = True, r["cls"], ""
            changed.append(c)

    reasons = Counter()
    for r in rejected:
        c = by_pk[r["_pk"]]
        # 중첩정리로 떨어진 것은 판정을 통과한 뒤 정리된 것이라 cls 를 남긴다
        cls = r.get("cls") or ""
        reasons[r["reject"]] += 1
        if c.passed or c.cls != cls or c.reject != r["reject"]:
            c.passed, c.cls, c.reject = False, cls, r["reject"]
            changed.append(c)

    if changed and not dry_run:
        Candidate.objects.bulk_update(changed, ["passed", "cls", "reject"],
                                      batch_size=1000)
    return before, len(kept), reasons, len(changed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slide", help="이 슬러그만 (기본: 전부)")
    ap.add_argument("--dry-run", action="store_true", help="확인만, 저장 안 함")
    ap.add_argument("-q", "--quiet", action="store_true", help="시야별 줄을 줄인다")
    ap.add_argument("--defaults", action="store_true",
                    help="주지 않은 문턱을 지금 값이 아니라 기본값으로 둔다")
    g = ap.add_argument_group("판정 문턱 (주지 않으면 지금 쓰는 값 그대로)")
    for f in judge.FIELDS:
        g.add_argument(f"--{f.replace('_', '-')}", type=float, default=None,
                       help=f"기본 {judge.DEFAULTS[f]:g}")
    args = ap.parse_args()

    overrides = {f: getattr(args, f) for f in judge.FIELDS
                 if getattr(args, f) is not None}

    if args.slide and not Slide.objects.filter(slug=args.slide).exists():
        raise SystemExit(f"슬라이드를 찾지 못했다: {args.slide}")
    dets = (Detection.objects.filter(is_current=True)
            .select_related("thresholds", "viewpoint", "viewpoint__slide")
            .prefetch_related("candidates"))
    if args.slide:
        dets = dets.filter(viewpoint__slide__slug=args.slide)
    dets = list(dets)
    if not dets:
        raise SystemExit("현재 검출이 없다. import_json.py 를 먼저 돌렸는가?")

    run = None
    if not args.dry_run:
        run = Run.objects.create(kind="refilter", status="running",
                                 params={"overrides": overrides,
                                         "slide": args.slide or "*",
                                         "from_defaults": args.defaults},
                                 host=socket.gethostname(),
                                 code_version=git_version())

    tot_before = tot_after = tot_changed = 0
    per_cls = Counter()
    reasons = Counter()
    ts_cache = {}

    with transaction.atomic():
        for det in dets:
            # 주지 않은 문턱은 이 검출이 지금 쓰는 값 그대로 — 하나를 바꾸려다
            # 나머지가 조용히 초기화되면 안 된다.
            base = (judge.DEFAULTS if args.defaults or not det.thresholds
                    else det.thresholds.as_dict())
            values = {**judge.DEFAULTS, **base, **overrides}

            before, after, why, changed = refilter_detection(det, values,
                                                             args.dry_run)
            tot_before += before
            tot_after += after
            tot_changed += changed
            reasons += why
            for c in det.candidates.all():
                if c.passed and c.cls:
                    per_cls[c.cls] += 1

            if not args.dry_run:
                key = tuple(sorted(values.items()))
                if key not in ts_cache:
                    ts_cache[key] = threshold_set_for(values)
                det.thresholds = ts_cache[key]
                det.save(update_fields=["thresholds"])

            if not args.quiet and before != after:
                vp = det.viewpoint
                print(f"  {vp.slide.slug} g{vp.idx:<3d} {before:4d} -> {after:4d}")

        if args.dry_run:
            # dry-run 은 아무것도 남기지 않는다 — 메모리에서만 판정했지만
            # 실수로 저장되는 경로가 생기지 않게 통째로 되돌린다.
            transaction.set_rollback(True)

    print(f"\n검출 {len(dets)}개 · 통과 {tot_before} -> {tot_after} "
          f"({tot_after - tot_before:+d})")
    if per_cls:
        print("  " + " · ".join(f"{k} {v}" for k, v in sorted(per_cls.items())))
    if reasons:
        top = " · ".join(f"{k} {v}" for k, v in reasons.most_common(6))
        print(f"  탈락 사유: {top}")

    if args.dry_run:
        print(f"\ndry-run — 바뀔 행 {tot_changed}개. 저장하지 않았다.")
        if overrides:
            print("  적용하려면 --dry-run 을 빼고 같은 명령을 다시 돌린다.")
        return

    run.status = "done"
    run.finished_at = timezone.now()
    run.counts = {"detections": len(dets), "before": tot_before,
                  "after": tot_after, "changed": tot_changed,
                  **{f"cls_{k}": v for k, v in per_cls.items()}}
    run.save()
    print(f"\n저장했다. 행 {tot_changed}개 갱신 · 문턱 조합 {len(ts_cache)}개 · "
          f"Run #{run.pk}")


if __name__ == "__main__":
    main()
