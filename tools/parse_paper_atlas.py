#!/usr/bin/env python3
"""논문 도판의 캡션을 도감(Atlas) JSON 으로 뽑는다 — P20 다음 단계.

`tools/plate_figs.py` 의 `SOURCE`·`CAPTIONS` 가 원본이다. 도판을 자르며
(`crop_plates.py`) 사람이 상자마다 짚어 넣은 표(그림 번호 → 학명)가 이미
검산까지 끝나 있다 — 여기서는 **이름을 새로 읽지 않고 그러모을 뿐이다.**

한 종이 도판 여러 장에 걸쳐 나오면(속 재검토 논문에 흔하다, 특히 1985) 한
항목에 자리(placements)를 여럿 담는다 — 한국 도감의 종이 그림을 여럿 갖는
것과 같은 모양이다. **`AtlasEntry` 에 FK 를 매달지 않는다**(P20) — 이 표는
`ops/import_atlas.py` 가 돌 때마다 통째로 갈아치워진다.

`__unnamed` 로 잘린 크롭(이름을 못 짚은 자리)은 담지 않는다 — 그림은 있지만
종을 모르는 것이라 도감 항목이 될 수 없다.

이름 검증 규칙(`binomial()`)은 여기서 새로 만들지 않는다 — `tools/parse_atlas.py`
가 이미 갖고 있는 `name_fields`·`entry`·`place` 를 그대로 부른다.

사용:

    python tools/parse_paper_atlas.py                 # atlas/<논문>.json 으로 뽑는다
    python tools/parse_paper_atlas.py --dry-run       # 안 쓰고 요약만 본다
    python tools/parse_paper_atlas.py --only 1936_skvortzov_ampen_neogene
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_atlas import entry, place  # noqa: E402
from plate_figs import CAPTIONS, SOURCE  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "atlas"

# 도판이 있는 넷 (161·162). 나머지 열한 편은 도판이 없거나(분포표만·초록만)
# 아직 안 땄다 — `Diadiction/papers/README.md` 의 "자료의 모양" 표를 볼 것
#
# **딕셔너리 키(파일 스템)와 `atlas_key` 는 다른 것이다.** 앞엣것은
# `plate_figs.py` 의 `SOURCE`·`CAPTIONS`·`ASSIGN` 을 잇는 내부 열쇠라 밑줄이
# 섞여 있고(크롭 파일 이름과도 물려 있다), **`atlas_key` 는 `Atlas.key` 로
# 나가는 공개 코드다.** `web/viewer/atlas.py` 의 `CODE` 정규식
# (`^[a-z0-9][a-z0-9-]{0,31}$`)이 도판 이미지 경로를 그 값으로 짓기 때문에
# **밑줄도, 32자를 넘는 것도 안 된다** — 이대로 두면 `Atlas` 행은 들어가도
# 도판 이미지는 영영 못 연다(`_ok()` 가 조용히 `None` 을 낸다).
PAPER_META = {
    "1936_skvortzov_ampen_neogene": dict(
        atlas_key="1936-skvortzov",
        title="Skvortzov, B.V. (1936) 함남 안변의 신생대 화석 규조 "
              "(Bull. Geol. Surv. Tyosen 12, Harbin)",
        short="1936 Skvortzov 안변",
    ),
    "1992_lee_galmal_quaternary_flora": dict(
        atlas_key="1992-lee-galmal",
        title="Lee, Y.G. (1992) 철원 갈말면 제4기 규조토 "
              "(J. Paleont. Soc. Korea 8(1):1–23)",
        short="1992 Lee 갈말",
    ),
    "1993_lee_chaetoceros_yeonil": dict(
        atlas_key="1993-lee-chaetoceros",
        title="Lee, Y.G. (1993) 포항 연일층군 Chaetoceros "
              "(J. Paleont. Soc. Korea 9(1):24–52)",
        short="1993 Lee Chaetoceros",
    ),
    "1985_akiba_yanagisawa_dsdp87_zonal_markers": dict(
        atlas_key="1985-akiba-yanagisawa",
        title="Akiba, F. & Yanagisawa, Y. (1985) 북태평양 신생대 분대 표준종 "
              "(DSDP Init. Repts. Leg 87, ch.7)",
        short="1985 Akiba & Yanagisawa",
    ),
}


def fig_sort_key(f):
    if isinstance(f, int):
        return (f, "")
    m = re.match(r"^(\d+)([A-Za-z]*)$", f)
    if m:
        return (int(m.group(1)), m.group(2))
    return (10**9, f)


def format_figs(figs: list) -> str:
    """원문에 인쇄된 대로 촘촘한 정수 이어달림만 범위로 줄인다.

    그림 번호 자체는 인용에 쓰는 값이라 **여기서 새로 매기지 않는다** —
    캡션에 있던 것을 정렬해 보기 좋게 이을 뿐이다.
    """
    figs = sorted(set(figs), key=fig_sort_key)
    if not figs:
        return ""
    runs = [[figs[0]]]
    for f in figs[1:]:
        prev = runs[-1][-1]
        if isinstance(prev, int) and isinstance(f, int) and f == prev + 1:
            runs[-1].append(f)
        else:
            runs.append([f])
    parts = []
    for run in runs:
        if len(run) >= 3 and all(isinstance(x, int) for x in run):
            parts.append(f"{run[0]}-{run[-1]}")
        else:
            parts.append(", ".join(str(x) for x in run))
    return ", ".join(parts)


def build(paper: str) -> dict:
    # **쉼표 유무는 종이 아니다.** "Crucidenticula kanayae … Yanagisawa n. sp"
    # 가 도판 1 의 기재문에서는 쉼표 없이, 도판 1 fig5 캡션 한 곳에서만
    # "…Yanagisawa, n. sp" 로 조판돼 같은 종이 둘로 갈라졌다 — 쉼표만 합친다
    COMMA_BEFORE_ACT = re.compile(
        r",(\s+n\.\s*(?:sp|comb|gen)\.?)\s*$", re.IGNORECASE)

    # **"n. sp." 의 `sp` 가 `GENUS_ONLY`(parse_atlas.py) 의 미확정 표시와
    # 우연히 겹친다.** "새 종" 표시인데 "종까지 못 내려간 것" 으로 떨어져
    # 학명이 있는데도 `rank: genus_only` 가 됐다 — 분류용으로만 꼬리를 뗀다.
    # 화면에 보일 `name` 은 원문 그대로(꼬리 포함) 둔다
    ACT_TAIL = re.compile(r"\s*,?\s*n\.\s*(?:sp|comb|gen)\.?\s*$", re.IGNORECASE)

    def merge_comma(name: str) -> str:
        return COMMA_BEFORE_ACT.sub(r"\1", name).strip()

    caps = CAPTIONS[paper]
    src = SOURCE[paper]

    occurrences: dict[str, list[tuple[int, object]]] = {}
    order: list[str] = []
    total_figs = 0
    for plate in sorted(caps):
        for fig in sorted(caps[plate], key=fig_sort_key):
            name = caps[plate][fig]
            total_figs += 1
            if not name or name == "__unnamed":
                continue
            name = merge_comma(name)
            occurrences.setdefault(name, []).append((plate, fig))
            if name not in order:
                order.append(name)

    entries = []
    for seq, name in enumerate(order, start=1):
        by_plate: dict[int, list] = {}
        for plate, fig in occurrences[name]:
            by_plate.setdefault(plate, []).append(fig)
        placements = [
            place(plate=plate, figures=format_figs(by_plate[plate]),
                  book_page=src[plate][0], pdf_page=src[plate][1])
            for plate in sorted(by_plate)
        ]
        first_plate = min(by_plate)
        e = entry(seq, first_plate, ACT_TAIL.sub("", name).strip(),
                   placements=placements)
        e["name"] = name          # 원문 그대로(n. sp./n. comb. 꼬리 포함) 되살린다
        entries.append(e)

    meta = PAPER_META[paper]
    source_note = ("tools/data/ak85_captions.json (자동 파싱, "
                    "parse_dsdp87_captions.py)" if "akiba" in paper
                    else "tools/plate_figs.py 의 CAPTIONS (손으로 짚었다)")
    # `caps` 는 도판마다 정수·글자 딸린 키가 섞여 `sort_keys` 가 못 견딘다 —
    # 키를 문자열로 내려 우리가 직접 정렬한 튜플로 해시한다
    flat = sorted((plate, str(fig), name)
                  for plate, figs in caps.items() for fig, name in figs.items())
    digest = hashlib.sha256(
        json.dumps(flat, ensure_ascii=False).encode()
    ).hexdigest()
    named = sum(1 for e in entries)
    unnamed = total_figs - sum(len(v) for v in occurrences.values())
    return {
        "atlas": {
            "key": meta["atlas_key"],
            "title": meta["title"],
            "short": meta["short"],
            "source": source_note,
            "source_sha256": digest,
            "note": f"도판 {len(caps)}장 · 그림 {total_figs}개"
                    + (f" (이름 못 짚은 {unnamed}개는 항목에 안 담았다)"
                       if unnamed else "")
                    + f" · 종 항목 {named}개",
        },
        "entries": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="논문 키 하나만")
    ap.add_argument("--dry-run", action="store_true", help="안 쓰고 요약만 본다")
    args = ap.parse_args()

    papers = [args.only] if args.only else list(PAPER_META)
    for paper in papers:
        if paper not in CAPTIONS or paper not in SOURCE:
            print(f"{paper}: plate_figs.py 에 없다", file=sys.stderr)
            return 2
        doc = build(paper)
        n_e = len(doc["entries"])
        n_p = sum(len(e["placements"]) for e in doc["entries"])
        print(f"{doc['atlas']['short']} — 항목 {n_e} · 자리 {n_p}")
        if not args.dry_run:
            out = OUT / f"{PAPER_META[paper]['atlas_key']}.json"
            out.write_text(
                json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
            print(f"  → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
