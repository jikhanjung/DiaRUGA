import hashlib
import json
import math
import re
from urllib.parse import urlencode

from django.conf import settings
from django.http import (FileResponse, Http404, HttpResponse,
                         HttpResponseBadRequest, JsonResponse)
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import data

# 파일명으로 그대로 쓰이므로 경로 성분이 될 수 있는 문자를 막는다.
SAFE_STEM = re.compile(r"^[A-Za-z0-9._-]+$")

# 메모 길이 상한. 사람이 손으로 적는 것이라 넉넉하면 충분하다.
NOTE_MAX = 500


def index(request):
    return render(request, "viewer/index.html", {"datasets": data.datasets()})


def dataset(request, slug):
    ctx = data.dataset_detail(slug)
    if ctx is None:
        raise Http404(f"unknown dataset: {slug}")
    return render(request, "viewer/dataset.html", ctx)


def group(request, slug, gid):
    ctx = data.group_detail(slug, gid)
    if ctx is None:
        raise Http404(f"unknown group: {slug}/{gid}")
    return render(request, "viewer/group.html", ctx)


def _candidate_rows(slug, ds):
    """데이터셋 전체의 검출 개체를 한 목록으로 모은다.

    `image_rel` 은 검출 JSON 에 적힌 경로가 아니라 뷰어가 실제로 찾아낸
    파일의 상대경로다 — 크롭 요청이 그 경로로 이미지를 다시 열기 때문에,
    JSON 이 절대경로로 기록된 경우에도 어긋나지 않아야 한다.
    """
    rows = []
    for g in ds["groups"]:
        detail = data.group_detail(slug, g["id"])
        # 합성본 검출이 있으면 그쪽을, 없으면 각 프레임 검출을 훑는다.
        sources = []
        if detail["stack"] and detail["stack"]["detection"]:
            sources.append((detail["stack"]["stem"],
                            detail["stack"]["detection"],
                            detail["stack"]["focused_rel"]))
        else:
            sources += [
                (f["name"], f["detection"], f["rel"])
                for f in detail["frames"] if f["detection"]
            ]
        for stem, det, image_rel in sources:
            for c in det["candidates"]:
                rows.append(
                    {
                        "group_id": g["id"],
                        "stem": stem,
                        "overlay_rel": det.get("overlay_rel"),
                        "image_rel": image_rel,
                        "reviewed": det.get("review_done"),
                        "um_per_pixel": det.get("um_per_pixel"),
                        **c,
                    }
                )
    return rows


def detections(request, slug):
    """데이터셋 전체에서 검출된 후보를 한 표로 모아 크기 분포를 본다."""
    ds = data.dataset_detail(slug)
    if ds is None:
        raise Http404(f"unknown dataset: {slug}")

    rows = _candidate_rows(slug, ds)
    rows.sort(key=lambda r: -r["long_side_um"])
    sizes = [r["long_side_um"] for r in rows]
    summary = None
    if sizes:
        ordered = sorted(sizes)
        summary = {
            "n": len(sizes),
            "min": round(ordered[0], 1),
            "median": round(ordered[len(ordered) // 2], 1),
            "max": round(ordered[-1], 1),
            "mean": round(sum(ordered) / len(ordered), 1),
        }
    return render(
        request,
        "viewer/detections.html",
        {"slug": slug, "label": ds["label"], "rows": rows, "summary": summary},
    )


CROPS_PER_PAGE = 500


def crops(request, slug):
    """검출된 개체만 잘라 썸네일로 늘어놓는다.

    시야를 하나씩 넘겨보지 않고 "이것들이 정말 규조각인가" 를 한 화면에서
    훑을 수 있어야 한다. 크기 내림차순이라 의심스러운 것(작고 밋밋한 것)이
    뒤쪽에 모인다.
    """
    ds = data.dataset_detail(slug)
    if ds is None:
        raise Http404(f"unknown dataset: {slug}")

    rows = _candidate_rows(slug, ds)
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
            "label": ds["label"],
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
    문턱만 바꾸는 refilter.py 실행에는 영향받지 않는다.

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

    path = data.review_path(stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"stem": stem, "done": done, "note": note,
            "removed": removed, "accepted": accepted,
            "labels": labels, "notes": notes}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return JsonResponse({"ok": True, "done": done, "note": bool(note),
                         "removed": len(removed), "accepted": len(accepted),
                         "labels": len(labels), "notes": len(notes)})


def healthz(request):
    return HttpResponse("ok")
