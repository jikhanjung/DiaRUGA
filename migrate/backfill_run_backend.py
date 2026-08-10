#!/usr/bin/env python3
"""묶음에 속했는데 `params["backend"]` 가 없는 실행에 backend 를 채운다.

    dbrun.sh backfill_run_backend.py                       # 대상만 보여준다
    dbrun.sh backfill_run_backend.py --run 19 --backend sam2 --apply

왜 있나 — P02 이전에 계산된 검출은 ingest 실행(#19, part=detections)으로
들어와 backend 가 기록되지 않았다. 검출 구분 라디오(◉ SAM / ○ YOLO)의 이름이
`Run.params["backend"]` 에서 오므로(`data.py`), 그 실행이 대표로 잡히는
슬라이드 셋(wap13-gc47 116cm·450cm, rs23)에서 라디오가 `?` 로 나온다 (094 뒤).

코드에서 묶음 이름으로 추정하지 않는 이유 — 값이 실제로 무엇이었는지는
사람이 안다(sam2-전수 묶음 설명에 SAM2.1 로 처리했다고 적혀 있다). 추정
폴백을 두면 "모르는 것" 과 "아는 것" 이 화면에서 같아 보인다.
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

from viewer.models import Run                                       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, help="채울 실행 번호")
    ap.add_argument("--backend", help="채울 값 (예: sam2)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 쓴다. 없으면 대상만 보여준다")
    args = ap.parse_args()

    targets = [r for r in Run.objects.filter(batch__isnull=False)
                                     .select_related("batch")
               if "backend" not in (r.params or {})]
    if not targets:
        print("묶음 소속인데 backend 가 없는 실행이 없다 — 할 일 없음")
        return
    for r in targets:
        print(f"  실행 #{r.id}  kind={r.kind}  묶음={r.batch.label}"
              f"  params={r.params}")

    if not args.apply:
        print("(--run N --backend 값 --apply 로 채운다)")
        return
    if not args.run or not args.backend:
        sys.exit("--apply 에는 --run 과 --backend 가 함께 필요하다")
    run = next((r for r in targets if r.id == args.run), None)
    if run is None:
        sys.exit(f"실행 #{args.run} 은 대상이 아니다 (위 목록에 없다)")
    run.params = {**(run.params or {}), "backend": args.backend}
    run.save(update_fields=["params"])
    print(f"채웠다: 실행 #{run.id} params={run.params}")


if __name__ == "__main__":
    main()
