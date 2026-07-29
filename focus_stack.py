#!/usr/bin/env python3
"""초점 시리즈를 합쳐 all-in-focus 이미지와 깊이(초점) 맵을 만든다.

group_focus_series.py 가 만든 groups.json 을 입력으로 받는다.

원리:
  1. 정렬 — 같은 위치라도 초점을 돌리면 배율이 미세하게 변하고(focus breathing)
     스테이지가 흔들리므로, ECC로 평행이동+스케일을 맞춘다.
  2. 선명도 맵 — 각 장에서 픽셀별 국소 선명도를 구한다. 라플라시안 절댓값을
     가우시안으로 부드럽게 한 값을 쓴다 (노이즈에 덜 민감).
  3. 합성 — 픽셀마다 가장 선명한 장을 고른다. 하드 선택은 경계에 이음매를
     만들므로, 선명도를 가중치로 한 soft blending 을 기본으로 한다.
  4. 깊이 맵 — 픽셀별로 '몇 번째 장이 가장 선명했나'가 곧 상대적인 높이다.
     규조류 피각의 입체 구조가 여기에 드러난다.

사용 예:
    python focus_stack.py groups_RS23.json -o stacked/
    python focus_stack.py groups_RS23.json -o stacked/ --only 0 1 2
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from zen_meta import ScaleLog, scaling_for, write_scale_sidecar


def align_to_reference(ref_gray, img, img_gray, use_ecc=True):
    """img 를 ref 에 맞춘다. 실패하면 원본 그대로 반환."""
    if not use_ecc:
        return img, True
    warp = np.eye(2, 3, dtype=np.float32)
    # 초점 차이에 강건하도록 블러 후 정렬
    a = cv2.GaussianBlur(ref_gray, (0, 0), 3)
    b = cv2.GaussianBlur(img_gray, (0, 0), 3)
    try:
        cv2.findTransformECC(
            a, b, warp, cv2.MOTION_EUCLIDEAN,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5),
            None, 5,
        )
    except cv2.error:
        return img, False
    h, w = img.shape[:2]
    out = cv2.warpAffine(img, warp, (w, h),
                         flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                         borderMode=cv2.BORDER_REPLICATE)
    return out, True


def sharpness_map(gray, sigma=3.0):
    """픽셀별 국소 선명도."""
    lap = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F, ksize=3)
    return cv2.GaussianBlur(np.abs(lap), (0, 0), sigma)


def build_depth(smaps, best, conf_pct):
    """초점 슬라이스 인덱스에서 연속 깊이 맵과 신뢰 영역 마스크를 만든다.

    슬라이스가 5~6장뿐이라 argmax를 그대로 쓰면 깊이가 5~6단계로 뭉툭해진다.
    최대점 주변 3점에 포물선을 맞춰 소수점 단위로 보간한다 (subslice refinement).

    배경은 어느 장에서도 초점이 맞지 않아 argmax가 사실상 난수다. 최대 선명도가
    배경 수준을 뚜렷이 넘는 픽셀만 신뢰 영역으로 남기고 나머지는 마스킹한다.
    """
    n = smaps.shape[0]
    conf = smaps.max(axis=0)

    # 배경 수준 추정: 하위 절반의 중앙값을 잡음 바닥으로 본다
    floor = np.median(conf[conf <= np.percentile(conf, 50)])
    mask = (conf > np.percentile(conf, conf_pct)) & (conf > floor * 3.0)
    # 자잘한 스페클 제거
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN,
                            np.ones((5, 5), np.uint8)).astype(bool)

    # 포물선 보간: d = i + 0.5*(s[i-1]-s[i+1]) / (s[i-1]-2*s[i]+s[i+1])
    idx = np.clip(best, 1, n - 2)
    take = lambda o: np.take_along_axis(smaps, (idx + o)[None], axis=0)[0]  # noqa: E731
    s0, s1, s2 = take(-1), take(0), take(1)
    denom = s0 - 2 * s1 + s2
    shift = np.where(np.abs(denom) > 1e-6, 0.5 * (s0 - s2) / (denom + 1e-12), 0.0)
    shift = np.clip(shift, -1.0, 1.0)
    depth = idx.astype(np.float32) + shift
    # 가장자리 슬라이스가 최대인 경우는 보간 불가 — argmax 그대로
    edge = (best == 0) | (best == n - 1)
    depth[edge] = best[edge]

    # 공간 정규화: 신뢰 영역 안에서만 median 필터
    depth_f = cv2.medianBlur(depth.astype(np.float32), 5)
    depth = np.where(mask, depth_f, np.nan).astype(np.float32)
    return depth, mask


def carry_scaling(paths, scale, out_img, tag, scale_log=None):
    """합성본에 픽셀 크기를 물려준다.

    합성본에는 ZEN XML 이 따라오지 않으므로, 원본에서 읽은 값을 사이드카로
    남기지 않으면 검출 단계가 계측 기준을 잃는다.
    """
    scalings = [scaling_for(p) for p in paths]
    native = scalings[0]["um_per_pixel"]
    if any(abs(s["um_per_pixel"] - native) > native * 1e-3 for s in scalings):
        print(f"{tag}: 경고 — 그룹 안에서 픽셀 크기가 다르다. "
              f"첫 장({paths[0].name}) 기준으로 남긴다", file=sys.stderr)

    um = native / scale        # 리사이즈했으면 픽셀이 그만큼 커진다
    write_scale_sidecar(out_img, um,
                        source=scalings[0]["source"],
                        native_um_per_pixel=native,
                        resize_scale=scale,
                        stacked_from=[p.name for p in paths])
    if scale_log is not None:
        scale_log.add(tag, um)
    return um


def stack_group(paths, scale, use_ecc, soft, conf_pct, out_dir, tag, scale_log=None):
    imgs, grays = [], []
    for p in paths:
        im = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if im is None:
            raise IOError(f"cannot read {p}")
        if scale != 1.0:
            im = cv2.resize(im, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_AREA)
        imgs.append(im)
        grays.append(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY))

    # 가장 선명한 장을 정렬 기준으로 삼는다
    ref_i = int(np.argmax([cv2.Laplacian(g, cv2.CV_32F).var() for g in grays]))
    ref_gray = grays[ref_i]

    aligned, ok_flags = [], []
    for i, (im, g) in enumerate(zip(imgs, grays)):
        if i == ref_i:
            aligned.append(im); ok_flags.append(True); continue
        a, ok = align_to_reference(ref_gray, im, g, use_ecc)
        aligned.append(a); ok_flags.append(ok)
    n_failed = ok_flags.count(False)

    grays_a = [cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) for a in aligned]
    smaps = np.stack([sharpness_map(g) for g in grays_a])       # (N,H,W)
    stack = np.stack(aligned).astype(np.float32)                # (N,H,W,3)

    best = np.argmax(smaps, axis=0).astype(np.int32)            # 깊이 인덱스

    if soft:  # noqa: SIM108  (아래에서 hard 분기와 함께 읽히도록 유지)
        # 선명도를 강조해 가중 평균 — 이음매 없이 합성
        w = smaps - smaps.min(axis=0, keepdims=True)
        w = (w / (w.max(axis=0, keepdims=True) + 1e-6)) ** 4
        w /= w.sum(axis=0, keepdims=True) + 1e-6
        fused = (stack * w[..., None]).sum(axis=0)
    else:
        fused = np.take_along_axis(stack, best[None, ..., None], axis=0)[0]
    fused = np.clip(fused, 0, 255).astype(np.uint8)

    depth, conf_mask = build_depth(smaps, best, conf_pct)

    depth_vis = np.full(depth.shape + (3,), 60, np.uint8)
    if conf_mask.any():
        lo, hi = depth[conf_mask].min(), depth[conf_mask].max()
        norm = (depth - lo) / (hi - lo) if hi > lo else np.zeros_like(depth)
        norm = np.nan_to_num(norm, nan=0.0)   # 마스크 밖은 NaN
        colored = cv2.applyColorMap((np.clip(norm, 0, 1) * 255).astype(np.uint8),
                                    cv2.COLORMAP_TURBO)
        depth_vis[conf_mask] = colored[conf_mask]

    out_img = out_dir / f"{tag}_focused.jpg"
    cv2.imwrite(str(out_img), fused, [cv2.IMWRITE_JPEG_QUALITY, 92])
    um_per_px = carry_scaling(paths, scale, out_img, tag, scale_log)
    cv2.imwrite(str(out_dir / f"{tag}_depth.jpg"), depth_vis,
                [cv2.IMWRITE_JPEG_QUALITY, 92])
    np.savez_compressed(str(out_dir / f"{tag}_depth.npz"),
                        depth=depth.astype(np.float32),
                        mask=conf_mask)

    # 선명도 비교는 전역 Laplacian 분산으로 하면 안 된다. 초점이 크게 어긋난
    # 덩어리는 짙은 그림자가 되어 오히려 분산을 키우므로, 합성이 성공해도
    # 숫자가 내려간다. 물체가 있는 영역(conf_mask)에서의 국소 선명도로 비교한다.
    fused_sharp = sharpness_map(cv2.cvtColor(fused, cv2.COLOR_BGR2GRAY))
    m = conf_mask
    per_slice = [float(s[m].mean()) for s in smaps] if m.any() else [0.0]
    fused_mean = float(fused_sharp[m].mean()) if m.any() else 0.0
    best_single = max(per_slice)
    print(f"{tag}: n={len(paths)} ref={paths[ref_i].stem} align_failed={n_failed} "
          f"local sharpness (object px) best-single {best_single:.2f} -> "
          f"fused {fused_mean:.2f} ({fused_mean / max(best_single, 1e-6):.2f}x)")
    return {"tag": tag, "n": len(paths), "ref": paths[ref_i].stem,
            "align_failed": n_failed, "um_per_pixel": round(um_per_px, 8),
            "object_px_frac": round(float(m.mean()), 4),
            "sharpness_best_single": round(best_single, 3),
            "sharpness_fused": round(fused_mean, 3),
            "gain": round(fused_mean / max(best_single, 1e-6), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("groups_json")
    ap.add_argument("-o", "--out", default="stacked")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--min-n", type=int, default=2,
                    help="이 장수 미만인 그룹은 건너뜀 (단발 촬영)")
    ap.add_argument("--only", type=int, nargs="*", help="특정 그룹 id 만 처리")
    ap.add_argument("--no-ecc", action="store_true", help="정렬 생략 (빠름)")
    ap.add_argument("--hard", action="store_true",
                    help="soft blending 대신 픽셀별 최선명 장을 그대로 선택")
    ap.add_argument("--conf-pct", type=float, default=90.0,
                    help="깊이 맵 신뢰 영역 퍼센타일 (높을수록 물체만 남음)")
    args = ap.parse_args()

    meta = json.loads(Path(args.groups_json).read_text(encoding="utf-8"))
    root = Path(meta["dir"])
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    scale_log = ScaleLog()
    for g in meta["groups"]:
        if args.only is not None and g["id"] not in args.only:
            continue
        if g["n"] < args.min_n:
            continue
        paths = [root / f"{name}.jpg" for name in g["images"]]
        tag = f"g{g['id']:03d}_{g['images'][0]}-{g['images'][-1].split('-')[-1]}"
        results.append(stack_group(paths, args.scale, not args.no_ecc,
                                   not args.hard, args.conf_pct, out_dir, tag,
                                   scale_log))

    (out_dir / "stack_report.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n{len(results)} groups stacked -> {out_dir}")


if __name__ == "__main__":
    main()
