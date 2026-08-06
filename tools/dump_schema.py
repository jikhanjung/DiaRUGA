#!/usr/bin/env python
"""SQLite 스키마를 `docs/schema-reference.json` 으로 뜬다.

**손으로 고치는 문서가 아니다.** DB 명세·ERD 는 사람이 읽으라고 쓴 글이고 이것은
**실제로 박혀 있는 것**이다 — 둘이 어긋나면 이쪽이 맞다. 스키마를 바꾼 뒤에
다시 돌린다.

    python tools/dump_schema.py                 # 운영 DB(.env 의 DIARUGA_DB)에서
    python tools/dump_schema.py --db <사본>

**읽기 전용으로 연다.** `backup_db.py`·`export_review.py` 와 같은 자리다 —
Django 를 임포트하지 않아 "같은 파일을 두 벌의 환경이 만진다" 가 생기지 않는다.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "schema-reference.json"


def env_db() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DIARUGA_DB="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("DIARUGA_DB", str(ROOT / "DiaRUGA.db"))


def dump(db: str) -> dict:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    out = {}
    names = [r[0] for r in c.execute(
        "select name from sqlite_master where type='table' "
        "and name not like 'sqlite_%' and name not like 'django_%' order by name")]
    for t in names:
        sql = c.execute("select sql from sqlite_master where name=?",
                        (t,)).fetchone()[0] or ""
        cols = {}
        for r in c.execute(f"pragma table_info('{t}')"):
            decl = r["type"]
            cols[r["name"]] = {
                # SQLite 의 형 친화도. 선언형과 다를 수 있어 둘 다 적는다
                "affinity": affinity(decl),
                "decl": decl,
                "default": r["dflt_value"],
                "notnull": bool(r["notnull"]),
                "pk": r["pk"],
            }
        fks = [f'{r["from"]}→{r["table"]}.{r["to"]}|del={r["on_delete"]}'
               f'|upd={r["on_update"]}'
               for r in c.execute(f"pragma foreign_key_list('{t}')")]
        uniques, unique_names = [], {}
        for r in c.execute(f"pragma index_list('{t}')"):
            if not r["unique"]:
                continue
            fields = [x["name"] for x in
                      c.execute(f"pragma index_info('{r['name']}')")]
            uniques.append(fields)
            # 이름이 있는 것(제약에 이름을 준 것)만 따로 적는다 — 마이그레이션이
            # 그 이름으로 떼고 붙인다
            if not r["name"].startswith("sqlite_autoindex"):
                unique_names[r["name"]] = fields
        out[t] = {
            "autoincrement": "AUTOINCREMENT" in sql.upper()
                             or any(v["pk"] and v["affinity"] == "INTEGER"
                                    for v in cols.values()),
            "checks": [x.strip() for x in checks(sql)],
            "columns": dict(sorted(cols.items())),
            "foreign_keys": sorted(fks),
            "unique_names": unique_names,
            "uniques": sorted(uniques),
        }
    c.close()
    return out


def affinity(decl: str) -> str:
    d = (decl or "").upper()
    if "INT" in d:
        return "INTEGER"
    if any(x in d for x in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in d or not d:
        return "BLOB"
    if any(x in d for x in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def checks(sql: str) -> list:
    """`CHECK (...)` 를 뽑는다. 괄호 짝을 세어 자른다 — 안에 괄호가 있다."""
    out, up = [], sql.upper()
    i = 0
    while True:
        i = up.find("CHECK", i)
        if i < 0:
            return out
        j = sql.find("(", i)
        if j < 0:
            return out
        depth, k = 0, j
        while k < len(sql):
            if sql[k] == "(":
                depth += 1
            elif sql[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append("".join(sql[j:k + 1].split()))
        i = k


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    db = args.db or env_db()
    if not Path(db).is_file():
        raise SystemExit(f"DB 가 없다: {db}")
    data = dump(db)
    Path(args.out).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"{args.out} — 테이블 {len(data)}개 ({db})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
