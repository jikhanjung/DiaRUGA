#!/usr/bin/env python3
"""사람이 AlgaeBase 에서 조회해 온 표를 대조표에 채운다 (P15).

AlgaeBase 는 자동으로 못 연다(Turnstile · `harvest_worms.py` 머리말). 그래서
**사람이 브라우저로 50종씩 조회해 표로 적어 온다** — `names/algaebase/` 의
`algaebase_dayN_....md` 가 그것이고, 번호는 `species_1845.tsv` 의 줄 번호다.
**앞으로도 300종씩 들어온다**(사용자 2026-08-14). 이 스크립트는 몇 벌이 들어와도
같은 자리에 얹히도록 **다시 돌릴 수 있게** 짰다.

**AlgaeBase 가 주 출처다** (사용자 방침 2026-08-12 · `md/name_validity_log.md`).
쓸 이름은 AlgaeBase 를 따르되, **엇갈렸다는 사실은 지우지 않는다** — 그래서
`AlgaeBase` 와 `AlgaeBase비고` 두 칸에 나눠 적고 WoRMS 칸은 그대로 둔다.

## 함정

- **번호가 이름과 맞는지 검사한다.** 표는 `species_1845.tsv` 의 줄 번호로
  적혀 오는데, 그 파일이 다시 만들어지면 번호가 밀린다. 번호로 짚지 않고
  **이름으로 짚되 번호를 검산에 쓴다** — 어긋나면 멈춘다
- **`(그대로 유효)` 는 이름이 아니다.** `확인 필요`·`미확인` 도 마찬가지다.
  학명 자리에 이런 말이 들어오면 조회 결과가 아니라 **사람이 남긴 상태**다
- **`**` 를 벗긴다.** 표에서 굵게 적어 온다

사용:

    python tools/ingest_algaebase.py                 # 있는 것을 전부 먹인다
    python tools/ingest_algaebase.py --dry-run       # 무엇이 들어가는지만 본다
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402

BATCHES = DIADICTION / "names/algaebase"
MASTER = DIADICTION / "names/worms/worms_master_20260814.tsv"
SPECIES = DIADICTION / "names/worms/species_1845.tsv"
ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|(.*?)\|\s*$", re.M)

# 통용명 칸에 오지만 **이름이 아닌 것들.** 정확히 일치시키려 들면 샌다 —
# 실제로 `(그대로 유효, 단 循環 이명 구조)`·`미확인(OCR 오독)` 처럼 꼬리가 붙어
# 온다. 낱말이 들어 있는지로 가르고, **원문은 언제나 비고에 그대로 남긴다**
STATES = [("AlgaeBase에 없음", "AlgaeBase 에 없다"),
          ("AlgaeBase 에 없음", "AlgaeBase 에 없다"),
          ("검색 안 함", "아직 안 찾았다"),
          ("그대로 유효", "그대로 유효"),
          ("확인 필요", "확인 필요"),
          ("미확인", "미확인")]
BINOMIAL = re.compile(r"^([A-Z][a-zë\-]+ [a-zë\-]+(?: (?:var|f|subsp)\. [a-zë\-]+)?)")


def clean(s: str) -> str:
    return s.replace("**", "").replace("*", "").strip()


def read_batches() -> tuple[dict[str, dict], list[str]]:
    """`algaebase_day*.md` 를 전부 읽는다. 값은 이름 → {번호·판정·비고·출처파일}."""
    out: dict[str, dict] = {}
    files = sorted(BATCHES.glob("algaebase_day*.md"))
    warn: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for num, name, verdict, note in ROW.findall(text):
            name, verdict, note = clean(name), clean(verdict), clean(note)
            if not name:
                continue
            # **원문을 먼저 챙긴다** — 어떻게 갈리든 적어 온 말은 안 버린다
            rec = {"번호": int(num), "출처": path.name, "비고": note,
                   "원문": verdict}
            m = BINOMIAL.match(verdict)
            hit = next((v for k, v in STATES if k in verdict), None)
            if m and not hit:
                rec["상태"], rec["이름"] = "이명 → 갈아탄다", m.group(1)
            elif hit:
                rec["상태"], rec["이름"] = hit, ""
            elif verdict.strip("()—- ") == "":
                rec["상태"], rec["이름"] = "안 적혀 있다", ""
            else:
                rec["상태"], rec["이름"] = "사람 메모", ""
                warn.append(f"{path.name} #{num} {name}: 통용명 칸이 {verdict!r}")
            if name in out and out[name]["상태"] != rec["상태"]:
                warn.append(f"같은 이름이 두 번 오고 판정이 다르다: {name}")
            out[name] = rec
    print(f"표 {len(files)}벌 · 항목 {len(out):,}개")
    return out, warn


def check_numbers(recs: dict[str, dict]) -> list[str]:
    """번호가 `species_1845.tsv` 의 그 줄을 가리키는가. **어긋나면 멈춘다.**"""
    if not SPECIES.exists():
        return ["species_1845.tsv 가 없어 번호 검산을 못 했다"]
    order = [l.split("\t")[0] for l in
             SPECIES.read_text(encoding="utf-8").splitlines()[1:] if l.strip()]
    bad = []
    for name, r in recs.items():
        i = r["번호"] - 1
        if not (0 <= i < len(order)):
            bad.append(f"#{r['번호']} 이 범위 밖이다 ({name})")
        elif order[i] != name:
            bad.append(f"#{r['번호']} 은 {order[i]!r} 인데 표에는 {name!r} 이다")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="번호 검산이 어긋나도 진행한다")
    args = ap.parse_args()

    recs, warn = read_batches()
    for w in warn:
        print(f"  ! {w}")
    bad = check_numbers(recs)
    if bad:
        print(f"\n번호 검산에서 {len(bad)}건 어긋났다:")
        for b in bad[:10]:
            print(f"  ! {b}")
        if not args.force:
            print("\n**멈춘다.** species_1845.tsv 가 다시 만들어졌을 수 있다 — "
                  "번호가 밀리면 엉뚱한 이름에 판정이 붙는다. 확인하고 --force")
            return 1
    else:
        print("번호 검산 통과 — 표의 번호가 species_1845.tsv 의 그 줄과 맞는다")

    lines = MASTER.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    for col in ("AlgaeBase", "AlgaeBase비고"):
        if col not in head:
            head.append(col)
    a, b = head.index("AlgaeBase"), head.index("AlgaeBase비고")

    rows, filled, unseen = [], 0, dict(recs)
    tally = collections.Counter()
    clash = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        cells += [""] * (len(head) - len(cells))
        r = unseen.pop(cells[0], None)
        if r:
            filled += 1
            tally[r["상태"]] += 1
            cells[a] = r["이름"] or r["상태"]
            # 원문과 비고를 **둘 다** 남긴다
            extra = " · ".join(x for x in (r["원문"] if r["원문"] != r["이름"] else "",
                                           r["비고"]) if x)
            cells[b] = f"{r['상태']} · {r['출처']}" + (f" · {extra}" if extra else "")
            # **엇갈림을 내가 직접 센다** — 표의 `비고` 를 믿지 않고 두 칸을 비교한다
            worms = dict(zip(head, cells)).get("유효명", "")
            if r["이름"] and worms and r["이름"] != worms and worms != cells[0]:
                clash.append((cells[0], r["이름"], worms))
        rows.append(cells)

    print(f"\n대조표 {len(rows):,}줄 중 {filled:,}줄에 채웠다")
    for k, n in tally.most_common():
        print(f"  {k:16s} {n:,}")
    if unseen:
        print(f"\n대조표에 없는 이름 {len(unseen)}개 — 표에는 있는데 못 붙였다:")
        for n in list(unseen)[:10]:
            print(f"  ! {n}")
    if clash:
        print(f"\n**AlgaeBase 와 WoRMS 가 엇갈린 것 {len(clash)}건** "
              f"(쓸 이름은 AlgaeBase 를 따르고, 엇갈림은 그대로 남긴다)")
        for n, ab, w in clash[:12]:
            print(f"  {n:30s} AlgaeBase {ab:32s} WoRMS {w}")

    if args.dry_run:
        print("\n(--dry-run 이라 파일은 안 썼다)")
        return 0
    MASTER.write_text("\t".join(head) + "\n"
                      + "".join("\t".join(c) + "\n" for c in rows), encoding="utf-8")
    print(f"\n→ {MASTER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
