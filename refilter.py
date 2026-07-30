#!/usr/bin/env python3
"""
검출 JSON 의 문턱만 바꿔 다시 거른다. SAM2 를 다시 돌리지 않는다.

segment_diatoms.py 가 형태·텍스처 지표를 통과분(candidates)과 탈락분(rejected)
양쪽에 모두 기록해 두므로, 두 목록을 합쳐 새 문턱으로 재판정하면 된다.
장당 30초짜리 추론 대신 밀리초로 끝난다.

    python refilter.py out/ --texture-min 3000 --rod-min-iou 0.7
    python refilter.py out/ --dry-run          # 개수만 보고 파일은 안 건드림
"""
import argparse
import json
from pathlib import Path

from segment_diatoms import classify, dedupe


def refilter(payload, args):
    # 통과분과 탈락분을 도로 합친다. 원래 순서는 의미가 없다.
    pool = list(payload.get("candidates", [])) + list(payload.get("rejected", []))
    for r in pool:
        r.pop("cls", None)
        r.pop("reject", None)

    passed, rejected = [], []
    for r in pool:
        if not (args.min_um <= r.get("long_side_um", 0) <= args.max_um):
            r["reject"] = "크기범위밖"
            rejected.append(r)
            continue
        cls, why = classify(r, args)
        if cls:
            r["cls"] = cls
            passed.append(r)
        else:
            r["reject"] = why
            rejected.append(r)

    kept = dedupe(passed)
    for r in passed:
        if r not in kept:
            r["reject"] = "중첩정리"
            rejected.append(r)

    kept.sort(key=lambda r: -r["area_px"])
    for i, r in enumerate(kept):
        r["id"] = i

    payload["n_candidates"] = len(kept)
    payload["counts"] = {
        "rod": sum(1 for r in kept if r.get("cls") == "rod"),
        "round": sum(1 for r in kept if r.get("cls") == "round"),
    }
    payload["candidates"] = kept
    payload["rejected"] = rejected
    payload["thresholds"] = {
        "min_um": args.min_um, "max_um": args.max_um,
        "texture_min": args.texture_min,
        "round_max_elong": args.round_max_elong,
        "round_min_iou": args.round_min_iou,
        "round_min_solidity": args.round_min_solidity,
        "round_texture_min": args.round_texture_min,
        "rod_min_elong": args.rod_min_elong, "rod_max_elong": args.rod_max_elong,
        "rod_min_iou": args.rod_min_iou, "rod_min_solidity": args.rod_min_solidity,
    }
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="검출 JSON 파일 또는 디렉토리")
    ap.add_argument("--dry-run", action="store_true", help="개수만 출력, 저장 안 함")
    ap.add_argument("--min-um", type=float, default=10.0)
    ap.add_argument("--max-um", type=float, default=150.0)
    ap.add_argument("--texture-min", type=float, default=1000.0)
    ap.add_argument("--round-max-elong", type=float, default=1.4)
    ap.add_argument("--round-min-iou", type=float, default=0.85)
    ap.add_argument("--round-min-solidity", type=float, default=0.92)
    # 원형에만 적용하는 areolae 세기 하한. segment_diatoms.py 와 기본값이 같아야
    # 문턱을 건드리지 않은 재적용이 결과를 바꾸지 않는다.
    ap.add_argument("--round-texture-min", type=float, default=1500.0)
    ap.add_argument("--rod-min-elong", type=float, default=2.0)
    ap.add_argument("--rod-max-elong", type=float, default=20.0)
    ap.add_argument("--rod-min-iou", type=float, default=0.72)
    ap.add_argument("--rod-min-solidity", type=float, default=0.85)
    # classify() 가 참조하지만 여기선 쓰지 않는 값
    ap.add_argument("--no-shape-filter", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    target = Path(args.target)
    files = sorted(target.glob("*_candidates.json")) if target.is_dir() else [target]
    if not files:
        raise SystemExit(f"검출 JSON 을 찾지 못했다: {target}")

    tot_before = tot_after = tot_rod = tot_round = 0
    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        before = payload.get("n_candidates", 0)
        payload = refilter(payload, args)
        after = payload["n_candidates"]
        tot_before += before
        tot_after += after
        tot_rod += payload["counts"]["rod"]
        tot_round += payload["counts"]["round"]
        print(f"{f.stem}: {before} -> {after} "
              f"(봉상 {payload['counts']['rod']}, 원형 {payload['counts']['round']})")
        if not args.dry_run:
            f.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    print(f"\n{len(files)}개 파일: 후보 {tot_before} -> {tot_after} "
          f"(봉상 {tot_rod}, 원형 {tot_round})")
    if args.dry_run:
        print("dry-run — 파일은 변경하지 않았다. 오버레이는 다시 그리지 않는다.")


if __name__ == "__main__":
    main()
