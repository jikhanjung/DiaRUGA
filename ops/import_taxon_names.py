#!/usr/bin/env python3
"""학명 유효성 판정 JSON 을 DB 에 넣는다 — P24 반입의 **2단계**.

    dbsync.sh import_taxon_names.py      # 저장소 → /srv (처음 한 번)
    dbrun.sh  import_taxon_names.py      # 컨테이너 안에서 돈다
    dbrun.sh  import_taxon_names.py --dry-run

1단계(`tools/parse_taxon_names.py`)가 NAS 두 벌(`worms_master_20260814.tsv`·
`paper_plates_156_result.json`)을 `taxon_names.json` 으로 뽑아 저장소에
넣어 두었다. **이쪽은 NAS 를 안 본다** — 그래서 컨테이너 안에서 돌 수 있다
(`ops/import_atlas.py` 와 같은 사정). JSON 은 `COPY . .` 를 타고 이미지의
`/app/taxon_names.json` 에 함께 실린다.

## 이 반입이 지키는 것

- **멱등이다.** 두 번 돌려도 같다. `TaxonName` 을 **통째로 갈아치운다** —
  이 표에는 사람이 만든 칸이 없다(판단 자체는 NAS 파일에 있다, P24)
- **자기 검산을 한다.** 넣은 뒤 JSON 이 말하는 수와 DB 를 맞춰 보고,
  어긋나면 트랜잭션을 되돌린다
"""
import argparse
import json
import os
import sys
from pathlib import Path

import django

APP = Path(os.environ.get("DIARUGA_APP")
           or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402

from viewer.models import TaxonName                                 # noqa: E402

# JSON 이 놓이는 자리. 저장소에서는 뿌리, 컨테이너에서는 `/app`
SRC = APP / "taxon_names.json"

FIELDS = ("binomial", "status", "valid_name", "source", "note", "checked")


def blank(v):
    return "" if v is None else v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC, help="taxon_names.json 자리")
    ap.add_argument("--dry-run", action="store_true", help="넣고 되돌린다")
    args = ap.parse_args()

    if not args.src.exists():
        print(f"taxon_names.json 이 없다: {args.src}\n"
              f"  1단계를 먼저 돌린다 — `python tools/parse_taxon_names.py` (호스트에서)",
              file=sys.stderr)
        return 2

    rows = json.loads(args.src.read_text(encoding="utf-8"))
    want = len(rows)

    try:
        with transaction.atomic():
            TaxonName.objects.all().delete()
            TaxonName.objects.bulk_create([
                TaxonName(**{f: blank(r.get(f)) for f in FIELDS})
                for r in rows])
            got = TaxonName.objects.count()
            if got != want:
                raise _Rollback([f"학명: JSON 은 {want} 인데 DB 는 {got}"])
            if args.dry_run:
                raise _Rollback([])
    except _Rollback as r:
        if r.bad:
            print("학명 유효성 — 되돌렸다")
            for b in r.bad:
                print(f"  ✗ {b}")
            return 1
        print(f"학명 유효성 — {got} 건 (되돌렸다)")
        return 0

    from collections import Counter
    c = Counter(TaxonName.objects.values_list("status", flat=True))
    print(f"학명 유효성 {got} 건")
    print("  " + " · ".join(f"{k} {v}" for k, v in c.most_common()))
    print(f"  ✓ JSON 과 맞는다 ({args.src.name})")
    return 0


class _Rollback(Exception):
    def __init__(self, bad):
        self.bad = bad


if __name__ == "__main__":
    raise SystemExit(main())
