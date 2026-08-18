#!/usr/bin/env python3
"""도감 색인 JSON 을 DB 에 넣는다 — P15 반입의 **2단계**.

    dbsync.sh import_atlas.py      # 저장소 → /srv (처음 한 번)
    dbrun.sh  import_atlas.py      # 컨테이너 안에서 돈다
    dbrun.sh  import_atlas.py --dry-run
    dbrun.sh  import_atlas.py --src /app/atlas --only schmidt

1단계(`tools/parse_atlas.py`)가 NAS 의 색인을 `atlas/*.json` 으로 뽑아 저장소에
넣어 두었다. **이쪽은 NAS 를 안 본다** — 그래서 컨테이너 안에서 돌 수 있다
(P15 7절). JSON 은 `COPY . .` 를 타고 이미지의 `/app/atlas/` 에 함께 실린다.

## 이 반입이 지키는 것

- **멱등이다.** 두 번 돌려도 같다. 도감마다 항목을 **통째로 갈아치운다** —
  `AtlasEntry` 를 지우고 다시 만들어도 아무것도 안 잃는 것이 이 표의 규약이고
  (P15 4.2), 그 규약이 서 있어야 이 반입이 안전하다
- **그래서 사람이 만든 것은 이 표에 없다** (P15 4.3). 학명 유효성 판정은
  `TaxonName` 자리이고 원본은 `md/name_validity_log.md` 다. **한 칸이라도
  이리로 들어오는 순간 위의 "안 잃는다" 가 거짓이 된다** — `migrate/import_json.py`
  가 겪은 것이 그 모양이다(`Candidate` 를 지우고 다시 만드는데 DB 에서만 한
  교정이 그 아래 있었다)
- **자기 검산을 한다.** 넣은 뒤 JSON 이 말하는 수와 DB 를 맞춰 보고, 어긋나면
  트랜잭션을 되돌린다. 1단계도 같은 자리를 검산한다 — 조용히 틀리는 것을
  두 겹으로 막는다

## 함정

- **`AtlasEntry` 에 FK 를 매달지 말 것.** 이 스크립트가 도는 순간 그 행들이
  사라진다(CASCADE). 살아야 하는 것은 **이름**으로 짚는다
- **속명은 안 고친다.** 색인에 적힌 그대로 들어온다 — 잘못 펴진 자리가 있고
  (119) 그것은 색인 쪽에서 닫는다. 여기서는 `ops/check_db.py` 가 `ClassDef` 와
  **안 맞는 속을 센다**(P15 8.2) — 기다리는 대신 세는 쪽이다
"""
import argparse
import json
import os
import sys
from pathlib import Path

import django

# `ops/check_db.py` 의 머리와 같다 — 컨테이너 안에서는 코드가 `/app` 이라
# `DIARUGA_APP` 을 봐야 한다. 자기 옆의 `web/` 을 보게 짜면
# `No module named 'diarugaweb'` 로 죽는다.
APP = Path(os.environ.get("DIARUGA_APP")
           or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db import transaction                                   # noqa: E402

from viewer.models import Atlas, AtlasEntry, AtlasPlacement          # noqa: E402

# JSON 이 놓이는 자리. 저장소에서는 뿌리의 `atlas/`, 컨테이너에서는 `/app/atlas`
SRC = APP / "atlas"

ENTRY_FIELDS = ("seq", "item_no", "name", "genus", "binomial", "rank",
                "infra", "authority", "genus_guess", "extra", "line")
PLACE_FIELDS = ("plate", "plate_label", "figures", "book_page",
                "pdf_page", "pdf_plate_page", "volume", "note")


def blank(v):
    """`null` 은 글자 칸에서 빈 칸이다. 숫자 칸은 `null` 그대로 둔다 —
    **빈 것을 0 으로 채우면 그것이 자료가 된다** (P15 9절)."""
    return "" if v is None else v


def load(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if "atlas" not in doc or "entries" not in doc:
        raise SystemExit(f"{path.name}: 도감 JSON 이 아니다")
    return doc


def put(doc: dict, order: int) -> tuple[Atlas, int, int]:
    """도감 하나를 넣는다. **항목은 통째로 갈아치운다.**"""
    a = doc["atlas"]
    atlas, _ = Atlas.objects.update_or_create(
        key=a["key"],
        defaults={"title": a["title"], "short": a["short"],
                  "source": blank(a.get("source")),
                  "source_sha256": blank(a.get("source_sha256")),
                  "note": blank(a.get("note")),
                  # 차례는 JSON 이 든다 — 파일 이름 정렬을 안 탄다
                  "sort_order": a.get("sort_order", order)})

    atlas.entries.all().delete()          # 자리도 CASCADE 로 함께 간다
    AtlasEntry.objects.bulk_create([
        AtlasEntry(atlas=atlas, **{f: blank(e.get(f)) for f in ENTRY_FIELDS})
        for e in doc["entries"]])

    by_seq = {e.seq: e for e in atlas.entries.all()}
    places = [
        AtlasPlacement(entry=by_seq[e["seq"]], seq=i,
                       **{f: (p[f] if f in ("plate", "book_page", "pdf_page",
                                            "pdf_plate_page") else blank(p[f]))
                          for f in PLACE_FIELDS})
        for e in doc["entries"] for i, p in enumerate(e["placements"])]
    AtlasPlacement.objects.bulk_create(places)
    return atlas, len(doc["entries"]), len(places)


def verify(atlas: Atlas, doc: dict) -> list[str]:
    """**넣은 것이 JSON 과 같은가.** 어긋나면 되돌린다."""
    bad = []
    want_e = len(doc["entries"])
    want_p = sum(len(e["placements"]) for e in doc["entries"])
    got_e = atlas.entries.count()
    got_p = AtlasPlacement.objects.filter(entry__atlas=atlas).count()
    if got_e != want_e:
        bad.append(f"항목: JSON 은 {want_e} 인데 DB 는 {got_e}")
    if got_p != want_p:
        bad.append(f"자리: JSON 은 {want_p} 인데 DB 는 {got_p}")
    want_g = {e["genus"] for e in doc["entries"] if e["genus"]}
    got_g = set(atlas.entries.exclude(genus="").values_list("genus", flat=True))
    if got_g != want_g:
        bad.append(f"속: {sorted(want_g ^ got_g)[:5]} 가 어긋난다")
    # 표제어를 고치지 않았는가 — 한 글자라도 다르면 인용이 원문과 어긋난다
    want_n = sorted(e["name"] for e in doc["entries"])
    got_n = sorted(atlas.entries.values_list("name", flat=True))
    if want_n != got_n:
        bad.append("표제어가 JSON 과 다르다")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC, help="도감 JSON 이 있는 자리")
    ap.add_argument("--only", help="도감 코드 하나만")
    ap.add_argument("--dry-run", action="store_true", help="넣고 되돌린다")
    args = ap.parse_args()

    files = sorted(args.src.glob("*.json"))
    if args.only:
        files = [f for f in files if f.stem == args.only]
    if not files:
        print(f"도감 JSON 이 없다: {args.src}\n"
              f"  1단계를 먼저 돌린다 — `python tools/parse_atlas.py` (호스트에서)",
              file=sys.stderr)
        return 2

    failed = False
    for order, path in enumerate(files):
        doc = load(path)
        try:
            with transaction.atomic():
                atlas, ne, np_ = put(doc, order)
                bad = verify(atlas, doc)
                if bad or args.dry_run:
                    raise _Rollback(bad)
        except _Rollback as r:
            if r.bad:
                failed = True
                print(f"\n{doc['atlas']['short']} — 되돌렸다")
                for b in r.bad:
                    print(f"  ✗ {b}")
                continue
            print(f"\n{doc['atlas']['short']} — 항목 {ne} · 자리 {np_} (되돌렸다)")
            continue
        print(f"\n{atlas.short} — 항목 {ne} · 자리 {np_}")
        print(f"  ✓ JSON 과 맞는다  ({path.name} · {doc['atlas']['source_sha256'][:12]})")

    if failed:
        print("\n반입이 어긋났다.", file=sys.stderr)
        return 1
    if not args.dry_run:
        print(f"\n도감 {Atlas.objects.count()} · 항목 {AtlasEntry.objects.count()} · "
              f"자리 {AtlasPlacement.objects.count()}")
        print("이제 `check_db.py` 의 11번(도감)을 본다.")
    return 0


class _Rollback(Exception):
    """`transaction.atomic` 을 되돌리는 유일한 길은 예외다."""

    def __init__(self, bad):
        self.bad = bad


if __name__ == "__main__":
    raise SystemExit(main())
