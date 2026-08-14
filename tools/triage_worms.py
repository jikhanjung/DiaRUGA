#!/usr/bin/env python3
"""WoRMS 대조 결과 다섯 표를 한 표로 모으고 다시 가른다 (P15).

**왜 필요한가.** 08-13 에 같은 폴더에 조회 결과가 **두 벌** 생겼다 —
`harvest_worms.py` 가 낸 `worms_20260813.json`(색인 이름 1,845개, 이름마다
`atlases` 로 **도감 출처를 들고 있다**)과, 그것을 신뢰도로 가른 표 다섯
(4,003개). **표 다섯은 도감 출처를 안 실었고**, 색인에 없는 이름 2,219개가
함께 들어 있다. 반입 수는 "도감에 실린 이름" 이 기준이라 그대로는 못 센다.

**아무것도 안 버린다.** 나오는 것은 두 출처를 합친 표 하나이고, 어느 이름이든
한 줄로 남는다. 지울 것으로 판정된 것도 줄이 남고 `재판정` 칸이 왜 그런지를
말한다 — 지운 뒤에 되돌아보려면 지운 것이 어디 있는지부터 알아야 한다.

## 다시 가르는 이유

`index_remove` 의 규칙 둘이 넓어서 **진짜 학명을 지우고 있었다**(08-14 확인).

- **`schmidt` 가 들어가면 저자명 조각으로 봤다** — 그런데 `-ii` 로 끝나는 것은
  Schmidt 를 기린 정당한 종소명이다. `Amphora schmidtii`(accepted)를 비롯해
  여섯이 그렇게 지워졌다. OCR 부스러기는 `sehmidt`·`schmidts`·`scamidt` 쪽이다
- **종소명이 짧으면 잘린 낱말로 봤다** — `Planktoniella sol`·`Ditylum sol` 의
  `sol` 은 실재하는 종소명이다

그래서 **지울 후보 전부를 WoRMS 에 다시 묻는다.** 규칙을 손보는 것으로는 다음
판에서 또 샌다 — 근거로 가른다. `harvest_worms.py` 와 같은 조건으로 묻는다
(`marine_only=false&extant_only=false` · `class == Bacillariophyceae`).
**화석을 빠뜨리는 함정은 그 파일 머리말에 있다.**

## 함정

- **`absent` 는 "WoRMS 에 없는 이름" 이 아니다.** 대부분 색인 파싱 부스러기이고
  (잘린 낱말·지명·독일어), 진짜 종도 섞여 있다(`Rouxia leventerae`). 갈라 놓지
  않으면 "없음" 을 오기로 읽는다. **다만 "담수라 빠졌다" 는 성립하지 않는다** —
  근거는 `why_missing` 머리말에 있다
- **`species_1845.tsv` 를 입력으로 쓰지 않는다.** 그것도 JSON 에서 나온 사본이라
  한 겹 멀다. 도감 출처의 원본은 JSON 의 `atlases` 다

사용:

    python tools/triage_worms.py            # 기본 자리가 names/worms 다
    python tools/triage_worms.py --out-dir /tmp/x --no-recheck   # 안 묻고 가르기만
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# 2026-08-14 에 `temp/` 에서 옮겼다 — 그 자리는 "언제든 비워도 됨" 이라
# 적혀 있는데 다시 못 만드는 것이 아흐레째 살고 있었다 (Diadiction/README.md)
NAMES = Path("/nfs/temp-share/DiaRUGA/Diadiction/names/worms")
API = "https://www.marinespecies.org/rest/AphiaRecordsByNames"
API_ONE = "https://www.marinespecies.org/rest/AphiaRecordsByName"
API_FUZZY = "https://www.marinespecies.org/rest/AphiaRecordsByMatchNames"
DIATOM_CLASS = "Bacillariophyceae"
BATCH = 50

STAMP_IN = "20260813"

# 다섯 표. 값은 (파일 접미사, 첫 칸 이름, 나머지 칸 이름들).
TABLES = {
    "confirmed":       ("worms_confirmed",       "학명",
                        ["저자", "상태", "유효명", "과", "목", "화석", "담수", "해수",
                         "AphiaID", "갱신"]),
    "needs_review":    ("worms_needs_review",    "입력명",
                        ["WoRMS 표제", "저자", "매칭유형", "상태", "유효명", "사유"]),
    "absent":          ("worms_absent",          "이름",  ["속"]),
    "index_remove":    ("index_remove",          "이름",  ["사유"]),
    "mismatch_dropped": ("worms_mismatch_dropped", "입력명", ["WoRMS가 준 것", "사유"]),
}

# 나오는 표의 칸. **원본 칸을 하나도 안 버린다** — 다섯 표의 칸이 서로 달라
# 합집합을 쓴다. 안 채워지는 자리는 빈칸이다.
OUT_COLS = [
    "이름", "도감", "원표", "재판정", "근거",
    "내조회", "AphiaID", "상태", "유효명", "저자", "과", "목",
    "화석", "담수", "해수", "갱신",
    "WoRMS표제", "매칭유형", "WoRMS가준것", "속", "원사유",
    # 없는 이름을 가르는 자리 (아래 `왜 없나` 절)
    "왜없나", "속상태", "속성격", "흐린매칭",
    # **사람이 채우는 칸이다.** AlgaeBase 는 자동으로 못 열어(Turnstile) 다른
    # 경로로 조금씩 모으고 있다 — 판정의 원본은 `md/name_validity_log.md` 이고
    # 여기는 이름으로 이어 붙일 자리로 비워 둔다
    "AlgaeBase",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        cells += [""] * (len(head) - len(cells))
        rows.append(dict(zip(head, cells)))
    return rows


def ask(batch: list[str], retries: int = 3) -> list[list[dict]]:
    """harvest_worms.ask 와 같은 조건으로 묻는다 (화석 포함)."""
    q = "&".join("scientificnames%5B%5D=" + urllib.parse.quote(n) for n in batch)
    url = f"{API}?{q}&marine_only=false&extant_only=false"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return [(x or []) for x in json.loads(r.read().decode())]
        except Exception as exc:
            if attempt == retries - 1:
                print(f"  ! {batch[0]}… {type(exc).__name__}: {exc}", file=sys.stderr)
                return [[] for _ in batch]
            time.sleep(2 ** attempt)
    return [[] for _ in batch]


def recheck(names: list[str], cache: Path, sleep: float) -> dict[str, list[dict]]:
    """지울 후보를 다시 묻는다. **없는 것도 자료라** 캐시에 함께 남긴다."""
    done: dict[str, list[dict]] = {}
    if cache.exists():
        done = json.loads(cache.read_text(encoding="utf-8"))
        print(f"이미 물어 둔 것 {len(done)}개 — 건너뛴다")
    todo = [n for n in names if n not in done]
    print(f"다시 물을 것 {len(todo)}개")
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        for name, recs in zip(batch, ask(batch)):
            done[name] = [
                {k: r.get(k) for k in ("AphiaID", "scientificname", "authority",
                                       "status", "valid_name", "family", "order",
                                       "isExtinct", "isMarine", "isFreshwater")}
                for r in recs if r.get("class") == DIATOM_CLASS
            ]
        cache.write_text(json.dumps(done, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")
        time.sleep(sleep)
    return done


def ask_genus(genera: list[str], cache: Path, sleep: float) -> dict[str, dict]:
    """속을 하나씩 묻는다. **없는 것도 남긴다.**

    종이 안 나올 때 남는 근거가 이것뿐이다 — 속조차 없으면 속 철자가 어긋난
    것이고, 속은 있는데 종이 없으면 WoRMS 가 그 종을 아직 안 담은 것이다.
    """
    done: dict[str, dict] = {}
    if cache.exists():
        done = json.loads(cache.read_text(encoding="utf-8"))
    todo = [g for g in genera if g not in done]
    print(f"속을 물을 것 {len(todo)}개")
    for i, g in enumerate(todo, 1):
        url = f"{API_ONE}/{urllib.parse.quote(g)}?like=false&marine_only=false&extant_only=false"
        rec = None
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                if r.status == 200:
                    for x in json.loads(r.read().decode()):
                        if x.get("rank") == "Genus":
                            rec = {k: x.get(k) for k in ("scientificname", "status",
                                                         "class", "family",
                                                         "isExtinct", "AphiaID")}
                            if x.get("class") == DIATOM_CLASS:
                                break
        except Exception as exc:
            print(f"  ! {g} {type(exc).__name__}", file=sys.stderr)
        if rec is None:
            # 속조차 없으면 **속 표기를 의심한다.** TAXAMATCH 가 움라우트·철자를
            # 되짚어 준다 — `Terpsinoe`→`Terpsinoë`[exact], `Raphoneis`→
            # `Rhaphoneis`[phonetic]. `harvest_worms.GENUS_FIX` 가 손으로 적어
            # 둔 것을 여기서는 물어서 얻는다
            try:
                url = (f"{API_FUZZY}?scientificnames%5B%5D={urllib.parse.quote(g)}"
                       f"&marine_only=false")
                with urllib.request.urlopen(url, timeout=30) as r:
                    if r.status == 200:
                        for grp in json.loads(r.read().decode()):
                            for x in (grp or []):
                                if x.get("class") == DIATOM_CLASS:
                                    rec = {"scientificname": x.get("scientificname"),
                                           "status": x.get("status"),
                                           "class": x.get("class"),
                                           "isExtinct": x.get("isExtinct"),
                                           "AphiaID": x.get("AphiaID"),
                                           "_흐림": x.get("match_type")}
                                    break
                            if rec:
                                break
            except Exception:
                pass
        done[g] = rec or {}
        if i % 20 == 0 or i == len(todo):
            cache.write_text(json.dumps(done, ensure_ascii=False, indent=1),
                             encoding="utf-8")
            print(f"  {i}/{len(todo)}")
        time.sleep(sleep)
    cache.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    return done


def ask_fuzzy(names: list[str], cache: Path, sleep: float) -> dict[str, list[dict]]:
    """흐린 매칭을 다시 묻는다. **204(내용 없음)도 자료다** — 오타조차 아니라는 뜻이다."""
    done: dict[str, list[dict]] = {}
    if cache.exists():
        done = json.loads(cache.read_text(encoding="utf-8"))
    todo = [n for n in names if n not in done]
    print(f"흐린 매칭을 물을 것 {len(todo)}개")
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        q = "&".join("scientificnames%5B%5D=" + urllib.parse.quote(n) for n in batch)
        groups: list[list[dict]] = [[] for _ in batch]
        try:
            with urllib.request.urlopen(
                    f"{API_FUZZY}?{q}&marine_only=false", timeout=60) as r:
                if r.status == 200:
                    got = json.loads(r.read().decode())
                    groups = [(x or []) for x in got] + [[]] * (len(batch) - len(got))
        except Exception as exc:
            print(f"  ! {batch[0]}… {type(exc).__name__}", file=sys.stderr)
        for name, recs in zip(batch, groups):
            done[name] = [{k: r.get(k) for k in ("scientificname", "match_type",
                                                 "status", "class", "AphiaID")}
                          for r in recs if r.get("class") == DIATOM_CLASS]
        cache.write_text(json.dumps(done, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")
        time.sleep(sleep)
    return done


def why_missing(name: str, genus_rec: dict, fuzzy: list[dict],
                genus_habit: str, elsewhere: list[str]) -> tuple[str, str]:
    """WoRMS 에 없는 이름이 **왜** 없는지를 근거로 가른다.

    **"담수라 빠졌다" 는 성립하지 않는다** (08-14 실측). 도감별 적중률이
    Schmidt 89.1% · 한국(담수조류 도감) 90.5% · 동남극 93.9% 로 거의 같고,
    확정된 것 중 담수만 799건이다 — DiatomBase 가 담수를 덮는다. 화석도
    `extant_only=false` 로 들어온다(119). 서식지로는 못 가른다.

    **화석은 절반만 성립한다.** 종은 들어오지만 **화석속은 종까지 다 등재되어
    있지 않다** — 그래서 속의 `isExtinct` 를 근거로만 쓰고, 그 이름이 진짜라는
    뜻으로는 안 쓴다(`Trinacria halb` 같은 부스러기가 같은 칸에 들어온다).

    실제로 가르는 것은 **속이다** — 있는가, 표기가 어긋났는가, 화석속인가.
    """
    if fuzzy:
        f = fuzzy[0]
        return "오기로 보인다", f"흐린 매칭이 걸린다 — {f['scientificname']} [{f['match_type']}]"
    if not genus_rec:
        return "속이 없다", "속조차 WoRMS 에 없다 — 속 철자부터 본다"
    if genus_rec.get("class") != DIATOM_CLASS:
        return "속이 규조가 아니다", f"{genus_rec['scientificname']} 는 {genus_rec.get('class')} 다"
    if genus_rec.get("_흐림"):
        return "속 표기가 어긋난다", (
            f"속을 {genus_rec['scientificname']} 로 고쳐 다시 물어야 한다 "
            f"[{genus_rec['_흐림']}]")
    tail = f" · 그 속의 확정종은 {genus_habit}" if genus_habit else ""
    # **딱 한 속에만 있을 때만 근거다.** `vulgaris`·`major`·`affinis` 처럼 흔한
    # 라틴어는 여러 속에 널려 있어 속을 잘못 붙였다는 증거가 못 된다 —
    # 넓게 잡으면 종소명 길이로 자르던 것과 같은 실수가 된다
    if len({n.split()[0] for n in elsewhere}) == 1:
        return "속 표기를 의심한다", (
            f"이 종소명은 다른 속 하나에만 있다 — {', '.join(sorted(elsewhere)[:3])}{tail}")
    if genus_rec.get("isExtinct"):
        return "화석속이라 종이 덜 담겼다", f"{genus_rec['scientificname']} 는 화석속이다{tail}"
    return "속은 있는데 종이 없다", (
        f"{genus_rec['scientificname']} 는 있다 — 흐린 매칭도 안 걸리니 "
        f"WoRMS 가 안 담은 종이거나 색인 쪽 오기다{tail}")


def epithet(name: str) -> str:
    parts = name.split()
    return parts[1].lower() if len(parts) > 1 else ""


def judge_absent(name: str, genera: set[str],
                 longer: dict[str, list[str]]) -> tuple[str, str]:
    """`absent` 를 가른다. **길이는 근거가 아니다.**

    "종소명이 짧으면 잘린 낱말" 은 틀린 전제다 — `sol`·`ovum`·`flos`·`major`·
    `nova`·`curta` 가 전부 정당한 종소명이다. 잘렸다고 말하려면 **무엇이
    잘렸는지**를 짚어야 한다: 같은 속에 그 종소명으로 시작하는 더 긴 이름이
    있어야 잘린 것이고, 그때 근거에 그 이름을 적는다.
    """
    ep = epithet(name)
    if " var. " in name:
        return "사람이 본다", "변종 — WoRMS 는 종까지만 받는다"
    if ep.capitalize() in genera:
        return "색인 쓰레기", "속 이름이 종소명 자리에 왔다 (파싱 오류)"
    full = longer.get(name)
    if full:
        return "색인 쓰레기", f"잘린 낱말 — {', '.join(full[:3])} 의 앞부분이다"
    return "사람이 본다", "WoRMS 에 없다 — 오기이거나 담수·화석 종이다"


def truncations(names: set[str], corpus: set[str]) -> dict[str, list[str]]:
    """이름마다 "같은 속에서 이것으로 시작하는 더 긴 이름" 을 찾는다.

    자기 자신은 뺀다. 이것이 있을 때만 잘렸다고 말할 수 있다.
    """
    by_genus: dict[str, list[str]] = collections.defaultdict(list)
    for n in corpus:
        parts = n.split()
        if len(parts) >= 2:
            by_genus[parts[0]].append(parts[1].lower())
    out: dict[str, list[str]] = {}
    for n in names:
        parts = n.split()
        if len(parts) < 2:
            continue
        genus, ep = parts[0], parts[1].lower()
        hit = sorted({f"{genus} {e}" for e in by_genus.get(genus, [])
                      if e != ep and e.startswith(ep)})
        if hit:
            out[n] = hit
    return out


# OCR 이 Schmidt 를 흘린 모양들. `schmidtii`·`schmidti` 는 **여기 없다** —
# 그것은 사람 이름을 기린 정당한 종소명이다.
AUTHOR_FRAGMENT = re.compile(r"^(s[ce][ch]?[mn][ai]?[iu]?d?t?s?|schmidts)$")


def judge_index_remove(name: str, reason: str, hits: list[dict]) -> tuple[str, str]:
    if hits:
        r = hits[0]
        return "되살린다", (f"WoRMS 에 있다 — {r['scientificname']} "
                        f"({r.get('authority') or '저자 없음'}, {r.get('status')}, "
                        f"AphiaID {r.get('AphiaID')})")
    ep = epithet(name)
    if ep.startswith("schmidt") and not AUTHOR_FRAGMENT.match(ep):
        return "사람이 본다", "저자명 조각으로 지웠지만 정당한 종소명 모양이다 (철자 변형 의심)"
    # **"짧으면 잘린 낱말" 도 틀린 전제다.** `sol` 이 그렇다 — `Planktoniella sol`
    # 은 조회로 건졌지만 `Ditylium sol` 은 **속 철자가 어긋나** 못 찾았다.
    # 조회 한 번으로는 안 걷히니 규칙 쪽에서 사람에게 넘긴다. `sp.` 만 확실하다
    if "너무 짧음" in reason and not name.rstrip().endswith("sp."):
        return "사람이 본다", "짧다는 이유로 지웠지만 짧은 종소명도 정당하다 (속 철자 확인)"
    return "색인 쓰레기", reason


def judge_needs_review(row: dict) -> tuple[str, str]:
    kind = row.get("매칭유형", "")
    if kind == "match_quarantine":
        return "격리", "WoRMS 내부 격리 레코드 — 대조할 표제가 없다"
    if kind in ("near_1", "phonetic"):
        return "오타교정 제안", f"{kind} — 입력 오기로 보인다. 표제를 확인만 한다"
    return "사람이 본다", f"{kind} — 느슨한 매칭이라 사람이 가른다"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--temp", type=Path, default=NAMES, help="표 다섯이 있는 폴더")
    ap.add_argument("--out-dir", type=Path, default=NAMES, help="결과를 쓸 폴더")
    ap.add_argument("--stamp", default="20260814", help="나오는 파일의 날짜")
    ap.add_argument("--no-recheck", action="store_true", help="WoRMS 를 안 묻는다")
    ap.add_argument("--sleep", type=float, default=0.5)
    args = ap.parse_args()

    if not args.temp.exists():
        print(f"폴더를 못 찾는다: {args.temp} — NAS 공유가 안 붙었다", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 다섯 표
    tables = {}
    for key, (stem, first, _) in TABLES.items():
        rows = read_tsv(args.temp / f"{stem}_{STAMP_IN}.tsv")
        tables[key] = {r[first]: r for r in rows if r.get(first)}
        print(f"{key:18s} {len(rows)}줄")

    # 2) 도감 출처의 원본 — harvest_worms 가 낸 JSON
    harvest = json.loads((args.temp / f"worms_{STAMP_IN}.json").read_text(encoding="utf-8"))
    print(f"harvest JSON       {len(harvest)}개 (도감 출처가 여기 있다)")

    # 3) 지울 후보를 다시 묻는다
    drop_candidates = sorted(tables["index_remove"])
    hits: dict[str, list[dict]] = {}
    if not args.no_recheck:
        hits = recheck(drop_candidates, args.out_dir / f"worms_recheck_{args.stamp}.json",
                       args.sleep)
    else:
        cache = args.out_dir / f"worms_recheck_{args.stamp}.json"
        if cache.exists():
            hits = json.loads(cache.read_text(encoding="utf-8"))

    # 4) 한 표로 모은다. **어느 출처에 있든 한 줄은 남는다**
    genera = {n.split()[0] for n in tables["confirmed"]} | {
        r.get("속", "") for r in tables["absent"].values()}
    genera.discard("")

    every = set().union(*(t.keys() for t in tables.values())) | set(harvest)

    # 잘렸다고 말할 근거를 모은다. 비교 대상은 **WoRMS 가 실재를 확인해 준
    # 이름들**이다 — 색인끼리 비교하면 부스러기가 부스러기를 증명한다
    real = set(tables["confirmed"]) | {
        r["유효명"] for r in tables["confirmed"].values() if r["유효명"]} | {
        r["WoRMS 표제"] for r in tables["needs_review"].values() if r["WoRMS 표제"]}
    cut = truncations(set(tables["absent"]), real)
    out: list[dict[str, str]] = []
    for name in sorted(every):
        row = {c: "" for c in OUT_COLS}
        row["이름"] = name

        h = harvest.get(name)
        if h is not None:
            row["도감"] = "·".join(h.get("atlases", []))
            row["내조회"] = f"찾음 {len(h['records'])}건" if h.get("records") else "못 찾음"
        else:
            row["내조회"] = "조회 안 함 (색인에 없는 이름)"

        where = [k for k in TABLES if name in tables[k]]
        row["원표"] = "·".join(where) if where else "(다섯 표에 없음)"

        if "confirmed" in where:
            s = tables["confirmed"][name]
            row.update({"AphiaID": s["AphiaID"], "상태": s["상태"], "유효명": s["유효명"],
                        "저자": s["저자"], "과": s["과"], "목": s["목"],
                        "화석": s["화석"], "담수": s["담수"], "해수": s["해수"],
                        "갱신": s["갱신"]})
            row["재판정"] = "확정"
            row["근거"] = ("이름이 바뀐다" if s["유효명"] and s["유효명"] != name
                         else "유효명 칸이 비었다" if not s["유효명"] else "그대로 쓴다")
        elif "needs_review" in where:
            s = tables["needs_review"][name]
            row.update({"WoRMS표제": s["WoRMS 표제"], "저자": s["저자"],
                        "매칭유형": s["매칭유형"], "상태": s["상태"],
                        "유효명": s["유효명"], "원사유": s["사유"]})
            row["재판정"], row["근거"] = judge_needs_review(s)
        elif "mismatch_dropped" in where:
            s = tables["mismatch_dropped"][name]
            row["WoRMS가준것"] = s["WoRMS가 준 것"]
            row["원사유"] = s["사유"]
            row["재판정"] = "비규조" if "규조가 아님" in s["사유"] else "속 다름"
            row["근거"] = s["사유"]
        elif "index_remove" in where:
            s = tables["index_remove"][name]
            row["원사유"] = s["사유"]
            row["재판정"], row["근거"] = judge_index_remove(name, s["사유"],
                                                        hits.get(name, []))
            if hits.get(name):
                r = hits[name][0]
                row.update({"AphiaID": str(r.get("AphiaID") or ""),
                            "상태": r.get("status") or "",
                            "유효명": r.get("valid_name") or "",
                            "저자": r.get("authority") or "",
                            "과": r.get("family") or "", "목": r.get("order") or "",
                            "화석": "화석" if r.get("isExtinct") else ""})
        elif "absent" in where:
            s = tables["absent"][name]
            row["속"] = s["속"]
            row["재판정"], row["근거"] = judge_absent(name, genera, cut)
        else:
            # 색인에는 있는데 다섯 표에 없다 — 아무도 안 본 이름이다
            row["재판정"] = "사람이 본다"
            row["근거"] = "색인에 있는데 다섯 표 어디에도 없다"
        out.append(row)

    # 4b) **없는 이름을 왜 없는지로 가른다.** 대상은 "WoRMS 에 없다" 로 남은 것들
    missing = [r for r in out if r["재판정"] == "사람이 본다"
               and r["근거"].startswith("WoRMS 에 없다")]
    if not args.no_recheck and missing:
        genera_todo = sorted({r["이름"].split()[0] for r in missing})
        grecs = ask_genus(genera_todo, args.out_dir / f"worms_genus_{args.stamp}.json",
                          args.sleep)
        fz = ask_fuzzy([r["이름"] for r in missing],
                       args.out_dir / f"worms_fuzzy_{args.stamp}.json", args.sleep)
        # 속의 성격은 **이미 확정된 종들**에서 읽는다 (조회를 더 하지 않는다)
        habit: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for nm, s in tables["confirmed"].items():
            g = nm.split()[0]
            habit[g]["담수" if s["담수"] else ""] += 1
            habit[g]["해수" if s["해수"] else ""] += 1
            habit[g]["화석" if s["화석"] else ""] += 1
        # 같은 종소명이 **다른 속의 확정종**에 있으면 속 표기를 의심한다 —
        # `Trinacria americanum` 옆에 `Triceratium americanum` 이 있다
        by_ep: dict[str, list[str]] = collections.defaultdict(list)
        for nm in tables["confirmed"]:
            parts = nm.split()
            if len(parts) >= 2:
                by_ep[parts[1].lower()].append(nm)

        for r in missing:
            g = r["이름"].split()[0]
            c = habit.get(g)
            prof = (f"담수 {c['담수']} · 해수 {c['해수']} · 화석 {c['화석']}"
                    if c else "")
            rec = grecs.get(g) or {}
            other = [n for n in by_ep.get(epithet(r["이름"]), [])
                     if n.split()[0] != g]
            r["왜없나"], r["근거"] = why_missing(r["이름"], rec, fz.get(r["이름"], []),
                                             prof, other)
            r["속상태"] = (f"{rec['scientificname']} ({rec.get('status')})"
                        if rec else "WoRMS 에 없음")
            r["속성격"] = ("화석속" if rec.get("isExtinct") else "") + (
                f" {prof}" if prof else "")
            r["흐린매칭"] = "; ".join(
                f"{f['scientificname']}[{f['match_type']}]" for f in fz.get(r["이름"], []))

    master = args.out_dir / f"worms_master_{args.stamp}.tsv"
    with master.open("w", encoding="utf-8") as f:
        f.write("\t".join(OUT_COLS) + "\n")
        for row in out:
            f.write("\t".join(row[c] for c in OUT_COLS) + "\n")

    # 5) 일감 — 사람이 볼 것만 따로. **master 에서 뺀 것이 아니라 뽑은 것이다**
    work = [r for r in out if r["재판정"] in ("사람이 본다", "되살린다", "격리")]
    wl = args.out_dir / f"worms_worklist_{args.stamp}.tsv"
    with wl.open("w", encoding="utf-8") as f:
        f.write("\t".join(OUT_COLS) + "\n")
        for row in sorted(work, key=lambda r: (r["재판정"], r["이름"])):
            f.write("\t".join(row[c] for c in OUT_COLS) + "\n")

    # 6) 요약
    print(f"\n한 표로 모았다 → {master}  ({len(out)}줄)")
    print(f"사람이 볼 것    → {wl}  ({len(work)}줄)")
    print("\n재판정")
    for k, n in collections.Counter(r["재판정"] for r in out).most_common():
        print(f"  {k:14s} {n}")
    print("\n도감 출처")
    for k, n in collections.Counter(r["도감"] or "(색인에 없음)" for r in out).most_common():
        print(f"  {k:20s} {n}")
    why = collections.Counter(r["왜없나"] for r in out if r["왜없나"])
    if why:
        print("\nWoRMS 에 없는 이름을 왜 없는지로 가른다")
        for k, n in why.most_common():
            print(f"  {k:24s} {n}")
    saved = [r for r in out if r["재판정"] == "되살린다"]
    if saved:
        print(f"\n지울 뻔한 것 중 진짜 학명 {len(saved)}건")
        for r in saved:
            print(f"  {r['이름']:32s} {r['근거']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
