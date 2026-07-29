#!/usr/bin/env python3
"""같은 위치를 초점만 바꿔 찍은 사진들을 하나의 그룹으로 묶는다.

XML에 스테이지 XY/Z 좌표가 기록돼 있지 않으므로 이미지 내용으로 판단한다.
초점이 달라지면 고주파(선명도)는 크게 변하지만 입자들의 배치는 그대로이므로,
축소 + 가우시안 블러로 고주파를 죽인 뒤 정규화 상관계수를 비교하면
초점 변화에 둔감하고 시야 이동에는 민감한 지문이 된다.

촬영 시각 간격을 보조 신호로 함께 쓴다 (그룹 내부는 촘촘, 시야 이동 시 벌어짐).

사용 예:
    python group_focus_series.py "/mnt/d/260729/RS23-GC03 71cm" -o groups.json
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

import cv2
import numpy as np

THUMB_W = 256


def read_timestamp(jpg: Path):
    xml = jpg.with_name(jpg.name + "_metadata.xml")
    if not xml.exists():
        return None
    # 전체 파싱은 낭비 — 앞부분만 읽어 정규식으로 뽑는다 (파일당 140KB)
    txt = xml.read_text(encoding="utf-8-sig", errors="ignore")
    m = re.search(r"<AcquisitionDateAndTime>(.*?)</AcquisitionDateAndTime>", txt)
    if not m:
        return None
    return dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))


def fingerprint(jpg: Path, blur_sigma: float):
    """초점 변화에 둔감한 저주파 지문."""
    img = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise IOError(f"cannot read {jpg}")
    h = int(THUMB_W * img.shape[0] / img.shape[1])
    small = cv2.resize(img, (THUMB_W, h), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small.astype(np.float32), (0, 0), blur_sigma)
    small -= small.mean()
    s = small.std()
    return small / s if s > 1e-6 else small


def sharpness(jpg: Path):
    """Laplacian 분산 — 값이 클수록 초점이 잘 맞은 장."""
    img = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE)
    small = cv2.resize(img, (1024, int(1024 * img.shape[0] / img.shape[1])),
                       interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(small, cv2.CV_32F).var())


def ncc(a, b):
    return float((a * b).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="이미지 디렉토리")
    ap.add_argument("-o", "--out", default="groups.json")
    ap.add_argument("--corr-thresh", type=float, default=0.55,
                    help="이 값 이상이면 같은 시야로 판단")
    ap.add_argument("--blur", type=float, default=2.0)
    ap.add_argument("--max-gap-sec", type=float, default=0.0,
                    help=">0 이면 이 시간 이상 벌어진 경우 상관계수와 무관하게 분리")
    args = ap.parse_args()

    files = sorted(Path(args.input).glob("*.jpg"))
    print(f"{len(files)} images")

    fps = [fingerprint(f, args.blur) for f in files]
    times = [read_timestamp(f) for f in files]

    corrs = [ncc(fps[i], fps[i + 1]) for i in range(len(files) - 1)]
    gaps = [
        (times[i + 1] - times[i]).total_seconds()
        if times[i] and times[i + 1] else float("nan")
        for i in range(len(files) - 1)
    ]

    groups, cur = [], [0]
    for i, c in enumerate(corrs):
        split = c < args.corr_thresh
        if args.max_gap_sec > 0 and gaps[i] == gaps[i] and gaps[i] > args.max_gap_sec:
            split = True
        if split:
            groups.append(cur)
            cur = []
        cur.append(i + 1)
    groups.append(cur)

    out = {"dir": str(args.input), "corr_thresh": args.corr_thresh, "groups": []}
    print(f"\n{len(groups)} groups")
    for gi, g in enumerate(groups):
        names = [files[i].stem for i in g]
        sharp = {files[i].stem: round(sharpness(files[i]), 1) for i in g}
        best = max(sharp, key=sharp.get)
        span = ((times[g[-1]] - times[g[0]]).total_seconds()
                if times[g[0]] and times[g[-1]] else None)
        out["groups"].append({
            "id": gi, "images": names, "n": len(g),
            "sharpest": best, "sharpness": sharp, "span_sec": span,
        })
        print(f"  [{gi:3d}] n={len(g):2d} {names[0]}..{names[-1]}  "
              f"best={best} span={span}s")

    # 진단용: 경계에서의 상관계수 분포
    inner = [corrs[i] for gi, g in enumerate(groups) for i in g[:-1] if i < len(corrs)]
    print(f"\ncorr within-group: min={min(inner):.3f}" if inner else "")
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
