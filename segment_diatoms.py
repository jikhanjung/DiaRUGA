#!/usr/bin/env python3
"""
규조류 현미경 사진에서 object 후보 위치를 찾아낸다.

백엔드는 교체 가능하게 설계했다. 현재는 SAM2.1 AutomaticMaskGenerator를 쓰고,
facebook/sam3 접근 권한이 생기면 --backend sam3 로 바꾸면 된다.

사용 예:
    python segment_diatoms.py "/data3/diatom/stacked/g000_Snap-21365-21370_focused.jpg"
    python segment_diatoms.py "/data3/diatom/photos/260729/RS23-GC03 71cm" --limit 5

DB 로 옮기면서 달라진 것 (P02 6단계):

- **검출을 덮어쓰지 않고 쌓는다.** 돌릴 때마다 새 `Detection` 행이고 `is_current`
  가 뷰어가 볼 것을 가리킨다. 덮어쓰면 엔진 교체 전후를 비교할 수 없다
- **사람의 교정을 다시 맺는다** (`rebind.py`). 개체 행은 통째로 새로 만들어지므로
  교정의 `candidate` 링크가 끊긴다. `is_current` 이동과 재바인딩은 **반드시 한
  트랜잭션**이다 — 중간에 끊기면 뷰어가 "교정이 붙지 않은 새 검출"을 보여준다
- 실행이 `Run(kind=detect)` 에 남는다

`out/*_candidates.json` 은 계속 쓴다. 원본은 DB 지만 이 파일은 내보내기 형식으로
남는다(`verify_db.py` 가 대조에 쓴다). 7단계에서 정리한다.
"""
import argparse
import contextlib
import fcntl
import json
import os
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
import django
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diatomweb.settings")
django.setup()

from django.conf import settings                                    # noqa: E402
from django.db import transaction                                   # noqa: E402
from django.utils import timezone                                   # noqa: E402

import rebind                                                       # noqa: E402
import runlog                                                       # noqa: E402
from viewer.models import (Candidate, Detection, Frame, Run,        # noqa: E402
                           ThresholdSet, Viewpoint)
from judge import classify, dedupe                 # noqa: F401,E402 (외부에서 쓴다)
from judge import DEFAULTS as JUDGE_DEFAULTS       # noqa: E402
from zen_meta import DEFAULT_UM_PER_PIXEL, ScaleLog, scaling_for    # noqa: E402

# 판정 규칙은 judge.py 에 있다 — refilter.py 와 같은 함수를 써야 하고,
# 문턱 재조정은 GPU 가 필요 없는 일이라 torch 에 기대지 않아야 한다.

# µm/픽셀은 사진마다 딸려 오는 XML(Scaling/Items/Distance)에서 읽는다.
# 상수로 박아 두면 촬영 조건이 바뀌었을 때 조용히 전부 틀리기 때문이다.
# DEFAULT_UM_PER_PIXEL 은 XML 이 없을 때만 쓰는 최후의 값이다 — zen_meta.py 참조.

# 규조각 조흔(striae)·areolae 의 주기 범위. 보통 10 µm 당 8~20 개다.
# 픽셀이 아니라 µm 로 정의해야 --scale 을 바꿔도 같은 구조를 본다.
TEXTURE_PERIOD_UM = (0.4, 1.6)


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
    if backend == "yolo":
        return YoloGenerator(args.weights, device, conf=args.yolo_conf,
                             imgsz=args.yolo_imgsz, iou=args.yolo_nms_iou)
    if backend == "sam3":
        raise SystemExit(
            "sam3 백엔드는 HF gated 접근 권한(HF_TOKEN)이 필요합니다. "
            "huggingface.co/facebook/sam3 에서 승인 후 재시도하세요."
        )
    raise SystemExit(f"unknown backend: {backend}")


class YoloGenerator:
    """학습한 YOLO-seg 를 SAM2AutomaticMaskGenerator 와 같은 모양으로 감싼다.

    `generate(arr)` 가 SAM2 와 같은 dict 목록을 내면 뒤의 파이프라인
    (`masks_to_records` → `filter_records` → `judge`)이 그대로 돈다. **엔진을
    갈아도 지표 계산과 판정이 한 곳에 남는다** — 텍스처·신장률을 YOLO 쪽에서
    따로 세면 두 엔진의 숫자를 견줄 수 없게 된다.

    SAM2 의 `predicted_iou`·`stability_score` 자리에는 YOLO 의 `conf` 를 넣는다.
    `judge.py` 는 이 둘을 안 쓰므로 판정에는 영향이 없고, 기록으로 남아
    나중에 conf 별로 다시 거를 수 있다(`refilter.py` 와 같은 갈래).

    **`conf` 를 낮게 두고 뽑는 것이 기본이다.** 운영점은 슬라이드마다 다르고
    (devlog 025 §8), 낮게 뽑아 두면 DB 에서 다시 고를 수 있다.
    """

    def __init__(self, weights: str, device: str, conf: float, imgsz: int,
                 iou: float):
        from ultralytics import YOLO                          # noqa: PLC0415

        if not Path(weights).exists():
            raise SystemExit(f"가중치가 없다: {weights}")
        self.model = YOLO(weights)
        self.device = 0 if device == "cuda" else "cpu"
        self.conf, self.imgsz, self.iou = conf, imgsz, iou

    def generate(self, arr):
        r = self.model.predict(arr, imgsz=self.imgsz, conf=self.conf,
                               iou=self.iou, device=self.device,
                               verbose=False, retina_masks=True)[0]
        if r.masks is None:
            return []
        h, w = arr.shape[:2]
        out = []
        confs = r.boxes.conf.tolist()
        for i, m in enumerate(r.masks.data.cpu().numpy()):
            # retina_masks=True 면 원본 크기지만, 확인 없이 믿지 않는다
            if m.shape != (h, w):
                m = cv2.resize(m.astype(np.float32), (w, h),
                               interpolation=cv2.INTER_NEAREST)
            seg = m > 0.5
            area = int(seg.sum())
            if area == 0:
                continue
            ys, xs = np.nonzero(seg)
            x0, x1 = int(xs.min()), int(xs.max())
            y0, y1 = int(ys.min()), int(ys.max())
            c = round(float(confs[i]), 4)
            out.append({
                "segmentation": seg,
                # **상자를 마스크에서 다시 뽑는다.** YOLO 의 상자와 마스크는
                # 따로 예측되어 미세하게 어긋난다. SAM2 쪽은 마스크가 곧 상자라
                # 여기서 맞춰 두어야 두 엔진의 기하가 같은 뜻이 된다
                "bbox": [x0, y0, x1 - x0 + 1, y1 - y0 + 1],
                "area": area,
                "predicted_iou": c,
                "stability_score": c,
            })
        return out


def shape_metrics(seg):
    """
    마스크 하나의 형태 지표. 측정 불가면 None.

    원형도(circularity)는 신장비에 지배되므로 '테두리 매끈함' 으로 쓸 수 없다.
    신장비 6인 봉상은 윤곽이 완벽해도 0.37 이다. 매끈함은 convexity 로 잰다.
    """
    # SAM 마스크가 비연속 뷰로 올 때가 있어 cv2 가 거부한다.
    m = np.ascontiguousarray(seg.astype(np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < 20 or len(c) < 5:
        return None

    peri = cv2.arcLength(c, True)
    hull = cv2.convexHull(c)
    hull_area = cv2.contourArea(hull)

    (cx, cy), (d1, d2), ang = cv2.fitEllipse(c)
    major, minor = max(d1, d2), min(d1, d2)

    # 외곽선을 단순화해 저장한다. 마스크 전체(RLE)를 넣으면 JSON 이 수십 배로
    # 불어나는데, 뷰어는 윤곽만 있으면 SVG 로 그릴 수 있다.
    # epsilon 을 둘레에 비례시켜 크기와 무관하게 같은 정도로 단순화한다.
    poly = cv2.approxPolyDP(c, 0.004 * peri, True).reshape(-1, 2)

    # 적합 타원과의 IoU — 봉상(길쭉한 타원)과 원형(이심률 0)을 한 지표로 묶는다.
    # OpenCV 5 는 RotatedRect 축약형을 안 받아서 인자를 풀어 쓴다.
    canvas = np.zeros(m.shape, dtype=np.uint8)
    cv2.ellipse(canvas, (int(round(cx)), int(round(cy))),
                (int(round(d1 / 2)), int(round(d2 / 2))),
                float(ang), 0.0, 360.0, 1, -1)
    inter = int(np.logical_and(m, canvas).sum())
    union = int(np.logical_or(m, canvas).sum())

    return {
        "circularity": round(float(4 * np.pi * area / max(peri**2, 1e-9)), 3),
        # 볼록껍질 둘레 / 실제 둘레. 울퉁불퉁하면 분모만 길어진다. 신장비와 무관.
        "convexity": round(float(cv2.arcLength(hull, True) / max(peri, 1e-9)), 3),
        "solidity": round(float(area / max(hull_area, 1e-9)), 3),
        "elongation": round(float(major / max(minor, 1e-6)), 2),
        "ellipse_iou": round(float(inter / max(union, 1)), 3),
        # [x0,y0,x1,y1,...] 평탄 배열 — 좌표쌍 리스트보다 JSON 이 작다.
        "polygon": [int(v) for v in poly.ravel()],
        "_major_px": float(major),
        "_minor_px": float(minor),
    }


def texture_score(gray, seg, bbox, um_per_px):
    """
    규칙적 주기 구조(조흔·areolae)의 세기. 클수록 규조각답다.

    쇄설물은 주기 구조가 없어 스펙트럼이 평평하다. 실측에서 규조각은
    1,500~19,000, 구조 없는 티끌은 12~240 으로 세 자릿수가 갈렸다.
    """
    x, y, w, h = bbox
    if w < 16 or h < 16:
        return 0.0
    crop = gray[y:y + h, x:x + w].astype(np.float32)
    m = seg[y:y + h, x:x + w].astype(bool)
    if m.sum() < 100:
        return 0.0

    # 배경을 물체 평균으로 채워 윤곽 자체가 만드는 에지 성분을 죽인다.
    filled = np.where(m, crop, crop[m].mean())
    filled = filled - filled.mean()

    # 창함수 — 테두리 불연속이 스펙트럼에 십자무늬를 만드는 것을 막는다.
    spec = np.abs(np.fft.fftshift(
        np.fft.fft2(filled * np.hanning(h)[:, None] * np.hanning(w)[None, :]))) ** 2

    lo_um, hi_um = TEXTURE_PERIOD_UM
    min_px, max_px = lo_um / um_per_px, hi_um / um_per_px
    if max_px < 2.5:            # 리사이즈가 심해 주기가 Nyquist 아래로 내려간 경우
        return 0.0

    cy, cx = h / 2, w / 2
    yy, xx = np.mgrid[0:h, 0:w]
    # 주기 p 픽셀 <-> 반경 r = 1/p (정사각이 아니므로 축별로 정규화)
    r = np.sqrt(((yy - cy) / h) ** 2 + ((xx - cx) / w) ** 2)
    band = (r >= 1.0 / max_px) & (r <= 1.0 / min_px)
    if band.sum() < 20:
        return 0.0

    vals = spec[band]
    med = float(np.median(vals))
    if med <= 0:
        return 0.0
    return float(vals.max() / med)


def largest_body(seg):
    """마스크에서 **가장 큰 연결 성분 하나만** 남긴다.

    후처리를 껐으므로(`apply_postprocessing=False`, `min_mask_region_area=0`)
    SAM 마스크에는 떨어져 나온 작은 조각이 남는다. 005 §5 실측으로 한 사진에서
    **마스크의 21%(24/117)가 연결 성분 2개 이상**이었고, 떠돌이 픽셀 하나가
    bbox 를 24 px 넓힌 사례가 있었다.

    이것이 조용히 문제가 되는 이유는 **두 갈래가 다른 것을 보기 때문**이다 —
    bbox·area 는 SAM 이 준 마스크 전체에서 오고, 폴리곤과 형태 지표는
    `shape_metrics()` 가 가장 큰 윤곽 하나에서 낸다. 그래서 통과분의 27.5%
    (694/2,522)가 bbox 가 본체보다 10 px 이상 컸고, bbox 로 재는 중복 정리가
    무력화됐다(실측: cover 0.794 로 문턱을 아슬아슬하게 피해 둘 다 남았는데,
    본체 bbox 였다면 0.925 로 정리됐을 것이다).

    여기서 본체만 남기면 두 갈래가 같은 것을 보게 된다.

    돌려주는 값: (본체 마스크, (x,y,w,h), 면적, 성분 수). 빈 마스크면 None.
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        seg.astype(np.uint8), connectivity=8)
    if n <= 1:                      # 0 번은 배경이다
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    box = (int(stats[idx, cv2.CC_STAT_LEFT]), int(stats[idx, cv2.CC_STAT_TOP]),
           int(stats[idx, cv2.CC_STAT_WIDTH]), int(stats[idx, cv2.CC_STAT_HEIGHT]))
    return labels == idx, box, int(stats[idx, cv2.CC_STAT_AREA]), n - 1


def masks_to_records(masks, um_per_px=DEFAULT_UM_PER_PIXEL, gray=None,
                     keep_largest_body=True):
    """SAM 마스크 dict 리스트를 정리된 후보 레코드로.

    `keep_largest_body` 는 2026-07-31 부터 켜 두는 것이 기본이다. 그 전에 검출한
    것(260729)은 다시 돌리지 않는다 — `bbox_xywh` 가 교정 기록의 키라서, 전수
    검토를 마친 자료의 키를 흔들면 2,400여 건을 다시 맺어야 한다(005 §5 가
    `tighten_bbox.py` 를 만들어 놓고도 적용하지 않은 이유가 그것이다).
    """
    records = []
    n_split = 0
    for i, m in enumerate(masks):
        x, y, w, h = m["bbox"]
        area_px = int(m["area"])
        seg = m["segmentation"]

        if keep_largest_body:
            body = largest_body(seg)
            if body is None:
                continue                       # 빈 마스크
            seg, (x, y, w, h), area_px, n_bodies = body
            if n_bodies > 1:
                n_split += 1
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
        rec = records[-1]
        rec["_seg"] = seg

        # 형태·텍스처 지표를 여기서 전부 계산해 JSON 에 남긴다.
        # 그래야 문턱을 바꿀 때 SAM2 를 다시 돌리지 않고 refilter.py 로 끝난다.
        sm = shape_metrics(seg)
        if sm is None:
            rec["shape_ok"] = False
            continue
        rec["shape_ok"] = True
        rec["major_um"] = round(sm.pop("_major_px") * um_per_px, 2)
        rec["minor_um"] = round(sm.pop("_minor_px") * um_per_px, 2)
        rec.update(sm)
        rec["texture"] = round(
            texture_score(gray, seg, (int(x), int(y), int(w), int(h)), um_per_px), 1
        ) if gray is not None else None
    if n_split:
        print(f"  연결 성분이 여럿인 마스크 {n_split}/{len(masks)}개 — "
              f"본체만 남겼다", file=sys.stderr)
    return records


def filter_records(records, min_um, max_um, drop_background_frac=0.5, img_area=None):
    """너무 작은 debris와 배경 전체를 덮는 마스크를 제거.

    **크기는 타원 장축으로 잰다.** README 가 그렇게 정해 뒀고 `judge.classify()`
    도 `major_um` 을 본다. 여기만 bbox 긴 변으로 재고 있었는데, 지금까지는 bbox 가
    떠돌이 조각 때문에 부풀어 있어서 이 관문이 거의 안 걸렸다. 본체만 남기면서
    bbox 가 조여지자 **타원 장축은 범위 안인데 bbox 로는 밖인 개체**가 생긴다
    (005 §5 실측 33개, 장축 중앙값 11.2 µm — 관문 한가운데다).

    형태를 못 낸 마스크(`shape_ok=False`)만 bbox 긴 변으로 대신 잰다.
    """
    out = []
    for r in records:
        size_um = r.get("major_um") if r.get("shape_ok") else r["long_side_um"]
        if size_um is None:
            size_um = r["long_side_um"]
        if size_um < min_um or size_um > max_um:
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
    # 봉상=파랑, 원형=초록, 미분류=무작위색
    palette = {"rod": (60, 120, 255), "round": (60, 220, 120)}
    for r in records:
        seg = r["_seg"]
        color = np.array(palette.get(r.get("cls"), rng.integers(60, 255, size=3)))
        overlay[seg] = (0.55 * overlay[seg] + 0.45 * color).astype(np.uint8)
    vis = Image.fromarray(overlay)
    d = ImageDraw.Draw(vis)
    for r in records:
        x, y, w, h = r["bbox_xywh"]
        d.rectangle([x, y, x + w, y + h], outline=(255, 40, 40), width=3)
        d.text((x + 4, max(y - 16, 0)), f"{r['id']}:{r['long_side_um']:.0f}um",
               fill=(255, 40, 40))
    vis.save(out_path, quality=88)


# Candidate 에 그대로 들어가는 수치 칸들 (import_json.py 와 같아야 한다)
NUM = ("area_um2", "major_um", "minor_um", "long_side_um", "short_side_um",
       "aspect_ratio", "fill_ratio", "circularity", "convexity", "solidity",
       "elongation", "ellipse_iou", "texture", "predicted_iou",
       "stability_score")


def git_version():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=Path(__file__).resolve().parent)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def rel(p) -> str:
    """DATA_ROOT 기준 상대경로. DB 는 이 형태로만 경로를 담는다."""
    p = Path(p)
    if not p.is_absolute():
        return str(p)
    try:
        return str(p.relative_to(Path(settings.DATA_ROOT)))
    except ValueError:
        return str(p)


def find_viewpoint(stem: str):
    """파일 이름으로 시야를 찾는다.

    합성본은 `<tag>_focused`, 싱글턴은 프레임 이름(`Snap-21171`)이다.
    """
    if stem.endswith("_focused"):
        tag = stem[: -len("_focused")]
        return Viewpoint.objects.filter(tag=tag).first(), "stack", None
    fr = Frame.objects.filter(name=stem).select_related("viewpoint").first()
    if fr and fr.viewpoint:
        return fr.viewpoint, "frame", fr
    return None, None, None


def threshold_set_for(values: dict) -> ThresholdSet:
    """같은 문턱 조합이면 한 행을 공유한다. refilter.py 와 같은 규칙."""
    found = ThresholdSet.objects.filter(**values).first()
    if found:
        return found
    name = (f"texture {values['texture_min']:g} · "
            f"areolae {values['round_texture_min']:g}")
    return ThresholdSet.objects.create(name=name, note="segment 가 만들었다",
                                       **values)


@contextlib.contextmanager
def gpu_lock(timeout: float = 7200.0):
    """GPU 를 쓰는 작업이 한 번에 하나만 돌게 한다.

    **부르는 쪽이 기억해야 하는 일로 두지 않는다.** 폴러는 `flock` 으로 자기들끼리
    막지만, 사람이 손으로 돌릴 때 그것을 잊으면 겹친다. 이 장비는 8 GB 라 두
    작업이 겹치면 둘 다 느려지거나 하나가 죽는다.

    잠금 파일은 호스트와 컨테이너가 같은 경로로 보는 자리에 둔다. 컨테이너가
    죽어도 파일 잠금은 커널이 풀어 준다 — 남은 파일이 막지 않는다.
    """
    path = Path(os.environ.get("DIATOM_GPU_LOCK",
                               str(Path(settings.DATA_ROOT) / "locks" / "gpu.lock")))
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    waited = 0.0
    try:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if waited >= timeout:
                    raise SystemExit(
                        f"다른 GPU 작업이 {timeout / 60:.0f}분 넘게 돌고 있다: {path}")
                if waited == 0:
                    print("다른 GPU 작업이 끝나기를 기다린다…", file=sys.stderr)
                time.sleep(5.0)
                waited += 5.0
        if waited:
            print(f"  {waited:.0f}초 기다렸다", file=sys.stderr)
        yield
    finally:
        fh.close()          # 닫으면 잠금도 풀린다


def mark_done_if_complete(slide) -> bool:
    """자동 처리가 다 끝났으면 슬라이드를 `done` 으로 연다.

    **`done` 이 되기 전에는 뷰어가 검토를 막는다** (P01 §1). 반쯤 처리된 슬라이드를
    사람이 검토하면, 아직 안 돌아간 시야의 검출이 뒤늦게 들어오면서 이미 본 화면이
    바뀐다. 최상위 디렉토리 하나를 단위로 열고 닫는다.

    `failed`(그룹핑이 미심쩍다고 표시한 것)는 열지 않는다 — 사람이 봐야 한다.
    """
    if slide.state == "failed":
        return False
    vps = list(slide.viewpoints.all())
    if not vps:
        return False
    missing = [vp for vp in vps
               if not vp.detections.filter(is_current=True).exists()]
    if missing:
        slide.state = "processing"
        slide.state_note = f"검출 대기 시야 {len(missing)}개"
        slide.save(update_fields=["state", "state_note"])
        return False
    slide.state = "done"
    slide.state_note = ""
    slide.processed_at = timezone.now()
    slide.save(update_fields=["state", "state_note", "processed_at"])
    return True


def save_detection(payload: dict, img_path: Path, run: Run, iou_min: float,
                   keep_current: bool = False):
    """검출 결과를 새 Detection 으로 쌓고 교정을 다시 맺는다.

    **통째로 한 트랜잭션이다.** `is_current` 를 옮기는 것과 교정을 다시 맺는 것이
    갈라지면, 그 사이에 뷰어를 연 사람은 "교정이 하나도 안 붙은 새 검출"을 본다.

    `keep_current=True` 면 **`is_current` 를 옮기지 않고 재바인딩도 하지 않는다.**
    새 검출은 `is_current=False` 로 쌓이기만 한다. 뷰어(`data.py`)는 current 인
    것만 보므로 화면도 교정도 그대로다 — 다른 엔진을 같은 시야에서 나란히
    재 보려고 둔 길이다(P01 §3).

    **이것이 없으면 실험 한 번이 교정 2,400건을 흔든다.** 엔진이 다르면
    `mask_key`(bbox 문자열)가 거의 전부 어긋나 재바인딩이 orphan 을 쏟아내고,
    되돌리려면 또 한 번 뒤집어야 한다.

    돌려주는 값: (Detection, 개체 수, 재바인딩 방법별 개수)
    """
    stem = img_path.stem
    vp, target, frame = find_viewpoint(stem)
    if vp is None:
        return None, 0, None

    with transaction.atomic():
        ts = threshold_set_for(payload["thresholds"])
        det = Detection.objects.create(
            viewpoint=vp, target=target, frame=frame,
            image_path=rel(img_path),
            width=payload["size"][0], height=payload["size"][1],
            scale=payload["scale"],
            um_per_pixel=payload["um_per_pixel"],
            um_per_pixel_native=payload["um_per_pixel_native"],
            um_per_pixel_source=payload["um_per_pixel_source"] or "",
            n_raw_masks=payload["n_raw_masks"], n_sized=payload["n_sized"],
            thresholds=ts, run=run, is_current=False)   # 아직 아니다

        rows, seen = [], set()
        for passed, pool in ((True, payload["candidates"]),
                             (False, payload["rejected"])):
            for c in pool:
                b = c["bbox_xywh"]
                key = rebind.mask_key(b)
                # 같은 bbox 가 두 번 나오면 unique 에 걸린다 — 첫 것만 둔다
                if key in seen:
                    continue
                seen.add(key)
                ctr = c.get("center_xy") or [None, None]
                rows.append(Candidate(
                    detection=det, mask_key=key, raw_id=c.get("id"),
                    bbox_x=int(b[0]), bbox_y=int(b[1]),
                    bbox_w=int(b[2]), bbox_h=int(b[3]),
                    center_x=ctr[0], center_y=ctr[1],
                    area_px=c.get("area_px") or 0,
                    shape_ok=bool(c.get("shape_ok")),
                    polygon=c.get("polygon") or [],
                    passed=passed, cls=c.get("cls") or "",
                    reject=(c.get("reject") or "") if not passed else "",
                    **{f: c.get(f) for f in NUM}))
        Candidate.objects.bulk_create(rows, batch_size=2000)

        # 여기부터가 한 덩어리여야 하는 부분이다
        if keep_current:
            # 쌓아만 둔다. 지금 것을 건드리지 않으므로 재바인딩도 하지 않는다.
            return det, len(rows), None

        old = list(vp.detections.filter(is_current=True))
        Detection.objects.filter(pk__in=[d.pk for d in old]).update(
            is_current=False, superseded_by=det)
        det.is_current = True
        det.save(update_fields=["is_current"])

        det.refresh_from_db()
        stat = rebind.rebind_viewpoint(vp, det, iou_min=iou_min)

    return det, len(rows), stat


def process(img_path: Path, gen, args, out_dir: Path, scale_log=None):
    # 계측의 기준이 되는 픽셀 크기. 사진 옆의 XML 이 원칙이고, 합성본은
    # focus_stack.py 가 남긴 사이드카에서 온다. --um-per-pixel 이 있으면 그것이
    # 우선한다 (메타데이터가 틀렸다고 판단한 사람의 지시이므로).
    if args.um_per_pixel:
        scaling = {"um_per_pixel": args.um_per_pixel, "source": "cli", "path": None}
    else:
        scaling = scaling_for(img_path)
    if scale_log is not None:
        scale_log.add(img_path.name, scaling["um_per_pixel"])

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

    # --scale 로 리사이즈했으면 픽셀이 그만큼 커진 셈이다
    um_per_px = scaling["um_per_pixel"] / args.scale
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    recs = masks_to_records(masks, um_per_px, gray=gray,
                            keep_largest_body=not args.all_bodies)
    sized = filter_records(recs, args.min_um, args.max_um,
                           img_area=arr.shape[0] * arr.shape[1])

    if args.no_shape_filter:
        kept, rejected = sized, []
        for r in kept:
            r["cls"] = None
    else:
        passed, rejected = [], []
        for r in sized:
            cls, why = classify(r, args)
            if cls:
                r["cls"] = cls
                passed.append(r)
            else:
                r["reject"] = why
                rejected.append(r)
        kept = dedupe(passed)
        dropped = [r for r in passed if r not in kept]
        for r in dropped:
            r["reject"] = "중첩정리"
        rejected += dropped

    kept.sort(key=lambda r: -r["area_px"])
    for i, r in enumerate(kept):
        r["id"] = i

    def clean(rs):
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rs]

    stem = img_path.stem
    draw_overlay(img, kept, out_dir / f"{stem}_overlay.jpg")
    payload = {
        "image": str(img_path),
        "size": [img.width, img.height],
        "scale": args.scale,
        "um_per_pixel": um_per_px,
        # 계측값을 나중에 의심할 때 어디서 온 배율인지 알 수 있게 남긴다
        "um_per_pixel_native": scaling["um_per_pixel"],
        "um_per_pixel_source": scaling["source"],
        "n_raw_masks": len(recs),
        "n_sized": len(sized),
        "n_candidates": len(kept),
        # 문턱을 바꿔 다시 거를 때 필요한 값들. refilter.py 가 이걸 읽는다.
        "thresholds": {
            "min_um": args.min_um, "max_um": args.max_um,
            "texture_min": args.texture_min,
            "round_max_elong": args.round_max_elong,
            "round_min_iou": args.round_min_iou,
            "round_min_solidity": args.round_min_solidity,
            "round_texture_min": args.round_texture_min,
            "rod_min_elong": args.rod_min_elong, "rod_max_elong": args.rod_max_elong,
            "rod_min_iou": args.rod_min_iou, "rod_min_solidity": args.rod_min_solidity,
        },
        "counts": {
            "rod": sum(1 for r in kept if r.get("cls") == "rod"),
            "round": sum(1 for r in kept if r.get("cls") == "round"),
        },
        "candidates": clean(kept),
        # 탈락분도 지표째 남긴다 — 문턱 재조정이 SAM2 재실행 없이 끝난다.
        "rejected": clean(rejected),
    }
    (out_dir / f"{stem}_candidates.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    c = payload["counts"]
    print(f"{stem}: raw={len(recs)} 크기통과={len(sized)} "
          f"최종={len(kept)} (봉상 {c['rod']}, 원형 {c['round']})")
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="이미지 파일 또는 디렉토리")
    ap.add_argument("--slide",
                    help="슬라이드 slug. 검출 대상을 DB 에서 고른다 — 합성본이 "
                         "있으면 그것을, 싱글턴 시야는 그 한 장을 쓴다")
    ap.add_argument("-o", "--out", default=None, help="기본값은 DATA_ROOT/out")
    ap.add_argument("--no-db", action="store_true",
                    help="JSON 만 쓰고 DB 는 건드리지 않는다 (시험용)")
    ap.add_argument("--rebind-iou", type=float, default=0.5,
                    help="mask_key 가 안 맞을 때 교정을 다시 맺는 IoU 하한")
    ap.add_argument("--force", action="store_true",
                    help="사람이 교정한 시야도 다시 검출한다 (아래 설명을 읽을 것)")
    ap.add_argument("--all-bodies", action="store_true",
                    help="떨어진 조각까지 마스크로 인정한다 (2026-07-31 이전 방식)")
    ap.add_argument("--backend", default="sam2",
                    choices=["sam2", "sam3", "yolo"])
    ap.add_argument("--weights",
                    default="runs/segment/11m-v1seg-1280/weights/best.pt",
                    help="--backend yolo 일 때 쓸 가중치. 옆의 PROVENANCE.md 에 "
                         "무엇으로 학습했고 문턱을 얼마로 써야 하는지가 있다")
    # 낮게 뽑아 DB 에 넣고, 고르는 것은 나중에 한다. 운영점이 슬라이드마다
    # 다르다는 것을 devlog 025 §8 이 실측했다.
    ap.add_argument("--yolo-conf", type=float, default=0.01,
                    help="YOLO 신뢰도 하한 (기본 0.01 — 낮게 뽑아 둔다)")
    ap.add_argument("--yolo-imgsz", type=int, default=1280,
                    help="학습과 같아야 한다 (기본 1280)")
    ap.add_argument("--yolo-nms-iou", type=float, default=0.7)
    ap.add_argument("--batch", default="",
                    help="여러 슬라이드에 걸친 한 번의 작업을 묶는 이름표. "
                         "슬라이드마다 명령을 나눠 불러도 같은 이름이면 "
                         "한 덩어리로 남는다 (예: yolo-v1seg-frames)")
    ap.add_argument("--batch-note", default="",
                    help="묶음을 만들 때 함께 남길 메모 (왜 돌렸는가)")
    ap.add_argument("--keep-current", action="store_true",
                    help="새 검출을 is_current 로 올리지 않는다. 뷰어와 교정을 "
                         "건드리지 않고 다른 엔진을 나란히 재 볼 때 쓴다")
    ap.add_argument("--scale", type=float, default=0.5,
                    help="처리 전 리사이즈 배율 (VRAM 절약)")
    ap.add_argument("--um-per-pixel", type=float, default=None,
                    help="픽셀 크기를 직접 지정 (기본: 사진 옆 XML 에서 읽는다)")
    # 도판(Plate 1~9) 스케일바 10 µm 기준 실측이 대략 13~95 µm 였다.
    ap.add_argument("--min-um", type=float, default=10.0)
    ap.add_argument("--max-um", type=float, default=150.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--points-per-side", type=int, default=32)
    ap.add_argument("--points-per-batch", type=int, default=32)
    ap.add_argument("--crop-layers", type=int, default=0,
                    help="1이면 2x2 타일 추가 스캔 (작은 객체 recall 향상, 느려짐)")
    ap.add_argument("--iou-thresh", type=float, default=0.5)
    ap.add_argument("--stability-thresh", type=float, default=0.75)

    # --- 규조각 판정 문턱 ---------------------------------------------------
    # 도판(Plate 1~9) 실측에 맞춰 잡았다. 값을 바꿔 다시 거를 때는 SAM2 를
    # 다시 돌릴 필요 없이 refilter.py 를 쓴다.
    g = ap.add_argument_group("규조각 판정")
    g.add_argument("--no-shape-filter", action="store_true",
                   help="형태·텍스처 판정 없이 크기 필터만 (지표는 그대로 기록)")
    g.add_argument("--texture-min", type=float, default=JUDGE_DEFAULTS["texture_min"],
                   help="주기 구조 세기 하한. 규조각 1500~19000, 티끌 12~240")
    g.add_argument("--round-max-elong", type=float, default=JUDGE_DEFAULTS["round_max_elong"])
    g.add_argument("--round-min-iou", type=float, default=JUDGE_DEFAULTS["round_min_iou"])
    g.add_argument("--round-min-solidity", type=float, default=JUDGE_DEFAULTS["round_min_solidity"])
    # 원형은 areolae 를 더 무겁게 본다 — 형태 지표가 텍스처 세기와 무관하게
    # 평평해서(§판정 기준), 밋밋한 원반을 형태로는 가려낼 수 없다.
    g.add_argument("--round-texture-min", type=float, default=JUDGE_DEFAULTS["round_texture_min"],
                   help="원형(중심목)에만 적용하는 areolae 세기 하한. "
                        "--texture-min 보다 높게 잡아 밋밋한 원반을 떨어뜨린다")
    # Plate 9 는 2:1 수준, Plate 1 의 #16/#17/#24 는 20:1 에 가깝다.
    g.add_argument("--rod-min-elong", type=float, default=JUDGE_DEFAULTS["rod_min_elong"])
    g.add_argument("--rod-max-elong", type=float, default=JUDGE_DEFAULTS["rod_max_elong"])
    g.add_argument("--rod-min-iou", type=float, default=JUDGE_DEFAULTS["rod_min_iou"])
    g.add_argument("--rod-min-solidity", type=float, default=JUDGE_DEFAULTS["rod_min_solidity"])
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    # **YOLO 는 학습과 같은 해상도로 봐야 한다.** --scale 기본값이 0.5 라
    # 그대로 두면 이미지가 절반이 되고, imgsz=1280 이 거의 축소를 안 해
    # 개체가 학습 때보다 2배 크게 보인다. 조용히 성적만 떨어진다 —
    # 배율을 잘못 믿어 통과율이 1.6% 로 주저앉았던 일이 있다(devlog 015).
    if args.backend == "yolo" and args.scale != 1.0:
        raise SystemExit(
            f"--backend yolo 는 --scale 1.0 이어야 한다 (지금 {args.scale}). "
            f"가중치는 원본 해상도에 imgsz={args.yolo_imgsz} 로 학습했다")
    print(f"device={device} backend={args.backend}", file=sys.stderr)

    if args.slide:
        # 검출 대상을 DB 에서 고른다. 합성본이 원칙이다 — 초점 흐림 잔해가 줄어
        # 20 µm 이상 구간에서 더 잘 잡힌다. 싱글턴 시야는 합성본이 없으므로
        # 그 한 장을 그대로 쓴다. 예전에는 run_batch.sh 가 JSON 을 읽어 골랐다.
        from viewer.models import Slide                             # noqa: PLC0415
        try:
            slide = Slide.objects.get(slug=args.slide)
        except Slide.DoesNotExist:
            raise SystemExit(f"그런 슬라이드가 없다: {args.slide}")
        # 슬라이드에 배율이 못 박혀 있으면 그것을 쓴다. CLI 로 준 값이 우선한다 —
        # 사람이 그 자리에서 내린 지시가 더 최근이다.
        if slide.um_per_pixel_override and not args.um_per_pixel:
            args.um_per_pixel = slide.um_per_pixel_override
            print(f"{slide.slug}: 슬라이드에 지정된 배율 "
                  f"{args.um_per_pixel:.9f} µm/px 를 쓴다", file=sys.stderr)
        data_root = Path(settings.DATA_ROOT)
        files = []
        for vp in slide.viewpoints.order_by("idx"):
            st = getattr(vp, "stack", None)
            if st and st.focused_path:
                files.append(data_root / st.focused_path)
            else:
                fr = vp.sharpest_frame or vp.frames.order_by("seq").first()
                if fr:
                    files.append(data_root / fr.path)
        files = [f for f in files if f.exists()]
        print(f"{slide.slug}: 검출 대상 {len(files)}개", file=sys.stderr)
    elif args.input:
        inp = Path(args.input)
        files = sorted(inp.glob("*.jpg")) if inp.is_dir() else [inp]
    else:
        raise SystemExit("--slide <slug> 또는 이미지 경로 중 하나가 필요하다")
    if args.limit:
        files = files[: args.limit]

    out_dir = Path(args.out) if args.out else (Path(settings.DATA_ROOT) / "out")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.um_per_pixel:
        print(f"픽셀 크기를 {args.um_per_pixel} µm/px 로 지정 — XML 을 읽지 않는다",
              file=sys.stderr)

    run = None
    if not args.no_db:
        run = runlog.start(
            "detect",
            batch_label=args.batch, batch_note=args.batch_note,
            params={"backend": args.backend, "scale": args.scale,
                    "points_per_side": args.points_per_side,
                    "min_um": args.min_um, "max_um": args.max_um,
                    "rebind_iou": args.rebind_iou, "n_files": len(files)},
            host=socket.gethostname(), gpu=device, code_version=git_version())

    # 사람이 교정한 시야는 GPU 를 돌리기 **전에** 걸러 낸다.
    #
    # 재검출 자체는 안전하다 — 교정은 (viewpoint, mask_key) 에 붙고 rebind.py 가
    # 다시 맺어 준다. 다만 SAM2 가 미세하게 다른 마스크를 내므로 결과가 달라진다
    # (실측: 67건 중 exact 26 · iou 40 · 고아 1). 전수 검토를 마친 시야에서 그것이
    # 실수로 일어나면 안 된다. 특히 2026-07-31 부터 연결 성분 처리가 바뀌어
    # bbox 가 조여지므로, 옛 자료를 다시 돌리면 키가 대량으로 흔들린다.
    # **--keep-current 면 이 관문이 필요 없다.** 관문이 있는 이유는 재검출이
    # is_current 를 옮기고 교정을 다시 맺기 때문인데, keep-current 는 둘 다 안
    # 한다 — 쌓아만 둔다. 여기서 걸러 버리면 검토를 마친 264 시야가 전부
    # 빠져 나가 정작 견주고 싶은 자리가 하나도 안 남는다.
    if args.keep_current:
        print("--keep-current: 새 검출을 is_current 로 올리지 않는다. "
              "뷰어와 교정은 그대로다", file=sys.stderr)
    elif not args.no_db and not args.force:
        keep, n_rev_skip, n_done_skip = [], 0, 0
        for f in files:
            vp, _, _ = find_viewpoint(f.stem)
            if vp is None:
                keep.append(f)
                continue
            if vp.object_reviews.exists():
                n_rev_skip += 1
                continue
            # 이미 검출한 시야도 건너뛴다. 주기 실행이 중간에 끊겼을 때 다음
            # 주기가 처음부터 다시 돌리면 한 슬라이드에 몇 시간이 또 든다.
            if vp.detections.filter(is_current=True).exists():
                n_done_skip += 1
                continue
            keep.append(f)
        if n_rev_skip:
            print(f"사람의 교정이 있는 시야 {n_rev_skip}개를 건너뛴다 "
                  f"(다시 검출하려면 --force)", file=sys.stderr)
        if n_done_skip:
            print(f"이미 검출한 시야 {n_done_skip}개를 건너뛴다", file=sys.stderr)
        files = keep
        if not files:
            print("검출할 것이 없다.", file=sys.stderr)
            # 다 끝나 있으면 상태를 열어 준다 — 앞 실행이 여기서 끊겼을 수 있다
            if args.slide:
                from viewer.models import Slide                     # noqa: PLC0415
                sl = Slide.objects.filter(slug=args.slide).first()
                if sl and mark_done_if_complete(sl):
                    print(f"  {sl.slug}: 자동 처리 완료 — 검토를 연다",
                          file=sys.stderr)
            return

    # GPU 를 잡는 것은 여기서부터다. 모델 적재도 VRAM 을 쓴다.
    gpu = gpu_lock() if device == "cuda" else contextlib.nullcontext()
    stack_ctx = contextlib.ExitStack()
    stack_ctx.enter_context(gpu)
    gen = load_generator(args.backend, device, args)
    scale_log = ScaleLog()
    n_det = n_cand = n_oom = 0
    bind = Counter()
    missing = []
    touched = set()
    try:
        for f in files:
            try:
                payload = process(f, gen, args, out_dir, scale_log)
            except torch.cuda.OutOfMemoryError:
                # 조용히 넘기면 "검출 0개 · done" 으로 끝나 성공처럼 보인다
                print(f"OOM on {f.name} — --points-per-batch 를 낮추세요 "
                      f"(지금 {args.points_per_batch})", file=sys.stderr)
                torch.cuda.empty_cache()
                n_oom += 1
                continue
            if args.no_db:
                continue
            det, nc, stat = save_detection(payload, f, run, args.rebind_iou,
                                           keep_current=args.keep_current)
            if det is None:
                # 조용히 넘기지 않는다 — 그룹핑과 DB 가 어긋났다는 뜻이다
                missing.append(f.stem)
                print(f"  {f.stem}: 시야를 DB 에서 못 찾았다 — DB 에 남기지 않았다",
                      file=sys.stderr)
                continue
            n_det += 1
            n_cand += nc
            # --keep-current 면 재바인딩을 안 하므로 stat 이 None 이다
            if stat:
                bind += stat
            touched.add(det.viewpoint.slide_id)
            if stat and (stat["iou"] or stat["orphan"]):
                # 고아는 손실이 아니지만(geom 이 남는다) 뷰어가 못 그린다.
                # 반드시 보이게 한다 — 조용하면 한참 뒤에나 알게 된다.
                print(f"  {f.stem}: 교정 재바인딩 exact {stat['exact']} · "
                      f"iou {stat['iou']} · 고아 {stat['orphan']}")
    except Exception as e:
        if run:
            run.status = "failed"
            run.error = f"{type(e).__name__}: {e}"
            run.finished_at = timezone.now()
            run.counts = {"detections": n_det, "candidates": n_cand}
            run.save()
        raise

    stack_ctx.close()          # GPU 를 놓는다. 뒷정리는 DB 작업뿐이다

    if run:
        run.status = "done"
        run.finished_at = timezone.now()
        run.counts = {"detections": n_det, "candidates": n_cand,
                      "missing_viewpoint": len(missing), "oom": n_oom,
                      **dict(bind)}
        # 전부 OOM 으로 죽었는데 done 으로 남으면 성공한 줄 안다
        if n_oom and not n_det:
            run.status = "failed"
            run.error = f"OOM {n_oom}건 — 검출된 것이 없다"
        run.save()
        # 슬라이드 하나가 다 끝났으면 검토를 연다.
        #
        # **--keep-current 면 손대지 않는다.** 나란히 재 보는 실험은 "자동 처리"
        # 가 아니다. 여기서 상태를 옮기면 `failed`(그룹핑이 미심쩍은 것)나
        # `processing` 인 슬라이드가 실험 한 번에 `done` 이 되어 검토가 열린다 —
        # 반쯤 처리된 것을 사람이 보게 되는 바로 그 사고다(P01 §1).
        from viewer.models import Slide                             # noqa: PLC0415
        if args.keep_current:
            print("  --keep-current: 슬라이드 상태를 건드리지 않는다")
        else:
            for sl in Slide.objects.filter(pk__in=touched):
                if mark_done_if_complete(sl):
                    print(f"  {sl.slug}: 자동 처리 완료 — 검토를 연다")
                else:
                    print(f"  {sl.slug}: {sl.state} — {sl.state_note}")

        print(f"\n검출 {n_det}개 · 개체 {n_cand}개 · Run #{run.pk}")
        if bind:
            print(f"  교정 재바인딩: exact {bind['exact']} · iou {bind['iou']} · "
                  f"고아 {bind['orphan']}")
        if bind["orphan"]:
            print(f"  ** 고아 {bind['orphan']}개 — 뷰어에서 안 보인다. "
                  f"geom 은 남아 있다 (P02 8단계의 고아 화면이 필요하다)",
                  file=sys.stderr)
        if missing:
            print(f"  [확인필요] 시야를 못 찾은 이미지 {len(missing)}개: "
                  f"{missing[:5]}", file=sys.stderr)


if __name__ == "__main__":
    main()
