"""conf 를 훑어 P·R·F1 과 개수비를 낸다 (devlog 025 §8).

    python pr_sweep.py                    # seg·detect 둘 다, val_slide
    python pr_sweep.py --split val

`mAP` 는 곡선 전체를 한 숫자로 접은 것이라 **운영점을 못 고른다.** 문턱마다
몇 개를 내고 그중 몇 개가 맞는지가 필요해서 따로 잰다.

개수비(예측÷정답)를 함께 내는 이유: 이 과제의 목적은 계수다. 개체 하나하나의
정오보다 **총 개수가 맞는지**가 군집 조성에 직결된다. 놓친 것과 헛본 것이
상쇄되는 자리가 있고, 그 자리는 F1 최대점과 다르다.

정답 상자는 폴리곤 라벨이면 외접 상자로 만든다 — 상자 판과 폴리곤 판에 같은
코드를 쓴다. 짝짓기는 시야마다 conf 내림차순 탐욕 매칭, IoU >= 0.5.
"""
import argparse
from pathlib import Path

import numpy as np
from ultralytics import YOLO

IOU_T = 0.5


def gt_boxes(label_path, w, h):
    """라벨 한 줄이 상자(5칸)든 폴리곤(홀수칸)이든 xyxy 로 만든다."""
    out = []
    if not label_path.exists():
        return np.zeros((0, 4))
    for line in label_path.read_text().strip().splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        v = np.array([float(x) for x in p[1:]])
        if len(v) == 4:                      # cx cy w h
            cx, cy, bw, bh = v
            x1, y1, x2, y2 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
        else:                                # x1 y1 x2 y2 ... (폴리곤)
            xs, ys = v[0::2], v[1::2]
            x1, y1, x2, y2 = xs.min(), ys.min(), xs.max(), ys.max()
        out.append([x1 * w, y1 * h, x2 * w, y2 * h])
    return np.array(out) if out else np.zeros((0, 4))


def iou_mat(a, b):
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    ar_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    ar_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (ar_a[:, None] + ar_b[None, :] - inter + 1e-9)


def sweep(weights, img_dir, lbl_dir):
    model = YOLO(weights)
    imgs = sorted(Path(img_dir).glob("*.jpg"))
    recs, n_gt = [], 0
    for im in imgs:
        r = model.predict(str(im), imgsz=1280, conf=0.001, iou=0.7,
                          max_det=300, device=0, verbose=False)[0]
        h, w = r.orig_shape
        g = gt_boxes(Path(lbl_dir) / f"{im.stem}.txt", w, h)
        n_gt += len(g)
        pb = r.boxes.xyxy.cpu().numpy()
        pc = r.boxes.conf.cpu().numpy()
        order = np.argsort(-pc)
        pb, pc = pb[order], pc[order]
        M = iou_mat(pb, g)
        taken = set()
        for i in range(len(pb)):
            j, best = -1, IOU_T
            for k in range(len(g)):
                if k in taken:
                    continue
                if M[i, k] >= best:
                    j, best = k, M[i, k]
            if j >= 0:
                taken.add(j)
            recs.append((pc[i], j >= 0))
    return recs, n_gt


def report(recs, n_gt, title):
    recs.sort(key=lambda t: -t[0])
    conf = np.array([r[0] for r in recs])
    tp = np.cumsum([r[1] for r in recs]).astype(float)
    fp = np.cumsum([not r[1] for r in recs]).astype(float)
    P = tp / (tp + fp)
    R = tp / n_gt
    F1 = 2 * P * R / (P + R + 1e-9)

    print(f"\n=== {title}  (정답 {n_gt}개, 예측 {len(recs)}개)")
    print(f"{'conf':>6} {'예측수':>7} {'TP':>5} {'FP':>6} "
          f"{'정밀도':>7} {'재현율':>7} {'F1':>6} {'개수비':>7}")
    for t in (0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05, 0.02, 0.01):
        i = np.searchsorted(-conf, -t, side="right") - 1
        if i < 0:
            continue
        print(f"{t:>6.2f} {i+1:>7} {tp[i]:>5.0f} {fp[i]:>6.0f} "
              f"{P[i]:>7.3f} {R[i]:>7.3f} {F1[i]:>6.3f} {(i+1)/n_gt:>7.2f}")
    b = int(np.argmax(F1))
    print(f"  최대 F1: conf={conf[b]:.3f}  P={P[b]:.3f} R={R[b]:.3f} "
          f"F1={F1[b]:.3f}  개수비={(b+1)/n_gt:.2f}")
    print(f"  재현율 상한(conf→0): {R[-1]:.3f}  "
          f"(그때 정밀도 {P[-1]:.3f}, 개수비 {len(recs)/n_gt:.1f})")
    return conf, P, R, F1


D = Path(__file__).resolve().parent
MODELS = {
    "seg": (D / "runs/segment/11m-v1seg-1280/weights/best.pt",
            D / "datasets/yolo-v1-seg"),
    "detect": (D / "runs/detect/11m-v1-1280/weights/best.pt",
               D / "datasets/yolo-v1"),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", default="val_slide",
                    choices=("val", "val_slide", "train"))
    ap.add_argument("--models", nargs="*", default=list(MODELS),
                    choices=list(MODELS))
    ap.add_argument("--json", help="곡선 전체를 이 파일에 낸다(그림용)")
    args = ap.parse_args()

    dump = {}
    for name in args.models:
        w, ds = MODELS[name]
        if not w.exists():
            print(f"건너뛴다 — 가중치가 없다: {w}")
            continue
        recs, n_gt = sweep(w, ds / "images" / args.split,
                           ds / "labels" / args.split)
        conf, P, R, F1 = report(recs, n_gt, f"{name} · {args.split}")
        dump[name] = {"n_gt": n_gt,
                      "conf": conf.tolist(), "P": P.tolist(),
                      "R": R.tolist(), "F1": F1.tolist()}
    if args.json:
        import json
        Path(args.json).write_text(json.dumps(dump))
        print(f"\n곡선을 {args.json} 에 냈다")
