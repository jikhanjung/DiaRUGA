import hashlib
import json
import re

from django.conf import settings
from django.http import (FileResponse, Http404, HttpResponse,
                         HttpResponseBadRequest, JsonResponse)
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import data

# 파일명으로 그대로 쓰이므로 경로 성분이 될 수 있는 문자를 막는다.
SAFE_STEM = re.compile(r"^[A-Za-z0-9._-]+$")


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


def detections(request, slug):
    """데이터셋 전체에서 검출된 후보를 한 표로 모아 크기 분포를 본다."""
    ds = data.dataset_detail(slug)
    if ds is None:
        raise Http404(f"unknown dataset: {slug}")

    rows = []
    for g in ds["groups"]:
        detail = data.group_detail(slug, g["id"])
        # 합성본 검출이 있으면 그쪽을, 없으면 각 프레임 검출을 훑는다.
        sources = []
        if detail["stack"] and detail["stack"]["detection"]:
            sources.append((detail["stack"]["stem"], detail["stack"]["detection"]))
        else:
            sources += [
                (f["name"], f["detection"]) for f in detail["frames"] if f["detection"]
            ]
        for stem, det in sources:
            for c in det["candidates"]:
                rows.append(
                    {
                        "group_id": g["id"],
                        "stem": stem,
                        "overlay_rel": det.get("overlay_rel"),
                        **c,
                    }
                )

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
        return FileResponse(path.open("rb"), content_type="image/jpeg")

    try:
        width = max(32, min(int(raw), 2048))
    except ValueError:
        raise Http404("bad width")

    thumb = _thumbnail(path, width)
    if thumb is None:
        return FileResponse(path.open("rb"), content_type="image/jpeg")
    return FileResponse(thumb.open("rb"), content_type="image/jpeg")


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
    교정 결과를 저장한다. {"stem": ..., "removed": [key], "accepted": [key]}

    키는 bbox 에서 만든 것이라 검출을 다시 돌려도 같은 마스크면 그대로 붙는다.
    문턱만 바꾸는 refilter.py 실행에는 영향받지 않는다.
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

    path = data.review_path(stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"stem": stem, "removed": removed, "accepted": accepted}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return JsonResponse({"ok": True, "removed": len(removed), "accepted": len(accepted)})


def healthz(request):
    return HttpResponse("ok")
