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

from django.db.models import Count

from .base import write_image
from .. import data
from ..images import ensure_frame_image, ensure_stack_images
from ..models import (Candidate, ClassDef, Detection, Frame, Image, Locality,
                      DiatomObject, ObjectReview, Run, RunBatch, Sample, Site,
                      Slide, Stack,
                      ThresholdSet, Viewpoint, ViewpointReview)


# 픽스처 이미지의 크기. **실물(2752x2208)보다 작게 잡되, 기록한 값과 실제 파일이
# 반드시 같아야 한다.** 처음에 64x48 파일을 만들어 놓고 `Frame.width` 에는
# 2752 를 적었더니 개체 bbox 가 이미지 밖에 앉아 `/crop` 이 잘라 낼 것을 못
# 찾았다 — **현실에서 생길 수 없는 상태를 시험한 것**이다. 크기는 여기 하나로
# 정하고 행·파일·bbox 가 전부 이 값을 따른다.
IMG_W, IMG_H = 640, 480

# `add_other_engine` 의 탈락 후보 자리 (x, y, w, h). **통과분과 안 겹친다.**
# 시험이 이 값을 짚어 그 자리를 누르므로 여기 하나로 정해 둔다 — 시험에 좌표를
# 베껴 두면 자리를 옮길 때 시험만 옛 자리를 누르고 조용히 건너뛴다.
REJECT_BOX = (480, 380, 44, 40)
REJECT_CENTER = (REJECT_BOX[0] + REJECT_BOX[2] // 2,
                 REJECT_BOX[1] + REJECT_BOX[3] // 2)


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
        """그 시야의 **대표** 현재 검출 — 합성본이 있으면 합성본.

        예전에는 `.get(is_current=True)` 였다. **시야마다 현재 검출이 하나**라는
        전제인데, 프레임별 검출을 올리면 깨진다(P09 1단계 · `add_frame_detections`).
        깨진 채로 두면 시험이 `MultipleObjectsReturned` 로 서는데, 그것은
        **시험이 못 쓰게 된 것이지 코드가 틀렸다는 말이 아니라** 무엇이 문제인지를
        가린다.

        집계가 세는 것과 같은 규칙이다(`data.representative_detection`) — 규칙이
        둘이 되면 시험이 화면과 다른 것을 증언한다.
        """
        return data.representative_detection(vp or self.vp)

    def keys(self, vp=None) -> list[str]:
        """그 시야 개체들의 `mask_key`. 화면이 보내는 것과 같은 것들이다."""
        return [c.mask_key for c in self.detection(vp).candidates.all()]

    def stem(self, vp=None) -> str:
        """화면이 `/review` 에 보내는 `stem`."""
        from pathlib import Path
        return Path(self.detection(vp).image_path).stem


# --- 분류표 ----------------------------------------------------------------

# `ClassDef` 는 여덟 칸을 전부 채워야 한다 — 하나라도 비면 **예외는 안 나고 그
# 분류만 조용히 다르게 구른다**(038~040).
#
# **운영의 분류표를 그대로 옮겨 적는다.** 아무 값이나 쓰면 안 되는 이유가 하나
# 있다 — `badge` 와 `color` 는 `base.html` 의 CSS 와 짝이고(`.badge.<badge>`),
# 그 짝이 맞는지가 `test_classdef_css.py` 의 시험 대상이다. 지어낸 배지를 쓰면
# 그 시험이 **늘 실패하거나 늘 통과하거나** 둘 중 하나가 되어 아무것도 안 본다.
#
# **옮겨 적은 것이라 한계가 있다** — 운영에 분류가 늘어도 여기는 모른다.
# 그쪽은 `check_db.py` 의 "4. 분류" 가 본다(운영 DB 를 직접 읽는다).
# 여기가 잡는 것은 반대 방향이다: **`base.html` 의 CSS 가 지워지거나 바뀌는 것.**
CLASSES = [
    # key,          label,        short, badge, color,          hotkey, counted, taxon
    ("round",       "원형",        "원",   "rnd",  "60,220,120",   "q",   True,   False),
    ("round_frag",  "원형조각",     "원조",  "rndf", "140,235,170",  "q",   False,  False),
    ("rod",         "봉상",        "봉",   "rod",  "70,140,255",   "w",   True,   False),
    ("rod_frag",    "봉상조각",     "봉조",  "rodf", "120,195,255",  "w",   False,  False),
    ("eucampia",    "Eucampia",   "Euc",  "euc",  "255,110,190",  "e",   True,   True),
    ("chaetoceros", "Chaetoceros", "Cha",  "cha",  "150,225,75",   "r",   True,   True),
    ("rhizosolenia", "Rhizosolenia", "RHZ", "rhi", "185,130,255",  "t",   True,   True),
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

    det = _make_detection(vp, img, n_candidates=n_candidates)
    # **완료 표시는 묶음에 붙는다** (073). 묶음 없는 줄은 시야 코멘트 자리라
    # 거기에 만들면 **운영에 없는 상태**가 된다 — 픽스처가 그런 상태를 만들면
    # 그 위에서 도는 시험이 전부 헛통과한다 (P10 0단계에서 두 번 당했다).
    ViewpointReview.objects.create(viewpoint=vp, batch=det.batch, done=False)
    return vp


def _make_detection(vp, img, *, n_candidates):
    # 문턱 11개는 전부 모델 기본값이 있다 — **여기서 베끼지 않는다.** 베껴 두면
    # 기본값이 바뀔 때 시험만 옛 값을 증언한다.
    ts, _ = ThresholdSet.objects.get_or_create(name="시험 기본",
                                               defaults={"is_default": True})
    # **현재 검출은 묶음에 들어 있다** (P09 0단계). 교정의 열쇠가
    # `(image, batch, mask_key)` 라 묶음 없는 검출에는 저장을 받지 않는다 —
    # `batch=None` 은 사람이 그린 개체의 자리이기 때문이다(P09 5.2).
    #
    # 운영 DB 의 현재 검출 508개가 전부 `sam2-전수` 에 들어 있다. 픽스처가 그
    # 사실을 안 지키면 **시험이 현실에 없는 상태를 만들어 놓고 통과한다** —
    # 실제로 그렇게 짜여 있었고, 0단계에서 가드가 5개를 세워 드러났다.
    # **검토 대상 묶음이 정해져 있다** (P10). 운영에는 늘 하나가 켜져 있고,
    # 없으면 화면이 빈 목록을 본다 — 픽스처가 그 사실을 안 지키면 시험이
    # 현실에 없는 상태를 만들어 놓고 통과한다(0단계에서 같은 일이 있었다).
    batch, made = RunBatch.objects.get_or_create(kind="detect", label="sam2-시험")
    if made and not RunBatch.objects.filter(for_review=True).exists():
        batch.for_review = True
        batch.save(update_fields=["for_review"])
    run = Run.objects.create(kind="detect", batch=batch, slide=vp.slide,
                             status="done")
    det = Detection.objects.create(
        viewpoint=vp, image=img, image_path=img.path,
        width=img.width or IMG_W, height=img.height or IMG_H,
        scale=1.0, um_per_pixel=0.1, um_per_pixel_source="xml",
        n_raw_masks=n_candidates + 1, n_sized=n_candidates,
        thresholds=ts, run=run, is_current=True)

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


def add_frame_detections(vp, *, n_candidates=2):
    """그 시야의 **프레임마다 현재 검출**을 하나씩 더 만든다 (P09 1단계).

    합성본에 하나 + 프레임마다 하나 — **시야 하나에 현재 검출이 여럿인 상태**다.
    YOLO 는 합성본이 아니라 원본 프레임을 보므로 갈아타면 그 모양이 된다
    (실측: `yolo-3차` 는 시야 452개에 프레임 검출 1,310개).

    **운영 DB 에는 아직 이 상태가 없다.** 그래서 시험이 먼저 만든다 — 없으면
    "시야마다 이미지가 하나" 를 전제한 코드가 전부 통과한 채로 남고, 갈아타는
    날 한꺼번에 드러난다. 그 날 잃는 것은 재생성 불가한 교정이다.

    돌려주는 것은 `[(frame, image, detection), …]`.
    """
    out = []
    for f in vp.frames.all():
        img = Image.objects.get(path=f.path)
        if vp.detections.filter(image=img, is_current=True).exists():
            continue                     # 싱글턴 시야 — 이미 그 프레임이 대상이다
        out.append((f, img, _make_detection(vp, img,
                                            n_candidates=n_candidates)))
    return out


def add_other_engine(vp, *, label=None, n_candidates=2, frames=False,
                     current=False, code="") -> Run:
    """같은 시야에 **다른 엔진의 검출**을 하나 더 쌓는다. `Run` 을 돌려준다.

    **검출은 덮어쓰지 않고 쌓는다** — `is_current` 가 뷰어가 볼 것을 가리킨다
    (CLAUDE.md). 이 함수가 만드는 것은 `is_current=False` 라 검토 화면에는
    안 나오고, `?batch=<run.id>` 로 골라야 보인다.

    **그리고 그때가 읽기 전용이다** (051). 교정은 `mask_key`(bbox 문자열)로
    붙는데 엔진이 다르면 거의 전부 어긋나므로 저장을 받으면 안 된다. 읽기
    전용 화면을 시험하려면 이 자료가 있어야 한다.

    `current=True` 면 **그 묶음 안에서 현재 검출**로 세운다. 운영이 그 모양이다 —
    `is_current` 는 "그 묶음 안에서 최신" 이라 묶음마다 따로 켜져 있고(실측으로
    `sam2-전수`·`yolo-3차` 둘 다 켜져 있다), 개체 카탈로그처럼 **묶음을 짚어
    여는 화면**은 그 자료라야 밟힌다. 기본값이 `False` 인 것은 051 계열 시험이
    "옛 검출" 을 필요로 하기 때문이다.

    `code` 는 그 묶음의 카탈로그 코드 (`RunBatch.code`).
    """
    batch, _ = RunBatch.objects.get_or_create(
        kind="detect", label=label or f"yolo-시험-{vp.slide.slug}",
        defaults={"code": code})
    if code and batch.code != code:
        batch.code = code
        batch.save(update_fields=["code"])
    run = Run.objects.create(kind="detect", batch=batch, slide=vp.slide,
                             status="done")

    cur = vp.detections.filter(is_current=True).first()
    if cur is None:
        cur = vp.detections.order_by("id").first()

    imgs = [(cur.image, cur.image_path)]
    if frames:
        for f in vp.frames.all():
            img = Image.objects.get(path=f.path)
            if img.pk != cur.image_id:
                imgs.append((img, f.path))

    dets = []
    for img, path in imgs:
        dets.append(Detection.objects.create(
            viewpoint=vp, image=img, image_path=path,
            width=cur.width, height=cur.height, scale=1.0,
            um_per_pixel=cur.um_per_pixel, um_per_pixel_source="xml",
            n_raw_masks=n_candidates, n_sized=n_candidates,
            run=run, is_current=current))

    # **현재 검출과 다른 자리에 둔다.** 같은 bbox 를 쓰면 `mask_key` 가 겹쳐
    # 교정이 우연히 붙고, "엔진이 다르면 키가 어긋난다" 는 전제가 시험 자료에서
    # 만 성립하지 않게 된다. 판마다도 조금씩 어긋나게 둔다 — 프레임끼리 키가
    # 같으면 "어느 판의 교정인지" 를 가르는 자리가 시험에서 안 눌린다.
    for det_i, det in enumerate(dets):
        for i in range(n_candidates):
            x, y = 300 + i * 90 + det_i * 5, 250 + i * 60 + det_i * 5
            w, h = 55 + i * 7, 45 + i * 7
            Candidate.objects.create(
                detection=det, raw_id=i,
                mask_key=data.cand_key({"bbox_xywh": [x, y, w, h]}),
                bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h,
                center_x=x + w // 2, center_y=y + h // 2,
                area_px=w * h // 2, area_um2=float(w * h) / 200,
                major_um=float(w) / 10, minor_um=float(h) / 10,
                long_side_um=float(w) / 10, short_side_um=float(h) / 10,
                aspect_ratio=w / h, fill_ratio=0.6,
                shape_ok=True, circularity=0.8, convexity=0.9, solidity=0.9,
                elongation=1.2, ellipse_iou=0.86, texture=2800.0,
                polygon=[x, y, x + w, y, x + w, y + h, x, y + h],
                passed=True, cls=CLASSES[i % len(CLASSES)][0])

        # 탈락분 하나 — 읽기 전용에서 **탈락 펼침판**이 어떻게 구는지 보려면
        # 있어야 한다.
        #
        # **통과분이 안 덮는 자리에 둔다.** 펼침판은 우클릭 메뉴의 "이 자리의
        # 탈락 후보 보기" 로 여는데, 그 항목은 **빈 자리를 눌렀을 때만**
        # (`d.target === null`) 나온다. 통과분 위에 겹쳐 두면 개체 메뉴가 떠서
        # 영영 못 연다.
        x, y, w, h = REJECT_BOX
        Candidate.objects.create(
            detection=det, raw_id=n_candidates,
            mask_key=data.cand_key({"bbox_xywh": [x, y, w, h]}),
            bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h,
            center_x=x + w // 2, center_y=y + h // 2,
            area_px=w * h // 2, area_um2=2.0, major_um=2.4, minor_um=2.0,
            long_side_um=2.4, short_side_um=2.0, aspect_ratio=1.2,
            fill_ratio=0.5, shape_ok=False, texture=180.0,
            polygon=[x, y, x + w, y, x + w, y + h, x, y + h],
            passed=False, reject="too_small")
    return run


def add_review(vp, mask_key, *, image=None, removed=False, accepted=False,
               label="", note="", species="") -> ObjectReview:
    """교정 한 줄. **`(image, batch, mask_key)` 가 열쇠다.**

    `geom` 을 반드시 채운다 — 교정은 기하를 스스로 들고 있어야 검출기가 바뀌어도
    읽힌다(CLAUDE.md). 빈 `geom` 으로 만들면 시험이 그 규칙을 안 지키는 자료를
    만들어 놓고 통과한다.

    `image` 를 주면 그 이미지의 현재 검출에 붙인다. 안 주면 대표 이미지다 —
    `World.detection()` 과 같은 규칙을 본다(둘로 갈라지면 어긋난다).

    **개체(`DiatomObject`)를 함께 세운다** (P12). 판정은 개체 없이 설 수 없고,
    분류·종명·코멘트는 그쪽에 산다(0036) — 여기서 갈래를 만들면 시험 자료가
    운영과 다른 모양이 되고, 그런 시험은 덮은 줄 알게 한다.
    """
    if image is None:
        det = data.representative_detection(vp)
    else:
        image_id = getattr(image, "pk", image)
        det = vp.detections.get(is_current=True, image_id=image_id)
    cand = det.candidates.filter(mask_key=mask_key).first()
    geom = {}
    if cand is not None:
        geom = {"bbox": cand.bbox_xywh, "polygon": list(cand.polygon)}
    obj = DiatomObject.objects.create(viewpoint=vp, batch=det.batch,
                                      label=label, species=species, note=note)
    return ObjectReview.objects.create(
        viewpoint=vp, image=det.image, batch=det.batch, mask_key=mask_key,
        candidate=cand, bind_method="exact" if cand else "orphan", geom=geom,
        diatom_object=obj, is_rep=True,
        removed=removed, accepted=accepted)


def new_review(**kw) -> ObjectReview:
    """판정 행을 손으로 세우는 자리 — **개체를 함께 세운다** (P12).

    `ObjectReview.objects.create(...)` 를 시험이 직접 부르면 개체가 없어
    `NOT NULL` 로 죽는다. 그리고 죽지 않게 고치더라도, 시험만 옆문으로 만드는
    자료는 **운영에 없는 모양**이 된다(이 파일 머리말의 그 규칙이다).

    `label`·`species`·`note` 는 개체로 넘긴다(0036). `add_review` 는 후보를 찾아
    `geom` 까지 채우는 정식 문이고, 이쪽은 **고아·다른 묶음처럼 후보가 없는
    자료**를 세울 때 쓴다.
    """
    label = kw.pop("label", "")
    species = kw.pop("species", "")
    note = kw.pop("note", "")
    obj = kw.pop("diatom_object", None)
    if obj is None:
        vp = kw.get("viewpoint") or kw.get("viewpoint_id")
        if vp is None:
            # 이미지에서 시야를 얻는다 — 부르는 자리마다 시야를 다시 적게
            # 하면 그 값이 이미지와 어긋날 자리가 생긴다.
            img = kw["image"]
            vp = getattr(img, "viewpoint", None) or Image.objects.get(
                pk=getattr(img, "pk", img)).viewpoint
            kw["viewpoint"] = vp
        vp_id = getattr(vp, "pk", vp)
        # **둘을 같이 주면 안 된다** — `batch=<객체>` 와 `batch_id=None` 을 함께
        # 넘기면 뒤엣것이 이겨 묶음이 조용히 비워진다.
        b = kw.get("batch")
        obj = DiatomObject.objects.create(
            viewpoint_id=vp_id, label=label, species=species, note=note,
            **({"batch": b} if b is not None else
               {"batch_id": kw.get("batch_id")}))
    kw.setdefault("is_rep", True)
    return ObjectReview.objects.create(diatom_object=obj, **kw)


def links(vp=None):
    """**묶음** — 멤버가 둘 이상인 개체만 (P12).

    P12 뒤로는 판정마다 개체가 하나씩 서므로 `DiatomObject.objects.count()` 는
    "묶음 몇 개" 가 아니다. 화면·감사 기록이 말하는 묶음은 여전히 *여러 판이
    한 규조각* 인 것이고, 시험도 그 눈으로 세야 한다.
    """
    qs = (DiatomObject.objects.annotate(_n=Count("members"))
          .filter(_n__gte=2))
    return qs if vp is None else qs.filter(viewpoint=vp)


def link_reviews(rows, rep=0) -> DiatomObject:
    """판정 여럿을 **한 개체로 묶는다** (P12). 돌려주는 것은 그 개체.

    묶기는 개체를 합치는 일이라, 그릇 하나만 남기고 나머지는 유령이 된다 —
    `data.prune_objects` 와 같은 순서로 **옮긴 뒤에** 걷는다.
    """
    rows = list(rows)
    target = rows[rep].diatom_object
    ghosts = []
    for i, row in enumerate(rows):
        if row.diatom_object_id != target.pk:
            ghosts.append(row.diatom_object_id)
        row.diatom_object = target
        row.is_rep = (i == rep)
        row.save(update_fields=["diatom_object", "is_rep"])
    DiatomObject.objects.filter(pk__in=ghosts, members__isnull=True).delete()
    return target


def _write(rel):
    """픽스처가 파일을 쓰는 유일한 자리.

    **`base.write_image` 를 지난다** — 거기서 뿌리가 임시 디렉토리인지 확인한다.
    픽스처가 자기 손으로 쓰면 그 확인을 건너뛴다: 실제로 그렇게 짰다가 시험이
    `/data3/DiaRUGA` 에 사진을 썼다 (base.py 머리말).

    크기는 `IMG_W x IMG_H` 하나뿐이다 — 행에 적은 값과 파일이 어긋나면 안 된다.
    """
    return write_image(rel, size=(IMG_W, IMG_H))
