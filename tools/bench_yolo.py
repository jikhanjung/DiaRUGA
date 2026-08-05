"""YOLO11m-seg 를 CPU 와 GPU 에서 재는 일회성 벤치마크. DB 를 건드리지 않는다.

    python bench_yolo.py <cpu|cuda> <가중치> <이미지> [반복] [threads]

운영과 같은 imgsz=1280 · conf 는 견주기에 쓴 0.033.
"""
import sys
import time

import torch
from ultralytics import YOLO

device = sys.argv[1]
weights = sys.argv[2]
img_path = sys.argv[3]
reps = int(sys.argv[4]) if len(sys.argv) > 4 else 5
threads = int(sys.argv[5]) if len(sys.argv) > 5 else 12

if device == "cpu":
    torch.set_num_threads(threads)

t = time.time()
model = YOLO(weights)
t_load = time.time() - t

# 첫 판은 준비 비용(그래프·메모리)이 섞인다 — 따로 잰다
t = time.time()
r = model.predict(img_path, imgsz=1280, conf=0.033, device=device, verbose=False)
if device == "cuda":
    torch.cuda.synchronize()
t_first = time.time() - t
n = len(r[0].boxes) if r[0].boxes is not None else 0

ts = []
for _ in range(reps):
    t = time.time()
    model.predict(img_path, imgsz=1280, conf=0.033, device=device, verbose=False)
    if device == "cuda":
        torch.cuda.synchronize()
    ts.append(time.time() - t)

ts.sort()
print(f"device={device} imgsz=1280 threads={threads if device=='cpu' else '-'}")
print(f"  모델 적재      {t_load:8.2f} s")
print(f"  첫 판(준비 포함) {t_first:8.2f} s   → 검출 {n}개")
print(f"  중앙값        {ts[len(ts)//2]:8.3f} s")
print(f"  최소~최대     {ts[0]:8.3f} ~ {ts[-1]:.3f} s   (반복 {reps}회)")
