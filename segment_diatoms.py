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

import cv2
import numpy as np
import torch
from PIL import Image

from zen_meta import DEFAULT_UM_PER_PIXEL, ScaleLog, scaling_for

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
    if backend == "sam3":
        raise SystemExit(
            "sam3 백엔드는 HF gated 접근 권한(HF_TOKEN)이 필요합니다. "
            "huggingface.co/facebook/sam3 에서 승인 후 재시도하세요."
        )
    raise SystemExit(f"unknown backend: {backend}")


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


def masks_to_records(masks, um_per_px=DEFAULT_UM_PER_PIXEL, gray=None):
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


def classify(r, args):
    """
    (분류, 탈락사유). 분류가 None 이면 규조각 후보가 아니다.

    텍스처가 1차 관문("규조각인가"), 형태가 2차("어떤 형태인가").
    둘 다 필요하다 — 텍스처만 쓰면 쇄설물 조각이, 형태만 쓰면 구조 없는
    티끌이 들어온다. 실측으로 확인했다.
    """
    if not r.get("shape_ok"):
        return None, "형태측정불가"
    # 크기는 적합 타원의 장축으로 다시 본다. bbox 긴 변은 비스듬히 누운 물체에서
    # 실제보다 커지므로, 그것만 보면 4 µm 짜리가 10 µm 관문을 통과한다.
    major = r.get("major_um")
    if major is not None and not (args.min_um <= major <= args.max_um):
        return None, "장축범위밖"
    if r.get("texture") is not None and r["texture"] < args.texture_min:
        return None, "텍스처부족"

    e, iou, sol = r["elongation"], r["ellipse_iou"], r["solidity"]
    if e < args.round_max_elong:
        # 원형은 areolae 를 봉상보다 무겁게 본다. 밋밋한 원반·기포·쇄설물 조각은
        # 형태만으로 걸러지지 않는다 — 실측에서 원형 통과분의 형태 지표는 텍스처
        # 세기와 무관하게 평평했다(IoU 중앙 0.886~0.898, 볼록성 0.957~0.966).
        # 형태로 가려낼 수 없으므로 areolae 세기 자체를 관문으로 둔다.
        round_tex = getattr(args, "round_texture_min", None)
        if round_tex and r.get("texture") is not None and r["texture"] < round_tex:
            return None, "원형areolae부족"
        if iou >= args.round_min_iou and sol >= args.round_min_solidity:
            return "round", None
        return None, "원형기준미달"
    if args.rod_min_elong <= e <= args.rod_max_elong:
        if iou >= args.rod_min_iou and sol >= args.rod_min_solidity:
            return "rod", None
        return None, "봉상기준미달"
    return None, "신장비범위밖"


def _cover(a, b):
    """a 의 bbox 가 b 안에 들어간 비율 (a 면적 기준)."""
    ax, ay, aw, ah = a["bbox_xywh"]
    bx, by, bw, bh = b["bbox_xywh"]
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy / max(aw * ah, 1)


def dedupe(selected):
    """
    중첩 마스크 정리.

    SAM2 AMG 는 격자 포인트마다 다중 스케일 마스크를 내므로 최대 6단계까지
    중첩된다. NMS 는 IoU 기반이라 이걸 못 잡는다 — 작은 것이 큰 것 안에 들면
    IoU 는 오히려 작아진다 (실측 중앙값 0.07).

    큰 쪽을 남기면 덩어리가 내부 규조각을 전부 삼키므로, 집합체를 골라 버리고
    개별 물체를 남긴다.
    """
    keep = []
    for a in selected:
        kids = [b for b in selected
                if b is not a and b["area_px"] < a["area_px"] and _cover(b, a) > 0.85]
        # 자식 2개 이상이 자기 면적의 절반 이상을 설명하면 개별 물체가 아니다.
        if len(kids) >= 2 and sum(b["area_px"] for b in kids) > 0.5 * a["area_px"]:
            continue
        keep.append(a)

    # 거의 같은 마스크는 하나로 — 텍스처가 높은 쪽을 남긴다.
    keep.sort(key=lambda r: -(r.get("texture") or 0))
    out = []
    for r in keep:
        if not any(_cover(r, k) > 0.8 and _cover(k, r) > 0.8 for k in out):
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
    recs = masks_to_records(masks, um_per_px, gray=gray)
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
    ap.add_argument("input", help="이미지 파일 또는 디렉토리")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--backend", default="sam2", choices=["sam2", "sam3"])
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
    g.add_argument("--texture-min", type=float, default=1000.0,
                   help="주기 구조 세기 하한. 규조각 1500~19000, 티끌 12~240")
    g.add_argument("--round-max-elong", type=float, default=1.4)
    g.add_argument("--round-min-iou", type=float, default=0.85)
    g.add_argument("--round-min-solidity", type=float, default=0.92)
    # 원형은 areolae 를 더 무겁게 본다 — 형태 지표가 텍스처 세기와 무관하게
    # 평평해서(§판정 기준), 밋밋한 원반을 형태로는 가려낼 수 없다.
    g.add_argument("--round-texture-min", type=float, default=1500.0,
                   help="원형(중심목)에만 적용하는 areolae 세기 하한. "
                        "--texture-min 보다 높게 잡아 밋밋한 원반을 떨어뜨린다")
    # Plate 9 는 2:1 수준, Plate 1 의 #16/#17/#24 는 20:1 에 가깝다.
    g.add_argument("--rod-min-elong", type=float, default=2.0)
    g.add_argument("--rod-max-elong", type=float, default=20.0)
    g.add_argument("--rod-min-iou", type=float, default=0.72)
    g.add_argument("--rod-min-solidity", type=float, default=0.85)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} backend={args.backend}", file=sys.stderr)

    inp = Path(args.input)
    files = sorted(inp.glob("*.jpg")) if inp.is_dir() else [inp]
    if args.limit:
        files = files[: args.limit]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.um_per_pixel:
        print(f"픽셀 크기를 {args.um_per_pixel} µm/px 로 지정 — XML 을 읽지 않는다",
              file=sys.stderr)

    gen = load_generator(args.backend, device, args)
    scale_log = ScaleLog()
    for f in files:
        try:
            process(f, gen, args, out_dir, scale_log)
        except torch.cuda.OutOfMemoryError:
            print(f"OOM on {f.name} — --scale 을 낮추세요", file=sys.stderr)
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
