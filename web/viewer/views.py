import hashlib
import json
import math
import os
import re
import time
from datetime import date
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import (FileResponse, Http404, HttpResponse,
                         HttpResponseBadRequest, JsonResponse)
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import antarctica, data, korea, thresholds as th
from .models import (Core, Detection, ObjectReview, Run, Site,  # noqa: E501
                     Slide, ThresholdSet, Viewpoint)

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import judge  # noqa: E402
import db_sentinel  # noqa: E402

# 파일명으로 그대로 쓰이므로 경로 성분이 될 수 있는 문자를 막는다.
SAFE_STEM = re.compile(r"^[A-Za-z0-9._-]+$")

# 메모 길이 상한. 사람이 손으로 적는 것이라 넉넉하면 충분하다.
NOTE_MAX = 500

# 문턱 조정 화면에 보여줄 순서와 이름. 판정에서 먼저 걸리는 것을 위에 둔다.
THRESHOLD_FIELDS = [
    ("texture_min", "텍스처", "1차 관문 — 규조각인가", 0, 8000, 50),
    ("round_texture_min", "원형 areolae", "원형에만 걸리는 하한", 0, 8000, 50),
    ("min_um", "크기 하한", "타원 장축 µm", 0, 60, 0.5),
    ("max_um", "크기 상한", "타원 장축 µm", 20, 400, 5),
    ("round_max_elong", "원형 신장비", "이 값 미만이면 원형으로 본다", 1, 3, 0.05),
    ("round_min_iou", "원형 타원 IoU", "", 0, 1, 0.01),
    ("round_min_solidity", "원형 볼록성", "", 0, 1, 0.01),
    ("rod_min_elong", "봉상 신장비 하한", "", 1, 10, 0.1),
    ("rod_max_elong", "봉상 신장비 상한", "", 2, 40, 0.5),
    ("rod_min_iou", "봉상 타원 IoU", "우상목은 피침형이라 구조적으로 낮다", 0, 1, 0.01),
    ("rod_min_solidity", "봉상 볼록성", "", 0, 1, 0.01),
]


def index(request):
    # 권역(한국·남극)은 `?area=` 로 고른다. 고르는 일을 data.area_tabs() 에 맡겨
    # 없는 값이 들어와도 빈 화면이 되지 않게 한다.
    area = data.area_tabs(request.GET.get("area"))
    rows = data.datasets(area["selected"])
    # **"전체" 에는 지도가 없다.** 투영이 권역마다 다르므로(남극 EPSG:3031 ·
    # 한국 EPSG:5179) 섞인 것을 한 지도에 올릴 수가 없다. 억지로 하나를 고르면
    # 다른 권역의 시료가 조용히 빠지거나 엉뚱한 자리에 찍힌다.
    show_map = not area["is_all"]
    return render(request, "viewer/index.html", {
        "datasets": rows,
        "area": area,
        "show_map": show_map,
        "totals": data.datasets_total(rows),
        # 표의 분류 열. 줄이 아니라 여기서 정한다 — 슬라이드마다 0인 분류를
        # 빼면 열 수가 달라져 세로로 안 맞는다.
        "count_classes": data.counted_classes(),
        # 지도는 세 번째 보기 방식이다. 해안선이 10~27 KB 뿐이라 늘 함께 보낸다 —
        # 따로 요청하게 만들면 전환이 즉시 되지 않는다.
        "antmap": (_map_ctx(area["selected"], data.map_points(area["selected"]))
                   if show_map else None),
    })


def _map_ctx(area: str, pts: list) -> dict:
    """권역에 맞는 지도 상수. 이름이 `antmap` 인 것은 남극만 있던 때의 흔적이다.

    **투영이 다르면 좌표 단위도 다르다** — 남극은 km, 한국은 m 다. 마커 그림은
    남극 기준(반지름 70)으로 그려져 있어서, 한국 지도에서는 같은 눈에 보이는
    크기가 되도록 `mark` 배율로 키운다. 이 값을 잘못 주면 마커가 안 보이거나
    지도를 덮는다.
    """
    common = {"points": pts, "any_approx": any(not q["exact"] for q in pts)}
    if area == "kr":
        x, y, w, h = korea.VIEWBOX
        return {
            **common, "kind": "kr",
            "land": korea.LAND,
            "viewbox": f"{x} {y} {w} {h}",
            "vb": korea.VIEWBOX,
            "sea_labels": korea.SEA_LABELS,
            # 눈금은 한 축만 자료로 갖고 있다. 나머지는 여기서 viewBox 안쪽으로
            # 붙인다 — 위경도로 자리를 잡으면 지도 밖으로 잘려 나간다.
            "lat_ticks": [(lab, x + round(w * 0.035), ty)
                          for lab, ty in korea.LAT_TICKS],
            "lon_ticks": [(lab, tx, y + h - round(h * 0.025))
                          for lab, tx in korea.LON_TICKS],
            # 남극 지도의 viewBox 폭이 7600(km)이다. 그 비로 마커를 키운다.
            "mark": round(w / 7600, 1),
            "scale_bar": korea.SCALE_BAR_M,
            "scale_mid": korea.SCALE_BAR_M // 2,
            "scale_label": korea.SCALE_BAR_LABEL,
            "scale_x": x + round(w * 0.06),
            "scale_y": y + h - round(h * 0.06),
        }
    return {
        **common, "kind": "ant",
        "land": antarctica.LAND,
        "boundary": antarctica.BOUNDARY_KM,
        "lat_circles": antarctica.LAT_CIRCLES,
        "boundary_label": antarctica.BOUNDARY_LABEL,
        "lon_labels": antarctica.LON_LABELS,
        "lon_spokes": antarctica.LON_SPOKES,
        "sea_labels": antarctica.SEA_LABELS,
    }


# --- 시험용: 다른 엔진의 결과 보기 -------------------------------------------
#
# 뷰어는 `is_current=True` 인 검출만 본다. 나란히 쌓아 둔 다른 엔진의 결과는
# 어디에도 안 보이므로 이 길로만 볼 수 있다.
#
# **읽기 전용이다.** 교정을 저장하지 않는다 — 교정은 mask_key 로 붙는데 엔진이
# 다르면 거의 전부 어긋나고, 여기서 저장하면 현재 검출에 엉뚱하게 얹힌다.
def engine_index(request):
    return render(request, "viewer/engine_index.html",
                  {"runs": data.engine_runs()})


def engine_run(request, run_id):
    run = Run.objects.filter(pk=run_id).first()
    if run is None:
        raise Http404(f"unknown run: {run_id}")
    return render(request, "viewer/engine_run.html", {
        "run": run,
        "title": run.batch.label if run.batch_id else f"실행 #{run.pk}",
        "note": run.batch.note if run.batch_id else "",
        "n_runs": len(data.engine_run_ids(run_id)),
        "backend": (run.params or {}).get("backend", "?"),
        "rows": data.engine_viewpoints(run_id),
    })


def engine_view(request, run_id, slug, gid):
    ctx = data.engine_viewpoints and data.engine_viewpoint(slug, gid, run_id)
    if ctx is None:
        raise Http404(f"unknown: {slug}/{gid} in run {run_id}")
    run = Run.objects.filter(pk=run_id).select_related("batch").first()
    ctx["backend"] = (run.params or {}).get("backend", "?") if run else "?"
    ctx["run_params"] = (run.params or {}) if run else {}
    ctx["batch_label"] = (run.batch.label if run and run.batch_id
                          else f"실행 #{run_id}")
    # 같은 시야를 보면서 엔진을 갈아 끼울 수 있게 한다
    ctx["batches"] = data.batches_for_viewpoint(slug, gid, run_id)
    return render(request, "viewer/engine_view.html", ctx)


def dataset(request, slug):
    ctx = data.dataset_detail(slug)
    if ctx is None:
        raise Http404(f"unknown dataset: {slug}")
    return render(request, "viewer/dataset.html", ctx)


def group(request, slug, gid):
    ctx = data.group_detail(slug, gid)
    if ctx is None:
        raise Http404(f"unknown group: {slug}/{gid}")
    # 보고 있는 시야를 다른 엔진으로 볼 수 있게. 묶음이 둘 이상일 때만 낸다 —
    # 하나뿐이면 지금 보는 그것이라 갈 곳이 없다.
    #
    # **검토 화면이 이미 보여 주는 묶음으로는 보내지 않는다.** 지금 화면이
    # 그리는 것이 현재 검출이라, 거기로 가면 같은 것을 교정만 뗀 채 다시 보게
    # 된다. 다른 엔진이 먼저 열려야 견주는 뜻이 산다.
    bs = data.batches_for_viewpoint(slug, gid)
    ctx["engine_batches"] = bs
    ctx["engine_link"] = next((b for b in bs if not b["current"]), None)
    return render(request, "viewer/group.html", ctx)


def _num(raw, cast=float):
    """빈 칸은 None 으로. 잘못된 값은 예외를 올려 보낸다 — 조용히 0 이 되면 안 된다."""
    raw = (raw or "").strip()
    if not raw:
        return None
    return cast(raw)


def dataset_edit(request, slug):
    """슬라이드·코어·지역의 속성을 사람이 채우는 화면.

    폴더 이름에서 뽑을 수 있는 것(지역 코드·코어 코드·깊이)은 파이프라인이 채워
    두었고, 뽑을 수 없는 것(정식 명칭·좌표·수심·채취일)은 비어 있다. 코드만으로
    "RS = 로스해" 를 단정하지 않는다 — `models.Site` 머리말이 정한 방침이다.
    화면에서는 그것을 **추천으로만** 보여 주고 사람이 확인해 넣게 한다.

    **지역과 코어는 여러 슬라이드가 공유한다.** 여기서 고치면 같은 코어의 다른
    깊이 슬라이드에도 반영되므로, 몇 개가 함께 바뀌는지 미리 알린다.
    """
    slide = Slide.objects.filter(slug=slug).select_related(
        "core", "core__site").first()
    if slide is None:
        raise Http404(f"unknown dataset: {slug}")
    core = slide.core
    site = core.site if core else None

    errors, saved = [], False
    if request.method == "POST":
        p = request.POST
        # **없으면 만든다.** 폴더 이름이 `<지역>-<코어> <깊이>cm` 꼴이 아니면
        # 파이프라인이 코어를 못 붙인다(실제로 `BP09-0901` 이 그랬다). 그런
        # 슬라이드는 어느 권역 탭에도 안 나오는데, 여기서 지역을 만들 수 없으면
        # 영영 붙일 길이 없다 — 안내문이 "속성 편집에서 지정하면" 이라고 적어
        # 놓고 실제로는 안 되는 상태였다.
        #
        # **같은 코드가 이미 있으면 그것에 붙인다.** 새로 만들면 unique 로 죽고,
        # 무엇보다 같은 지역이 둘로 갈라진다.
        site_code = (p.get("site_code") or "").strip()
        core_code = (p.get("core_code") or "").strip()
        made_site = made_core = False
        if site is None and site_code:
            site = Site.objects.filter(code=site_code).first()
            if site is None:
                site, made_site = Site(code=site_code), True
        if core is None and core_code and site is not None:
            core = (Core.objects.filter(site=site, code=core_code).first()
                    if site.pk else None)
            if core is None:
                core, made_core = Core(site=site, code=core_code), True
        try:
            slide.name = (p.get("slide_name") or slide.name).strip()
            slide.depth_cm = _num(p.get("depth_cm"))
            slide.description = (p.get("description") or "").strip()
            slide.um_per_pixel_override = _num(p.get("um_per_pixel_override"))
            if core:
                core.code = (p.get("core_code") or core.code).strip()
                core.kind = (p.get("core_kind") or "").strip()
                core.lat = _num(p.get("core_lat"))
                core.lon = _num(p.get("core_lon"))
                core.water_depth_m = _num(p.get("core_water_depth"))
                d = (p.get("core_collected_at") or "").strip()
                core.collected_at = date.fromisoformat(d) if d else None
                core.note = (p.get("core_note") or "").strip()
            if site:
                site.code = (p.get("site_code") or site.code).strip()
                site.name = (p.get("site_name") or "").strip()
                site.region = (p.get("site_region") or "").strip()
                # 목록·지도를 가르는 값이라 아무 문자열이나 들어오면 안 된다.
                # 모르는 값이 오면 조용히 바꾸지 않고 그대로 둔다.
                a = (p.get("site_area") or "").strip()
                if a in dict(Site.AREA):
                    site.area = a
                site.lat = _num(p.get("site_lat"))
                site.lon = _num(p.get("site_lon"))
                site.note = (p.get("site_note") or "").strip()
        except ValueError as e:
            errors.append(f"값을 읽지 못했습니다: {e}")

        if not errors:
            # 셋을 한 덩어리로 저장한다. 코어만 바뀌고 지역이 안 바뀌면
            # 화면에 보이는 것과 저장된 것이 어긋난다.
            try:
                with transaction.atomic():
                    if site:
                        site.save()
                    if core:
                        # 새로 만든 지역이면 이제야 pk 가 생긴다
                        core.site = site
                        core.save()
                    # 코어가 없던 슬라이드를 이제 매단다
                    if core and slide.core_id != core.pk:
                        slide.core = core
                    slide.save()
                saved = True
                if made_site or made_core:
                    made = " · ".join(
                        x for x in (f"지역 {site.code}" if made_site else "",
                                    f"코어 {core.code}" if made_core else "") if x)
                    messages_made = f"{made} 을(를) 새로 만들어 붙였습니다."
                else:
                    messages_made = ""
            except IntegrityError as e:
                errors.append(f"같은 코드가 이미 있습니다: {e}")
                messages_made = ""

    scales = data.scales_by_slide()
    return render(request, "viewer/dataset_edit.html", {
        "slug": slug,
        "label": slide.name,
        "slide": slide,
        "core": core,
        "site": site,
        "core_code": core.code if core else "-",
        "site_code": site.code if site else "-",
        "n_slides_core": core.slides.count() if core else 0,
        "n_slides_site": (Slide.objects.filter(core__site=site).count()
                          if site else 0),
        "n_viewpoints": slide.viewpoints.count(),
        "n_frames": slide.frames.count(),
        "site_areas": Site.AREA,
        "um_per_pixel": scales.get(slug),
        "errors": errors,
        "saved": saved,
        "made": locals().get("messages_made", ""),
        # 지역·코어가 아직 없으면 화면이 그렇게 말해야 한다 — 빈 칸만 보이면
        # "고치는 곳" 으로 읽히지 "만드는 곳" 으로는 안 읽힌다.
        "no_site": site is None,
        "no_core": core is None,
    })


# 표 한 장에 몇 줄까지 낼 것인가. 369cm 슬라이드가 1,166줄이라 전부 내면
# HTML 이 371 KB 가 된다 — 화면에서 그만큼을 한 번에 훑을 일도 없다.
DETECT_PER_PAGE = 300


def detections(request, slug):
    """데이터셋 전체에서 검출된 후보를 한 표로 모아 크기 분포를 본다."""
    label = data.slide_label(slug)
    if label is None:
        raise Http404(f"unknown dataset: {slug}")

    rows = data.candidate_rows(slug)
    rows.sort(key=lambda r: -r["long_side_um"])

    # **요약은 전부를 기준으로 낸다.** 보고 있는 쪽만 세면 페이지를 넘길 때마다
    # 중앙값이 달라져서, 그 값이 무엇의 중앙값인지 알 수 없게 된다.
    sizes = sorted(r["long_side_um"] for r in rows)
    summary = None
    if sizes:
        summary = {
            "n": len(sizes),
            "min": round(sizes[0], 1),
            "median": round(sizes[len(sizes) // 2], 1),
            "max": round(sizes[-1], 1),
            "mean": round(sum(sizes) / len(sizes), 1),
        }

    total = len(rows)
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        offset = 0
    page = rows[offset:offset + DETECT_PER_PAGE]

    return render(
        request,
        "viewer/detections.html",
        {"slug": slug, "label": label, "rows": page, "summary": summary,
         "total": total,
         "shown_from": offset + 1 if page else 0,
         "shown_to": offset + len(page),
         "prev_url": (f"?offset={max(0, offset - DETECT_PER_PAGE)}"
                      if offset else None),
         "next_url": (f"?offset={offset + DETECT_PER_PAGE}"
                      if offset + DETECT_PER_PAGE < total else None)},
    )


CROPS_PER_PAGE = 500


def crops(request, slug):
    """검출된 개체만 잘라 썸네일로 늘어놓는다.

    시야를 하나씩 넘겨보지 않고 "이것들이 정말 규조각인가" 를 한 화면에서
    훑을 수 있어야 한다. 크기 내림차순이라 의심스러운 것(작고 밋밋한 것)이
    뒤쪽에 모인다.
    """
    label = data.slide_label(slug)
    if label is None:
        raise Http404(f"unknown dataset: {slug}")

    rows = data.candidate_rows(slug)
    cls = request.GET.get("cls") or ""
    if cls in data.CLASSES:
        rows = [r for r in rows if r.get("cls") == cls]
    elif cls == "manual":
        rows = [r for r in rows if r.get("manual")]
    elif cls == "labeled":
        rows = [r for r in rows if r.get("cls_user")]
    elif cls == "noted":
        rows = [r for r in rows if r.get("note")]
    rows.sort(key=lambda r: -r["long_side_um"])

    # 방향을 세워서 보여준다 — 폴리곤의 주축을 세로로. 갤러리에서 형태를 나란히
    # 비교하려면 방향이 통일돼야 한다. 원형처럼 축 비율이 1에 가까우면 돌리지
    # 않는다(굳이 보간으로 흐릴 이유가 없다).
    upright = request.GET.get("upright", "1") != "0"
    n_upright = 0
    for r in rows:
        geo = data.crop_geometry(r, rotate=upright)
        if not geo:
            continue
        r["rot"], r["out"] = geo["rot"], geo["out"]
        if geo["rot"]:
            n_upright += 1
        # 스케일바 — 크롭 폭이 몇 µm 인지 알기 때문에 그릴 수 있다.
        r["sb"] = data.scalebar_for(geo["out_w"], r.get("um_per_pixel") or 0)

    total = len(rows)
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        offset = 0
    page = rows[offset:offset + CROPS_PER_PAGE]

    def page_url(off, **extra):
        q = {"offset": off}
        if cls:
            q["cls"] = cls
        if not upright:
            q["upright"] = 0
        q.update(extra)
        return f"?{urlencode(q)}"

    return render(
        request,
        "viewer/crops.html",
        {
            "slug": slug,
            "label": label,
            "rows": page,
            "cls": cls,
            "upright": upright,
            "n_upright": n_upright,
            "upright_url": f"?{urlencode({'cls': cls} if cls else {})}",
            "flat_url": f"?{urlencode(dict({'cls': cls} if cls else {}, upright=0))}",
            "total": total,
            "shown_from": offset + 1 if page else 0,
            "shown_to": offset + len(page),
            "per_page": CROPS_PER_PAGE,
            "prev_url": page_url(max(0, offset - CROPS_PER_PAGE)) if offset else None,
            "next_url": (page_url(offset + CROPS_PER_PAGE)
                         if offset + CROPS_PER_PAGE < total else None),
        },
    )


def crop(request):
    """
    ?p=<DATA_ROOT 기준 상대경로>&b=<x,y,w,h>&w=<출력 폭>

    검출 개체 하나만 잘라 낸다. 데이터셋 하나에 개체가 800~1,100개라 매번
    자르면 갤러리가 못 쓸 정도로 느려지므로 축소본과 같은 방식으로 캐시한다.
    """
    path = data.safe_image_path(request.GET.get("p", ""))
    if path is None:
        raise Http404("image not found or outside allowed dirs")

    try:
        box = [int(round(float(v))) for v in request.GET.get("b", "").split(",")]
    except ValueError:
        return HttpResponseBadRequest("bad bbox")
    if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
        return HttpResponseBadRequest("bad bbox")

    try:
        width = max(32, min(int(request.GET.get("w", 200)), 512))
    except ValueError:
        return HttpResponseBadRequest("bad width")

    # pad=0 이면 넘겨받은 box 를 그대로 자른다. 마스크를 겹쳐 그리는 쪽에서는
    # 잘린 범위를 정확히 알아야 폴리곤을 맞출 수 있으므로 여백을 직접 계산한다.
    raw_pad = request.GET.get("pad")
    try:
        pad = None if raw_pad is None else max(0, min(int(raw_pad), 512))
    except ValueError:
        return HttpResponseBadRequest("bad pad")

    # rot/out: 개체를 세워서 보여줄 때 쓴다(장축을 세로로). 회전량과 결과 크기는
    # 폴리곤을 가진 쪽(crops 뷰)이 계산해 넘긴다 — 여기서는 마스크가 없다.
    rot = request.GET.get("rot")
    size = request.GET.get("out")
    try:
        rot = None if rot is None else max(-180.0, min(float(rot), 180.0))
        if size is not None:
            ow, oh = (int(v) for v in size.split(","))
            if not (0 < ow <= 4096 and 0 < oh <= 4096):
                raise ValueError("out")
            size = (ow, oh)
    except ValueError:
        return HttpResponseBadRequest("bad rot/out")

    if rot is not None and size is not None:
        out = _upright_thumb(path, box, width, rot, size)
    else:
        out = _crop_thumb(path, box, width, pad)
    if out is None:
        raise Http404("cannot crop")
    return _jpeg(request, out)


def _upright_thumb(path, box, width, rot, size):
    """개체를 세워서 잘라 낸 축소본. 장축이 세로가 된다.

    한 번의 affine 변환으로 회전과 자르기를 함께 한다 — 잘라서 돌리면 모서리가
    비고 두 번 보간하게 된다. 회전 규약은 data.rotated_extent() 와 같아야 한다
    (같은 회전행렬을 쓰고, PIL 에는 그 역변환을 넘긴다).
    """
    from PIL import Image

    x, y, w, h = box
    # out 은 여백까지 포함한 최종 크기다(data.crop_geometry 가 정한다) — 여기서
    # 여백을 더하면 몇 µm 폭인지 알 수 없어 스케일바를 그릴 수 없다.
    ow, oh = size

    stat = path.stat()
    key = f"up|{path}|{stat.st_mtime_ns}|{x},{y},{w},{h}|{rot:.2f}|{ow}x{oh}|{width}"
    name = hashlib.sha1(key.encode()).hexdigest()[:20] + ".jpg"
    cache_dir = settings.THUMB_CACHE
    out = cache_dir / name
    if out.exists():
        return out

    rad = math.radians(rot)
    cos, sin = math.cos(rad), math.sin(rad)
    scx, scy = x + w / 2.0, y + h / 2.0        # 원본에서 개체 중심
    ocx, ocy = ow / 2.0, oh / 2.0              # 결과에서의 중심

    # PIL 의 AFFINE 은 결과 -> 원본 사상을 받는다. 회전의 역행렬이다.
    a1, b1 = cos, sin
    d1, e1 = -sin, cos
    c1 = scx - (a1 * ocx + b1 * ocy)
    f1 = scy - (d1 * ocx + e1 * ocy)

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as img:
            img = img.convert("RGB")
            piece = img.transform((ow, oh), Image.AFFINE, (a1, b1, c1, d1, e1, f1),
                                  resample=Image.BICUBIC)
            piece.thumbnail((width, width), Image.LANCZOS)
            tmp = out.with_suffix(".tmp")
            piece.save(tmp, "JPEG", quality=84)
            tmp.replace(out)
    except OSError:
        return None
    return out


def _jpeg(request, path):
    """JPEG 응답. v= (원본 mtime) 가 붙은 주소면 영구 캐시를 허용한다.

    주소에 mtime 이 들어 있으므로 그림이 바뀌면 주소가 바뀐다 — 옛 그림을
    붙잡고 있을 수가 없다. v= 없이 들어온 주소는 캐시를 막는다.
    """
    resp = FileResponse(path.open("rb"), content_type="image/jpeg")
    if request.GET.get("v"):
        resp["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        resp["Cache-Control"] = "no-cache"
    return resp


def _crop_thumb(path, box, width, pad=None):
    """잘라낸 축소본 경로. 원본 mtime 이 바뀌면 자동으로 다시 만든다."""
    from PIL import Image

    x, y, w, h = box
    stat = path.stat()
    key = f"crop|{path}|{stat.st_mtime_ns}|{x},{y},{w},{h}|{width}|{pad}"
    name = hashlib.sha1(key.encode()).hexdigest()[:20] + ".jpg"
    cache_dir = settings.THUMB_CACHE
    out = cache_dir / name
    if out.exists():
        return out

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as img:
            img = img.convert("RGB")
            # 개체가 테두리에 딱 붙으면 형태를 판단하기 어렵다. 조금 넓게 잡는다.
            if pad is None:
                pad = max(4, round(0.08 * max(w, h)))
            left = max(0, x - pad)
            top = max(0, y - pad)
            right = min(img.width, x + w + pad)
            bottom = min(img.height, y + h + pad)
            if right <= left or bottom <= top:
                return None
            piece = img.crop((left, top, right, bottom))
            # 가로세로 어느 쪽도 width 를 넘지 않게 — 봉상은 아주 납작하다.
            piece.thumbnail((width, width), Image.LANCZOS)
            tmp = out.with_suffix(".tmp")
            piece.save(tmp, "JPEG", quality=84)
            tmp.replace(out)
    except OSError:
        return None
    return out


def threshold_page(request, slug=None):
    """문턱 조정 화면.

    한 시야를 보며 정한 값이 124개 시야 전부에 걸린다. 그 영향을 눈으로 볼 수
    없으면 적용하고 나서 시야를 하나씩 확인해야 한다 — 그래서 이 화면은 **영향받는
    시야를 영향 큰 순으로** 늘어놓는다. 영향 없는 시야는 볼 이유가 없다.
    """
    # 이름만 있으면 된다. dataset_detail() 은 시야를 전부 훑어 0.46초가 든다.
    label = data.slide_label(slug) if slug else None
    if slug and label is None:
        raise Http404(f"unknown dataset: {slug}")
    # 배율이 다르면 텍스처 문턱을 같이 걸 수 없다 (devlog 013). 전역 적용 화면에서
    # 미리 알린다 — 적용하고 나서 한쪽이 무너진 것을 발견하면 되돌리기가 번거롭다.
    scales = data.scales_by_slide()
    return render(request, "viewer/thresholds.html", {
        "slug": slug or "",
        "label": label or "전체",
        "fields": THRESHOLD_FIELDS,
        "current": th.current_values(slug),
        "defaults": dict(judge.DEFAULTS),
        "presets": list(ThresholdSet.objects.values(
            "id", "name", *judge.FIELDS)),
        "spread": th.threshold_spread(slug),
        "scale_mixed": len(set(scales.values())) > 1,
        "scale_list": " · ".join(f"{s} {v:g}" for s, v in sorted(scales.items())),
    })


@require_POST
def threshold_preview(request):
    """문턱을 받아 전체 영향과 시야별 뒤집힘을 돌려준다. 저장하지 않는다."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("bad json")

    slug = payload.get("slug") or None
    try:
        values = th.clean_values(payload.get("values") or {},
                                 th.current_values(slug))
    except ValueError as e:
        return HttpResponseBadRequest(f"bad threshold: {e}")

    pool = th.load_pool(slug)
    result = th.preview(values, pool)
    index = th.detection_index(slug)

    # 영향 큰 순으로 — 볼 것이 위에 오게 한다
    rows = []
    for did, r in result["per_det"].items():
        meta = index.get(did)
        if not meta:
            continue
        flips = len(r["added"]) + len(r["removed"])
        rows.append({**meta, "before": r["before"], "after": r["after"],
                     "added": r["added"], "removed": r["removed"],
                     "flips": flips})
    rows.sort(key=lambda x: (-x["flips"], x["slug"], x["gid"]))

    # 무엇을 보여줄지는 **서버가 정한다.** 영향 큰 순으로 잘라 보낸 뒤 클라이언트가
    # 또 거르면, 잘린 것이 이미 전부 "영향받는 것" 이라 필터가 헛돈다 — 반대로
    # 영향이 없을 때는 켜는 순간 화면이 텅 빈다.
    touched = [r for r in rows if r["flips"]]
    only_touched = bool(payload.get("only_touched", True))
    limit = max(1, min(int(payload.get("limit") or 24), 200))

    if only_touched:
        shown = touched[:limit]
    else:
        # 끄면 영향 없는 시야도 섞여야 뜻이 통한다 — 영향받는 것이 24개를 넘으면
        # 그것만으로 화면이 차서 켠 것과 구분이 안 된다. 절반은 영향 순으로,
        # 나머지는 시야 순으로 채운다.
        head = touched[:max(1, limit // 2)]
        seen = {r["detection_id"] for r in head}
        rest = sorted((r for r in rows if r["detection_id"] not in seen),
                      key=lambda x: (x["slug"], x["gid"]))
        shown = head + rest[:limit - len(head)]
    verdicts = {r["detection_id"]: result["per_det"][r["detection_id"]]["verdict"]
                for r in shown}

    return JsonResponse({
        "ok": True,
        "values": values,
        "total": result["total"],
        # preview 가 낸 판정을 다시 세기만 한다 — 두 번 판정하지 않는다
        "classes": th.class_counts_from(result["per_det"]),
        "rows": shown,
        "n_rows": len(rows),
        "n_touched": len(touched),
        "only_touched": only_touched,
        "verdicts": verdicts,
    })


@require_POST
def threshold_apply(request):
    """미리보기와 같은 판정을 실제로 저장한다."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("bad json")

    slug = payload.get("slug") or None
    try:
        values = th.clean_values(payload.get("values") or {},
                                 th.current_values(slug))
    except ValueError as e:
        return HttpResponseBadRequest(f"bad threshold: {e}")

    run = Run.objects.create(kind="refilter", status="running",
                             params={"values": values, "slide": slug or "*",
                                     "via": "viewer"})
    try:
        out = th.apply_values(values, slug, run)
    except Exception as e:                       # noqa: BLE001
        run.status = "failed"
        run.error = str(e)
        run.finished_at = timezone.now()
        run.save()
        raise
    run.status = "done"
    run.finished_at = timezone.now()
    run.save()
    return JsonResponse({"ok": True, "run": run.pk, **out})


def threshold_masks(request):
    """시야 하나의 폴리곤. 슬라이더를 움직일 때마다 다시 받지 않게 따로 둔다.

    폴리곤은 시야당 29 KB 로 무겁지만 문턱과 무관하다 — 한 번 받아 두고, 이후에는
    판정(mask_key -> cls)만 갈아 끼우면 색이 바뀐다.
    """
    try:
        det_id = int(request.GET.get("det", ""))
    except ValueError:
        return HttpResponseBadRequest("bad det")
    det = Detection.objects.filter(pk=det_id, is_current=True).first()
    if det is None:
        raise Http404("unknown detection")
    masks = []
    for c in det.candidates.all():
        pts = data.mask_points({"polygon": c.polygon})
        if pts:
            masks.append({"k": c.mask_key, "p": pts})
    resp = JsonResponse({"ok": True, "masks": masks})
    # 폴리곤은 검출이 바뀌지 않는 한 그대로다
    resp["Cache-Control"] = "private, max-age=300"
    return resp


def threshold_history(request, slug=None):
    """문턱을 언제 무엇으로 바꿨나. 되돌리기의 근거가 된다."""
    runs = (Run.objects.filter(kind="refilter", status="done")
            .order_by("-started_at")[:50])
    rows = []
    for r in runs:
        v = (r.params or {}).get("values") or (r.params or {}).get("overrides") or {}
        # 웹은 슬라이더 11개를 통째로 보내므로 그대로 보여주면 무엇을 바꿨는지
        # 안 보인다. 기본값과 다른 것만 추린다 — 불러오기는 전체 값을 쓴다.
        changed = {k: val for k, val in v.items()
                   if abs(float(val) - judge.DEFAULTS.get(k, val)) > 1e-9}
        rows.append({
            "id": r.pk,
            "at": r.started_at.strftime("%m-%d %H:%M"),
            "slide": (r.params or {}).get("slide", "*"),
            "via": (r.params or {}).get("via", "cli"),
            "values": v,          # 불러올 때 쓴다
            "changed": changed,   # 화면에 보여줄 것
            "counts": r.counts or {},
        })
    return JsonResponse({"ok": True, "rows": rows})


def api_dataset(request, slug):
    ctx = data.dataset_detail(slug)
    if ctx is None:
        raise Http404(f"unknown dataset: {slug}")
    return JsonResponse(ctx)


def image(request):
    """
    ?p=<DATA_ROOT 기준 상대경로>&w=<가로 픽셀>

    폴더명에 공백이 있어서 경로를 URL 세그먼트가 아니라 쿼리로 받는다.
    w 가 있으면 축소본을 만들어 캐시한다. 원본이 2752x2208 이라
    그리드에 원본을 그대로 물리면 페이지가 못 쓸 정도로 무거워진다.
    """
    rel = request.GET.get("p", "")
    path = data.safe_image_path(rel)
    if path is None:
        raise Http404("image not found or outside allowed dirs")

    raw = request.GET.get("w")
    if not raw:
        return _jpeg(request, path)

    try:
        width = max(32, min(int(raw), 2048))
    except ValueError:
        raise Http404("bad width")

    thumb = _thumbnail(path, width)
    if thumb is None:
        return _jpeg(request, path)
    return _jpeg(request, thumb)


def _thumbnail(path, width):
    """축소본 경로를 돌려준다. 원본 mtime 이 바뀌면 자동으로 다시 만든다."""
    from PIL import Image

    stat = path.stat()
    key = f"{path}|{stat.st_mtime_ns}|{width}"
    name = hashlib.sha1(key.encode()).hexdigest()[:20] + ".jpg"
    cache_dir = settings.THUMB_CACHE
    out = cache_dir / name
    if out.exists():
        return out

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > width:
                height = round(img.height * width / img.width)
                img = img.resize((width, height), Image.LANCZOS)
            tmp = out.with_suffix(".tmp")
            img.save(tmp, "JPEG", quality=82)
            tmp.replace(out)
    except OSError:
        return None
    return out


@require_POST
def save_review(request):
    """
    교정 결과를 저장한다.

        {"stem": ..., "done": bool, "removed": [key], "accepted": [key],
         "labels": {key: "round"|"round_frag"|"rod"|"rod_frag"},
         "notes":  {key: "사람이 적은 메모"}}

    키는 bbox 에서 만든 것이라 검출을 다시 돌려도 같은 마스크면 그대로 붙는다.
    문턱만 바꾸는 refilter.py 실행에는 영향받지 않는다. 저장 위치는 DB 이고
    (예전에는 review/<stem>_review.json), git 에 남길 감사 기록은
    export_review.py 가 내보낸다.

    labels 는 자동 판정을 사람이 덮어쓴 것이다 — 조각난 규조각이 봉상/원형으로
    잘못 분류되는 것을 손으로 고치는 수단이고, 학습 데이터의 정답이 된다.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("bad json")

    stem = str(payload.get("stem", ""))
    if not SAFE_STEM.match(stem):
        return HttpResponseBadRequest("bad stem")

    # 자동 처리가 끝나기 전에는 저장을 받지 않는다 (P01 §1).
    # 반쯤 처리된 슬라이드를 검토하면 아직 안 돌아간 시야의 검출이 뒤늦게
    # 들어오면서 이미 본 화면이 바뀐다. 최상위 폴더 하나를 단위로 열고 닫는다.
    blocked = data.review_blocked(stem)
    if blocked:
        return JsonResponse({"ok": False, "error": blocked}, status=409)

    def keys(name):
        v = payload.get(name) or []
        if not isinstance(v, list):
            raise ValueError(name)
        return sorted({str(k) for k in v if isinstance(k, (str, int))})

    try:
        removed, accepted = keys("removed"), keys("accepted")
    except ValueError:
        return HttpResponseBadRequest("bad keys")

    # 검토 완료 표시. 교정이 하나도 없어도(고칠 것이 없어서) 켜질 수 있으므로
    # 삭제·복구 목록과 독립적으로 저장한다.
    done = bool(payload.get("done"))

    def mapping(name, clean):
        v = payload.get(name) or {}
        if not isinstance(v, dict):
            raise ValueError(name)
        out = {}
        for k, raw in v.items():
            k = str(k)
            if not data.CAND_KEY.match(k):
                raise ValueError(name)
            val = clean(raw)
            if val is not None:
                out[k] = val
        return dict(sorted(out.items()))

    def as_label(v):
        return str(v) if v in data.CLASSES else None

    def as_note(v):
        if not isinstance(v, str):
            return None
        # 줄바꿈은 남기고 앞뒤 공백만 정리한다. 빈 메모는 저장하지 않는다.
        text = v.replace("\r\n", "\n").strip()[:NOTE_MAX]
        return text or None

    try:
        labels = mapping("labels", as_label)
        notes = mapping("notes", as_note)
    except ValueError:
        return HttpResponseBadRequest("bad labels/notes")

    # 시야 전체에 대한 메모. 개체에 붙지 않는 이야기(촬영 상태, 판정이 애매한
    # 이유 등)를 적을 곳이 있어야 한다.
    note = as_note(payload.get("note")) or ""
    if not isinstance(payload.get("note", ""), (str, type(None))):
        return HttpResponseBadRequest("bad note")

    try:
        saved = data.save_review(stem, done=done, note=note, removed=removed,
                                 accepted=accepted, labels=labels, notes=notes)
    except ValueError as e:
        # 현재 검출에 없는 키가 섞여 왔다. 아무것도 바꾸지 않고 돌려보낸다 —
        # 그대로 두면 그 시야의 교정이 통째로 지워진다 (data.save_review 주석).
        return JsonResponse({"ok": False, "error": str(e)}, status=409)
    if saved is None:
        return HttpResponseBadRequest("unknown stem")
    return JsonResponse({"ok": True, "done": done, "note": bool(note), **saved})


# /healthz 가 "자료가 있다" 고 볼 표. 없으면 이 뷰어는 볼 것이 없는 상태다.
HEALTH_TABLES = (("slide", Slide), ("viewpoint", Viewpoint),
                 ("detection", Detection), ("objectreview", ObjectReview))


def healthz(request):
    """판·DB·안전망 상태를 한 번에 낸다 (`.guides/web/operations.md` §4).

    ## 세 상태, 그리고 degraded 가 200 인 이유

    | 상태 | 코드 | 뜻 |
    |---|---|---|
    | `ok` | 200 | 정상 |
    | `degraded` | **200** | 서비스는 되는데 손상이 감지됐다 (백업 깃발 등) |
    | `unhealthy` | 503 | DB 를 못 열거나 자료가 통째로 없다 |

    **`degraded` 를 503 으로 두면 안 된다.** 두 가지가 깨진다. 하나는 503 이
    "여기로 보내지 말라" 는 교통 신호라, 재시작으로 안 고쳐질 상태에 대고 앞단이
    호스트를 빼거나 계속 돌리게 된다. 다른 하나가 더 실질적이다 — `deploy.sh` 의
    기동 게이트가 **200 을 기다린다**(deployment.md §5). degraded 에 503 을 내면
    "백업이 깨졌다" 는 신호가 배포 자체를 못 끝내게 만든다. 배포를 막는 일은
    `smoke.sh` 가 `status != ok` 로 하고, 이쪽은 살아 있다고만 답한다.

    ## 가볍게 유지한다

    인증이 없는 엔드포인트다. 여기서 `integrity_check` 나 전체 훑기를 돌리면
    누구나 부를 수 있는 DoS 표면이 된다. **비싼 검사는 백업이 한 번 하고**
    (`backup_db.py`), 여기서는 그것이 남긴 깃발 파일을 읽기만 한다
    (data-safety.md §2). 나머지는 `count(*)` 넷과 `stat` 하나다.

    ## 빈 DB 함정

    `slide` 가 0 이면 **unhealthy** 다. 마운트가 어긋나 컨테이너가 빈 DB 를 새로
    만들어도 "파일이 있는가" 검사는 통과한다 — `rows > 0` 만이 그것을 잡는다
    (data-safety.md §8). 그래서 배포 게이트가 여기서 걸리는 편이 맞다.
    """
    info = {"status": "ok", "version": os.environ.get("IMAGE_TAG", "")}
    notes = []

    # 1) DB — 연결과 행 수. 못 열면 나머지는 볼 것도 없다.
    try:
        info["db"] = {name: model.objects.count() for name, model in HEALTH_TABLES}
    except Exception as e:                       # noqa: BLE001 — 무엇이 나오든 죽지 않는다
        info["status"] = "unhealthy"
        info["db"] = None
        notes.append(f"DB 를 읽지 못했다: {e}")
    else:
        if info["db"]["slide"] == 0:
            info["status"] = "unhealthy"
            notes.append("슬라이드가 0 이다 — DB 마운트가 어긋났을 수 있다")

    # 2) 백업이 세운 무결성 깃발. 파일을 읽기만 한다.
    flags = db_sentinel.read(settings.DIATOM_DB)
    info["integrity_flags"] = flags
    if flags and info["status"] == "ok":
        info["status"] = "degraded"
    for f in flags:
        notes.append(f"백업 실패 깃발 [{f['source']} {f['time']}] {f['reason']}")

    # 3) 백업 신선도. 문턱을 안 주면 알려만 준다 (settings.BACKUP_MAX_AGE_H 주석).
    age_h = None
    try:
        snaps = list(settings.BACKUP_DIR.glob("diatom_*.db"))
        if snaps:
            newest = max(snaps, key=lambda p: p.stat().st_mtime)
            age_h = round((time.time() - newest.stat().st_mtime) / 3600, 1)
    except OSError:
        pass
    info["backup"] = {"age_h": age_h, "max_age_h": settings.BACKUP_MAX_AGE_H}
    if settings.BACKUP_MAX_AGE_H and (age_h is None
                                      or age_h > settings.BACKUP_MAX_AGE_H):
        if info["status"] == "ok":
            info["status"] = "degraded"
        notes.append("백업 사본이 없다" if age_h is None else
                     f"백업이 낡았다 — 가장 새 사본이 {age_h} 시간 전 "
                     f"(문턱 {settings.BACKUP_MAX_AGE_H})")

    info["notes"] = notes
    code = 503 if info["status"] == "unhealthy" else 200
    resp = JsonResponse(info, status=code, json_dumps_params={"ensure_ascii": False})
    # 앞단이나 브라우저가 이 답을 캐시하면 지난 상태를 보고 판단하게 된다
    resp["Cache-Control"] = "no-store"
    return resp
