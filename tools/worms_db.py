#!/usr/bin/env python3
"""내려받은 WoRMS 전체(DwC-A)에서 규조만 뽑아 SQLite 로 세운다 (P15).

**왜 로컬인가.** REST 는 **정확 매칭과 TAXAMATCH 흐린 매칭**만 답한다 — 못
찾으면 204 이고 왜 없는지는 안 말한다. 덤프가 있으면 **찾는 방식을 내가
고른다**: 움라우트를 접고, 종소명 어간으로 훑고, 변종·품종까지 본다.
REST 로는 못 하던 것 셋이 여기서 된다.

- **변종·품종이 보인다.** REST 는 종까지만 답했는데 덤프에는 변종 1,712 ·
  품종 377 이 있다. 대조표의 `var.` 104건이 여기서 갈린다 (13건이 걸렸다)
- **철자를 접어 맞춘다.** `Terpsinoe` → `Terpsinoë`, `Raphoneis` →
  `Rhaphoneis` 를 조회 없이 짚는다
- **속의 종을 통째로 훑는다.** "속은 있는데 종이 없다" 를 눈으로 확인할 수 있다

**덤프는 REST 를 대신하지 않는다 — 재배포가 막힌 자료가 빠져 있다.**
내려받기 안내가 *"data originating from AlgaeBase is excluded, since the license
does not allow redistribution"* 라고 적고 있고, 규조는 그 비중이 큰 분류군이다.
실측으로 **REST 가 확정한 3,153건의 38.1% 만** 담고 있다.

**"해양만 담았다" 가 아니다** — 덤프에 담수 전용 규조가 175건 있다
(*Asterionella formosa* 등). 서식지가 아니라 **출처로 걸러진 것**이라
`usersrequest.php` 로 전체 사본을 받아도 이 자리는 안 채워진다.

그래서 여기서 **없다**는 것은 REST 에서 없다는 것보다 약한 말이다 — 근거로
쓸 때 어느 쪽에서 없었는지를 함께 적는다. `--against` 가 걸린 것만 적고
안 걸린 것을 빈칸으로 두는 이유다.

## 함정

- **`fieldsEnclosedBy="`" 다.** 줄을 `split('\\t')` 로 가르면 인용부호 안의 탭에
  걸린다 — `csv` 로 읽는다. 줄바꿈도 `\\r\\n` 이라 `newline=""` 이 필요하다
- **`scientificName` 에 저자가 없다.** 저자는 `scientificNameAuthorship` 이
  따로 든다. 이름만으로 짚으면 된다
- **`class` 가 빈 줄이 있다** (상위 계급·불확실 자리). 규조를 `class` 로만
  거르면 그런 줄이 빠진다 — `phylum` 도 함께 본다

사용:

    python tools/worms_db.py                      # names/db 아래에 세운다
    python tools/worms_db.py --scope              # 세운 것이 얼마나 넓은지 잰다
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import unicodedata
from pathlib import Path

DB_DIR = Path("/nfs/temp-share/DiaRUGA/Diadiction/names/db")
DWCA = DB_DIR / "worms_dwca_20260701"
OUT = DB_DIR / "worms_diatoms_20260701.db"

DIATOM_CLASS = "Bacillariophyceae"
DIATOM_PHYLUM = "Bacillariophyta"

KEEP = ["taxonID", "scientificName", "acceptedNameUsage", "acceptedNameUsageID",
        "kingdom", "phylum", "class", "order", "family", "genus", "subgenus",
        "specificEpithet", "infraspecificEpithet", "taxonRank",
        "scientificNameAuthorship", "taxonomicStatus", "nomenclaturalStatus",
        "namePublishedInYear", "modified", "references"]
PROFILE = ["isMarine", "isFreshwater", "isBrackish", "isTerrestrial", "isExtinct"]


def fold(s: str) -> str:
    """맞춰 볼 때 쓰는 모양 — 소문자로 내리고 발음기호를 뗀다.

    `Terpsinoë` 와 `Terpsinoe` 가 같은 자리에 서야 한다. 독일어 `ö`→`o` 는
    엄밀히는 `oe` 지만, 여기서는 **양쪽을 다 만들어 둔다**(`fold` 와
    `fold_de`) — 어느 쪽으로 흘렸는지가 자료마다 다르다.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def fold_de(s: str) -> str:
    """독일어식 — `ö`→`oe`. OCR 이 `moelleri`/`mölleri` 를 오간다."""
    tr = str.maketrans({"ö": "oe", "ä": "ae", "ü": "ue", "Ö": "oe",
                        "Ä": "ae", "Ü": "ue", "ß": "ss"})
    return fold((s or "").translate(tr))


def build(dwca: Path, out: Path) -> None:
    csv.field_size_limit(10 ** 9)

    profile: dict[str, dict] = {}
    with (dwca / "speciesprofile.txt").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t", quotechar='"'):
            profile[row["taxonID"]] = row
    print(f"speciesprofile {len(profile):,}줄")

    out.unlink(missing_ok=True)
    db = sqlite3.connect(out)
    cols = KEEP + PROFILE + ["name_fold", "name_fold_de", "genus_fold", "epithet_fold"]
    # `order` 는 SQL 예약어다 — 칸 이름을 따옴표로 감싼다 (DwC 용어를 그대로 쓴다)
    db.execute(f"CREATE TABLE taxon ({', '.join(f'\"{c}\" TEXT' for c in cols)})")

    n = kept = 0
    batch = []
    with (dwca / "taxon.txt").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t", quotechar='"'):
            n += 1
            # `class` 가 빈 상위 계급 줄이 있어 `phylum` 도 본다
            if row.get("class") != DIATOM_CLASS and row.get("phylum") != DIATOM_PHYLUM:
                continue
            kept += 1
            p = profile.get(row["taxonID"], {})
            name = row.get("scientificName") or ""
            batch.append([row.get(c) for c in KEEP] + [p.get(c) for c in PROFILE]
                         + [fold(name), fold_de(name), fold(row.get("genus") or ""),
                            fold(row.get("specificEpithet") or "")])
            if len(batch) >= 5000:
                db.executemany(f"INSERT INTO taxon VALUES ({','.join('?' * len(cols))})",
                               batch)
                batch.clear()
    if batch:
        db.executemany(f"INSERT INTO taxon VALUES ({','.join('?' * len(cols))})", batch)

    for idx, col in [("i_name", "name_fold"), ("i_name_de", "name_fold_de"),
                     ("i_genus", "genus_fold"), ("i_ep", "epithet_fold"),
                     ("i_id", "taxonID")]:
        db.execute(f"CREATE INDEX {idx} ON taxon({col})")
    db.commit()
    print(f"taxon.txt {n:,}줄 중 규조 {kept:,}줄 → {out}")


def scope(out: Path) -> None:
    """세운 것이 얼마나 넓은가. **덤프의 '없음' 을 근거로 쓰기 전에 본다.**"""
    db = sqlite3.connect(out)
    db.row_factory = sqlite3.Row
    q = db.execute("SELECT taxonRank, COUNT(*) n FROM taxon "
                   "GROUP BY taxonRank ORDER BY n DESC").fetchall()
    print("계급:", "  ".join(f"{r['taxonRank']} {r['n']:,}" for r in q))
    q = db.execute("SELECT taxonomicStatus s, COUNT(*) n FROM taxon "
                   "GROUP BY s ORDER BY n DESC LIMIT 6").fetchall()
    print("상태:", "  ".join(f"{r['s']} {r['n']:,}" for r in q))
    for col in PROFILE:
        one = db.execute(f"SELECT COUNT(*) FROM taxon WHERE {col}='1'").fetchone()[0]
        print(f"  {col:16s} {one:,}")
    print("\n**빠진 것은 AlgaeBase 출처다** (재배포 불가). 담수 전용이 175건 들어 "
          "있으니 서식지로 거른 것이 아니다 — '덤프에 없다' 를 'WoRMS 에 없다' 로 "
          "읽으면 안 된다")


def against(out: Path, master: Path) -> None:
    """대조표의 모든 이름을 덤프로 한 번 더 물어 `덤프` 칸을 채운다.

    **덤프에 없다고 판정을 뒤집지 않는다** — AlgaeBase 출처가 빠져 REST 가
    확정한 것의 38%만 담고 있다(머리말). 여기서 얻는 것은 **한쪽 방향뿐**이다:
    걸리면 다른 출처가 같은 말을 한 것이고, 안 걸리면 아무 말도 아니다.

    그래도 값이 있다 — 변종은 REST 가 답한 적이 없고(종까지만 물었다), "색인
    쓰레기" 로 지울 것들이 **다른 출처에도 없다**는 것은 지우기 전에 볼 만하다.
    """
    db = sqlite3.connect(out)
    db.row_factory = sqlite3.Row
    lines = master.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    col = "덤프(20260701)"
    if col in head:
        at = head.index(col)
    else:
        head.append(col)
        at = len(head) - 1
    rows = []
    hit = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        cells += [""] * (len(head) - len(cells))
        f = fold(cells[0])
        r = db.execute("SELECT scientificName, taxonRank, taxonomicStatus, "
                       "acceptedNameUsage FROM taxon WHERE name_fold=? OR name_fold_de=? "
                       "LIMIT 1", (f, f)).fetchone()
        if r:
            hit += 1
            same = (r["acceptedNameUsage"] or "") == r["scientificName"]
            cells[at] = (f"{r['taxonRank']} · {r['taxonomicStatus']}"
                         + ("" if same or not r["acceptedNameUsage"]
                            else f" → {r['acceptedNameUsage']}"))
        else:
            cells[at] = ""     # **비운다. "없다" 가 아니라 "이 판에는 없다" 다**
        rows.append(cells)
    master.write_text("\t".join(head) + "\n"
                      + "".join("\t".join(c) + "\n" for c in rows), encoding="utf-8")
    print(f"{master.name}: {len(rows):,}줄 중 {hit:,}줄이 덤프에도 있다")
    kinds: dict[str, int] = {}
    for c in rows:
        if c[at]:
            kinds[c[at].split(" · ")[0]] = kinds.get(c[at].split(" · ")[0], 0) + 1
    print("  계급별:", "  ".join(f"{k} {v}" for k, v in sorted(kinds.items(),
                                                            key=lambda x: -x[1])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dwca", type=Path, default=DWCA)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--scope", action="store_true", help="세운 것만 재고 안 세운다")
    ap.add_argument("--against", type=Path, help="이 대조표에 `덤프` 칸을 채운다")
    args = ap.parse_args()
    if args.against:
        against(args.out, args.against)
        return 0
    if not args.scope:
        if not args.dwca.exists():
            print(f"푼 자리를 못 찾는다: {args.dwca}", file=sys.stderr)
            return 2
        build(args.dwca, args.out)
    scope(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
