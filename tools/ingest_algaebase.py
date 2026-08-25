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
- **발음부호를 벗겨 적어 오기도 한다** (`kützingiana` → `kutzingiana`). 열쇠가
  안 맞으면 그 줄이 대조표에 안 붙는다 — **번호가 가리키는 줄과 발음부호만
  다를 때에 한해** 색인 표기로 되돌리고 적어 온 철자는 비고에 남긴다

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
import unicodedata
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

# **이름 칸에 도감의 다른 표기를 괄호로 달아 오기도 한다** —
# `Chaetoceros affine (Chaetoceras affine)` 처럼 고전 속명을 함께 적어 온다.
# 대조표의 열쇠는 괄호 앞이다. 안 벗기면 번호 검산이 어긋나 **그 줄이 통째로
# 안 붙는다**(8일차에 5건이 그랬다). 괄호 안은 비고로 옮겨 남긴다
PAREN = re.compile(r"^(.+?)\s*\(([^()]*)\)$")

# 같은 이름이 두 벌 이상 온다 — **급한 148건을 먼저 돈 표와 순번 표가 겹친다.**
# 뒤에 읽은 것이 이기게 두면 **무엇이 이길지가 파일 이름 정렬에 달린다**(`day10`
# 이 `day7` 보다 앞이다). 알아낸 것이 많은 쪽이 이기게 하되, **진 기록도
# 지우지 않는다** — 비고에 남기고 끝에 목록으로 낸다
RANK = {"이명 → 갈아탄다": 5, "그대로 유효": 4, "확인 필요": 3, "미확인": 3,
        "AlgaeBase 에 없다": 2, "사람 메모": 1, "아직 안 찾았다": 0,
        "안 적혀 있다": 0}

# **사람이 갈라야 하는 것.** 두 표가 다르게 말했는데 **어느 쪽도 근거가 약해서**
# RANK 에 맡기면 안 되는 이름들이다. 규칙대로 두면 "이름을 찾은 쪽" 이 이기는데,
# 진 쪽이 든 것은 이름이 없다는 말이 아니라 **그 이름이 여기 것이 아니라는 말**
# 이라 층이 다르다. 판정을 안 적고 **원문 재판독으로 넘긴다** (⑦ · 127 · 사용자
# 2026-08-18). 여기서 빼려면 원문이 무엇을 말하는지 보고 나서 뺀다
HOLD = {
    "Chaetoceros paradoxum":
        "원문이 **Pavillard 판**이라고 한다(126 · 한국동식물도감 색인 306번 "
        "`Chaetoceras paradoxum PAVILLARD`). 148건이 찾은 C. paradoxus 는 Cleve 판이고 "
        "9일차가 든 동명이종도 Cleve·Peragallo 둘뿐이라 **셋 다 아니다** — "
        "Pavillard 판 이름으로 AlgaeBase 에 다시 물어야 한다",
}

# **넘겼다가 원문으로 닫힌 것.** HOLD 에서 빼면 규칙이 도로 이름을 채우는데,
# 여기 든 것은 **그 이름이 맞다고 원문이 말해 준** 자리다. 이름은 규칙이 채우게
# 두고 근거만 비고에 남긴다 — 닫은 근거가 없으면 다음 사람이 또 넘긴다
RESOLVED = {
    "Chaetoceros ikari":
        "원문으로 닫혔다(126) — 한국동식물도감 색인 299번이 "
        "`Chaetoceras Ikari SKVORTZOW` 로 저자를 달고 있다. Ikari 가 종소명 자리이고 "
        "저자는 SKVORTZOW 라 148건의 C. ikarii Skvortzov 가 맞다. "
        "같은 도감에서 IKARI 가 저자로 나오는 줄은 278·311·318 로 따로 있다",
}


def clean(s: str) -> str:
    return s.replace("**", "").replace("*", "").strip()


def better(a: dict, b: dict) -> dict:
    """둘 중 더 많이 알아낸 쪽. 같으면 적어 온 말이 긴 쪽 (정렬 순서를 안 탄다)."""
    ra, rb = RANK.get(a["상태"], 0), RANK.get(b["상태"], 0)
    if ra != rb:
        return a if ra > rb else b
    la = len(a["원문"]) + len(a["비고"])
    lb = len(b["원문"]) + len(b["비고"])
    return a if la >= lb else b


def read_batches() -> tuple[dict[str, dict], list[str], list[tuple], list[str]]:
    """`algaebase_day*.md` 를 전부 읽는다. 값은 이름 → {번호·판정·비고·출처파일}.

    **못 읽은 꾸러미는 세어서 돌려준다.** NAS 가 파일마다 권한을 따로 걸어
    읽기가 막히는 일이 있는데(08-25 에 27~29 일차 셋이 그랬다), 조용히 건너뛰면
    **그 회차가 안 들어온 것이 아니라 판정이 달라진다** — 같은 이름을 두 표가
    말했을 때 RANK 로 갈리던 것이 "읽힌 쪽" 으로 갈리기 때문이다. 부르는 쪽이
    멈출 수 있게 목록을 낸다.
    """
    out: dict[str, dict] = {}
    files = sorted(BATCHES.glob("algaebase_day*.md"))
    warn: list[str] = []
    clash: list[tuple] = []
    unread: list[tuple[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            unread.append((path.name, e.strerror or str(e)))
            continue
        for num, name, verdict, note in ROW.findall(text):
            name, verdict, note = clean(name), clean(verdict), clean(note)
            if not name:
                continue
            표기 = ""
            p = PAREN.match(name)
            if p:
                name, 표기 = p.group(1).strip(), p.group(2).strip()
            # **원문을 먼저 챙긴다** — 어떻게 갈리든 적어 온 말은 안 버린다
            rec = {"번호": int(num), "출처": path.name, "비고": note,
                   "원문": verdict}
            rec["표기"] = 표기
            m = BINOMIAL.match(verdict)
            hit = next((v for k, v in STATES if k in verdict), None)
            if m and m.group(1) != name:
                # `Caloneis silicula(그대로 유효)` — **고친 이름 뒤에 상태를 달아
                # 온다.** 뒤의 "그대로 유효" 는 *고친 이름이* 유효하다는 말이지
                # 도감 표기가 유효하다는 말이 아니다. 상태 낱말을 먼저 보면
                # 고친 이름을 통째로 버린다 (7~12일차 표가 이 꼴로 온다)
                rec["상태"], rec["이름"] = "이명 → 갈아탄다", m.group(1)
            elif m:
                rec["상태"], rec["이름"] = "그대로 유효", ""
            elif hit:
                rec["상태"], rec["이름"] = hit, ""
            elif verdict.strip("()—- ") == "":
                rec["상태"], rec["이름"] = "안 적혀 있다", ""
            else:
                rec["상태"], rec["이름"] = "사람 메모", ""
                warn.append(f"{path.name} #{num} {name}: 통용명 칸이 {verdict!r}")
            prev = out.get(name)
            if prev is None:
                out[name] = rec
                continue
            win = better(prev, rec)
            lose = rec if win is prev else prev
            win = dict(win)
            # **도감의 다른 표기는 진 기록에만 있을 수 있다** — 이긴 쪽이 그 칸을
            # 안 적어 왔으면 가져온다. 판정이 아니라 도감이 어떻게 썼는가라서
            # 어느 표가 이겼는지와 무관하다
            win["표기"] = win.get("표기") or lose.get("표기", "")
            if (prev["상태"], prev["이름"]) != (rec["상태"], rec["이름"]):
                clash.append((name, win, lose))
                win["진 기록"] = f"{lose['출처']} 은 {lose['원문'] or '—'}"
            out[name] = win
    for name, why in HOLD.items():
        r = out.get(name)
        if r is None:
            warn.append(f"HOLD 에 적은 {name} 이 표에 없다 — 번호가 밀렸을 수 있다")
            continue
        r = dict(r)
        r["상태"], r["이름"], r["보류"] = "원문 재판독", "", why
        out[name] = r
    for name, why in RESOLVED.items():
        r = out.get(name)
        if r is None:
            warn.append(f"RESOLVED 에 적은 {name} 이 표에 없다 — 번호가 밀렸을 수 있다")
            continue
        r = dict(r)
        r["닫힘"] = why
        out[name] = r
    print(f"표 {len(files)}벌 · 항목 {len(out):,}개")
    return out, warn, clash, unread


def species_order() -> list[str]:
    """색인 표제어를 순번대로. 번호 검산과 발음부호 되돌리기가 함께 쓴다."""
    if not SPECIES.exists():
        return []
    return [l.split("\t")[0] for l in
            SPECIES.read_text(encoding="utf-8").splitlines()[1:] if l.strip()]


def fold(s: str) -> str:
    """발음부호를 벗긴다 (ü→u · é→e). **비교에만 쓰고 저장하지 않는다.**"""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c)).casefold()


def restore_diacritics(recs: dict[str, dict], order: list[str]) -> list[str]:
    """표가 발음부호를 벗겨 적어 온 이름을 색인 표기로 되돌린다.

    **번호가 가리키는 줄과 발음부호만 다를 때에만** 손댄다 — 벗긴 꼴이 같아야
    하므로 엉뚱한 이름에 붙을 수가 없고, 번호 검산이 그 위에서 또 본다.
    되돌리지 않으면 그 줄은 대조표의 열쇠와 안 맞아 **통째로 안 붙는다**
    (13일차 #637 `kutzingiana`. 대조표에 발음부호가 든 이름이 열이다).
    """
    fixed = []
    for name in list(recs):
        r = recs[name]
        i = r["번호"] - 1
        if not (0 <= i < len(order)) or order[i] == name:
            continue
        if fold(order[i]) != fold(name):
            continue
        rec = dict(recs.pop(name))
        rec["철자"] = name
        prev = recs.get(order[i])
        recs[order[i]] = rec if prev is None else better(prev, rec)
        fixed.append(f"#{r['번호']} {name} → {order[i]}")
    return fixed


def check_numbers(recs: dict[str, dict], order: list[str]) -> list[str]:
    """번호가 `species_1845.tsv` 의 그 줄을 가리키는가. **어긋나면 멈춘다.**"""
    if not order:
        return ["species_1845.tsv 가 없어 번호 검산을 못 했다"]
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
    ap.add_argument("--skip-unreadable", action="store_true",
                    help="못 읽은 꾸러미가 있어도 진행한다 (무엇이 빠졌는지 보고 나서)")
    args = ap.parse_args()

    recs, warn, dupes, unread = read_batches()
    if unread:
        print(f"**꾸러미 {len(unread)}개를 못 읽었다:**")
        for name, why in unread:
            print(f"  ! {name}: {why}")
        if not args.skip_unreadable:
            print("\n**멈춘다.** 빠진 회차의 이름이 다른 회차에도 있으면 "
                  "판정이 달라진다 — 확인하고 --skip-unreadable")
            return 1
        print("  (--skip-unreadable · 빠진 회차의 줄은 대조표의 지금 값 그대로 둔다)")
    for w in warn:
        print(f"  ! {w}")
    if dupes:
        print(f"\n**같은 이름을 두 표가 다르게 말한 것 {len(dupes)}건** "
              f"(알아낸 것이 많은 쪽을 쓰고, 진 쪽은 비고에 남긴다)")
        for name, win, lose in sorted(dupes, key=lambda x: x[1]["번호"]):
            골 = ("원문 재판독으로 넘겼다" if name in HOLD else
                 f"{win['이름']} (원문으로 닫혔다)" if name in RESOLVED else
                 (win["이름"] or win["상태"]))
            print(f"  #{win['번호']:4d} {name:32s} "
                  f"{win['출처'].removeprefix('algaebase_').removesuffix('.md'):18s} "
                  f"{골[:34]:34s} "
                  f"← {lose['원문'][:30] or '—'}")
    order = species_order()
    fixed = restore_diacritics(recs, order)
    if fixed:
        print(f"\n표가 발음부호를 벗겨 적어 온 것 {len(fixed)}건 — "
              f"색인 표기로 되돌렸다 (적어 온 철자는 비고에 남긴다)")
        for f in fixed:
            print(f"  {f}")
    bad = check_numbers(recs, order)
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
    unread_files = {n for n, _ in unread}
    kept: list[tuple] = []
    tally = collections.Counter()
    clash = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        cells += [""] * (len(head) - len(cells))
        r = unseen.pop(cells[0], None)
        if r and any(f in cells[b] for f in unread_files):
            # **못 읽은 회차가 이겨 놓은 줄이다.** 그 회차가 이번엔 안 돌아서
            # RANK 가 아니라 "읽힌 쪽" 이 이기게 되는 자리 — 지금 값이 더 많이
            # 알아낸 것이면 그대로 둔다. 안 그러면 `그대로 유효` 가 `없다` 로
            # 뒤로 간다 (08-25 에 둘이 그랬다)
            cur = cells[b].split(" · ")[0]
            if RANK.get(cur, 0) > RANK.get(r["상태"], 0):
                kept.append((cells[0], cur, r["상태"], r["출처"]))
                rows.append(cells)
                continue
        if r:
            filled += 1
            tally[r["상태"]] += 1
            cells[a] = r["이름"] or r["상태"]
            # 원문과 비고를 **둘 다** 남긴다
            표기 = f"도감 표기 {r['표기']}" if r.get("표기") else ""
            철자 = f"표는 {r['철자']} 로 적어 왔다" if r.get("철자") else ""
            extra = " · ".join(x for x in (r["원문"] if r["원문"] != r["이름"] else "",
                                           표기, 철자, r["비고"], r.get("진 기록", ""),
                                           r.get("보류", ""), r.get("닫힘", "")) if x)
            cells[b] = f"{r['상태']} · {r['출처']}" + (f" · {extra}" if extra else "")
            # **엇갈림을 내가 직접 센다** — 표의 `비고` 를 믿지 않고 두 칸을 비교한다
            worms = dict(zip(head, cells)).get("유효명", "")
            if r["이름"] and worms and r["이름"] != worms and worms != cells[0]:
                clash.append((cells[0], r["이름"], worms))
        rows.append(cells)

    print(f"\n대조표 {len(rows):,}줄 중 {filled:,}줄에 채웠다")
    if kept:
        print(f"\n**못 읽은 회차가 이겨 둔 {len(kept)}줄은 그대로 뒀다** "
              f"(읽힌 표가 덜 알아냈다):")
        for name, cur, new_state, src in kept:
            print(f"  {name:30s} 지킨 값 {cur:14s} ← {src} 은 {new_state}")
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
