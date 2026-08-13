#!/usr/bin/env python3
"""도감 색인의 학명을 DiatomBase/WoRMS 에 물어 한 벌로 모은다 (P15 5절).

**왜 WoRMS 인가.** 학명 판정의 주 출처는 AlgaeBase 이지만(사용자 방침 2026-08-12)
**AlgaeBase 는 자동으로 못 연다** — Cloudflare Turnstile 이 걸려 있고 그 문의
목적이 자동 수집을 막는 것이다. 자동으로 갈 수 있는 것은 **공개 REST 를 내놓은
DiatomBase/WoRMS** 다. 여기서 모은 것은 **근거**이고, 엇갈리거나 비는 자리만
사람이 AlgaeBase 를 연다. 그렇게 하면 사람이 열 횟수가 실제로 줄어든다 —
속에서는 9쌍이 3개로, 종에서는 41쌍이 19쌍으로 줄었다.

**출력은 사본이다.** 원본은 `Diadiction/md/*.md` 이고(P15 4.2), 이 파일은 언제든
지우고 다시 만들 수 있다. **사람이 내린 판정을 여기에 적지 않는다** — 그것은
`Diadiction/md/name_validity_log.md` 자리다.

## 함정

- **`class == "Bacillariophyceae"` 로 거른다.** `marine_only=false` 로 물으면
  동명이의가 함께 온다 — `Navicula` 하나가 규조 하나와 연체동물 둘을 낸다.
  거르지 않으면 `Chaetoceras`(홍조류)에 규조 55종이 붙는다
- **"accepted" 는 "그 이름을 쓰라" 가 아니다.** `status` 와 `valid_name` 을
  함께 본다 — `unaccepted` 인데 `valid_name` 이 변종으로 내려가는 경우가 있다
- **없는 것도 자료다.** 조회해서 안 나온 이름은 `records: []` 로 남긴다.
  다시 물을 필요가 없고, 오기를 가르는 근거가 바로 이것이다

사용:

    python tools/harvest_worms.py --out /tmp/worms.json
    python tools/harvest_worms.py --out /tmp/worms.json --limit 200   # 끊어서
    python tools/harvest_worms.py --out /tmp/worms.json --report      # 안 묻고 요약만
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DIADICTION = Path("/nfs/temp-share/DiaRUGA/Diadiction")
API = "https://www.marinespecies.org/rest/AphiaRecordsByNames"
DIATOM_CLASS = "Bacillariophyceae"
BATCH = 50

# 색인마다 표제어의 모양이 다르다 (117 §남은 것). 파서가 도감마다 하나인 이유다.
INDEXES = [
    ("한국", "md/korean_flora_diatom_index.md", r"^\*\*\d+\.\s*\*(.+?)\*\*\*", None),
    ("Schmidt", "md/schmidt_atlas_name_index.md", r"^- \*\*\*(.+?)\*\*\*", None),
    ("동남극", "md/east_antarctic_plates_index.md", r"^\*\*\*(.+?)\*\*\*",
     ("## 학명별 색인", "## Plate 별 원문")),
]

# 흐린 검색 + WoRMS 로 갈린 속 표기 (2026-08-13, name_validity_log.md 에 근거).
# **여기 있는 것은 "한쪽에만 있고 짝은 accepted 규조속" 인 것뿐이다** — 둘 다
# 실재하는 짝(Coscinodiscus ~ Cosmiodiscus)은 넣지 않는다. 사람이 가른다.
GENUS_FIX = {
    "Raphoneis": "Rhaphoneis",
    "Gophonema": "Gomphonema",
    "Navicla": "Navicula",
    "Rhicophenia": "Rhoicosphenia",
    "Sceletonema": "Skeletonema",
    "Cyrosigma": "Gyrosigma",
    "Chaetoceras": "Chaetoceros",
}


def read_names(root: Path) -> dict[str, set[str]]:
    """색인 셋에서 이명법을 뽑는다. 값은 그 이름이 나온 도감들."""
    names: dict[str, set[str]] = collections.defaultdict(set)
    for atlas, rel, pat, section in INDEXES:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        if section:
            text = text.split(section[0])[1].split(section[1])[0]
        for m in re.finditer(pat, text, re.M):
            words = m.group(1).replace("*", "").split()
            if len(words) < 2:
                continue
            genus, epithet = words[0].capitalize(), words[1].lower()
            # `sp.`·`group` 처럼 종까지 안 내려간 것은 물을 것이 없다
            if not re.fullmatch(r"[a-zöäüéë\-]+", epithet):
                continue
            names[f"{GENUS_FIX.get(genus, genus)} {epithet}"].add(atlas)
    return dict(names)


def ask(batch: list[str], retries: int = 3) -> list[list[dict]]:
    q = "&".join("scientificnames%5B%5D=" + urllib.parse.quote(n) for n in batch)
    url = f"{API}?{q}&marine_only=false"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                out = json.loads(r.read().decode())
            # 응답은 물은 순서대로 온다. 못 찾은 자리는 null 이다
            return [(x or []) for x in out]
        except Exception as exc:  # 네트워크·5xx. 물러났다 다시 문다
            if attempt == retries - 1:
                print(f"  ! {batch[0]}… {type(exc).__name__}: {exc}", file=sys.stderr)
                return [[] for _ in batch]
            time.sleep(2 ** attempt)
    return [[] for _ in batch]


def keep(rec: dict) -> dict:
    """쓸 칸만 남긴다. 전체 응답은 크고 대부분 안 쓴다."""
    return {k: rec.get(k) for k in (
        "AphiaID", "scientificname", "authority", "status", "unacceptreason",
        "valid_AphiaID", "valid_name", "valid_authority", "rank",
        "kingdom", "phylum", "class", "order", "family", "genus",
        "isMarine", "isFreshwater", "isBrackish", "isTerrestrial",
        "citation", "modified",
    )}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DIADICTION, help="Diadiction 폴더")
    ap.add_argument("--out", type=Path, required=True, help="결과 JSON")
    ap.add_argument("--limit", type=int, default=0, help="이번에 물을 최대 개수 (0=전부)")
    ap.add_argument("--sleep", type=float, default=0.5, help="배치 사이 쉬는 시간(초)")
    ap.add_argument("--report", action="store_true", help="안 묻고 있는 것만 요약")
    args = ap.parse_args()

    if not args.root.exists():
        print(f"Diadiction 을 못 찾는다: {args.root}\n"
              f"  NAS 공유가 안 붙었을 수 있다 (P14 4.4 와는 다른 자리다 — "
              f"이 스크립트는 호스트에서 돈다)", file=sys.stderr)
        return 2

    names = read_names(args.root)
    print(f"색인 셋의 이명법 {len(names)}개")

    # **이어서 돈다.** 한 번에 다 못 물어도 다음 실행이 남은 것부터 간다
    done: dict[str, dict] = {}
    if args.out.exists():
        done = json.loads(args.out.read_text(encoding="utf-8"))
        print(f"이미 물어 둔 것 {len(done)}개 — 건너뛴다")

    if not args.report:
        todo = [n for n in sorted(names) if n not in done]
        if args.limit:
            todo = todo[:args.limit]
        print(f"이번에 물을 것 {len(todo)}개 ({BATCH}개씩)")
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            for name, recs in zip(batch, ask(batch)):
                diatoms = [keep(r) for r in recs if r.get("class") == DIATOM_CLASS]
                done[name] = {
                    "atlases": sorted(names[name]),
                    "records": diatoms,
                    # 규조가 아닌 동명이의가 있었다는 사실도 남긴다 — 거르는
                    # 규칙이 실제로 일하고 있는지 나중에 셀 수 있다
                    "homonyms": len(recs) - len(diatoms),
                }
            args.out.write_text(json.dumps(done, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")
            time.sleep(args.sleep)

    # 요약
    hit = [n for n, v in done.items() if v["records"]]
    miss = [n for n, v in done.items() if not v["records"]]
    status = collections.Counter(
        r["status"] for v in done.values() for r in v["records"][:1])
    homonym = sum(1 for v in done.values() if v["homonyms"])
    print(f"\n물어 둔 것 {len(done)} · 규조로 찾음 {len(hit)} · 못 찾음 {len(miss)}")
    print(f"동명이의를 걸러 낸 이름 {homonym}개")
    for s, n in status.most_common():
        print(f"  {s or '(없음)':24s} {n}")
    print(f"\n**못 찾은 {len(miss)}개가 다음 일감이다** — 오기이거나, WoRMS 에 없는 "
          f"옛 이름이거나, AlgaeBase 를 열어야 하는 것이다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
