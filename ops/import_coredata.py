#!/usr/bin/env python3
"""중간 CSV → DB. 코어 자료 반입의 뒷단이다 (P17 4절).

    deploy/host/dbsync.sh import_coredata.py
    deploy/host/dbrun.sh  import_coredata.py --dir /data3/DiaRUGA/coredata --dry-run
    deploy/host/dbrun.sh  import_coredata.py --dir /data3/DiaRUGA/coredata

앞단은 `tools/coredata_extract.py` 다. **여기서는 xlsx 를 안 읽는다** — 어느
열이 무엇인지, 깊이 단위가 무엇인지 하는 판단은 전부 앞단의 매핑표
(`coredata/mapping.toml`)에서 끝나 있고, 이쪽이 받는 것은 이미 정리된
`key,depth_mm,value` 다.

**언제든 다시 돌릴 수 있다.** 다만 `source='import'` 인 항목만 갈아치운다 —
사람이 넣은 항목(`manual`)은 손대지 않는다. 안 가르면 재반입 한 번에 사람이
넣은 값이 지워진다(063 이 당한 것과 같은 줄이다).

**지점을 만들지 않는다.** 없으면 그렇게 말하고 멈춘다 — 층을 만드는 문은
시스템 설정 화면 하나이고(`manage_data.create`), 반입기가 지점을 지어내면
이름이 한 글자 틀렸을 때 **엉뚱한 지점이 조용히 생긴다.**
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import django

# `ops/check_db.py` 와 같은 머리다. 컨테이너 안에서는 코드가 `/app` 이라
# `DIARUGA_APP` 을 봐야 한다 — 자기 옆의 `web/` 을 보게 짜면
# `No module named 'diarugaweb'` 로 죽는다.
APP = Path(os.environ.get("DIARUGA_APP")
          or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402

from viewer.models import CorePoint, CoreSeries, Locality           # noqa: E402


def _pairs(directory: Path) -> list[tuple[str, str, Path, Path]]:
    """`<지역>-<지점>.series.csv` 짝을 찾는다.

    **이름이 곧 지점이다.** 파일 안에 지점을 적어 두면 이름과 내용이 어긋날 수
    있고, 그때 어느 쪽을 믿을지가 또 규칙이 된다.
    """
    out = []
    for sf in sorted(directory.glob("*.series.csv")):
        name = sf.name[:-len(".series.csv")]
        pf = directory / f"{name}.points.csv"
        if "-" not in name:
            print(f"  !! 이름이 <지역>-<지점> 이 아닙니다: {sf.name}")
            continue
        if not pf.exists():
            print(f"  !! 점 파일이 없습니다: {pf.name}")
            continue
        site, loc = name.split("-", 1)
        out.append((site, loc, sf, pf))
    return out


def load_one(site_code: str, loc_code: str, series_csv: Path,
             points_csv: Path, dry: bool) -> int:
    loc = (Locality.objects.select_related("site")
           .filter(site__code=site_code, code=loc_code).first())
    if loc is None:
        print(f"  !! 지점이 없습니다: {site_code}-{loc_code} — "
              f"시스템 설정 화면에서 먼저 만드세요")
        return 1

    with series_csv.open() as f:
        meta = list(csv.DictReader(f))
    points: dict[str, list[tuple[int, float]]] = {m["key"]: [] for m in meta}
    unknown = set()
    with points_csv.open() as f:
        for r in csv.DictReader(f):
            if r["key"] not in points:
                unknown.add(r["key"])
                continue
            points[r["key"]].append((int(r["depth_mm"]), float(r["value"])))
    if unknown:
        # 점 파일에만 있고 항목 파일에 없는 key. **조용히 버리지 않는다** —
        # 앞단이 반쯤 쓰다 만 파일일 수 있다.
        print(f"  !! 항목 파일에 없는 key 가 점 파일에 있습니다: "
              f"{', '.join(sorted(unknown))}")
        return 1

    n_pts = sum(len(v) for v in points.values())
    # 사람이 넣은 것은 세기만 한다 — 건드리지 않는다는 것을 눈으로 보이려고.
    kept = CoreSeries.objects.filter(locality=loc, source="manual").count()
    print(f"  {loc}  항목 {len(meta)}개 · 점 {n_pts:,}개"
          + (f" · 수동 항목 {kept}개는 그대로 둡니다" if kept else ""))
    if dry:
        return 0

    with transaction.atomic():
        # **자기 출처만 지운다.** `source='manual'` 은 이 filter 에 안 걸린다.
        # 점은 FK CASCADE 로 함께 지워진다.
        CoreSeries.objects.filter(locality=loc, source="import").delete()
        for m in meta:
            cs = CoreSeries.objects.create(
                locality=loc, key=m["key"], label=m["label"], unit=m["unit"],
                source="import",
                default_on=m["default_on"] == "1",
                sort_order=int(m["sort_order"]), origin=m["origin"])
            CorePoint.objects.bulk_create(
                [CorePoint(series=cs, depth_mm=mm, value=v)
                 for mm, v in points[m["key"]]],
                batch_size=2000)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="코어 자료 중간 CSV → DB")
    ap.add_argument("--dir", default="/data3/DiaRUGA/coredata",
                    help="tools/coredata_extract.py 가 낸 자리")
    ap.add_argument("--only", default="", help="지역-지점 하나만 (RS14-GC04)")
    ap.add_argument("--dry-run", action="store_true",
                    help="아무것도 안 쓴다. 무엇이 들어갈지만 센다")
    a = ap.parse_args()

    directory = Path(a.dir)
    if not directory.is_dir():
        print(f"자리가 없습니다: {directory}")
        return 1
    pairs = _pairs(directory)
    if not pairs:
        print(f"반입할 것이 없습니다: {directory}/*.series.csv")
        return 1
    print(f"자리: {directory}" + ("  (dry-run — 아무것도 안 씁니다)"
                                  if a.dry_run else ""))
    rc = 0
    for site, loc, sf, pf in pairs:
        if a.only and a.only != f"{site}-{loc}":
            continue
        rc |= load_one(site, loc, sf, pf, a.dry_run)
    return rc


if __name__ == "__main__":
    sys.exit(main())
