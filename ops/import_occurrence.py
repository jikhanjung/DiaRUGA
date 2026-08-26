#!/usr/bin/env python3
"""출현 기록 JSON 을 DB 에 넣는다 — P20 2단계.

    dbsync.sh import_occurrence.py      # 저장소 → /srv (처음 한 번)
    dbrun.sh  import_occurrence.py
    dbrun.sh  import_occurrence.py --dry-run
    dbrun.sh  import_occurrence.py --src /app/atlas/occurrence --only korean

1단계(`tools/parse_occurrence.py`)가 도감·논문의 분포 문장을
`atlas/occurrence/*.json` 으로 뽑아 저장소에 넣어 두었다. **이쪽은 NAS 를
안 본다** — `ops/import_atlas.py` 와 같은 자리다.

## 이 반입이 지키는 것

- **`Reference` 는 `key` 로 upsert 한다.** `Atlas` 처럼 통째로 지우지
  않는다 — 논문이 늘면 같은 저자가 다른 source 에도 나올 수 있어, 지우고
  다시 만들면 먼저 반입된 source 의 참조가 끊긴다
- **`Occurrence` 는 `source` 단위로 통째로 갈아치운다.** 그 source(도감
  하나·논문 하나)의 옛 기록을 지우고 새로 넣는다 — `AtlasEntry` 와 같은
  규약이다
- **`AtlasEntry` 에 FK 를 매달지 않는다** (P20). `item_no`·`binomial` 은
  문자열로 들고, 도감과 맞추는 것은 질의가 한다
- **`Reference.key` 는 이 스크립트가 못 박는다.** 저자·연도로 자동 생성하지
  않는다 — 로마자 표기가 애매한 이름이 섞여 있어(殖田三郎·奧野春雄) 사람이
  한 번 정한 것을 `REF_KEY` 에 적어 두고 벗어나면 멈춘다
"""
import argparse
import json
import os
import sys
from pathlib import Path

import django

# `ops/check_db.py` 의 머리와 같다 — 컨테이너 안에서는 코드가 `/app` 이라
# `DIARUGA_APP` 을 봐야 한다.
APP = Path(os.environ.get("DIARUGA_APP")
           or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402

from viewer.models import Occurrence, Reference                     # noqa: E402

SRC = APP / "atlas" / "occurrence"

# **여기서만 열쇠를 정한다.** `jung1967`·`kurashige1943` 처럼 저자·연도로
# 짓지만 **로마자 표기를 보증하지 않는다** — 성씨만 짚는 내부 열쇠다
# (`Reference` 머리말). 한자 인명 셋(殖田三郎·奧野春雄·羽田良禾)은 훈독을
# 확신하지 못해도 이 목적에는 문제가 안 된다 — 화면에 보이는 것은
# `authors`(원문 그대로)다.
REF_KEY = {
    ("정 영호 외", "1967"): "jung1967",
    ("정 영호 외", "1965"): "jung1965",
    ("최 상", "1967"): "choi1967",
    ("최 상", "1966"): "choi1966",
    ("이 민재 외", "1967"): "leemj1967",
    ("엄 규백 외", "1967"): "uhm1967",
    ("倉茂英次郎", "1943"): "kurashige1943",
    ("박 태수", "1956"): "park1956",
    ("殖田三郎 외", "1935"): "ueda1935",
    ("奧野春雄", "1948"): "okuno1948",
    ("羽田良禾", "1936"): "haneda1936",
    ("Skvortzow", "1929"): "skvortzow1929",
    ("Skvortzow", "1931"): "skvortzow1931",
    ("Skvortzow", "1932"): "skvortzow1932",
    ("Skvortzow", "1936"): "skvortzow1936",
}


def ref_key(ref: str, year: str) -> str:
    key = REF_KEY.get((ref, year))
    if key is None:
        raise SystemExit(
            f"REF_KEY 에 없는 문헌이다: {ref!r} {year!r} — "
            f"tools/parse_occurrence.py 가 못 보던 문헌을 냈다. "
            f"열쇠를 정해 이 스크립트의 REF_KEY 에 추가한다.")
    return key


def load(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if "source" not in doc or "occurrences" not in doc:
        raise SystemExit(f"{path.name}: 출현 기록 JSON 이 아니다")
    return doc


def put(doc: dict) -> tuple[str, int, int]:
    """출현 기록 하나(도감 하나·논문 하나 분)를 넣는다."""
    source = doc["source"]["atlas"]

    by_pair = {}
    for r in doc["references"]:
        key = ref_key(r["ref"], r["year"])
        ref, _ = Reference.objects.update_or_create(
            key=key,
            defaults={"authors": r["ref"], "year": int(r["year"]),
                      "title": r.get("cite") or "", "note": r.get("note") or ""})
        by_pair[(r["ref"], r["year"])] = ref

    # **이 source 몫만 갈아치운다** — 다른 source 가 같은 Reference 를 이미
    # 쓰고 있어도 그쪽 Occurrence 는 안 건드린다
    Occurrence.objects.filter(source=source).delete()
    rows = []
    for o in doc["occurrences"]:
        ref = by_pair.get((o["ref"], o["year"]))
        if ref is None:
            raise SystemExit(
                f"{source}: 참조를 못 찾았다 — {o['ref']!r} {o['year']!r} "
                f"(#{o.get('item_no')} {o['binomial']}) — references[] 에 없다")
        rows.append(Occurrence(
            source=source, item_no=o.get("item_no") or "",
            binomial=o["binomial"], region_raw=o.get("region_raw") or "",
            region=o.get("region") or "", reference=ref,
            note=o.get("note") or ""))
    Occurrence.objects.bulk_create(rows)
    return source, len(by_pair), len(rows)


def verify(source: str, doc: dict) -> list[str]:
    """넣은 것이 JSON 과 같은가."""
    bad = []
    want_o = len(doc["occurrences"])
    got_o = Occurrence.objects.filter(source=source).count()
    if got_o != want_o:
        bad.append(f"출현 기록: JSON 은 {want_o} 인데 DB 는 {got_o}")
    want_species = {o["binomial"] for o in doc["occurrences"]}
    got_species = set(Occurrence.objects.filter(source=source)
                      .values_list("binomial", flat=True))
    if want_species != got_species:
        bad.append(f"종: {sorted(want_species ^ got_species)[:5]} 가 어긋난다")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC, help="출현 기록 JSON 이 있는 자리")
    ap.add_argument("--only", help="source(도감·논문 키) 하나만")
    ap.add_argument("--dry-run", action="store_true", help="넣고 되돌린다")
    args = ap.parse_args()

    files = sorted(args.src.glob("*.json"))
    if args.only:
        files = [f for f in files if f.stem == args.only]
    if not files:
        print(f"출현 기록 JSON 이 없다: {args.src}\n"
              f"  1단계를 먼저 돌린다 — `python tools/parse_occurrence.py` (호스트에서)",
              file=sys.stderr)
        return 2

    failed = False
    for path in files:
        doc = load(path)
        try:
            with transaction.atomic():
                source, nr, no = put(doc)
                bad = verify(source, doc)
                if bad or args.dry_run:
                    raise _Rollback(bad)
        except _Rollback as r:
            if r.bad:
                failed = True
                print(f"\n{path.name} — 되돌렸다")
                for b in r.bad:
                    print(f"  ✗ {b}")
                continue
            print(f"\n{path.name} — 문헌 {nr} · 출현 기록 {no} (되돌렸다)")
            continue
        print(f"\n{source} — 문헌 {nr} · 출현 기록 {no}")
        print(f"  ✓ JSON 과 맞는다  ({path.name})")

    if failed:
        print("\n반입이 어긋났다.", file=sys.stderr)
        return 1
    if not args.dry_run:
        print(f"\n문헌 {Reference.objects.count()} · 출현 기록 {Occurrence.objects.count()}")
        print("이제 `check_db.py` 의 12번(출현 기록)을 본다.")
    return 0


class _Rollback(Exception):
    """`transaction.atomic` 을 되돌리는 유일한 길은 예외다."""

    def __init__(self, bad):
        self.bad = bad


if __name__ == "__main__":
    raise SystemExit(main())
