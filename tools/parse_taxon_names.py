#!/usr/bin/env python3
"""학명 유효성 판정을 `taxon_names.json` 으로 뽑는다 — P24.

원본은 NAS 두 벌이다. **여기서는 이름을 새로 조회하지 않는다** — 사람이
브라우저로 AlgaeBase 를 이미 열어 확인한 것을 그러모을 뿐이다.

- `Diadiction/names/worms/worms_master_20260814.tsv` — 도감 1,845종의
  마스터 표(08-14~08-26, 37일치 배치). `AlgaeBase` 칼럼이 채워진 행만
  쓴다. 그 칼럼 값이 상태 문구 여섯 개(`그대로 유효`·`AlgaeBase 에
  없다`·`확인 필요`·`아직 안 찾았다`·`안 적혀 있다`·`미확인`) 중
  하나가 아니면, **그 값 자체가 새 학명이다**(이명 → 갈아탄다)
- `Diadiction/temp/paper_plates_156_result.json` — 논문 도판(P22·P23)
  캡션 학명 156종의 AlgaeBase 조회 결과(2026-08-31). API 응답 그대로라
  `status` 문장을 읽어 판정을 가른다

열쇠는 `tools/harvest_worms.binomial()` 로 정규화한다 — `var.`·`sp.`
꼬리는 종 단위로 뭉뚱그려진다(예: `Actinocyclus ehrenbergii var.
tenella` → `Actinocyclus ehrenbergii`). **두 소스가 같은 binomial 을
내면**(실측 2건뿐이다, 08-31) 실제 판정이 있는 쪽(accepted/synonym)을
실패한 쪽(absent/unassessed)보다 우선하고, 둘 다 판정이 있는데 갈리면
`worms_master`(더 크고 오래 검토된 자료)를 쓰되 **엇갈렸다는 사실은
`note` 에 남긴다**(지우지 않는다 — `name_validity_log.md` 의 규칙).

사용:

    python tools/parse_taxon_names.py                 # taxon_names.json 으로 뽑는다
    python tools/parse_taxon_names.py --dry-run       # 안 쓰고 요약만 본다
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION, binomial  # noqa: E402

WORMS_MASTER = DIADICTION / "names/worms/worms_master_20260814.tsv"
PAPER_RESULT = DIADICTION / "temp/paper_plates_156_result.json"
OUT = Path(__file__).resolve().parent.parent / "taxon_names.json"

# worms_master 의 `AlgaeBase` 칼럼이 이 문구 중 하나면 그게 상태다.
# 그 여섯이 아니면 값 자체가 새 학명(synonym) 이다.
STATUS_WORDS = {
    "그대로 유효": "accepted",
    "AlgaeBase 에 없다": "absent",
    "확인 필요": "unassessed",
    "아직 안 찾았다": "unassessed",
    "안 적혀 있다": "unassessed",
    "미확인": "unassessed",
}

SYNONYM_OF = re.compile(r"^This name is currently regarded as a synonym of (.+?)\.?$")
ACCEPTED_RE = re.compile(r"is of an entity that is currently accepted taxonomically")

RESOLVED = {"accepted", "synonym"}


def from_worms_master() -> dict[str, dict]:
    """도감 1,845종 마스터 표를 읽는다."""
    out: dict[str, dict] = {}
    with WORMS_MASTER.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ab = (row.get("AlgaeBase") or "").strip()
            if not ab:
                continue
            b = binomial(row["이름"]) or row["이름"].strip()
            if ab in STATUS_WORDS:
                status, valid_name = STATUS_WORDS[ab], ""
            else:
                status, valid_name = "synonym", ab
            out[b] = {
                "binomial": b,
                "status": status,
                "valid_name": valid_name,
                "source": "worms-master-20260814",
                "note": (row.get("AlgaeBase비고") or "").strip(),
                "checked": (row.get("갱신") or "").strip(),
            }
    return out


def from_paper_plates() -> dict[str, dict]:
    """논문 도판 156종 AlgaeBase 조회 결과를 읽는다."""
    data = json.loads(PAPER_RESULT.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for name, rec in data["records"].items():
        b = binomial(name)
        if b is None:
            continue
        if rec.get("ok"):
            status_text = rec.get("status") or ""
            m = SYNONYM_OF.match(status_text)
            if m:
                status, valid_name = "synonym", m.group(1)
            elif ACCEPTED_RE.search(status_text):
                status, valid_name = "accepted", ""
            else:
                status, valid_name = "unassessed", ""
            note = status_text
        else:
            total = (rec.get("total") or "0").strip()
            status = "absent" if total == "0" else "unassessed"
            valid_name = ""
            note = f"AlgaeBase 후보 {total}건, 정확 일치 없음 ({rec.get('err','')})"
        out[b] = {
            "binomial": b,
            "status": status,
            "valid_name": valid_name,
            "source": "paper-plates-20260831",
            "note": note,
            "checked": rec.get("updated") or "",
        }
    return out


def merge(worms: dict[str, dict], paper: dict[str, dict]) -> dict[str, dict]:
    """겹치는 이름은 판정이 있는 쪽을 우선하고, 갈리면 worms_master 를 쓰되
    엇갈렸다는 사실을 note 에 남긴다."""
    out = dict(worms)
    for b, p in paper.items():
        w = out.get(b)
        if w is None:
            out[b] = p
            continue
        if w["status"] in RESOLVED and p["status"] in RESOLVED:
            if w["status"] == p["status"] and w["valid_name"] == p["valid_name"]:
                w["note"] = (w["note"] + " · 논문 도판 조회도 같은 판정"
                             if w["note"] else "논문 도판 조회도 같은 판정")
            else:
                w["note"] = (
                    f"{w['note']} · ⚠ 논문 도판 조회는 다른 판정"
                    f"({p['status']}"
                    f"{' → ' + p['valid_name'] if p['valid_name'] else ''})"
                ).strip(" ·")
        elif w["status"] not in RESOLVED and p["status"] in RESOLVED:
            out[b] = p  # worms_master 쪽이 못 찾았는데 논문 조회가 판정을 냈다
        # 그 반대(w 가 판정 있고 p 가 실패)는 w 를 그대로 둔다 — 위 사례
        # (var. 형태를 종 단위로 뭉뚱그려 조회가 실패한 경우)가 이 자리다
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    worms = from_worms_master()
    paper = from_paper_plates()
    merged = merge(worms, paper)

    from collections import Counter
    c = Counter(v["status"] for v in merged.values())
    overlap = set(worms) & set(paper)
    print(f"worms_master {len(worms)} · paper_plates {len(paper)} "
          f"· 겹침 {len(overlap)} · 합계 {len(merged)}")
    print("  " + " · ".join(f"{k} {v}" for k, v in c.most_common()))

    if args.dry_run:
        return 0

    OUT.write_text(json.dumps(sorted(merged.values(), key=lambda r: r["binomial"]),
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
