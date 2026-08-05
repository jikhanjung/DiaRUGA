"""SAM2.1 을 CPU 와 GPU 에서 재는 일회성 벤치마크. DB 를 건드리지 않는다.

    python bench_sam2.py <cpu|cuda> <points_per_side> <이미지> [threads]

운영 설정과 같은 모델·문턱을 쓴다 (segment_diatoms.py 참고):
    facebook/sam2.1-hiera-base-plus · pred_iou 0.5 · stability 0.75
"""
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

device = sys.argv[1]
pps = int(sys.argv[2])
img_path = sys.argv[3]
threads = int(sys.argv[4]) if len(sys.argv) > 4 else 6

if device == "cpu":
    torch.set_num_threads(threads)

t = time.time()
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
from sam2.build_sam import build_sam2_hf
from sam2.sam2_image_predictor import SAM2ImagePredictor
t_import = time.time() - t

t = time.time()
sam2 = build_sam2_hf("facebook/sam2.1-hiera-base-plus", device=device,
                     apply_postprocessing=False)
t_load = time.time() - t

img = np.array(Image.open(img_path).convert("RGB"))

# 1) 이미지 인코더만 — 이미지당 한 번 도는 고정 비용
pred = SAM2ImagePredictor(sam2)
t = time.time()
with torch.inference_mode():
    pred.set_image(img)
if device == "cuda":
    torch.cuda.synchronize()
t_encode = time.time() - t

# 2) 전체 자동 마스크 생성 — 점 pps*pps 개
gen = SAM2AutomaticMaskGenerator(
    sam2, points_per_side=pps, points_per_batch=32,
    pred_iou_thresh=0.5, stability_score_thresh=0.75)
t = time.time()
with torch.inference_mode():
    masks = gen.generate(img)
if device == "cuda":
    torch.cuda.synchronize()
t_gen = time.time() - t

print(f"device={device} pps={pps} points={pps*pps} threads={threads if device=='cpu' else '-'}")
print(f"  이미지        {img.shape[1]}x{img.shape[0]}")
print(f"  import        {t_import:8.2f} s")
print(f"  모델 적재      {t_load:8.2f} s")
print(f"  인코더(1회)    {t_encode:8.2f} s")
print(f"  전체 생성      {t_gen:8.2f} s   → 마스크 {len(masks)}개")
print(f"  디코딩분(추정)  {t_gen - t_encode:8.2f} s   "
      f"({(t_gen - t_encode) / (pps * pps) * 1000:.1f} ms/점)")
