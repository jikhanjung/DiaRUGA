#!/usr/bin/env python3
"""SQLite 스키마를 **의미로** 견준다 (050 §5).

    python tools/schema_diff.py <A.db|A.json> <B.db|B.json>
    python tools/schema_diff.py --dump <db> -o schema.json

데스크탑 앱이 ORM 을 peewee 로 옮기면서 **제약을 흘리지 않았는지**를 사람 눈
대신 붙잡는 도구다. 표 15개 × 칼럼 수십 개를 눈으로 맞출 수는 없다.

**왜 글자 비교가 아닌가.** 같은 유일 제약을 Django 는 `CREATE TABLE` 안의
`CONSTRAINT … UNIQUE (…)` 로 만들고, peewee 는 별도 `CREATE UNIQUE INDEX` 로
만든다. 강제하는 효과는 같은데 스키마 텍스트가 다르다. 그래서 둘 다 모아
`(표, 칼럼 집합)` 으로 정규화한 뒤 견준다. 제약 **이름**도 무시한다 —
다르게 지어져도 기능은 같다. 다만 보고에는 적어 준다.

**형은 SQLite 친화도(affinity)로 견준다.** `bigint` 와 `integer` 는 둘 다
INTEGER 친화도라 SQLite 에게 같은 것이다. `varchar(120)` 과 `varchar(32)` 도
TEXT 로 같다 — 길이는 SQLite 가 강제하지 않는다. 선언 문자열까지 똑같아야
한다면 `--strict-types` 를 준다.

**Django 없이 돈다** (stdlib 만 쓴다). 그래야 데스크탑 쪽 CI 에서도 돌릴 수 있다.

기준을 JSON 으로 떠 두면 Django 를 설치하지 않은 자리에서도 견줄 수 있다:

    python tools/schema_diff.py --dump /srv/DiaRUGA/db/DiaRUGA.db -o docs/schema.json
    python tools/schema_diff.py docs/schema.json build/peewee.db
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

# 스키마 견주기에서 뺄 표. 장부용이라 두 쪽이 다른 것이 정상이다.
SKIP_PREFIX = ("sqlite_", "django_", "auth_", "migratehistory")


# ── SQLite 형 친화도 (공식 규칙) ─────────────────────────────────────
def affinity(decl: str) -> str:
    t = (decl or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in t or not t:
        return "BLOB"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


# ── CREATE TABLE 본문을 최상위 쉼표로 가른다 ─────────────────────────
def split_top_level(body: str) -> list[str]:
    """괄호와 따옴표 안의 쉼표는 건너뛴다."""
    parts, buf, depth, quote = [], [], 0, None
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'`":
            quote = ch
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def table_body(sql: str) -> str:
    """`CREATE TABLE x (…)` 의 바깥 괄호 안쪽."""
    i = sql.find("(")
    if i < 0:
        return ""
    depth, out = 0, []
    for ch in sql[i:]:
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        out.append(ch)
    return "".join(out)


def unquote(tok: str) -> str:
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] in "\"'`[" and tok[-1] in "\"'`]":
        return tok[1:-1]
    return tok


def col_list(chunk: str) -> list[str]:
    """`("a", "b")` → ['a', 'b']"""
    inner = chunk[chunk.find("(") + 1: chunk.rfind(")")]
    return [unquote(c).lower() for c in split_top_level(inner)]


def norm_check(expr: str) -> str:
    """CHECK 식을 견줄 수 있게 정규화한다.

    따옴표와 공백을 걷어 내고 소문자로. 양쪽에 같은 처리를 하므로 붙어 버리는
    것은 문제가 되지 않는다 — 견주는 것이 목적이지 읽는 것이 목적이 아니다.
    """
    e = re.sub(r'["`\[\]]', "", expr)
    e = re.sub(r"\s+", "", e)
    return e.lower()


def norm_default(v):
    if v is None:
        return None
    s = str(v).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    return s


# ── 스키마 읽기 ──────────────────────────────────────────────────────
def read_schema(db_path: str) -> dict:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out: dict[str, dict] = {}

    tables = [
        (r["name"], r["sql"] or "")
        for r in con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'")
        if not r["name"].lower().startswith(SKIP_PREFIX)
    ]

    for name, sql in sorted(tables):
        body = table_body(sql)
        parts = split_top_level(body)

        uniques: set[frozenset] = set()
        unique_names: dict[frozenset, str] = {}
        checks: set[str] = set()
        autoinc = "AUTOINCREMENT" in sql.upper()

        for p in parts:
            head = p.upper()
            m = re.match(r'CONSTRAINT\s+("?[^"\s]+"?)\s+(.*)', p, re.S)
            cname, rest = (unquote(m.group(1)), m.group(2)) if m else (None, p)
            rhead = rest.upper().lstrip()

            if rhead.startswith("UNIQUE"):
                cols = frozenset(col_list(rest))
                uniques.add(cols)
                if cname:
                    unique_names[cols] = cname
            elif rhead.startswith("CHECK"):
                checks.add(norm_check(rest[rest.find("("):]))
            elif rhead.startswith(("PRIMARY KEY", "FOREIGN KEY")):
                pass                      # PK 는 table_info, FK 는 pragma 로 본다
            elif not head.startswith(("CONSTRAINT", "UNIQUE", "CHECK",
                                      "PRIMARY", "FOREIGN")):
                # 칼럼 정의 — 칼럼에 직접 붙은 UNIQUE·CHECK 를 줍는다
                cn = unquote(split_top_level(p)[0].split()[0])
                if re.search(r"\bUNIQUE\b", p, re.I):
                    cols = frozenset([cn.lower()])
                    uniques.add(cols)
                for cm in re.finditer(r"\bCHECK\s*\(", p, re.I):
                    tail = p[cm.end() - 1:]
                    depth, buf = 0, []
                    for ch in tail:
                        buf.append(ch)
                        depth += (ch == "(") - (ch == ")")
                        if depth == 0:
                            break
                    checks.add(norm_check("".join(buf)))

        # 인덱스로 만들어진 유일 제약도 같은 자루에 담는다
        for r in con.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name=?", (name,)):
            if r["sql"] and re.search(r"\bUNIQUE\b", r["sql"], re.I):
                cols = frozenset(col_list(r["sql"]))
                uniques.add(cols)
                unique_names.setdefault(cols, r["name"])

        cols = {}
        for c in con.execute(f'PRAGMA table_info("{name}")'):
            cols[c["name"].lower()] = {
                "decl": c["type"],
                "affinity": affinity(c["type"]),
                "notnull": bool(c["notnull"]),
                "default": norm_default(c["dflt_value"]),
                "pk": c["pk"],
            }

        fks = sorted(
            [f'{f["from"].lower()}→{f["table"].lower()}.'
             f'{(f["to"] or "").lower()}|del={f["on_delete"]}|upd={f["on_update"]}'
             for f in con.execute(f'PRAGMA foreign_key_list("{name}")')])

        out[name] = {
            "columns": cols,
            "uniques": sorted(sorted(u) for u in uniques),
            "unique_names": {",".join(sorted(k)): v
                             for k, v in unique_names.items()},
            "checks": sorted(checks),
            "foreign_keys": fks,
            "autoincrement": autoinc,
        }
    con.close()
    return out


def load(path: str) -> dict:
    if path.endswith(".json"):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return read_schema(path)


# ── 견주기 ───────────────────────────────────────────────────────────
class Report:
    def __init__(self):
        self.fail: list[str] = []
        self.warn: list[str] = []

    def bad(self, msg):
        self.fail.append(msg)

    def note(self, msg):
        self.warn.append(msg)


def compare(a: dict, b: dict, strict_types: bool,
            allow_extra: bool = False) -> Report:
    """A 를 기준으로 B 를 견준다.

    `allow_extra` 면 **B 가 더 가진 것은 넘어간다** — 잃은 것만 실패다.
    DB 를 웹과 공유하지 않고 데스크탑만 쓰는 경우에 쓴다: 앱이 자기 표를
    더하는 것은 괜찮지만, `models.py` 가 들고 있던 제약을 흘리면 안 된다.
    **바뀐 것은 더한 것이 아니다** — 형·NOT NULL·기본값이 다르거나 외래키
    규칙이 달라지면 이 모드에서도 실패한다.
    """
    r = Report()
    ta, tb = set(a), set(b)
    extra = r.note if allow_extra else r.bad

    for t in sorted(ta - tb):
        r.bad(f"표가 B 에 없다: {t}")
    for t in sorted(tb - ta):
        extra(f"표가 A 에 없다: {t}" + (" (더한 것 — 넘어간다)" if allow_extra else ""))

    for t in sorted(ta & tb):
        A, B = a[t], b[t]
        ca, cb = A["columns"], B["columns"]

        for c in sorted(set(ca) - set(cb)):
            r.bad(f"{t}.{c} 칼럼이 B 에 없다")
        for c in sorted(set(cb) - set(ca)):
            extra(f"{t}.{c} 칼럼이 A 에 없다"
                  + (" (더한 것 — 넘어간다)" if allow_extra else ""))

        for c in sorted(set(ca) & set(cb)):
            x, y = ca[c], cb[c]
            key = "decl" if strict_types else "affinity"
            if x[key] != y[key]:
                r.bad(f"{t}.{c} 형이 다르다: {x[key]} ≠ {y[key]}")
            elif x["decl"] != y["decl"]:
                r.note(f"{t}.{c} 선언 문자열만 다르다: "
                       f"{x['decl']} vs {y['decl']} (친화도는 같다)")
            if x["notnull"] != y["notnull"]:
                r.bad(f"{t}.{c} NOT NULL 이 다르다: {x['notnull']} ≠ {y['notnull']}")
            if x["default"] != y["default"]:
                r.bad(f"{t}.{c} DB 기본값이 다르다: "
                      f"{x['default']!r} ≠ {y['default']!r}")
            if bool(x["pk"]) != bool(y["pk"]):
                r.bad(f"{t}.{c} 기본키 여부가 다르다")

        ua = {tuple(u) for u in A["uniques"]}
        ub = {tuple(u) for u in B["uniques"]}
        for u in sorted(ua - ub):
            r.bad(f"{t} 유일 제약이 B 에 없다: ({', '.join(u)})")
        for u in sorted(ub - ua):
            extra(f"{t} 유일 제약이 A 에 없다: ({', '.join(u)})")
        for u in sorted(ua & ub):
            k = ",".join(sorted(u))
            na = A["unique_names"].get(k)
            nb = B["unique_names"].get(k)
            if na != nb:
                r.note(f"{t} 유일 제약 ({', '.join(u)}) 의 이름만 다르다: "
                       f"{na} vs {nb}")

        for k in ("checks", "foreign_keys"):
            sa, sb = set(A[k]), set(B[k])
            label = "CHECK" if k == "checks" else "외래키"
            for x in sorted(sa - sb):
                r.bad(f"{t} {label} 가 B 에 없다: {x}")
            for x in sorted(sb - sa):
                # 외래키는 "더한 것" 으로 넘기지 않는다 — 같은 칼럼의 규칙이
                # 바뀐 것(ON DELETE 등)이 이 모양으로 나타나기 때문이다.
                (extra if k == "checks" else r.bad)(
                    f"{t} {label} 가 A 에 없다: {x}")

        if A["autoincrement"] != B["autoincrement"]:
            r.bad(f"{t} AUTOINCREMENT 가 다르다: "
                  f"{A['autoincrement']} ≠ {B['autoincrement']}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser(
        description="SQLite 스키마를 의미로 견준다 (050 §5)")
    ap.add_argument("left", help="A: .db 또는 --dump 로 뜬 .json")
    ap.add_argument("right", nargs="?", help="B: .db 또는 .json")
    ap.add_argument("--dump", action="store_true",
                    help="견주지 않고 A 의 스키마를 JSON 으로 뜬다")
    ap.add_argument("-o", "--out", help="--dump 의 출력 파일 (기본: 표준출력)")
    ap.add_argument("--strict-types", action="store_true",
                    help="친화도가 아니라 선언 문자열까지 같아야 한다")
    ap.add_argument("--allow-extra", action="store_true",
                    help="B 가 더 가진 표·칼럼·제약은 넘어간다 (잃은 것만 실패). "
                         "DB 를 공유하지 않고 데스크탑만 쓸 때")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="경고를 적지 않는다")
    args = ap.parse_args()

    if args.dump:
        js = json.dumps(read_schema(args.left), ensure_ascii=False,
                        indent=2, sort_keys=True, default=list)
        if args.out:
            Path(args.out).write_text(js + "\n", encoding="utf-8")
            print(f"{args.left} → {args.out}")
        else:
            print(js)
        return 0

    if not args.right:
        ap.error("견주려면 B 도 줘야 한다 (또는 --dump)")

    r = compare(load(args.left), load(args.right), args.strict_types,
                args.allow_extra)

    if r.warn and not args.quiet:
        print(f"경고 {len(r.warn)}건 — 기능은 같다")
        for w in r.warn:
            print(f"  · {w}")
        print()

    if r.fail:
        print(f"스키마가 다르다 — {len(r.fail)}건")
        for f in r.fail:
            print(f"  ✗ {f}")
        return 1

    print("스키마가 같다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
