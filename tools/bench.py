#!/usr/bin/env python3
"""리사이즈 배율 / points_per_batch / 모델 크기 조합별 장당 시간과 peak VRAM 측정.

4GB 카드에서 sysmem fallback(스래싱)을 피하는 게 핵심이라
peakVRAM이 3.0GB를 넘지 않는 조합을 찾는 것이 목표다.
"""
import sys, time
import numpy as np, torch
from PIL import Image
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
from sam2.build_sam import build_sam2_hf

src = Image.open(sys.argv[1]).convert("RGB")
print(f"source {src.size}", flush=True)

CONFIGS = [
    # (model, scale, points_per_side, points_per_batch)
    ("facebook/sam2.1-hiera-tiny",      0.5, 32, 16),
    ("facebook/sam2.1-hiera-small",     0.5, 32, 16),
    ("facebook/sam2.1-hiera-base-plus", 0.5, 32, 16),
    ("facebook/sam2.1-hiera-base-plus", 0.5, 48, 16),
    ("facebook/sam2.1-hiera-base-plus", 0.4, 64, 16),
]

cache = {}
for model_id, scale, pps, ppb in CONFIGS:
    if model_id not in cache:
        cache.clear()
        torch.cuda.empty_cache()
        cache[model_id] = build_sam2_hf(model_id, device="cuda",
                                        apply_postprocessing=False)
    m = cache[model_id]

    img = np.array(src.resize((int(src.width * scale), int(src.height * scale)),
                              Image.LANCZOS))
    gen = SAM2AutomaticMaskGenerator(
        model=m, points_per_side=pps, points_per_batch=ppb,
        pred_iou_thresh=0.5, stability_score_thresh=0.75,
        crop_n_layers=0, min_mask_region_area=0)

    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize(); t0 = time.time()
    with torch.inference_mode():
        masks = gen.generate(img)
    torch.cuda.synchronize()
    dt = time.time() - t0
    peak = torch.cuda.max_memory_allocated() / 2**30
    tag = model_id.rsplit("-", 1)[-1]
    print(f"{tag:10s} scale={scale} pps={pps:3d} ppb={ppb:3d} | "
          f"{dt:6.1f}s  masks={len(masks):4d}  peakVRAM={peak:.2f}GB", flush=True)
