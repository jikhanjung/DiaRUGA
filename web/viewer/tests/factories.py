"""시험 자료를 세우는 자리. **모든 시험이 여기를 지난다.**

모델이 16개고 그래프가 깊다.

    Site → Locality → Sample → Slide → Viewpoint → Frame → Image → Detection
                                            ↓                 ↓        ↓
                                    ViewpointReview     ObjectReview  Candidate

매 시험이 자기 자료를 손으로 세우면 **픽스처가 시험보다 길어지고**, 스키마가
바뀔 때 고칠 자리가 시험 수만큼 는다. 여기 하나만 고치면 되게 한다.

## 무엇을 그대로 따르는가

- **`Image` 는 `images.ensure_image` 로만 만든다.** 그것이 "문 하나" 다(P06 4).
  시험이 옆문으로 만들면 시험만 통과하는 규칙이 생긴다
- **`mask_key` 는 `data.cand_key` 로 만든다.** 손으로 `"10_20_30_40"` 이라
  적으면 키 규칙이 바뀌었을 때 시험이 옛 규칙을 증언한다
- **파일도 실제로 심는다.** 뷰가 디스크에서 읽으므로(`/img`·`/crop`) 행만 있고
  파일이 없으면 화면 시험이 진짜 화면을 안 본 것이 된다

## 쓰는 법

    world = make_world()                      # 한 벌 전부
    world = make_world(slug="rs23", n_viewpoints=2, n_candidates=3)

    a = make_world(slug="a", frame_name="Snap-1")   # 053 재현 —
    b = make_world(slug="b", frame_name="Snap-1")   # 프레임 이름이 겹친다
"""
from dataclasses import dataclass, field

from .base import write_image
from .. import data
from ..images import ensure_frame_image, ensure_stack_images
from ..models import (Candidate, ClassDef, Detection, Frame, Image, Locality,
                      ObjectReview, Sample, Site, Slide, Stack, ThresholdSet,
                      Viewpoint, ViewpointReview)


# 픽스처 이미지의 크기. **실물(2752x2208)보다 작게 잡되, 기록한 값과 실제 파일이
# 반드시 같아야 한다.** 처음에 64x48 파일을 만들어 놓고 `Frame.width` 에는
# 2752 를 적었더니 개체 bbox 가 이미지 밖에 앉아 `/crop` 이 잘라 낼 것을 못
# 찾았다 — **현실에서 생길 수 없는 상태를 시험한 것**이다. 크기는 여기 하나로
# 정하고 행·파일·bbox 가 전부 이 값을 따른다.
IMG_W, IMG_H = 640, 480


@dataclass
class World:
    """`make_world` 가 세운 것들. 시험이 짚어 쓸 수 있게 전부 들고 있다."""

    site: Site
    locality: Locality
    sample: Sample
    slide: Slide
    viewpoints: list = field(default_factory=list)

    @property
    def vp(self) -> Viewpoint:
        return self.viewpoints[0]

    @property
    def slug(self) -> str:
        return self.slide.slug

    def detection(self, vp=None) -> Detection:
        """그 시야의 현재 검출."""
        vp = vp or self.vp
        return vp.detections.get(is_current=True)

    def keys(self, vp=None) -> list[str]:
        """그 시야 개체들의 `mask_key`. 화면이 보내는 것과 같은 것들이다."""
        return [c.mask_key for c in self.detection(vp).candidates.all()]

    def stem(self, vp=None) -> str:
        """화면이 `/review` 에 보내는 `stem`."""
        from pathlib import Path
        return Path(self.detection(vp).image_path).stem


# --- 분류표 ----------------------------------------------------------------

# `ClassDef` 는 여덟 칸을 전부 채워야 한다 — 하나라도 비면 **예외는 안 나고 그
# 분류만 조용히 다르게 구른다**(038~040). 시험 자료도 예외가 아니다. 실제 표의
# 뼈대를 따라 최소 넷만 둔다.
CLASSES = [
    # key,          label,    short, badge, color,           hotkey, counted, taxon
    ("round",       "원형",    "원",  "R",   "80,200,255",    "1",    True,    False),
    ("round_frag",  "원형조각", "원조", "r",  "80,140,180",    "2",    False,   False),
    ("rod",         "봉상",    "봉",  "B",   "255,180,80",    "3",    True,    False),
    ("rod_frag",    "봉상조각", "봉조", "b",  "180,130,60",    "4",    False,   False),
]


def make_classes():
    """분류표. **시험마다 새로 만들지 말고 이것을 부른다.**

    `data.py` 가 분류표를 캐시하므로(`_class_rows`) 만든 뒤 반드시 무효화한다 —
    안 하면 앞 시험의 표가 다음 시험에 남는다.
    """
    for i, (key, label, short, badge, color, hot, counted, taxon) in enumerate(CLASSES):
        ClassDef.objects.update_or_create(
            key=key,
            defaults={"label": label, "short": short, "badge": badge,
                      "color": color, "hotkey": hot, "counted": counted,
                      "is_taxon": taxon, "sort_order": i, "active": True})
    data.invalidate_classes()


# --- 한 벌 -----------------------------------------------------------------

def make_world(slug="rs23", *, name=None, area="ant", kind="core",
               site_code="RS23", loc_code="GC03", sample_code="71cm",
               depth_cm=71.0, n_viewpoints=1, n_frames=3, n_candidates=2,
               frame_name=None, state="done", with_stack=True,
               with_files=True) -> World:
    """지점 하나 · 시료 하나 · 관찰 하나와 그 아래 전부.

    `frame_name` 을 주면 프레임 이름을 그것으로 못 박는다 — **슬라이드끼리
    프레임 이름이 겹치는 상황**(053)을 만들 때 쓴다.

    `with_stack=False` 면 합성본을 안 만들고 **싱글턴 시야**가 된다(프레임 한
    장이 곧 검출 대상). 053 이 난 자리가 거기다.
    """
    site, _ = Site.objects.get_or_create(
        code=site_code, defaults={"name": f"{site_code} 지역", "area": area})
    loc, _ = Locality.objects.get_or_create(
        site=site, code=loc_code, defaults={"kind": kind})
    smp, _ = Sample.objects.get_or_create(
        locality=loc, code=sample_code,
        defaults={"depth_cm": depth_cm if kind == "core" else None,
                  "sample_no": None if kind == "core" else 1})

    slide = Slide.objects.create(
        name=name or f"{site_code}-{loc_code} {sample_code}",
        slug=slug, image_dir=f"photos/260801/{slug}", sample=smp, state=state)

    w = World(site=site, locality=loc, sample=smp, slide=slide)
    for idx in range(n_viewpoints):
        w.viewpoints.append(
            _make_viewpoint(slide, idx, n_frames=n_frames,
                            n_candidates=n_candidates, frame_name=frame_name,
                            with_stack=with_stack, with_files=with_files))
    return w


def _make_viewpoint(slide, idx, *, n_frames, n_candidates, frame_name,
                    with_stack, with_files):
    tag = f"g{idx:03d}_Snap-{21000 + idx * 10}"
    vp = Viewpoint.objects.create(slide=slide, idx=idx, tag=tag,
                                  n_frames=n_frames)

    frames = []
    for s in range(n_frames):
        # 이름을 못 박으면 첫 장만 그 이름을 쓴다 — 겹치게 만들려는 것이 그
        # 한 장이고, 나머지까지 같으면 `(slide, name)` 유일 제약에 걸린다.
        fname = (frame_name if (frame_name and s == 0)
                 else f"Snap-{21000 + idx * 10 + s}")
        rel = f"{slide.image_dir}/{fname}.jpg"
        f = Frame.objects.create(slide=slide, viewpoint=vp, name=fname,
                                 path=rel, width=IMG_W, height=IMG_H, seq=s,
                                 um_per_pixel=0.1, um_per_pixel_source="xml",
                                 is_sharpest=(s == 0))
        if with_files:
            _write(rel)
        ensure_frame_image(f)
        frames.append(f)
    vp.sharpest_frame = frames[0]
    vp.save(update_fields=["sharpest_frame"])

    if with_stack:
        rel = f"stacked/{slide.slug}/{tag}_focused.jpg"
        st = Stack.objects.create(viewpoint=vp, focused_path=rel,
                                  um_per_pixel=0.1, native_um_per_pixel=0.1,
                                  resize_scale=1.0, um_per_pixel_source="xml",
                                  ref_frame=frames[0])
        if with_files:
            _write(rel)
        img = ensure_stack_images(st)
    else:
        # 싱글턴 시야 — 프레임 한 장이 곧 검출 대상이다.
        img = Image.objects.get(path=frames[0].path)

    _make_detection(vp, img, n_candidates=n_candidates)
    ViewpointReview.objects.create(viewpoint=vp, done=False)
    return vp


def _make_detection(vp, img, *, n_candidates):
    # 문턱 11개는 전부 모델 기본값이 있다 — **여기서 베끼지 않는다.** 베껴 두면
    # 기본값이 바뀔 때 시험만 옛 값을 증언한다.
    ts, _ = ThresholdSet.objects.get_or_create(name="시험 기본",
                                               defaults={"is_default": True})
    det = Detection.objects.create(
        viewpoint=vp, image=img, image_path=img.path,
        width=img.width or IMG_W, height=img.height or IMG_H,
        scale=1.0, um_per_pixel=0.1, um_per_pixel_source="xml",
        n_raw_masks=n_candidates + 1, n_sized=n_candidates,
        thresholds=ts, is_current=True)

    for i in range(n_candidates):
        # bbox 는 전부 이미지 안이어야 한다 (IMG_W x IMG_H).
        x, y = 40 + i * 120, 50 + i * 80
        w, h = 60 + i * 10, 40 + i * 10
        cls = CLASSES[i % len(CLASSES)][0]
        Candidate.objects.create(
            detection=det, raw_id=i,
            mask_key=data.cand_key({"bbox_xywh": [x, y, w, h]}),
            bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h,
            center_x=x + w // 2, center_y=y + h // 2,
            area_px=w * h // 2, area_um2=float(w * h) / 200,
            major_um=float(w) / 10, minor_um=float(h) / 10,
            long_side_um=float(w) / 10, short_side_um=float(h) / 10,
            aspect_ratio=w / h, fill_ratio=0.62,
            shape_ok=True, circularity=0.85, convexity=0.95, solidity=0.93,
            elongation=1.2, ellipse_iou=0.88, texture=3000.0,
            predicted_iou=0.95, stability_score=0.97,
            polygon=[x, y, x + w, y, x + w, y + h, x, y + h],
            passed=True, cls=cls)

    # 탈락분 하나. 통과분만 있으면 "탈락 펼침판" 이 도는지 알 수 없다.
    x, y, w, h = 500, 400, 20, 18
    Candidate.objects.create(
        detection=det, raw_id=n_candidates,
        mask_key=data.cand_key({"bbox_xywh": [x, y, w, h]}),
        bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h,
        center_x=x + w // 2, center_y=y + h // 2,
        area_px=w * h // 2, area_um2=1.8, major_um=2.0, minor_um=1.8,
        long_side_um=2.0, short_side_um=1.8, aspect_ratio=1.1,
        fill_ratio=0.5, shape_ok=False, texture=200.0,
        polygon=[x, y, x + w, y, x + w, y + h, x, y + h],
        passed=False, reject="too_small")
    return det


def add_review(vp, mask_key, *, removed=False, accepted=False, label="",
               note="") -> ObjectReview:
    """교정 한 줄. **`(image, mask_key)` 가 열쇠다.**

    `geom` 을 반드시 채운다 — 교정은 기하를 스스로 들고 있어야 검출기가 바뀌어도
    읽힌다(CLAUDE.md). 빈 `geom` 으로 만들면 시험이 그 규칙을 안 지키는 자료를
    만들어 놓고 통과한다.
    """
    det = vp.detections.get(is_current=True)
    cand = det.candidates.filter(mask_key=mask_key).first()
    geom = {}
    if cand is not None:
        geom = {"bbox": cand.bbox_xywh, "polygon": list(cand.polygon)}
    return ObjectReview.objects.create(
        viewpoint=vp, image=det.image, mask_key=mask_key, candidate=cand,
        bind_method="exact" if cand else "orphan", geom=geom,
        removed=removed, accepted=accepted, label=label, note=note)


def _write(rel):
    """픽스처가 파일을 쓰는 유일한 자리.

    **`base.write_image` 를 지난다** — 거기서 뿌리가 임시 디렉토리인지 확인한다.
    픽스처가 자기 손으로 쓰면 그 확인을 건너뛴다: 실제로 그렇게 짰다가 시험이
    `/data3/DiaRUGA` 에 사진을 썼다 (base.py 머리말).

    크기는 `IMG_W x IMG_H` 하나뿐이다 — 행에 적은 값과 파일이 어긋나면 안 된다.
    """
    return write_image(rel, size=(IMG_W, IMG_H))
