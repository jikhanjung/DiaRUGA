#!/usr/bin/env python3
"""잘못 묶인 시야를 프레임 경계에서 가른다 — **바뀌는 시야만 다시 만든다.**

`viewer/regroup.py` 가 진짜 구현이고 이것은 그 위의 CLI 다. 화면
(`/d/<slug>/g/<n>/` 의 "시야 가르기")도 같은 것을 부른다 — 두 벌로 두면 한쪽만
고쳐지고, 그 종류의 어긋남은 사람이 화면을 눌러 보기 전까지 안 드러난다.
**왜 부분 재분할인지, 무엇이 지워지는지는 그 모듈 머리말에 있다.**

쓰임:

    python resplit.py --slide 260731_am22-gc10b_25cm --after 22131          # 미리보기
    python resplit.py --slide 260731_am22-gc10b_25cm \\
        --after 22131 --after 22155 --after 22159 --after 22170 --apply

`--after` 는 **그 프레임 뒤에서 자른다**. 이름(`Snap-22131`)도 번호(`22131`)도 받는다.
DB 를 만지므로 `deploy/host/dbrun.sh` 로 들어간다 (HANDOFF 9.2).

> 화면이 있는데 CLI 를 남겨 두는 이유: 여러 시야를 한 번에 가를 때는 이쪽이 낫고,
> 무엇보다 **화면이 못 뜨는 상태에서도 고칠 수 있어야 한다.**
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

from viewer import regroup                                          # noqa: E402
from viewer.models import Slide                                     # noqa: E402


def short(names):
    return " ".join(n.replace("Snap-", "") for n in names)


def main():
    ap = argparse.ArgumentParser(
        description="잘못 묶인 시야를 프레임 경계에서 가른다 (바뀌는 시야만)")
    ap.add_argument("--slide", required=True, help="슬라이드 slug")
    ap.add_argument("--after", action="append", default=[], metavar="프레임",
                    help="이 프레임 **뒤에서** 자른다. 여러 번 줄 수 있다")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 고친다 (기본은 미리보기)")
    args = ap.parse_args()

    slide = Slide.objects.filter(slug=args.slide).first()
    if slide is None:
        raise SystemExit(f"그런 슬라이드가 없다: {args.slide}")

    p = regroup.preview(slide, args.after)
    if not p["ok"]:
        for e in p["errors"]:
            print(f"  {e}", file=sys.stderr)
        raise SystemExit("자를 자리가 옳지 않다 — 아무것도 고치지 않았다")

    print(f"슬라이드 {slide.slug} · 시야 {p['before']}개 → {p['after']}개")
    for s in p["splits"]:
        print(f"\n  g{s['idx']} {s['tag']}")
        print(f"    지운다  검출 {s['detections']} · 교정 {s['object_reviews']}"
              f"{' · 검토 완료였다' if s['reviewed'] else ''}"
              f"{' · 합성본' if s['stack'] else ''}")
        print(f"    만든다  {' / '.join(short(x) for x in s['pieces'])}")
    t = p["totals"]
    print(f"\n합계 — 시야 {t['split']}개를 {t['created']}개로 가른다 · "
          f"검출 {t['detections']}건 · 교정 {t['object_reviews']}건이 사라진다")
    print(f"       나머지 시야 {p['untouched']}개는 건드리지 않는다 "
          f"(그 아래 검출·교정 그대로)")

    if not args.apply:
        print("\n미리보기다 — 고치려면 --apply")
        return

    r = regroup.apply_split(slide, args.after, source="resplit.py")
    print(f"\n고쳤다 — 시야 {r['after']}개 · 상태 {slide.state} · Run #{r['run_id']}")
    print("  폴러가 1분 안에 합성·검출을 이어서 한다. 손으로 하려면:")
    print(f"    docker compose run --rm pipeline python focus_stack.py "
          f"--slide {slide.slug}")
    print(f"    docker compose run --rm pipeline python segment_diatoms.py "
          f"--slide {slide.slug} --scale 1.0 --points-per-side 48 "
          f"--min-um 10 --max-um 150 --batch sam2-전수")
    print(f"  가른 시야 {r['created']}개는 검토가 비어 있다 — 사람이 다시 봐야 한다.")


if __name__ == "__main__":
    main()
