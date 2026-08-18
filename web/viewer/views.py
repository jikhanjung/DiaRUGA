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
from django.db.models import Count
from django.http import (FileResponse, Http404, HttpResponse,
                         HttpResponseBadRequest, JsonResponse)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import (antarctica, atlas as atlas_mod, data, korea,
               manage_data, outcrop, regroup, thresholds as th)
from .models import (Candidate, Detection, DiatomObject,  # noqa: E501
                     Image as ImageModel,
                     Locality,
                     ObjectReview, Run,
                     Sample, Site,
                     Slide, ThresholdSet, Viewpoint)

import sys
from pathlib import Path
# **뷰어가 저장소의 스크립트 둘을 함께 쓴다** (100 에서 자리를 옮겼다).
#
# - `pipeline/judge.py` — 판정 규칙. 뷰어와 파이프라인이 **같은 것**을 봐야
#   한다: 규칙이 둘이면 화면과 검출이 다른 말을 한다
# - `ops/db_sentinel.py` — 무결성 깃발. `/healthz` 가 그것을 읽는다
#
# 저장소 뿌리는 `web/viewer` 의 두 단계 위다. **컨테이너 안에서도 같다** —
# 이미지가 저장소를 통째로 `/app` 에 담으므로 `/app/pipeline`·`/app/ops` 다.
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "pipeline"))
sys.path.insert(0, str(_ROOT / "ops"))
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


def _with_hidden(request) -> bool:
    """숨긴 슬라이드를 보이는가. `?hidden=1`.

    **화면이 아니라 서버가 거른다** — 권역 갈래와 같은 이유다(`index.html` 머리말).
    표·카드·지도가 같은 목록을 봐야 하고, 코어 묶음의 "N장" 도 그것으로 센다.
    화면에서 줄만 감추면 셋이 서로 다른 것을 보게 된다.

    **합계는 이 값을 안 본다** — `datasets_total()` 머리말.
    """
    return request.GET.get("hidden") == "1"


def index(request):
    # 권역(한국·남극)은 `?area=` 로 고른다. 고르는 일을 data.area_tabs() 에 맡겨
    # 없는 값이 들어와도 빈 화면이 되지 않게 한다.
    area = data.area_tabs(request.GET.get("area"))
    with_hidden = _with_hidden(request)
    rows = data.datasets(area["selected"])
    shown = [r for r in rows if with_hidden or not r["hidden"]]
    # **"전체" 에는 지도가 없다.** 투영이 권역마다 다르므로(남극 EPSG:3031 ·
    # 한국 EPSG:5179) 섞인 것을 한 지도에 올릴 수가 없다. 억지로 하나를 고르면
    # 다른 권역의 시료가 조용히 빠지거나 엉뚱한 자리에 찍힌다.
    show_map = not area["is_all"]
    return render(request, "viewer/index.html", {
        # **보이는 것만.** 합계 줄의 "N장" 이 이것으로 센다 — 화면에 없는 장을
        # 세면 줄을 세어 봐도 안 맞는다.
        "datasets": shown,
        # 표·카드 둘 다 코어로 묶어 낸다. 코어가 분석의 단위이고(깊이에 따른
        # 변화가 목적이다) 슬라이드가 늘수록 평평한 목록은 못 읽는다.
        "groups": data.datasets_by_locality(rows, with_hidden),
        "area": area,
        "show_map": show_map,
        # **합계만은 숨긴 것까지 센다** — 토글이 숫자를 흔들면 안 된다.
        # 어긋남은 `n_hidden_in` 으로 화면이 적는다.
        "totals": data.datasets_total(rows),
        "with_hidden": with_hidden,
        # **켜 놓았을 때도 실제 숨김 수를 센다** (`len(rows) - len(shown)` 이
        # 아니다 — 그러면 켠 순간 0 이 되어 몇 장이 숨겨진 것인지 사라진다).
        "n_hidden": sum(1 for r in rows if r["hidden"]),
        # 표의 분류 열. 줄이 아니라 여기서 정한다 — 슬라이드마다 0인 분류를
        # 빼면 열 수가 달라져 세로로 안 맞는다.
        "count_classes": data.counted_classes(),
        # **표의 "검출" 칸이 어느 묶음의 것인가** (088). 이 목록의 숫자는 전부
        # 검토 대상 묶음에서 나온다(`_kept_masks`·`datasets` 가 `reviewing()` 을
        # 지난다) — 묶음을 갈면 통째로 달라지므로 화면이 그것을 말해야 한다.
        # `dataset_detail`·`group_detail` 은 이미 같은 값을 담고 있다.
        "review_batch": data.review_batch_label(),
        # 지도는 세 번째 보기 방식이다. 해안선이 10~27 KB 뿐이라 늘 함께 보낸다 —
        # 따로 요청하게 만들면 전환이 즉시 되지 않는다.
        "antmap": (_map_ctx(area["selected"],
                            data.map_points(area["selected"], with_hidden))
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


def system_settings_ops(request):
    """관리 · 운영 — 검토할 묶음과 조리법 (083).

    **자료 화면과 갈라 둔다.** 묻는 것이 다르다: 저쪽은 "이 관찰이 어느 지점의
    것인가"(새 슬라이드가 들어올 때), 이쪽은 "지금 무엇을 보고 있고 새 자료를
    어떻게 채우는가"(회차를 돌릴 때). 한 화면에 있으면 자주 쓰는 것이 드물게
    쓰는 것에 묻힌다 — 실제로 층 편집표 셋 아래에 묶음 고르기가 있었다.
    """
    if request.method == "POST":
        p = request.POST
        act = (p.get("act") or "").strip()
        if act == "review_batch":
            ok, m = manage_data.set_review_batch(_num(p.get("batch"), int) or 0)
        elif act == "recipe":
            ok, m = manage_data.set_recipe(_num(p.get("batch"), int) or 0, p)
        elif act == "new_batch":
            ok, m = manage_data.create_batch(p)
        else:
            ok, m = False, "모르는 동작입니다."
        return redirect(f"{reverse('system_settings_ops')}?{'msg' if ok else 'err'}={m}")

    plan = []
    for r in data.batches_to_run():
        plan.append({**r, "args": " ".join(_recipe_args(r["recipe"]))})
    return render(request, "viewer/system_settings_ops.html", {
        "msg": request.GET.get("msg", ""), "err": request.GET.get("err", ""),
        "batches": manage_data.batch_choices(),
        "batches_all": manage_data.batches_with_recipe(),
        "backends": manage_data.BACKENDS,
        "plan": plan,
    })


def _recipe_args(recipe: dict) -> list:
    """조리법을 명령줄 모양으로 — **화면이 보여줄 뿐 여기서 돌리지 않는다.**

    `batch_plan.py` 와 같은 것을 내야 한다. 그쪽이 폴러가 실제로 먹는 것이고,
    화면이 다른 것을 보여주면 사람이 화면을 믿고 틀린 명령을 만든다.
    """
    out = []
    for k, flag in (("backend", "--backend"), ("scale", "--scale"),
                    ("points_per_side", "--points-per-side"),
                    ("min_um", "--min-um"), ("max_um", "--max-um"),
                    ("weights", "--weights"), ("yolo_conf", "--yolo-conf"),
                    ("yolo_imgsz", "--yolo-imgsz")):
        if recipe.get(k) is not None:
            out += [flag, str(recipe[k])]
    if recipe.get("all_images"):
        out.append("--all-images")
    return out


def system_settings_pipeline(request):
    """시스템 설정 · 파이프라인 — 폴러가 살아 있는가, 무엇이 밀려 있는가 (098).

    097 이 이 화면의 값을 증명했다: 폴러 3단계가 사흘을 조용히 죽어 있었는데
    멈춘 것을 알려 주는 자리가 없었다. 값 셋 — 마지막 정찰(정찰 파일의 나이) ·
    마지막 실행(Run) · 끝나지 않은 슬라이드와 그 진행. 해석은 화면이 먼저
    한다(경고 줄) — 사람이 숫자를 조합해서 알아내게 두지 않는다.
    """
    return render(request, "viewer/system_settings_pipeline.html",
                  {"p": data.pipeline_status()})


def system_settings_dataset(request):
    """관리 · 학습 자료 — 검토가 끝난 결과에서 **정답을 뽑는** 자리 (083).

    **가중치를 만드는 화면이 아니다.** 학습은 그다음 별도의 일이고, 이 구분이
    흐려지면 "학습이 왜 안 좋지" 를 자료 문제와 학습 문제로 가를 수 없다.
    """
    t = manage_data.training_overview()
    return render(request, "viewer/system_settings_dataset.html", {
        "t": t,
        # 내보낼 곳 이름을 제안한다 — 회차마다 새 이름이어야 덮어쓰지 않는다
        "suggest": timezone.now().strftime("%y%m%d"),
    })


def dataset(request, slug):
    ctx = data.dataset_detail(slug)
    if ctx is None:
        raise Http404(f"unknown dataset: {slug}")
    # 방금 무엇을 했는지. 바뀐 수를 주소에 실어 새로고침해도 남게 한다 —
    # POST 뒤에 redirect 하므로(뒤로 가기가 다시 쓰지 않게) 이 길밖에 없다.
    ctx["marked"] = request.GET.get("marked") or ""
    ctx["marked_n"] = request.GET.get("n") or ""
    return render(request, "viewer/dataset.html", ctx)


@require_POST
def mark_all(request, slug):
    """시야 전체를 검토 완료로 / 미검토로. **POST 로만 온다.**

    GET 으로 열어 두면 주소를 누르는 것만으로 508 시야의 판단이 뒤집힌다 —
    브라우저의 미리 가져오기나 링크 검사기도 그것을 누른다.

    `done` 깃발만 뒤집고 시야 코멘트·개체 교정은 안 건드린다
    (`data.mark_all_reviewed` 머리말).
    """
    want = (request.POST.get("act") or "").strip()
    if want not in ("done", "undone"):
        raise Http404("unknown act")

    # 자동 처리가 안 끝났으면 검토를 막는 규칙이 여기에도 걸린다 (P01 §1) —
    # 한 시야씩은 막아 놓고 전체 표시로는 뚫리면 막은 뜻이 없다.
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        raise Http404(f"unknown dataset: {slug}")
    if data.review_blocked(slide):
        return redirect(f"{reverse('dataset', args=[slug])}?marked=blocked")

    out = data.mark_all_reviewed(slug, done=(want == "done"))
    if out is None:
        raise Http404(f"unknown dataset: {slug}")
    return redirect(f"{reverse('dataset', args=[slug])}"
                    f"?marked={want}&n={out['changed']}")


def core_redirect(request, site_code, core_code):
    """옛 `/core/…` 주소를 새 `/loc/…` 로 보낸다.

    **301 이 아니라 302 다.** 영구 리다이렉트는 브라우저가 캐시해서, 나중에
    주소 규칙을 다시 손볼 때 되돌릴 방법이 없다.
    """
    return redirect("core", site_code=site_code, core_code=core_code)


def settings_redirect(request, tab=""):
    """옛 `/manage/…` 주소를 새 `/settings/…` 로 보낸다.

    시스템 설정이 데이터셋 목록과 같은 층의 최상위 메뉴가 되면서 주소를
    `/system-settings/` 로 옮겼다 (2026-08-08). **옛 주소를 지우지 않는다** —
    사내에 이미 퍼진 링크와 브라우저 기록이 조용히 깨진다. `core/` → `loc/`
    때와 같은 갈래다.

    **302 다.** 영구 리다이렉트는 브라우저가 캐시해서, 나중에 주소 규칙을 다시
    손볼 때 되돌릴 방법이 없다.

    쿼리스트링을 그대로 넘긴다 — 저장 뒤 `?msg=…` 로 돌아오는 길이 있고,
    옛 주소를 북마크한 사람이 그 메시지를 잃으면 "저장이 됐나" 를 묻게 된다.
    """
    name = {"ops": "system_settings_ops",
            "dataset": "system_settings_dataset"}.get(tab, "system_settings")
    url = reverse(name)
    if request.META.get("QUERY_STRING"):
        url = f"{url}?{request.META['QUERY_STRING']}"
    return redirect(url)


def core_page(request, site_code, core_code):
    """지점 하나 — 위치 방향으로 본 화면. 근거는 `data.locality_detail()` 머리말.

    **읽기 전용이다.** 속성은 `/d/<slug>/edit/` 이 고친다 — 같은 `Locality`·
    `Site` 행에 쓰는 문을 둘로 만들지 않는다.
    """
    with_hidden = _with_hidden(request)
    ctx = data.locality_detail(site_code, core_code, with_hidden)
    if ctx is None:
        raise Http404(f"unknown locality: {site_code}/{core_code}")
    return render(request, "viewer/core.html", {
        **ctx, "with_hidden": with_hidden,
        # 사진을 올리거나 지운 뒤 여기로 돌아온다 (POST → redirect)
        "msg": request.GET.get("msg", ""), "err": request.GET.get("err", ""),
        "max_photos": outcrop.MAX_PHOTOS,
    })


def _highlight_arg(request):
    """링크가 짚어 온 개체 — `?obj=<mask_key>&img=<이미지>` (118).

    카탈로그·크롭·계측 표에서 사진을 누르면 그 시야로 오는데, **거기 개체가
    수십 개라 어느 것을 보고 눌렀는지 다시 찾아야 했다** (사용자 보고
    2026-08-13). 링크가 개체와 그 개체가 있는 판을 함께 나르고 화면이 그 자리를
    표시한다.

    **`img` 가 함께 가야 한다.** 시야 하나에 판이 여럿이고(합성본 + 프레임마다
    하나) 교정도 판마다 따로다 — 키만 보내면 화면은 지금 열린 판에서만 찾고,
    프레임에서 잡힌 개체는 "못 찾았다" 가 된다.

    **서버는 그 값이 실제로 있는지 안 본다.** 어느 판에 무엇이 있는지는 화면이
    이미 들고 있고(`shot_dets`), 못 찾으면 화면이 그렇게 적는다. 여기서 404 를
    내면 **적어 둔 링크 하나가 낡았다는 이유로 시야 전체를 못 열게 된다** —
    표시는 곁들이는 것이지 이 화면이 서는 조건이 아니다.
    """
    key = (request.GET.get("obj") or "").strip()
    # 64 는 `ReviewMark.mask_key` 의 폭이다. 그보다 긴 것은 이 DB 에 있을 수
    # 없는 값이라 찾을 것도 없다.
    if not key or len(key) > 64:
        return None
    img = (request.GET.get("img") or "").strip()
    return {"key": key, "image": img if img.isdigit() else ""}


def group(request, slug, gid):
    """검토 화면. `?batch=<실행 번호>` 로 **엔진을 갈아 끼운다** (051).

    검출 엔진 고르기는 `/engine/` 이라는 다른 화면에만 있던 기능이다. 비교하려면
    화면을 나갔다 들어와야 했고, 그때마다 어느 시야를 보고 있었는지 잃었다. 이제
    검토 화면 안에서 고른다 — 시야는 그대로 두고 그림 위의 개체만 바뀐다.
    **그 화면은 075 에서 지웠다. 비교는 이 길 하나로만 한다.**

    **현재 검출(SAM2)일 때만 교정이 저장된다.** 다른 묶음을 고르면 읽기 전용이고
    화면 가운데 위에 그렇게 적힌다. 근거는 `data.group_detail` 머리말.
    """
    # 이 시야에 쌓인 묶음들. 검토 화면이 그리는 현재 검출도 그중 하나로 나온다.
    raw = (request.GET.get("batch") or "").strip()
    try:
        run_id = int(raw) if raw else None
    except ValueError:
        run_id = None

    bs = data.batches_for_viewpoint(slug, gid, run_id)
    picked = next((b for b in bs if b["on"]), None) if run_id else None
    # 모르는 묶음이거나, 지금 검토 화면이 이미 그리고 있는 그것이면 제 주소로
    # 돌려보낸다. **읽기 전용 화면으로 현재 검출을 보게 두면 안 된다** — 같은
    # 것을 교정만 뗀 채 보게 되고, 거기서 고친 것은 저장되지 않는다.
    if run_id is not None and (picked is None or picked["current"]):
        return redirect("group", slug=slug, gid=gid)

    ctx = data.group_detail(slug, gid, run_id)
    if ctx is None:
        raise Http404(f"unknown group: {slug}/{gid}")

    # **묶음이 아니라 엔진으로 고른다.** `yolo-1차`·`yolo-3차` 가 따로 서면
    # 무엇을 눌러야 할지 알 수 없다 — 재는 것은 엔진이다 (`engines_from_batches`).
    here = reverse("group", args=[slug, gid])
    engines = data.engines_from_batches(bs)
    for e in engines:
        # 현재 검출을 낸 엔진이 곧 검토 가능한 화면이다 — 맨 주소로 간다.
        e["url"] = here if e["current"] else f"{here}?batch={e['run_id']}"
        e["editable"] = e["current"]
    ctx["engines"] = engines
    # 아무 것도 안 켜져 있으면(=?batch= 가 없으면) 현재 검출을 보고 있는 것이다
    ctx["engine_now"] = (next((e for e in engines if e["on"]), None) if run_id
                         else next((e for e in engines if e["current"]), None))
    # 링크가 짚어 온 개체 (118). 읽기 전용 갈래(`?batch=`)에도 그대로 얹는다 —
    # 표시는 보는 일이지 고치는 일이 아니다.
    ctx["hl"] = _highlight_arg(request)
    return render(request, "viewer/group.html", ctx)


@require_POST
def split_group(request, slug, gid):
    """시야를 프레임 경계에서 가른다. **두 걸음이다 — 미리보기 다음에 확인.**

    검토가 끝난 시야를 지우는 일이라(그 아래 검출·교정이 `CASCADE` 로 딸려 간다)
    한 번의 눌림으로 끝나면 안 된다. 첫 POST 는 **무엇이 사라지는지 보여 주기만**
    하고, `confirm=1` 이 실린 두 번째 POST 만 실제로 고친다.

    **읽기 전용(`?batch=`)에는 이 길이 없다.** 화면 조각을 `_detection.html`
    (읽기 전용과 공유한다)이 아니라 `group.html` 에만 두었고, 서버도 다시 막는다 —
    027 이 정확히 그 자리에서 났다: "읽기 전용" 이라 적어 놓고 CSS 로 버튼만
    감췄더니 한 번의 클릭이 교정 37건을 지웠다. **화면에서 감추는 것은 막는 것이
    아니다.**

    처리 중인 슬라이드도 막는다. 파이프라인이 쓰는 중에 시야를 지우면 SQLite 가
    잠기고(HANDOFF 3.8 — 그렇게 프레임 229장을 잃었다), 반쯤 처리된 상태 위에
    재분할을 얹으면 무엇이 옳은 상태인지 알 수 없게 된다.
    """
    slide = Slide.objects.filter(slug=slug).first()
    if slide is None:
        raise Http404(f"unknown dataset: {slug}")
    if data.review_blocked(slide):
        return HttpResponse("자동 처리가 끝나기 전에는 시야를 가를 수 없습니다.",
                            status=409)

    cuts = [c for c in request.POST.getlist("after") if c.strip()]
    ctx = {"slug": slug, "label": slide.name, "id": gid, "cuts": cuts,
           "back_url": reverse("group", args=[slug, gid])}

    if request.POST.get("confirm") == "1":
        try:
            r = regroup.apply_split(slide, cuts, source="viewer")
        except ValueError as e:
            ctx["preview"] = {"ok": False, "errors": [str(e)]}
            return render(request, "viewer/regroup_confirm.html", ctx,
                          status=400)
        # 방금 만든 첫 조각으로 보낸다 — 사람이 한 일을 눈으로 확인해야 한다.
        # 검출이 아직 없어 화면은 사진만 낸다 (stack.detection.preview_only).
        return redirect("group", slug=slug, gid=r["first_idx"])

    ctx["preview"] = regroup.preview(slide, cuts)
    return render(request, "viewer/regroup_confirm.html", ctx,
                  status=200 if ctx["preview"]["ok"] else 400)


def _num(raw, cast=float):
    """빈 칸은 None 으로. 잘못된 값은 예외를 올려 보낸다 — 조용히 0 이 되면 안 된다."""
    raw = (raw or "").strip()
    if not raw:
        return None
    return cast(raw)


def dataset_edit(request, slug):
    """관찰·시료·지점·지역의 속성을 사람이 채우는 화면. 층 넷을 한 폼으로 낸다.

    폴더 이름에서 뽑을 수 있는 것(지역·지점·시료 코드·위치)은 파이프라인이 채워
    두었고, 뽑을 수 없는 것(정식 명칭·좌표·수심·채취일)은 비어 있다. 코드만으로
    "RS = 로스해" 를 단정하지 않는다 — `models.Site` 머리말이 정한 방침이다.
    화면에서는 그것을 **추천으로만** 보여 주고 사람이 확인해 넣게 한다.

    **위 세 층은 여러 관찰이 공유한다.** 여기서 고치면 같은 시료의 다른 관찰,
    같은 지점의 다른 시료에도 반영되므로 몇 개가 함께 바뀌는지 미리 알린다.

    **소속이 없으면 붙이거나 만든다.** 폴더 이름이 규칙에 안 맞으면 파이프라인이
    아무것도 못 붙이는데(실제로 `BP09-0901` 이 그랬다), 여기서 만들 수 없으면
    영영 붙일 길이 없다 — 지역이 없는 관찰은 어느 권역 탭에도 안 나온다.
    """
    slide = (Slide.objects.filter(slug=slug)
             .select_related("sample__locality__site").first())
    if slide is None:
        raise Http404(f"unknown dataset: {slug}")
    sample = slide.sample
    loc = sample.locality if sample else None
    site = loc.site if loc else None

    # 이 관찰이 처음부터 들고 있던 소속인가. **폼의 시료·지점·지역 칸을 저장에
    # 쓸지 말지가 여기서 갈린다** — 화면은 이 시점의 값으로 그려지므로, 소속이
    # 없던 관찰의 탭은 **빈 칸**이다. 그 빈 칸을 남의 행에 그대로 쓰면 이미
    # 채워 둔 좌표·수심·해역이 지워지고, 그 행을 쓰는 관찰 전부가 함께 당한다.
    had = {"sample": sample is not None, "loc": loc is not None,
           "site": site is not None}

    errors, saved, messages_made = [], False, ""
    if request.method == "POST":
        p = request.POST
        made = {"sample": False, "loc": False, "site": False}

        # --- 1) 이미 있는 시료에 그대로 붙이는 길 -------------------------
        #
        # 코드를 세 칸에 다시 받아 적게 하는 것이 코드를 맞히기 놀이가 됐다 —
        # `BP09-0901 (1)` 을 붙이려고 시료 코드만 적으면 **아무 일도 안 일어나고
        # "저장했습니다" 가 떴다.** 골라서 붙이는 길을 따로 둔다.
        attach = (p.get("attach_sample") or "").strip()
        if sample is None and attach:
            sample = (Sample.objects.select_related("locality__site")
                      .filter(pk=attach).first())
            if sample is None:
                errors.append("고른 시료를 찾지 못했습니다.")
            else:
                loc, site = sample.locality, sample.locality.site

        # --- 2) 코드를 적어 새로 만드는 길 --------------------------------
        #
        # **같은 코드가 이미 있으면 그것에 붙인다.** 새로 만들면 unique 로 죽고,
        # 무엇보다 같은 지역·지점이 둘로 갈라진다.
        site_code = (p.get("site_code") or "").strip()
        loc_code = (p.get("core_code") or "").strip()
        sample_code = (p.get("sample_code") or "").strip()
        if sample is None and site is None and site_code:
            site = Site.objects.filter(code=site_code).first()
            if site is None:
                site, made["site"] = Site(code=site_code), True
        if sample is None and loc is None and loc_code and site is not None:
            loc = (Locality.objects.filter(site=site, code=loc_code).first()
                   if site.pk else None)
            if loc is None:
                loc, made["loc"] = Locality(site=site, code=loc_code), True
        if sample is None and sample_code and loc is not None:
            sample = (Sample.objects.filter(locality=loc, code=sample_code)
                      .first() if loc.pk else None)
            if sample is None:
                sample = Sample(locality=loc, code=sample_code)
                made["sample"] = True

        # 아래 칸만 적고 위를 비운 경우. 예전에는 조용히 통과했다 —
        # **아무것도 안 한 저장이 성공으로 보이면 사람이 같은 일을 다시 한다.**
        if sample is None and (sample_code or loc_code) and not attach:
            errors.append(
                "시료를 붙이려면 지역·지점·시료 코드를 모두 채워야 합니다 — "
                "위의 기존 시료에 붙이기 에서 고르는 쪽이 안전합니다.")

        own = {k: had[k] or made[k] for k in had}
        try:
            slide.name = (p.get("slide_name") or slide.name).strip()
            slide.description = (p.get("description") or "").strip()
            slide.um_per_pixel_override = _num(p.get("um_per_pixel_override"))
            # 관찰 이름표. **`obs_no` 는 여기서 못 고친다** — 폴더 접미사가
            # 정하는 자동값이라 사람이 고쳐 봐야 다음 반입에 덮인다.
            slide.obs_label = (p.get("obs_label") or "").strip()[:10]
            # 체크박스는 안 켜면 아무것도 안 보낸다 — 없는 것이 곧 꺼짐이다.
            slide.hide_in_list = bool(p.get("hide_in_list"))
            slide.exclude_from_totals = bool(p.get("exclude_from_totals"))

            # **붙이기만 할 때는 위 세 층의 칸을 안 쓴다** (`own`).
            if sample and own["sample"]:
                sample.code = (p.get("sample_code") or sample.code).strip()
                sample.note = (p.get("sample_note") or "").strip()
                # **지점 유형이 어느 칸을 쓸지 정한다.** 화면이 안 쓰는 칸을
                # 잠그면 브라우저가 값을 안 보내는데, 그것을 "비웠다" 로 읽으면
                # 유형을 잘못 골랐다 되돌릴 때 값이 이미 사라져 있다.
                kind = (p.get("locality_kind") or "").strip()
                kind = kind if kind in dict(Locality.KIND) else (
                    loc.kind if loc else "core")
                if kind == "outcrop":
                    sample.sample_no = _num(p.get("sample_no"), int)
                else:
                    sample.depth_cm = _num(p.get("depth_cm"))
            if loc and own["loc"]:
                loc.code = (p.get("core_code") or loc.code).strip()
                k = (p.get("locality_kind") or "").strip()
                if k in dict(Locality.KIND):
                    loc.kind = k
                loc.collect_kind = (p.get("core_kind") or "").strip()
                loc.lat = _num(p.get("core_lat"))
                loc.lon = _num(p.get("core_lon"))
                loc.water_depth_m = _num(p.get("core_water_depth"))
                d = (p.get("core_collected_at") or "").strip()
                loc.collected_at = date.fromisoformat(d) if d else None
                loc.note = (p.get("core_note") or "").strip()
            if site and own["site"]:
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
            # 넷을 한 덩어리로 저장한다. 아래만 바뀌고 위가 안 바뀌면 화면에
            # 보이는 것과 저장된 것이 어긋난다.
            try:
                attached = sample is not None and slide.sample_id != sample.pk
                with transaction.atomic():
                    if site and own["site"]:
                        site.save()
                    if loc and own["loc"]:
                        loc.site = site          # 새로 만든 지역이면 이제야 pk
                        loc.save()
                    if sample and own["sample"]:
                        sample.locality = loc
                        sample.save()
                    if attached:
                        slide.sample = sample
                    slide.save()
                saved = True
                new = " · ".join(x for x in (
                    f"지역 {site.code}" if made["site"] else "",
                    f"지점 {loc.code}" if made["loc"] else "",
                    f"시료 {sample.code}" if made["sample"] else "") if x)
                if new:
                    messages_made = f"{new} 을(를) 새로 만들어 붙였습니다."
                elif attached:
                    # **무엇에 붙었는지 적는다.** 고르는 화면이라 엉뚱한 시료를
                    # 골랐을 때 사람이 알아챌 자리가 여기밖에 없다.
                    messages_made = (f"{site.code} · {loc.code} · {sample.code} "
                                     f"시료에 붙였습니다.")
            except IntegrityError as e:
                errors.append(f"같은 코드가 이미 있습니다: {e}")

    # 붙일 수 있는 시료 목록. 이미 시료가 있으면 안 만든다 — 시료를 **옮기는**
    # 것은 다른 일이다(관리 화면이 맡는다).
    sample_choices, sibling = [], None
    if sample is None:
        for sm in (Sample.objects.select_related("locality__site")
                   .order_by("locality__site__code", "locality__code",
                             "depth_cm", "sample_no", "code")):
            sample_choices.append({
                "pk": sm.pk,
                "site_code": sm.locality.site.code,
                "loc_code": sm.locality.code,
                "code": sm.code,
                "label": sm.locality.site.region or sm.locality.site.name or "",
                "n_slides": sm.slides.count(),
            })
        # 같은 시료의 다른 관찰이 이미 어딘가 붙어 있으면 그것이 답이다.
        sibling = next((s for s in slide.sibling_observations() if s.sample_id),
                       None)

    scales = data.scales_by_slide()
    return render(request, "viewer/dataset_edit.html", {
        "slug": slug,
        "label": slide.name,
        "slide": slide,
        "sample": sample,
        "core": loc,
        "site": site,
        "locality_kinds": Locality.KIND,
        "sample_choices": sample_choices,
        "sibling": sibling,
        "sibling_sample_pk": sibling.sample_id if sibling else None,
        "core_code": loc.code if loc else "-",
        "site_code": site.code if site else "-",
        "sample_code": sample.code if sample else "-",
        "n_slides_sample": sample.slides.count() if sample and sample.pk else 0,
        "n_samples_loc": loc.samples.count() if loc and loc.pk else 0,
        "n_slides_site": (Slide.objects.filter(
            sample__locality__site=site).count() if site and site.pk else 0),
        "n_viewpoints": slide.viewpoints.count(),
        "n_frames": slide.frames.count(),
        "site_areas": Site.AREA,
        "um_per_pixel": scales.get(slug),
        "errors": errors,
        "saved": saved,
        "made": messages_made,
        # 아직 없는 층은 화면이 그렇게 말해야 한다 — 빈 칸만 보이면 "고치는 곳"
        # 으로 읽히지 "만드는 곳" 으로는 안 읽힌다.
        "no_site": site is None,
        "no_core": loc is None,
        "no_sample": sample is None,
    })



def system_settings(request):
    """관리 화면 — 지역·지점·시료를 만들고 고치고 지운다. 소속도 여기서 옮긴다.

    **관찰은 여기서 안 만들고 안 지운다.** 폴더가 만드는 것이고 그 아래에
    재생성 불가한 교정이 달려 있다 — 옮기고 떼는 것만 된다.

    **쓰기는 전부 POST 다.** GET 으로 열어 두면 주소를 누르는 것만으로 지워진다.
    지우기에는 문턱이 따로 있다 (`manage_data` 머리말).
    """
    msg, err = "", ""
    if request.method == "POST":
        p = request.POST
        act = (p.get("act") or "").strip()
        if act == "create":
            ok, m = manage_data.create((p.get("kind") or "").strip(), p)
        elif act == "delete":
            ok, m = manage_data.delete((p.get("kind") or "").strip(),
                                       _num(p.get("pk"), int) or 0)
        elif act == "move_slide":
            ok, m = manage_data.move_slide(_num(p.get("slide"), int) or 0,
                                           _num(p.get("sample"), int))
        elif act == "move_sample":
            ok, m = manage_data.move_sample(_num(p.get("sample"), int) or 0,
                                            _num(p.get("locality"), int) or 0)
        else:
            ok, m = False, "모르는 동작입니다."
        # POST 뒤에 redirect 한다 — 새로 고침이 같은 일을 다시 하면 안 된다.
        return redirect(f"{reverse('system_settings')}?{'msg' if ok else 'err'}={m}")

    msg, err = request.GET.get("msg", ""), request.GET.get("err", "")
    ctx = manage_data.overview()
    # 지우기 문턱을 **미리** 계산해 행에 달아 둔다. 눌러 보고 "지울 수 없습니다"
    # 를 만나면 무엇을 먼저 치워야 하는지 알 수 없다. 템플릿 필터를 새로 만들지
    # 않으려고 dict 가 아니라 객체에 붙인다.
    for kind, rows in (("site", ctx["sites"]), ("locality", ctx["localities"]),
                       ("sample", ctx["samples"])):
        for row in rows:
            row.block_why = " · ".join(manage_data.deletable(kind, row.pk)[1])
    return render(request, "viewer/system_settings.html", {
        **ctx,
        "site_areas": Site.AREA,
        "locality_kinds": Locality.KIND,
        "msg": msg, "err": err,
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
         # **이 표가 어느 묶음의 개체인가** (088). `candidate_rows` 가
         # `reviewing()` 을 지나므로 묶음을 갈면 표도 요약도 통째로 달라진다.
         "review_batch": data.review_batch_label(),
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
            # 같은 이유로 여기도 (088)
            "review_batch": data.review_batch_label(),
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


CATALOG_PER_PAGE = 120

# 카드에 얹는 거르개. 크롭 화면(`crops`)과 같은 것을 쓰되 **동정 진행률**을
# 보는 둘을 더한다 — 이 화면에서 사람이 알고 싶은 것은 "어디까지 했나" 다.
#
# **`named`·`unnamed` 는 진행도와 같은 기준이다** (2026-08-11) — 종명·등급·자세가
# 다 차야 완료다. 둘이 다른 뜻이면 진행도가 "80%" 인데 "덜 된 것" 거르개가 빈
# 화면을 내는 상태가 생기고, 사람은 무엇을 믿어야 할지 모른다.
CATALOG_FILTERS = {
    "manual": ("수동 복구", lambda r: r.get("manual")),
    "labeled": ("사람 지정", lambda r: r.get("cls_user")),
    "noted": ("코멘트 있음", lambda r: r.get("note")),
    "named": ("동정 완료", data.catalog_done),
    "unnamed": ("덜 된 것", lambda r: not data.catalog_done(r)),
}


def catalog(request, slug):
    """개체 카탈로그 — 검출된 규조 개체마다 카드 하나, 거기에 동정을 적는다.

    **검토 대상 묶음 하나만 따라간다** (사용자 방침 2026-08-10). 고르는 장치를
    두지 않는 이유는 `data.catalog_rows` 머리말에 있다 — 화면마다 다른 판을 보는
    상태가 051 이 난 자리다. 대신 **어느 엔진의 판인지 머리에 적는다.**
    """
    label = data.slide_label(slug)
    if label is None:
        raise Http404(f"unknown dataset: {slug}")

    rows = data.catalog_rows(slug)

    # **진행도에서 파편을 뺀다** (사용자 2026-08-11). 파편에는 등급·자세를 안
    # 매기므로 완료가 될 수 없고, 분모에 두면 진행률이 영영 100%에 못 닿는다 —
    # 실측으로 살아 있는 교정의 65%가 파편이다. **모수가 틀린 막대는 안 보는
    # 것만 못하다.** 분류가 없는 것은 남긴다(정하면 완형일 수 있다).
    scope = [r for r in rows if not data.is_fragment(r.get("cls"))]
    n_all = len(scope)
    n_named = sum(1 for r in scope if data.catalog_done(r))
    # 감춘 것이 몇 개인지 화면이 적는다 — **"없다" 와 "감췄다" 는 다르다.**
    # `catalog_rows` 를 다시 부르지 않는다: 한 판을 통째로 다시 만드는 함수다.
    n_frag = len(rows) - n_all

    # **지운 것은 따로 본다** (P16 5.1). 카탈로그에서 지울 수 있게 됐으니
    # 되살릴 자리도 같은 화면에 있어야 한다 — 섞어서 내지는 않는다.
    #
    # **진행도는 위에서 이미 냈다.** 여기서 갈아 끼우는 것은 화면에 놓을 카드
    # 뿐이라 `n_all`·`n_named`·`n_frag` 는 통과분 기준으로 남는다 — 분모가 지운
    # 것으로 바뀌면 "모수가 틀린 막대" 가 된다(파편에서 이미 겪은 자리다).
    show_gone = request.GET.get("gone") == "1"
    if show_gone:
        rows = data.catalog_rows(slug, gone=True)

    cls = request.GET.get("cls") or ""
    # **파편은 기본으로 감춘다** (사용자 2026-08-11). 처음부터 다 내면 카드가
    # 파편으로 덮여 동정할 것이 안 보인다. 감추는 것은 화면일 뿐이라 진행도·
    # 개수는 그대로다.
    #
    # **파편 분류를 콕 집었으면 감추지 않는다** — 그 칩을 누르고 빈 화면을 보면
    # 사람은 자료가 없다고 읽는다. 눌러서 아무 일도 안 일어나는 화면을 만들지
    # 않는다.
    #
    # **지운 것을 보는 화면에서는 감추지 않는다** (P16). 파편 분류를 콕 집었을
    # 때와 같은 이유다 — 지운 것을 되살리러 온 사람에게 지운 것의 절반을 감추면
    # "지웠는데 없다" 가 된다. 실측으로 살아 있는 교정의 65%가 파편이다.
    show_frag = request.GET.get("frag") == "1" or show_gone
    if not show_frag and not data.is_fragment(cls):
        rows = [r for r in rows if not data.is_fragment(r.get("cls"))]

    if cls in data.CLASSES:
        rows = [r for r in rows if r.get("cls") == cls]
    elif cls in CATALOG_FILTERS:
        rows = [r for r in rows if CATALOG_FILTERS[cls][1](r)]

    # **찾는 것은 번호·종명·코멘트 셋이다.** 번호를 통째로 붙여 넣는 쓰임이
    # 첫째이므로 부분 일치이고 대소문자를 안 가린다 (`catalog.parse` 와 같다).
    q = (request.GET.get("q") or "").strip()
    if q:
        low = q.lower()
        rows = [r for r in rows
                if low in r["catalog_no"].lower()
                or low in (r.get("species") or "").lower()
                or low in (r.get("note") or "").lower()]

    for r in rows:
        # 묶었으면 가장 큰 프레임을 그린다 — 번호는 그대로다 (`link_mains`).
        view = r.get("view") or r
        # **세워서 자른다** — 크롭 갤러리와 같다(`crops`). 방향이 통일돼야 형태를
        # 나란히 비교할 수 있고, 동정은 그 비교로 한다. 축 비율이 1에 가까우면
        # 안 돌린다(굳이 보간으로 흐릴 이유가 없다 — `crop_geometry`).
        geo = data.crop_geometry(view, rotate=True)
        r["src_rel"] = view.get("rel") or r["image_rel"]
        r["src_bbox"] = view.get("bbox_xywh") or r["bbox_xywh"]
        r["rot"], r["out"] = (geo["rot"], geo["out"]) if geo else (0, "")
        if geo:
            r["sb"] = data.scalebar_for(geo["out_w"], r.get("um_per_pixel") or 0)

    total = len(rows)
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        offset = 0
    page = rows[offset:offset + CATALOG_PER_PAGE]

    def page_url(off):
        qd = {"offset": off}
        if cls:
            qd["cls"] = cls
        if q:
            qd["q"] = q
        # 다음 쪽으로 넘어가면서 파편이 도로 감춰지면 안 된다 — 사람은 켠 것이
        # 꺼진 줄 모르고 개체가 사라졌다고 읽는다.
        if show_frag:
            qd["frag"] = "1"
        # 지운 것을 보다가 다음 쪽으로 넘어가면 통과분으로 돌아가면 안 된다 —
        # 파편 체크박스와 같은 이유다.
        if show_gone:
            qd["gone"] = "1"
        return f"?{urlencode(qd)}"

    # **왜 못 적는가를 화면이 말한다.** 잠가 놓고 이유를 안 적으면 사람이 같은
    # 일을 몇 번이고 다시 한다 (063).
    batch = data.review_batch_info()
    if batch is None:
        blocked = ("검토할 묶음이 정해져 있지 않아 개체가 하나도 안 보입니다 — "
                   "시스템 설정 · 운영에서 고르세요.")
    elif not batch["code"]:
        blocked = (f"묶음 \"{batch['label']}\" 의 카탈로그 코드가 비어 있어 "
                   f"번호를 만들 수 없습니다 — 시스템 설정 · 운영에서 채우세요.")
    else:
        blocked = data.review_blocked(
            Slide.objects.filter(slug=slug).first())

    return render(request, "viewer/catalog.html", {
        "slug": slug,
        "label": label,
        "rows": page,
        "batch": batch,
        "review_batch": (batch or {}).get("label", ""),
        "blocked": blocked,
        "readonly": bool(blocked),
        "cls": cls,
        "filters": [{"key": k, "label": v[0]} for k, v in CATALOG_FILTERS.items()],
        "q": q,
        "show_frag": show_frag,
        "n_frag": n_frag,
        "show_gone": show_gone,
        # **등급·자세는 완형에만 매긴다.** 어느 분류가 완형인지를 화면이 알아야
        # 카드가 두 칸을 감추고, 유형을 파편으로 바꿀 때 물어볼 수 있다.
        # 서버는 `data.check_grade_pose` 가 다시 검사한다 — 화면에서 막는 것은
        # 막는 것이 아니다(063).
        "counted_keys": [r["key"] for r in data.counted_classes()],
        "grades": DiatomObject.GRADE,
        "poses": DiatomObject.POSE,
        "species_seen": data.species_seen(),
        "n_all": n_all,
        "n_named": n_named,
        "n_left": n_all - n_named,
        "pct": round(100 * n_named / n_all) if n_all else 0,
        "total": total,
        "shown_from": offset + 1 if page else 0,
        "shown_to": offset + len(page),
        "per_page": CATALOG_PER_PAGE,
        "prev_url": page_url(max(0, offset - CATALOG_PER_PAGE)) if offset else None,
        "next_url": (page_url(offset + CATALOG_PER_PAGE)
                     if offset + CATALOG_PER_PAGE < total else None),
    })


def _catalog_fields(src, *, with_note=True):
    """카드가 보낸 칸들을 고른다. **`None` 은 안 고친다, `""` 는 비운다.**

    둘을 같이 다루면 화면이 안 보내는 칸을 저장이 지운다 — `drawn` 과 같은 규칙.
    문자열이 아닌 값은 `ValueError` 다(부르는 쪽이 400 으로 낸다).

    **일괄에는 코멘트가 없다** (P16 3.3). 같은 글을 여러 개체에 붙이는 것은
    *이 규조각을 두고 하는 말* (0036)이라는 그 칸의 뜻과 어긋난다.
    """
    def text(name, limit):
        v = src.get(name)
        if v is None:
            return None                      # **안 고친다** (빈 것과 다르다)
        if not isinstance(v, str):
            raise ValueError(name)
        return v[:limit]

    fields = {"species": text("species", data.SPECIES_MAX),
              "cls": text("cls", 32),
              # 값이 셋뿐이라 자르는 길이가 뜻이 없다 — 모르는 값은
              # `check_grade_pose` 가 `ValueError` 로 물린다(409).
              "grade": text("grade", 8),
              "pose": text("pose", 16)}
    if with_note:
        fields["note"] = text("note", NOTE_MAX)
    return fields


@require_POST
def save_catalog(request, slug):
    """카드 한 장을 저장한다. **개체 하나만 고친다** (`data.save_catalog_entry`).

    `/review` 처럼 범위를 갈아치우지 않으므로 017·027·053 계열의 사고가
    구조적으로 안 생긴다. 그래도 짚는 것은 그때와 같은 방식이다 —
    **`(slug, gid)` 로 시야를, id 로 이미지를** 짚고 서버가 다시 확인한다.

    문이 넷이다 (`act` · P16 5절). **주소를 늘리지 않는다** — 짚는 방식과 막는
    검사가 완전히 같아서, 주소로 가르면 같은 검사를 네 벌 적게 된다.

    | `act` | 무엇을 | 어느 층에 |
    |---|---|---|
    | `save`(기본) | 종명·유형·등급·자세·코멘트 | 개체 (`DiatomObject`) |
    | `remove`·`restore` | 오검출로 지우기·되돌리기 | `(이미지, 묶음, mask_key)` |
    | `bulk` | 고른 카드들에 넷을 한 번에 | 개체 — 하나씩 저장한다 |

    **`remove` 를 `save` 와 한 payload 에 안 싣는다** (116). 층이 다른 것을 한
    요청으로 보내면 한쪽을 고르는 일이 다른 쪽까지 갈아치운다.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("bad json")

    act = payload.get("act") or "save"
    if act == "bulk":
        return _save_catalog_bulk(slug, payload)
    if act not in ("save", "remove", "restore"):
        return HttpResponseBadRequest("bad act")

    try:
        gid = int(payload.get("gid"))
        image_id = int(payload.get("image"))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("bad gid/image")

    vp, why = data.find_viewpoint(slug=slug, gid=gid)
    if vp is None:
        return JsonResponse({"ok": False, "error": why}, status=409)

    blocked = data.review_blocked(vp.slide)
    if blocked:
        return JsonResponse({"ok": False, "error": blocked}, status=409)

    if act in ("remove", "restore"):
        try:
            saved = data.set_catalog_removed(vp, image_id, payload.get("key"),
                                             act == "remove")
        except ValueError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=409)
        return JsonResponse({"ok": True, **saved})

    try:
        fields = _catalog_fields(payload)
    except ValueError:
        return HttpResponseBadRequest("bad field")

    try:
        saved = data.save_catalog_entry(vp, image_id, payload.get("key"),
                                        **fields)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=409)
    return JsonResponse({"ok": True, **saved})


def _save_catalog_bulk(slug, payload):
    """고른 카드들에 같은 값을 넣는다 (P16 5.2).

        {"act": "bulk",
         "items": [{"gid": 3, "image": 12, "key": "10_10_50_50"}, …],
         "fields": {"cls": "diatom", "grade": "A"}}

    **한 트랜잭션으로 묶지 않는다.** 40장 중 하나가 409 면 나머지 39장의 저장까지
    되돌아가고, 사람은 무엇이 걸렸는지 모른 채 전부 다시 한다. **개체마다
    `save_catalog_entry` 를 부른다** — 저장하는 규칙이 둘이 되지 않는다.

    **결과를 항목마다 돌려준다.** "N장 중 M장 저장됨" 한 줄로 끝내면 화면이
    실패한 카드를 짚어 주지 못한다 (063 — 못 한 것은 오류로 말한다).
    """
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return HttpResponseBadRequest("no items")
    # 한 판에 놓이는 카드 수가 상한이다 — 화면에 없는 것을 고를 수는 없다.
    if len(items) > CATALOG_PER_PAGE:
        return HttpResponseBadRequest("too many items")

    try:
        fields = _catalog_fields(payload.get("fields") or {}, with_note=False)
    except ValueError:
        return HttpResponseBadRequest("bad field")
    if all(v is None for v in fields.values()):
        return HttpResponseBadRequest("no fields")

    results, n_ok = [], 0
    # **막는 검사는 슬라이드마다 한 번이다** (105 — 같은 값을 되묻지 말 것).
    blocked, seen = None, {}
    for it in items:
        if not isinstance(it, dict):
            results.append({"ok": False, "error": "항목이 객체가 아니다"})
            continue
        try:
            gid = int(it.get("gid"))
            image_id = int(it.get("image"))
        except (TypeError, ValueError):
            results.append({"ok": False, "error": "gid·image 가 없다"})
            continue
        here = {"gid": gid, "image": image_id, "key": it.get("key")}

        if gid not in seen:
            seen[gid] = data.find_viewpoint(slug=slug, gid=gid)
        vp, why = seen[gid]
        if vp is None:
            results.append({**here, "ok": False, "error": why})
            continue
        if blocked is None:
            blocked = data.review_blocked(vp.slide) or ""
        if blocked:
            return JsonResponse({"ok": False, "error": blocked}, status=409)

        try:
            saved = data.save_catalog_entry(vp, image_id, it.get("key"),
                                            **fields)
        except ValueError as e:
            results.append({**here, "ok": False, "error": str(e)})
            continue
        results.append({**here, "ok": True, **saved})
        n_ok += 1

    return JsonResponse({"ok": True, "n_ok": n_ok, "n": len(items),
                         "results": results})


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


# 축소본은 늘 JPEG 이지만(`_thumbnail` 이 그렇게 굽는다) **원본은 아니다** —
# 도감 도판이 PNG 로 들어왔다 (129). 확장자로 정한다.
_CTYPE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def _jpeg(request, path):
    """이미지 응답. v= (원본 mtime) 가 붙은 주소면 영구 캐시를 허용한다.

    주소에 mtime 이 들어 있으므로 그림이 바뀌면 주소가 바뀐다 — 옛 그림을
    붙잡고 있을 수가 없다. v= 없이 들어온 주소는 캐시를 막는다.
    """
    ctype = _CTYPE.get(path.suffix.lower(), "image/jpeg")
    resp = FileResponse(path.open("rb"), content_type=ctype)
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


def atlas_index(request):
    """도감 — **검색이 먼저고 도판이 그다음이다** (P15 §6 · 129 · 131).

    사용자가 청한 것은 "DB 내용을 빠르게 검색해 찾아오는" 화면이다. 그래서
    검색창을 맨 위에 두고, 아무것도 안 찾았을 때만 도감 카드를 낸다 — 찾으러
    온 사람에게 목록을 먼저 보이면 한 번 더 눌러야 한다.

    **두 자료가 한 화면에 있고 서로 안 매달린다.** 글자(`AtlasEntry`)는 DB 에서
    오고 도판은 파일에서 온다(`viewer/atlas.py`). 반입 전이면 검색만 비고,
    도판을 안 구웠으면 카드만 빈다 — 한쪽이 없다고 다른 쪽이 안 뜨지 않는다.
    """
    q = (request.GET.get("q") or "").strip()
    atlas_key = (request.GET.get("atlas") or "").strip()
    genus = (request.GET.get("genus") or "").strip()
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        offset = 0

    plates = atlas_mod.atlases()
    searched = bool(q or atlas_key or genus)
    ctx = {
        "atlases": plates,
        # 굽는 중일 수 있다. **몇 쪽 중 몇 쪽인지 화면이 말한다** — 안 말하면
        # 덜 구운 상태를 "원본이 그만큼" 으로 읽는다.
        "partial": [a for a in plates if a["partial"]],
        "books": data.atlas_list(),
        "searched": searched,
        "genera": data.atlas_genera(atlas_key),
    }
    if searched:
        ctx.update(data.atlas_search(q, atlas_key, genus, offset))
        base = reverse("atlas")
        keep = {k: v for k, v in (("q", q), ("atlas", atlas_key),
                                  ("genus", genus)) if v}
        for name, off in (("prev_url", ctx["prev_offset"]),
                          ("next_url", ctx["next_offset"])):
            ctx[name] = (f"{base}?{urlencode({**keep, 'offset': off})}"
                         if off is not None else None)
        # 칩 주소는 `offset` 을 안 들고 간다 — 거르는 것을 바꾸면 결과가
        # 달라지는데 옛 페이지 번호를 그대로 쓰면 빈 화면이 나온다.
        ctx["chip_base"] = base
        ctx["keep_q"] = q
    else:
        ctx["q"] = q
        ctx["atlas_key"] = atlas_key
        ctx["genus"] = genus
    return render(request, "viewer/atlas.html", ctx)


def atlas_volume(request, atlas, vol):
    """권 하나 — 쪽 격자."""
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        offset = 0
    # **쪽 번호로 곧장 간다** (`?n=`). 색인이 `PDF p.174` 를 알려 주는데 격자를
    # 넘겨 가며 찾게 하면 그 번호를 들고 온 뜻이 없다. 없는 쪽이면 격자로
    # 물러나되 **말은 한다** — 조용히 첫 판을 내면 사람이 갔다고 믿는다.
    raw_n = (request.GET.get("n") or "").strip()
    if raw_n.isdigit():
        if atlas_mod.page(atlas, vol, int(raw_n)) is not None:
            return redirect("atlas_page", atlas=atlas, vol=vol, n=int(raw_n))
        missing = raw_n
    else:
        missing = ""

    ctx = atlas_mod.volume(atlas, vol, offset)
    if ctx is None:
        raise Http404(f"unknown atlas volume: {atlas}/{vol}")
    ctx["missing_n"] = missing
    here = reverse("atlas_volume", args=[atlas, vol])
    ctx["prev_url"] = (f"{here}?offset={ctx['prev_offset']}"
                       if ctx["prev_offset"] is not None else None)
    ctx["next_url"] = (f"{here}?offset={ctx['next_offset']}"
                       if ctx["next_offset"] is not None else None)
    return render(request, "viewer/atlas_volume.html", ctx)


def atlas_page(request, atlas, vol, n):
    """쪽 하나. **색인이 짚어 오는 자리다** — 주소의 `n` 이 `PDF p.N` 이다.

    안 구워진 쪽은 404 다. 빈 그림을 내면 사람이 **원본에 그 쪽이 없다**고
    읽는다 — 아직 안 뜬 것과 원본에 없는 것은 다른 말이다.
    """
    # **두 쪽 보기** (131). 원래 책처럼 펼쳐 본다 — Schmidt 는 해설면과 도판면이
    # 한 펼침이라 왼쪽에서 읽고 오른쪽을 본다. 상태를 주소에 둔다: 눌러서 온
    # 자리를 적어 두거나 새로고침해도 보던 모양 그대로여야 한다.
    two = request.GET.get("spread") == "1"
    ctx = (atlas_mod.spread(atlas, vol, n) if two
           else atlas_mod.page(atlas, vol, n))
    if ctx is None:
        raise Http404(f"unknown atlas page: {atlas}/{vol}/{n}")
    ctx["spread"] = two
    ctx["grid_url"] = (reverse("atlas_volume", args=[atlas, vol])
                       + f"?offset={ctx['grid_offset']}")
    suffix = "?spread=1" if two else ""
    for k, name in (("prev", "prev_url"), ("next", "next_url")):
        ctx[name] = (reverse("atlas_page", args=[atlas, vol, ctx[k]]) + suffix
                     if ctx[k] else None)
    # 보기를 바꾸는 문. **지금 보고 있는 쪽을 들고 간다** — 펼침에서 한 장으로
    # 갈 때 첫 쪽으로 돌아가면 찾던 자리를 잃는다.
    here = reverse("atlas_page", args=[atlas, vol, n])
    ctx["one_url"], ctx["two_url"] = here, here + "?spread=1"
    return render(request,
                  "viewer/atlas_spread.html" if two else "viewer/atlas_page.html",
                  ctx)


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
    # **검토 대상 묶음의 검출만** (P10 1단계). 정규화 뒤에는 쌓아 둔 것도
    # 전부 `is_current` 라, 그것만 걸면 다른 엔진의 마스크가 나간다.
    det = Detection.objects.reviewing().filter(pk=det_id).first()
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


def _locality(site_code, core_code, outcrop_only=True):
    qs = Locality.objects.select_related("site").filter(
        site__code=site_code, code=core_code)
    if outcrop_only:
        qs = qs.filter(kind="outcrop")
    loc = qs.first()
    if loc is None:
        raise Http404(f"unknown outcrop locality: {site_code}/{core_code}")
    return loc


def outcrop_photo(request, site_code, core_code, index):
    """노두 지점의 현장 사진 한 장. `?w=` 로 축소본.

    **파일 이름을 URL 로 안 받는다.** 서버가 그 지점의 사진 목록을 만들고 순번
    하나를 고를 뿐이라 `../` 로 바깥을 가리킬 방법이 없다.
    """
    path = outcrop.photo_path(_locality(site_code, core_code), index)
    if path is None:
        raise Http404("outcrop photo not found")
    raw = request.GET.get("w")
    if not raw:
        return _jpeg(request, path)
    try:
        width = max(32, min(int(raw), 2048))
    except ValueError:
        raise Http404("bad width")
    thumb = _thumbnail(path, width)
    return _jpeg(request, thumb or path)


@require_POST
def outcrop_edit(request, site_code, core_code):
    """현장 사진을 올리거나 지운다. 노두 지점에만 있다.

    **POST 전용이다.** GET 으로 열어 두면 주소를 누르는 것만으로 지워진다.

    올린 파일은 **줄여서 JPEG 으로 다시 쓴다**(`outcrop.save_upload`) — 카메라
    원본이 장당 12 MB 라 그대로 두면 여럿이 쓰는 NAS 공유가 금방 찬다.
    이름도 우리가 짓는다(`<지점코드> (n).jpg`).
    """
    loc = _locality(site_code, core_code)
    act = (request.POST.get("act") or "").strip()
    here = reverse("core", args=[site_code, core_code])

    if act == "delete":
        try:
            i = int(request.POST.get("i") or "")
        except ValueError:
            raise Http404("bad index")
        ok, m = outcrop.delete_photo(loc, i)
    elif act == "upload":
        files = request.FILES.getlist("photo")
        if not files:
            ok, m = False, "고른 파일이 없습니다."
        else:
            done, msgs = 0, []
            for f in files:
                good, m1 = outcrop.save_upload(loc, f)
                done += 1 if good else 0
                if not good:
                    msgs.append(m1)
            ok = done > 0
            m = (f"{done}장을 올렸습니다." if done else "") + \
                (" " + " · ".join(msgs) if msgs else "")
    else:
        raise Http404("unknown act")
    return redirect(f"{here}?{'msg' if ok else 'err'}={m.strip()}")


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
def save_object_link(request, slug, gid):
    """같은 개체 묶음 하나를 저장하거나 푼다 (P11 2단계).

        {"act": "save",   "link_id": 3 또는 없음,
         "members": [{"image": 12, "mask_key": "10_10_50_50", "rep": true}, …]}
        {"act": "unlink", "link_id": 3}

    **`/review` 에 싣지 않는다.** 그 길은 "그 시야의 교정 전체를 갈아치운다"
    는 전제 위에 있고 두 번 사고 낸 자리다 — 전제가 다른 자료를 같은 길에
    실으면 세 번째가 된다. 여기는 묶음 하나 단위다.

    **서버가 다시 검사한다** (화면에서 막는 것은 막는 것이 아니다):
    이미지가 그 시야의 것인가 · 마스크가 실재하는가(검토 대상 묶음의 현재
    검출, 또는 사람이 그린 교정) · **지운 마스크가 아닌가** · 대표가 정확히
    하나인가 · 멤버가 둘 이상인가. 기하는 서버가 스스로 뜬다 — 화면이 보낸
    것을 믿지 않는다.
    """
    vp = (Viewpoint.objects.filter(slide__slug=slug, idx=gid)
          .select_related("slide").first())
    if vp is None:
        raise Http404(f"unknown viewpoint: {slug}/g{gid}")

    def bad(msg, status=400):
        return JsonResponse({"ok": False, "error": msg}, status=status)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return bad("JSON 이 아니다")

    act = payload.get("act") or "save"
    link_id = payload.get("link_id")

    if act == "unlink":
        link = DiatomObject.objects.filter(pk=link_id, viewpoint=vp).first()
        if link is None:
            return bad("그 묶음이 이 시야에 없다", 404)
        # **개체를 지우지 않는다 — 가른다** (P12). `ObjectReview.diatom_object`
        # 가 `CASCADE` 라 `link.delete()` 는 이제 **그 판들의 교정을 통째로
        # 지운다.** 풀기는 "이것들이 한 개체가 아니다" 라는 말이지 "이 판단들이
        # 없던 일" 이라는 말이 아니다.
        with transaction.atomic():
            rows = list(ObjectReview.objects.filter(diatom_object=link)
                        .select_related("diatom_object"))
            for row in rows[1:]:
                _split_off(row, link)
            if rows:
                # 남은 하나는 혼자이므로 자기가 대표다
                ObjectReview.objects.filter(pk=rows[0].pk).update(is_rep=True)
        return JsonResponse({"ok": True, "links": data.object_links_of(vp)})

    if act != "save":
        return bad(f"모르는 act: {act}")

    rb = data.review_batch_id()
    if rb is None:
        return bad("검토 대상 묶음이 정해져 있지 않다")

    # **묶으면서 분류·종명을 하나로 맞춘다** (사용자 요청 2026-08-10).
    #
    # 묶음은 "이 판들의 이것이 한 개체다" 라는 말이므로 분류도 종명도 하나여야
    # 하는데, 묶기 **전에** 판마다 따로 적어 둔 것이 서로 다를 수 있다. 화면이
    # 그것을 알리고 사람이 하나를 고르면 여기로 실려 온다.
    #
    # **안 보내면 안 건드린다** (`None`). `""` 는 **비운다**는 말이다 —
    # `save_catalog_entry` 와 같은 규칙이고, 둘을 같이 다루면 화면이 안 보낸
    # 칸을 저장이 지운다.
    unify_label = payload.get("label")
    if unify_label is not None:
        unify_label = str(unify_label)
        if unify_label and unify_label not in data.CLASSES:
            return bad(f"모르는 분류다: {unify_label}")
    unify_species = payload.get("species")
    if unify_species is not None:
        if not isinstance(unify_species, str):
            return bad("종명이 문자열이 아니다")
        unify_species = unify_species.strip()[:data.SPECIES_MAX]

    members = payload.get("members") or []
    if len(members) < 2:
        return bad("멤버가 둘 미만이다 — 혼자인 묶음은 뜻이 없다")
    reps = [m for m in members if m.get("rep")]
    if len(reps) != 1:
        return bad(f"대표가 {len(reps)}개다 — 정확히 하나여야 한다")

    # 이미지 → 시야 검증을 한 번에. 남의 시야 이미지는 화면에 안 그려지므로
    # 여기 걸리는 것은 화면 밖에서 만든 요청이다.
    img_ids = [m.get("image") for m in members]
    if len(set(img_ids)) != len(img_ids):
        return bad("같은 이미지의 멤버가 둘이다")
    # `ImageModel` 이다 — 이 파일은 PIL 의 `Image` 를 함수 안에서 따로
    # 임포트한다. 같은 이름을 쓰면 어느 쪽인지 읽는 사람이 매번 따져야 한다.
    imgs = {i.pk: i for i in ImageModel.objects.filter(pk__in=img_ids)}
    resolved = []
    for m in members:
        img = imgs.get(m.get("image"))
        key = m.get("mask_key") or ""
        if img is None or img.viewpoint_id != vp.pk:
            return bad(f"이미지 {m.get('image')} 가 이 시야의 것이 아니다")
        # 마스크가 실재하는가 — 검토 대상 묶음의 현재 검출에서 찾고, 없으면
        # 사람이 그린 교정에서 찾는다. 기하도 여기서 뜬다.
        cand = (Candidate.objects
                .filter(detection__image=img, detection__is_current=True,
                        detection__run__batch_id=rb, mask_key=key)
                .first())
        if cand is not None:
            # **지운 마스크는 못 묶는다.** 사람이 오검출로 지운 것을 묶으면
            # "이 개체는 오검출이면서 실재한다" 가 된다.
            gone = ObjectReview.objects.filter(
                image=img, batch_id=rb, mask_key=key, removed=True).exists()
            if gone:
                return bad(f"{key} 는 오검출로 지운 마스크다")
            geom = {"bbox_xywh": [cand.bbox_x, cand.bbox_y,
                                  cand.bbox_w, cand.bbox_h],
                    "polygon": cand.polygon}
            # **문턱에서 떨어진 후보도 묶을 수 있다** (102). 그 프레임에서 가장
            # 좋은 마스크가 탈락해 있는 일이 실제로 있다 — 초점이 흐려 텍스처가
            # 모자란 판이 그렇다. 사람이 "이것이 그 개체다" 라고 하면 그것은
            # **검출이 맞다는 판단이기도 하므로 되살린다**(탈락 펼침판을 눌러
            # 되살리는 것과 같은 뜻이다).
            #
            # **서버가 한다.** 화면에서 하려면 그 판(이미지)에 대고 `/review` 를
            # 따로 보내야 하는데, 그 길은 "그 이미지의 교정 전체를 갈아치운다"
            # 는 전제라 다른 판의 상태를 실어 보내는 사고가 난다(027·053 계열).
            # 여기서는 행 하나만 좁게 세운다.
            # **후보를 들고 간다.** 판정 행을 새로 세울 때 이것을 안 넘기면
            # `bind_method="orphan"` · `candidate=NULL` 로 앉는다 — 짝이
            # 멀쩡히 있는데 "재검출로 짝을 잃은 교정" 으로 기록되는 것이고,
            # `check_db` 3번의 바인딩 집계와 `/orphans/`·`rebind` 가 그 값을
            # 본다. 실제로 그렇게 앉았다 (테스트 인스턴스 2026-08-11).
            resolved.append((img, rb, key, bool(m.get("rep")), geom,
                             not cand.passed, cand))
            continue
        drawn = ObjectReview.objects.filter(
            image=img, batch__isnull=True, mask_key=key).first()
        if drawn is not None and not drawn.removed:
            # 사람이 그린 것은 후보가 없다 — 행도 이미 있다
            resolved.append((img, None, key, bool(m.get("rep")), drawn.geom,
                             False, None))
            continue
        return bad(f"{key} 는 이 화면의 마스크가 아니다")

    try:
        with transaction.atomic():
            # ── 1. 멤버마다 판정 행을 확보한다 ─────────────────────────────
            #
            # **없으면 세운다.** P12 이후 판정 행이 곧 멤버이고, 개체는 그
            # 행이 생길 때 함께 생긴다 (`data.judgement_for` 가 그 문이다).
            rows, revived = [], 0
            for img, b, key, rep, geom, rej, cand in resolved:
                row = data.judgement_for(vp, img, b, key, cand)
                fields = []
                # **이미 있는 행도 다시 맺는다** (`save_review` 와 같은 줄).
                # `judgement_for` 는 있는 행을 그대로 돌려주므로, 옛 바인딩이
                # `orphan` 이면 다시 묶어도 그대로 남는다 — 그런데 여기까지 온
                # 것은 그 (이미지, 묶음, 키) 의 후보를 **방금 찾았다**는 뜻이라
                # 짝이 없다는 기록이 거짓이다. 고아 화면·`rebind` 가 그 값을 본다.
                if cand and row.candidate_id != cand.pk:
                    row.candidate = cand
                    row.bind_method = "exact"
                    row.bind_score = 1.0
                    fields += ["candidate", "bind_method", "bind_score"]
                if not row.geom:
                    row.geom = geom
                    fields.append("geom")
                if rej:
                    # 탈락 후보를 묶었다 → 되살린다. **있는 행은 안 덮는다** —
                    # 분류·코멘트가 붙어 있을 수 있고, 다른 축의 판단이다.
                    if not row.accepted:
                        row.accepted = True
                        fields.append("accepted")
                    revived += 1
                if fields:
                    row.save(update_fields=fields)
                rows.append((row, rep))

            # ── 2. 합칠 그릇을 고른다 ────────────────────────────────────
            if link_id:
                link = DiatomObject.objects.filter(pk=link_id,
                                                   viewpoint=vp).first()
                if link is None:
                    raise _Reject("그 묶음이 이 시야에 없다", 404)
            else:
                # **대표의 개체를 그릇으로 쓴다.** 분류·종명이 개체에 살고,
                # 대표는 사람이 "이 개체의 얼굴" 로 고른 판이다 — 그쪽 값을
                # 남기는 것이 덮어쓰기를 가장 적게 한다.
                link = next((r.diatom_object for r, rep in rows if rep),
                            rows[0][0].diatom_object)

            # **이미 다른 묶음에 속한 마스크는 안 받는다** (409). P12 이후로는
            # 옮기는 것이 기술적으로 가능해졌는데, 그러면 **남의 묶음이 조용히
            # 깨진다** — 사람이 먼저 풀고 다시 묶어야 한다.
            #
            # **고치는 요청(`link_id`)일 때만 그릇 자신을 뺀다.** 새로 묶는
            # 요청이라면 그릇으로 고른 개체가 이미 묶음이어도 안 된다 — 그쪽이
            # "이미 묶인 마스크를 새 묶음의 대표로 보냈다" 는 경우다.
            others = (DiatomObject.objects
                      .filter(pk__in={r.diatom_object_id for r, _ in rows})
                      .annotate(n=Count("members")).filter(n__gte=2))
            if link_id:
                others = others.exclude(pk=link.pk)
            if others.exists():
                raise _Reject("멤버 중 하나가 이미 다른 묶음에 속해 있다", 409)

            # **그릇이 안 든 값은 멤버에게서 물려받는다.** 대표의 개체를 그릇으로
            # 삼으므로, 대표가 비어 있고 다른 판에만 분류·종명이 있으면 합치는
            # 순간 그것이 사라진다 — **묶는다고 남의 동정을 잃으면 안 된다.**
            # 107 의 팝업이 "하나뿐이면 미리 고른다" 로 하던 일을 서버도 한다
            # (화면을 안 거치고 들어오는 요청이 있다). 여럿이 다르면 여기서
            # 고르지 않는다 — 그것은 사람이 팝업에서 정할 일이다.
            #
            # **엇갈리는데 안 골랐으면 묶지 않는다.** 개체가 값을 하나만 들 수
            # 있으므로 "그대로" 는 성립하지 않는다 — 그릇의 값이 남의 동정을
            # 덮는다. 107 의 팝업이 그것을 물어보게 돼 있고, 여기 걸리는 것은
            # **팝업을 안 지난 요청**이다. 종명은 현미경을 보며 적는 것이라
            # 자동으로 고르면 안 된다.
            carried = []
            given = {"label": unify_label, "species": unify_species}
            for fld in ("label", "species"):
                vals = {getattr(r.diatom_object, fld) for r, _ in rows
                        if getattr(r.diatom_object, fld)}
                if given[fld] is not None or len(vals) < 2:
                    if not getattr(link, fld) and len(vals) == 1:
                        setattr(link, fld, next(iter(vals)))
                        carried.append(fld)
                    continue
                what = "분류" if fld == "label" else "종명"
                raise _Reject(
                    f"판마다 {what} 이 다르다 — 무엇을 남길지 골라야 묶을 수 "
                    f"있다 ({' · '.join(sorted(vals))})", 409)
            link.batch_id = rb
            link.save(update_fields=["batch", "updated_at"] + carried)

            # ── 3. 이번 목록에 없는 옛 멤버는 떼어 낸다 ──────────────────
            #
            # **지우지 않는다.** 예전에는 `link.members.all().delete()` 로
            # 갈아끼웠는데, 지금 그 줄은 교정을 지운다.
            keep = {r.pk for r, _ in rows}
            for row in (ObjectReview.objects.filter(diatom_object=link)
                        .exclude(pk__in=keep).select_related("diatom_object")):
                _split_off(row, link)

            # ── 4. 그릇으로 옮긴다 ──────────────────────────────────────
            #
            # **규칙은 `data.merge_into_object` 하나다** — 그린 마스크가 판마다
            # 번질 때도 같은 문을 지난다. 대표를 내렸다 세우는 순서와 빈 개체를
            # 걷는 순서가 거기 적혀 있다.
            data.merge_into_object(link, rows)

            # **고른 값을 개체에 적는다.** 묶음이 선 뒤라야 한다 — 그 전에
            # 하면 아직 합쳐지지 않은 개체에 쓰게 되고, 같은 트랜잭션 안이라
            # 묶기가 실패하면 이것도 함께 물러난다.
            unified = _unify_members(link, resolved, unify_label, unify_species)
    except _Reject as e:
        return bad(e.msg, e.status)
    except IntegrityError:
        # 유일 제약 — 그 마스크가 이미 다른 묶음에 속해 있다
        return bad("멤버 중 하나가 이미 다른 묶음에 속해 있다", 409)

    return JsonResponse({"ok": True, "link_id": link.pk, "revived": revived,
                         "unified": unified,
                         "links": data.object_links_of(vp)})


class _Reject(Exception):
    """묶기를 거절한다 — **`atomic()` 안에서는 예외로만 물러난다.**

    `return` 은 트랜잭션을 되돌리지 않는다. 거절하기 전에 세운 판정 행(그리고
    그것이 데리고 온 개체)이 그대로 남아, **거절했는데 빈 껍데기가 생긴다** —
    103 에서 겪은 "한쪽은 거절, 한쪽은 통과" 와 같은 모양이다.
    """

    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.msg, self.status = msg, status


def _split_off(row, src) -> DiatomObject:
    """판정 하나를 묶음에서 떼어 **자기 개체**로 보낸다 (P12 의 "풀기").

    사람이 적은 것은 **전부 물려준다.** 묶여 있는 동안 그 값은 이 판의 것이기도
    했고, 가른다고 해서 사람이 적은 동정이 사라질 이유가 없다 — 재생성 불가
    자료를 구조 변경의 부수 효과로 잃지 않는다.

    **칸이 늘면 여기도 는다.** 0034·0035 가 등급·자세를 개체에 앉히고 이 줄을
    안 고쳐, 풀기 한 번에 사람이 매긴 등급이 사라지고 있었다 — 예외도 경고도
    없는 종류다. 코멘트를 얹으면서(0036) 함께 채운다.
    """
    obj = DiatomObject.objects.create(
        viewpoint_id=src.viewpoint_id, batch_id=src.batch_id,
        label=src.label, species=src.species, note=src.note,
        grade=src.grade, pose=src.pose)
    ObjectReview.objects.filter(pk=row.pk).update(diatom_object=obj,
                                                  is_rep=True)
    return obj


def _unify_members(link, resolved, label, species) -> dict:
    """묶음의 분류·종명을 고른 값으로 맞춘다 (107 · P12 에서 한 줄이 됐다).

    돌려주는 것은 `{이미지 id: {"label": …, "species": …}}` — **화면이 이걸
    받아야 한다.** 다른 판의 상태는 화면이 열릴 때 받은 것이라 방금 맞춘 값을
    모르고, 그 판에서 다음 저장이 나가면 자기가 아는 옛 값을 보내 되돌린다
    (104 와 같은 자리).

    **쓰는 자리는 개체 하나다.** 예전에는 멤버마다 행을 찾아 적고, 행이 없으면
    세우고, 빈 껍데기를 안 만들려고 갈래를 타야 했다 — 분류가 판마다 살았기
    때문이다. 지금은 개체가 들고 있어 그 전부가 필요 없다.

    **분류·종명 말고는 안 건드린다** — 삭제·되살림·코멘트·기하는 판마다 하는
    판단이라 묶는다고 같아질 이유가 없다.
    """
    if label is None and species is None:
        return {}
    fields = []
    if label is not None and link.label != label:
        link.label = label
        fields.append("label")
    if species is not None and link.species != species:
        link.species = species
        fields.append("species")
    if fields:
        link.save(update_fields=fields + ["updated_at"])

    # 바뀌지 않았어도 화면에 알린다 — 아직 교정 행이 없던 판은 화면 쪽 상태에도
    # 없어서, 안 알리면 그 판만 옛 값으로 남는다.
    ent = {}
    if label is not None:
        ent["label"] = label
    if species is not None:
        ent["species"] = species
    return {str(img.pk): dict(ent) for img, *_ in resolved}


@require_POST
def save_review(request):
    """
    교정 결과를 저장한다.

        {"stem": ..., "slug": ..., "gid": int,
         "done": bool, "removed": [key], "accepted": [key],
         "labels": {key: "round"|"round_frag"|"rod"|"rod_frag"},
         "note":   "이 시야에 대한 메모"}

    **`{"only": "done"}` 이면 완료 표시 하나만 쓴다** (116 덧) — 교정은 안
    싣고 안 지운다. 완료는 `(시야, 묶음)` 이고 교정은 `(이미지, 묶음)` 이라
    층이 다르다 (`data.save_done` 머리말).

    **개체 코멘트(`notes`)는 여기로 안 온다** (0036) — 카탈로그에서만 적는다.
    옛 탭이 보내면 조용히 흘린다.

    키는 bbox 에서 만든 것이라 검출을 다시 돌려도 같은 마스크면 그대로 붙는다.
    문턱만 바꾸는 refilter.py 실행에는 영향받지 않는다. 저장 위치는 DB 이고
    (예전에는 review/<stem>_review.json), git 에 남길 감사 기록은
    export_review.py 가 내보낸다.

    labels 는 자동 판정을 사람이 덮어쓴 것이다 — 조각난 규조각이 봉상/원형으로
    잘못 분류되는 것을 손으로 고치는 수단이고, 학습 데이터의 정답이 된다.

    ## 어느 시야에 쓰는가는 `(slug, gid)` 가 정한다

    예전에는 `stem` 하나로 찾았다. **프레임 이름은 슬라이드끼리 겹친다** —
    싱글턴 시야는 stem 이 곧 프레임 이름이라, 12개 화면이 **다른 슬라이드의
    시야를 열고 있었다.** 이 뷰는 마지막에 그 시야의 교정을 통째로 갈아치우므로
    (`data.save_review`), "검토 완료" 만 누른 빈 payload 하나가 남의 교정 7건을
    지웠다 — 사본에서 재현했다(2026-08-05). 예외도 409 도 없이 200 이었다.

    `stem` 은 남겨 두고 **검증용**으로 쓴다: 그 시야의 현재 검출과 다르면 받지
    않는다. 화면과 저장 대상이 어긋난 채 통과하는 길을 남기지 않는다.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("bad json")

    stem = str(payload.get("stem", ""))
    if not SAFE_STEM.match(stem):
        return HttpResponseBadRequest("bad stem")

    # 옛 화면(배포 중에 열려 있던 탭)은 slug·gid 를 안 보낸다. 그때는 stem 으로
    # 찾되 **모호하면 거절한다** — 아무거나 집는 길은 없앤다.
    slug = str(payload.get("slug", "") or "")
    gid = payload.get("gid")
    if gid is not None:
        try:
            gid = int(gid)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("bad gid")

    vp, why = data.find_viewpoint(stem=stem, slug=slug, gid=gid)
    if vp is None:
        return JsonResponse({"ok": False, "error": why}, status=409)

    # 자동 처리가 끝나기 전에는 저장을 받지 않는다 (P01 §1).
    # 반쯤 처리된 슬라이드를 검토하면 아직 안 돌아간 시야의 검출이 뒤늦게
    # 들어오면서 이미 본 화면이 바뀐다. 최상위 폴더 하나를 단위로 열고 닫는다.
    blocked = data.review_blocked(vp.slide)
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

    # **완료만 보내는 요청** (116 덧). `{"only": "done"}` 이면 교정을 안 싣고
    # `(시야, 묶음)` 한 줄만 쓴다 — 표시 하나를 켜자고 그 판의 교정을
    # 갈아치우는 갈래를 남기지 않는다 (`data.save_done` 머리말).
    #
    # **위의 검사는 다 지난 뒤다** — `stem` 과 `(slug, gid)` 로 시야를 짚었고
    # (053), 자동 처리가 끝났는지도 봤다. 여기서 줄이는 것은 payload 뿐이다.
    if payload.get("only") == "done":
        try:
            saved = data.save_done(vp, done)
        except ValueError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=409)
        return JsonResponse({"ok": True, **saved})

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

    # **개체 코멘트는 안 받는다** (0036). 적는 자리를 개체 카탈로그 하나로
    # 모았다 — 이 화면은 읽기만 한다. 옛 탭이 `notes` 를 실어 보내면 **조용히
    # 흘린다**: 오류로 물리면 그 저장에 함께 실린 삭제·되살림까지 잃는다
    # (`save_review` 머리말).
    try:
        labels = mapping("labels", as_label)
    except ValueError:
        return HttpResponseBadRequest("bad labels")

    # 시야 전체에 대한 메모. 개체에 붙지 않는 이야기(촬영 상태, 판정이 애매한
    # 이유 등)를 적을 곳이 있어야 한다.
    note = as_note(payload.get("note")) or ""
    if not isinstance(payload.get("note", ""), (str, type(None))):
        return HttpResponseBadRequest("bad note")

    # **어느 이미지를 보고 한 교정인가** (P09 1단계). 시야 하나에 현재 검출이
    # 여럿일 수 있으므로(합성본 하나 + 프레임마다 하나) 화면이 짚어서 보낸다.
    #
    # **이름이 아니라 id 다.** 프레임 이름은 슬라이드끼리 겹치고(143종) 053 이
    # 정확히 그 자리에서 났다 — 이름은 겹쳐도 주소는 안 겹친다. 서버는 그 id 가
    # **이 시야의 것인지** 다시 확인한다(`save_review` 안에서).
    image_id = payload.get("image")
    if image_id is not None:
        try:
            image_id = int(image_id)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("bad image")

    # **사람이 그린 개체** (P09 3단계). `[{key, polygon, cls}]` 이고
    # 기하는 서버가 다시 잰다 — 클라이언트가 보낸 면적을 믿으면 브라우저마다
    # 다른 숫자가 DB 에 앉는다(P09 5.8).
    #
    # **없는 것과 빈 것은 다르다.** 없으면 `None` 으로 넘겨 손대지 않고, 빈
    # 목록이면 "그린 것이 하나도 없다" 로 받아 지운다 — 둘을 같이 다루면
    # **그리기를 모르는 옛 탭의 저장 한 번**이 그린 개체를 전부 지운다.
    drawn = payload.get("drawn")
    if drawn is not None:
        if not isinstance(drawn, list) or len(drawn) > 500:
            return HttpResponseBadRequest("bad drawn")
        clean = []
        for it in drawn:
            if not isinstance(it, dict):
                return HttpResponseBadRequest("bad drawn item")
            cls = as_label(it.get("cls")) or ""
            # 코멘트는 여기서도 안 받는다 — 위 `notes` 와 같은 갈래다(0036).
            clean.append({"key": it.get("key"), "polygon": it.get("polygon"),
                          "cls": cls})
        drawn = clean

    # **사람이 고친 기하** (P09 4단계). `{키: 폴리곤}` 이고 **빈 폴리곤은
    # "엔진 것으로 되돌린다"** 는 말이다. 그린 개체(`drawn`)와 달리 엔진 개체의
    # 교정이라 묶음에 속한다 — `Candidate` 는 안 건드리고 교정 행의 `geom` 만
    # 덮는다(P09 5.6).
    edits = payload.get("edits")
    if edits is not None:
        if not isinstance(edits, dict) or len(edits) > 500:
            return HttpResponseBadRequest("bad edits")
        for v in edits.values():
            if not isinstance(v, list):
                return HttpResponseBadRequest("bad edits polygon")

    try:
        saved = data.save_review(vp, done=done, note=note, removed=removed,
                                 accepted=accepted, labels=labels,
                                 image=image_id, drawn=drawn, edits=edits)
    except ValueError as e:
        # 현재 검출에 없는 키가 섞여 왔다. 아무것도 바꾸지 않고 돌려보낸다 —
        # 그대로 두면 그 시야의 교정이 통째로 지워진다 (data.save_review 주석).
        return JsonResponse({"ok": False, "error": str(e)}, status=409)
    if saved is None:
        return HttpResponseBadRequest("unknown stem")
    return JsonResponse({"ok": True, "done": done, "note": bool(note), **saved})


# /healthz 가 "자료가 있다" 고 볼 테이블. 없으면 이 뷰어는 볼 것이 없는 상태다.
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
    flags = db_sentinel.read(settings.DIARUGA_DB)
    info["integrity_flags"] = flags
    if flags and info["status"] == "ok":
        info["status"] = "degraded"
    for f in flags:
        # **"백업 실패" 라고 적지 않는다.** 깃발을 세우는 주인이 백업만이 아니다 —
        # 폴러도 자동 처리 뒤 화면이 안 뜨면 여기 세운다(061). 원인을 짐작해 적으면
        # 엉뚱한 곳을 파게 만든다(026 에서 그렇게 4시간 반을 잃었다).
        notes.append(f"무결성 깃발 [{f['source']} {f['time']}] {f['reason']}")

    # 3) 백업 신선도. 문턱을 안 주면 알려만 준다 (settings.BACKUP_MAX_AGE_H 주석).
    age_h = None
    try:
        snaps = list(settings.BACKUP_DIR.glob("DiaRUGA_*.db"))
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
