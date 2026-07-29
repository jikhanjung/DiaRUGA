#!/usr/bin/env python3
"""
규조류 현미경 사진에서 object 후보 위치를 찾아낸다.

백엔드는 교체 가능하게 설계했다. 현재는 SAM2.1 AutomaticMaskGenerator를 쓰고,
facebook/sam3 접근 권한이 생기면 --backend sam3 로 바꾸면 된다.

사용 예:
    python segment_diatoms.py "/mnt/d/260729/RS23-GC03 71cm/Snap-21365.jpg" -o out/
    python segment_diatoms.py "/mnt/d/260729/RS23-GC03 71cm" -o out/ --limit 5
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

# 40x/0.95 + 1.6x optovar + 0.63x adapter, Axiocam 506 (4.54 µm pixel)
# XML의 Scaling/Items/Distance = 1.1259920634920635E-07 m
UM_PER_PIXEL = 0.11259920634920635


def autocast_dtype():
    """GPU 세대에 맞는 autocast dtype. Pascal(6.x)은 bf16 미지원 + fp16이 느려서 fp32."""
    if not torch.cuda.is_available():
        return None
    major, _ = torch.cuda.get_device_capability()
    if major >= 8:
        return torch.bfloat16
    if major == 7:
        return torch.float16
    return None


def load_generator(backend: str, device: str, args):
    if backend == "sam2":
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
        from sam2.build_sam import build_sam2_hf

        model_id = os.environ.get("SAM2_MODEL", "facebook/sam2.1-hiera-base-plus")
        sam2 = build_sam2_hf(model_id, device=device, apply_postprocessing=False)
        return SAM2AutomaticMaskGenerator(
            model=sam2,
            points_per_side=args.points_per_side,
            points_per_batch=args.points_per_batch,   # 4GB VRAM 고려
            pred_iou_thresh=args.iou_thresh,          # 후보 많이 뽑는 쪽으로 완화
            stability_score_thresh=args.stability_thresh,
            crop_n_layers=args.crop_layers,           # 1 이상이면 타일링 — 작은 객체 recall↑
            crop_overlap_ratio=0.35,
            box_nms_thresh=0.8,
            min_mask_region_area=0,
        )
    if backend == "sam3":
        raise SystemExit(
            "sam3 백엔드는 HF gated 접근 권한(HF_TOKEN)이 필요합니다. "
            "huggingface.co/facebook/sam3 에서 승인 후 재시도하세요."
        )
    raise SystemExit(f"unknown backend: {backend}")


def masks_to_records(masks, um_per_px=UM_PER_PIXEL):
    """SAM 마스크 dict 리스트를 정리된 후보 레코드로."""
    records = []
    for i, m in enumerate(masks):
        x, y, w, h = m["bbox"]
        area_px = int(m["area"])
        seg = m["segmentation"]
        # 형태 지표: 채움율, 종횡비 — 규조류(껍질)는 대체로 채움율이 높다
        fill = area_px / max(w * h, 1)
        records.append(
            {
                "id": i,
                "bbox_xywh": [int(x), int(y), int(w), int(h)],
                "center_xy": [int(x + w / 2), int(y + h / 2)],
                "area_px": area_px,
                "area_um2": round(area_px * um_per_px**2, 2),
                "long_side_um": round(max(w, h) * um_per_px, 2),
                "short_side_um": round(min(w, h) * um_per_px, 2),
                "aspect_ratio": round(max(w, h) / max(min(w, h), 1), 2),
                "fill_ratio": round(fill, 3),
                "predicted_iou": round(float(m["predicted_iou"]), 3),
                "stability_score": round(float(m["stability_score"]), 3),
                "rle": None,  # 필요하면 별도 저장
            }
        )
        records[-1]["_seg"] = seg
    return records


def filter_records(records, min_um, max_um, drop_background_frac=0.5, img_area=None):
    """너무 작은 debris와 배경 전체를 덮는 마스크를 제거."""
    out = []
    for r in records:
        if r["long_side_um"] < min_um or r["long_side_um"] > max_um:
            continue
        if img_area and r["area_px"] > drop_background_frac * img_area:
            continue
        out.append(r)
    return out


def draw_overlay(img: Image.Image, records, out_path: Path):
    from PIL import ImageDraw

    vis = img.convert("RGB").copy()
    overlay = np.array(vis)
    rng = np.random.default_rng(0)
    for r in records:
        seg = r["_seg"]
        color = rng.integers(60, 255, size=3)
        overlay[seg] = (0.55 * overlay[seg] + 0.45 * color).astype(np.uint8)
    vis = Image.fromarray(overlay)
    d = ImageDraw.Draw(vis)
    for r in records:
        x, y, w, h = r["bbox_xywh"]
        d.rectangle([x, y, x + w, y + h], outline=(255, 40, 40), width=3)
        d.text((x + 4, max(y - 16, 0)), f"{r['id']}:{r['long_side_um']:.0f}um",
               fill=(255, 40, 40))
    vis.save(out_path, quality=88)


def process(img_path: Path, gen, args, out_dir: Path):
    img = Image.open(img_path).convert("RGB")
    if args.scale != 1.0:
        img = img.resize((int(img.width * args.scale), int(img.height * args.scale)),
                         Image.LANCZOS)
    arr = np.array(img)

    with torch.inference_mode():
        dtype = autocast_dtype()
        if dtype is None:
            masks = gen.generate(arr)
        else:
            with torch.autocast("cuda", dtype=dtype):
                masks = gen.generate(arr)

    um_per_px = UM_PER_PIXEL / args.scale
    recs = masks_to_records(masks, um_per_px)
    kept = filter_records(recs, args.min_um, args.max_um, img_area=arr.shape[0] * arr.shape[1])
    kept.sort(key=lambda r: -r["area_px"])
    for i, r in enumerate(kept):
        r["id"] = i

    stem = img_path.stem
    draw_overlay(img, kept, out_dir / f"{stem}_overlay.jpg")
    payload = {
        "image": str(img_path),
        "size": [img.width, img.height],
        "scale": args.scale,
        "um_per_pixel": um_per_px,
        "n_raw_masks": len(recs),
        "n_candidates": len(kept),
        "candidates": [{k: v for k, v in r.items() if not k.startswith("_")} for r in kept],
    }
    (out_dir / f"{stem}_candidates.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(f"{stem}: raw={len(recs)} kept={len(kept)}")
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="이미지 파일 또는 디렉토리")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--backend", default="sam2", choices=["sam2", "sam3"])
    ap.add_argument("--scale", type=float, default=0.5,
                    help="처리 전 리사이즈 배율 (VRAM 절약)")
    ap.add_argument("--min-um", type=float, default=5.0)
    ap.add_argument("--max-um", type=float, default=250.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--points-per-side", type=int, default=32)
    ap.add_argument("--points-per-batch", type=int, default=32)
    ap.add_argument("--crop-layers", type=int, default=0,
                    help="1이면 2x2 타일 추가 스캔 (작은 객체 recall 향상, 느려짐)")
    ap.add_argument("--iou-thresh", type=float, default=0.5)
    ap.add_argument("--stability-thresh", type=float, default=0.75)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} backend={args.backend}", file=sys.stderr)

    inp = Path(args.input)
    files = sorted(inp.glob("*.jpg")) if inp.is_dir() else [inp]
    if args.limit:
        files = files[: args.limit]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = load_generator(args.backend, device, args)
    for f in files:
        try:
            process(f, gen, args, out_dir)
        except torch.cuda.OutOfMemoryError:
            print(f"OOM on {f.name} — --scale 을 낮추세요", file=sys.stderr)
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
