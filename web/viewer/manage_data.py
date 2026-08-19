"""관리 화면이 쓰는 것 — 층을 세어 보이고, 만들고, 고치고, 지운다.

**`data.py` 와 갈라 둔다.** 그쪽은 읽기 전용이고(DB → 뷰가 쓰는 dict) 이쪽은
쓰는 문이다. 한 파일에 섞으면 "이 함수가 쓰는가" 를 매번 확인해야 한다.

## 지우기에 문턱이 있다

`Slide.sample` 이 `SET_NULL` 이라 시료를 지우면 **관찰이 조용히 소속을 잃는다**
— 아침에 `BP09-0901 (1)` 이 그 상태였고, 500 도 404 도 아니어서 목록을 세어
보기 전에는 알 수가 없었다. 그래서:

- 딸린 것이 있으면 **막는다.** 사람이 먼저 옮기거나 지워야 한다
- 무엇이 몇 개 딸려 있는지 화면에 **미리** 적는다. 눌러 보고 알게 하지 않는다
- 관찰(`Slide`)은 여기서 안 지운다. 폴더가 만드는 것이고 그 아래에 **재생성
  불가한 교정**이 달려 있다 — 지우는 문을 아예 두지 않는다
"""
import re
from collections import Counter
from pathlib import Path

from django.db import transaction
from django.db.models import Count

from . import data
from .models import (CorePoint, CoreSeries,
                     Locality, ObjectReview, RunBatch, Sample, Site, Slide,
                     Viewpoint)


def overview() -> dict:
    """층 넷을 한 화면에 — 무엇이 몇 개이고 어디가 비었는가."""
    sites = list(Site.objects.annotate(n_loc=Count("localities", distinct=True))
                 .order_by("area", "code"))
    for s in sites:
        s.n_samples = Sample.objects.filter(locality__site=s).count()
        s.n_slides = Slide.objects.filter(sample__locality__site=s).count()

    locs = list(Locality.objects.select_related("site")
                .annotate(n_samples=Count("samples", distinct=True))
                .order_by("site__code", "code"))
    for c in locs:
        c.n_slides = Slide.objects.filter(sample__locality=c).count()

    samples = list(Sample.objects.select_related("locality__site")
                   .annotate(n_slides=Count("slides", distinct=True))
                   .order_by("locality__site__code", "locality__code",
                             "depth_cm", "sample_no", "code"))

    # 소속을 잃은 관찰. **이 화면이 있어야 하는 첫째 이유다** — 다른 어느 화면에도
    # 안 나온다(어느 권역 탭에도 안 걸린다). 붙일 곳을 추천까지 해서 낸다.
    orphans = []
    for sl in (Slide.objects.filter(sample__isnull=True)
               .order_by("name")):
        sib = next((s for s in sl.sibling_observations() if s.sample_id), None)
        orphans.append({"slide": sl, "suggest": sib.sample if sib else None,
                        "suggest_from": sib})
    return {"sites": sites, "localities": locs, "samples": samples,
            "orphans": orphans,
            "n_sites": len(sites), "n_locs": len(locs),
            "n_samples": len(samples),
            "n_slides": Slide.objects.count()}


def deletable(kind: str, pk: int) -> tuple[object | None, list[str]]:
    """지울 수 있는가. 돌려주는 것은 (행, 막는 이유들).

    **이유를 문자열로 돌려준다** — 화면이 "지울 수 없습니다" 만 내면 무엇을 먼저
    치워야 하는지 알 수 없다.
    """
    if kind == "site":
        obj = Site.objects.filter(pk=pk).first()
        if obj is None:
            return None, []
        n = obj.localities.count()
        return obj, ([f"지점 {n}개가 이 지역에 달려 있습니다"] if n else [])
    if kind == "locality":
        obj = Locality.objects.filter(pk=pk).first()
        if obj is None:
            return None, []
        why = []
        n = obj.samples.count()
        if n:
            why.append(f"시료 {n}개가 이 지점에 달려 있습니다")
        # **코어 자료도 센다** (P17). `CorePoint` 가 `CASCADE` 라 예외도 경고도
        # 없이 함께 지워진다 — 실제로 `RS19-GC17` 을 지워 27개 항목 10,795점이
        # 조용히 날아가는 것을 보고 넣었다. **새 코어는 시료가 0개라** 이 줄이
        # 없으면 문턱이 그냥 열린다.
        cs = list(obj.core_series.annotate(n_pts=Count("points"))
                  .values("source", "n_pts"))
        if cs:
            pts = sum(c["n_pts"] for c in cs)
            man = sum(1 for c in cs if c["source"] == "manual")
            line = f"코어 자료 {len(cs)}개 항목 · 점 {pts:,}개가 함께 지워집니다"
            if man:
                line += f" (그중 수동 {man}개는 다시 만들 수 없습니다)"
            why.append(line)
        return obj, why
    if kind == "sample":
        obj = Sample.objects.filter(pk=pk).first()
        if obj is None:
            return None, []
        n = obj.slides.count()
        # **`SET_NULL` 이라 지워도 예외가 안 난다** — 관찰이 조용히 소속을 잃을
        # 뿐이다. 막는 자리는 여기밖에 없다.
        return obj, ([f"관찰 {n}개가 이 시료를 보고 있습니다 "
                      f"(지우면 소속을 잃습니다)"] if n else [])
    return None, []


def delete(kind: str, pk: int) -> tuple[bool, str]:
    """지운다. 문턱을 통과할 때만."""
    obj, why = deletable(kind, pk)
    if obj is None:
        return False, "찾지 못했습니다."
    if why:
        return False, " · ".join(why)
    label = str(obj)
    obj.delete()
    return True, f"{label} 을(를) 지웠습니다."


def move_slide(slide_id: int, sample_id: int | None) -> tuple[bool, str]:
    """관찰의 소속을 옮긴다. `sample_id` 가 없으면 떼어 낸다.

    **떼어 내는 것도 길로 둔다.** 잘못 붙은 것을 고치려면 일단 떼야 할 때가 있고,
    막아 두면 사람이 시료를 지워서 떼려 든다 — 그쪽이 훨씬 위험하다.
    """
    sl = Slide.objects.filter(pk=slide_id).first()
    if sl is None:
        return False, "관찰을 찾지 못했습니다."
    if sample_id:
        sm = Sample.objects.select_related("locality__site").filter(
            pk=sample_id).first()
        if sm is None:
            return False, "시료를 찾지 못했습니다."
        sl.sample = sm
        sl.save(update_fields=["sample"])
        return True, f"{sl.name} 을(를) {sm} 에 붙였습니다."
    sl.sample = None
    sl.save(update_fields=["sample"])
    return True, f"{sl.name} 의 소속을 뗐습니다."


def move_sample(sample_id: int, locality_id: int) -> tuple[bool, str]:
    """시료를 다른 지점으로 옮긴다. 딸린 관찰이 함께 간다.

    **같은 코드가 이미 그 지점에 있으면 막는다.** `(locality, code)` 가 유일
    제약이라 그냥 저장하면 IntegrityError 로 죽는데, 그 화면에는 무엇이 부딪혔는지
    가 안 나온다.
    """
    sm = Sample.objects.filter(pk=sample_id).first()
    loc = Locality.objects.filter(pk=locality_id).first()
    if sm is None or loc is None:
        return False, "찾지 못했습니다."
    if Sample.objects.filter(locality=loc, code=sm.code).exclude(
            pk=sm.pk).exists():
        return False, f"{loc} 에 이미 시료 {sm.code} 가 있습니다."
    n = sm.slides.count()
    with transaction.atomic():
        sm.locality = loc
        sm.save(update_fields=["locality"])
    return True, f"시료 {sm.code} 를 {loc} 로 옮겼습니다 (관찰 {n}개 함께)."


def create(kind: str, data: dict) -> tuple[bool, str]:
    """지역·지점·시료를 새로 만든다. 관찰은 여기서 안 만든다 — 폴더가 만든다."""
    try:
        if kind == "site":
            code = (data.get("code") or "").strip()
            if not code:
                return False, "지역 코드가 비었습니다."
            if Site.objects.filter(code=code).exists():
                return False, f"지역 {code} 가 이미 있습니다."
            area = (data.get("area") or "").strip()
            Site.objects.create(
                code=code, name=(data.get("name") or "").strip(),
                region=(data.get("region") or "").strip(),
                area=area if area in dict(Site.AREA) else "ant")
            return True, f"지역 {code} 를 만들었습니다."
        if kind == "locality":
            site = Site.objects.filter(pk=data.get("site")).first()
            code = (data.get("code") or "").strip()
            if site is None or not code:
                return False, "지역과 지점 코드가 필요합니다."
            if Locality.objects.filter(site=site, code=code).exists():
                return False, f"{site.code} 에 지점 {code} 가 이미 있습니다."
            # **`kind` 가 아니라 `locality_kind` 다.** 같은 폼의 숨은
            # 칸이 층 이름을 `kind` 로 나른다 — 겹치면 Django 가 뒤엣것을
            # 집어 "모르는 층" 이 된다.
            k = (data.get("locality_kind") or "").strip()
            Locality.objects.create(
                site=site, code=code,
                kind=k if k in dict(Locality.KIND) else "core")
            return True, f"지점 {site.code}-{code} 를 만들었습니다."
        if kind == "sample":
            loc = Locality.objects.filter(pk=data.get("locality")).first()
            code = (data.get("code") or "").strip()
            if loc is None or not code:
                return False, "지점과 시료 코드가 필요합니다."
            if Sample.objects.filter(locality=loc, code=code).exists():
                return False, f"{loc} 에 시료 {code} 가 이미 있습니다."
            # 위치 칸은 지점 유형이 고른다 — 아닌 칸에 값이 들어가면
            # `check_db.py` 7번이 잡는다. 애초에 안 들어가게 여기서 가른다.
            depth = _num(data.get("depth_cm"))
            no = _num(data.get("sample_no"), int)
            Sample.objects.create(
                locality=loc, code=code,
                depth_cm=None if loc.kind == "outcrop" else depth,
                sample_no=no if loc.kind == "outcrop" else None)
            return True, f"시료 {loc}-{code} 를 만들었습니다."
    except ValueError as e:
        return False, f"값을 읽지 못했습니다: {e}"
    return False, "모르는 층입니다."


def _num(raw, cast=float):
    raw = (raw or "").strip()
    return cast(raw) if raw else None


# --- 검토할 묶음 (P10 3단계) ------------------------------------------------

def batch_choices() -> list[dict]:
    """고를 수 있는 묶음들과 **고르면 무엇이 달라지는지.**

    **누르기 전에 보인다.** 063 이 "지우기 문턱은 눌러 보기 전에 보여야 한다" 를
    배운 자리와 같다 — 바꾸고 나서 "시야 56개가 비었다" 를 알면 늦다.

    줄마다 셋을 센다:

    | 칸 | 무엇 |
    |---|---|
    | `n_views` | 이 묶음이 덮는 시야 수 |
    | `n_blank` | **이 묶음에 검출이 없어 빈 화면이 될 시야** |
    | `n_objects` | 이 묶음이 낸 개체 수 (엔진이 낸 그대로 — 교정 전) |

    검출이 있는 묶음만 낸다. 빈 묶음을 고르면 화면이 통째로 비는데, 그것을
    고를 이유가 없다.
    """
    from .models import Candidate, Detection, RunBatch, Viewpoint

    total = Viewpoint.objects.count()
    out = []
    for b in RunBatch.objects.filter(kind="detect").order_by("-started_at"):
        dets = Detection.objects.filter(run__batch=b, is_current=True)
        n_views = dets.values("viewpoint_id").distinct().count()
        if not n_views:
            continue
        out.append({
            "batch": b,
            "on": b.for_review,
            "n_views": n_views,
            "n_blank": total - n_views,
            "n_images": dets.count(),
            "n_objects": Candidate.objects.filter(detection__in=dets,
                                                  passed=True).count(),
        })
    return out


def set_review_batch(batch_id: int) -> tuple[bool, str]:
    """검토할 묶음을 바꾼다. **자료는 안 건드린다 — 깃발 하나다.**

    그래서 **되돌리기가 같은 동작**이다. 예전 계획(P09 5단계)은 검출 2,132행을
    UPDATE 하는 것이었는데, 사본에서 해 보니 YOLO 가 없는 56 시야가 현재 검출을
    잃고 빈 화면이 됐다 — 되돌리려면 또 한 번의 대량 UPDATE 였다(P10 §1).

    **서버가 다시 검사한다.** 화면이 고를 수 없게 해 두어도 그것은 막는 것이
    아니다 — 051·027 이 그 자리에서 났다.
    """
    from .models import Detection, Run, RunBatch

    b = RunBatch.objects.filter(pk=batch_id, kind="detect").first()
    if b is None:
        return False, "그런 묶음이 없습니다."
    if b.for_review:
        return False, f"{b.label} 은 이미 검토 대상입니다."
    # **검출이 없는 묶음은 안 받는다.** 고르면 화면이 통째로 빈다.
    n_views = (Detection.objects.filter(run__batch=b, is_current=True)
               .values("viewpoint_id").distinct().count())
    if not n_views:
        return False, f"{b.label} 에는 검출이 없습니다 — 먼저 돌려야 합니다."

    was = RunBatch.objects.filter(for_review=True).first()
    with transaction.atomic():
        # 유일 제약이 하나만 허용하므로 **끄고 켠다** — 순서가 뒤바뀌면 막힌다.
        RunBatch.objects.filter(for_review=True).update(for_review=False)
        RunBatch.objects.filter(pk=b.pk).update(for_review=True)
        # 누가 언제 어디서 어디로 — 되짚을 수 있어야 한다.
        Run.objects.create(
            kind="reconcile", batch=b, status="done",
            params={"action": "set_review_batch",
                    "from": was.label if was else None, "to": b.label},
            counts={"views": n_views})
    return True, (f"검토할 묶음을 {b.label} 로 바꿨습니다 — 시야 {n_views}개. "
                  f"판정 캐시가 어긋날 수 있으니 refilter.py 를 돌리십시오.")


# --- 운영: 조리법 ------------------------------------------------------------
# 조리법에 담는 것. `segment_diatoms.py` 의 인자와 이름이 같다 — 화면에서 고친
# 값이 그대로 명령줄이 되므로 여기서 이름을 바꾸면 안 된다 (`batch_plan.py`).
RECIPE_NUM = ("scale", "min_um", "max_um", "yolo_conf", "yolo_imgsz")
BACKENDS = ("sam2", "yolo")


def create_batch(form) -> tuple[bool, str]:
    """새 검출 묶음을 만든다 (084).

    지금까지 묶음은 **파이프라인이 `--batch` 로 처음 쓸 때** 생겼다. 그래서
    "다음 회차를 이렇게 돌리겠다" 를 미리 적어 둘 수가 없었다 — 조리법을 적으려면
    묶음이 먼저 있어야 하는데, 묶음을 만들려면 검출을 한 번 돌려야 했다.

    **조리법을 베껴 올 수 있다.** 새 회차는 대개 지난 회차에서 가중치만 바뀐
    것이라, 빈 칸에서 시작하면 배율·크기 문턱 같은 것을 옮겨 적다가 틀린다.

    **만드는 것으로 자료가 생기지는 않는다.** 새 슬라이드가 들어오면 폴러가
    채우지만, **이미 있는 슬라이드는 사람이 한 번 돌려야 한다** — 몇 시간짜리
    GPU 작업이라 화면이 조용히 시작하면 안 된다. 그 말을 응답에 담는다.
    """
    label = (form.get("label") or "").strip()
    if not label:
        return False, "묶음 이름을 적어 주십시오."
    if RunBatch.objects.filter(kind="detect", label=label).exists():
        return False, f"이미 있는 이름입니다: {label}"

    recipe = {}
    src_id = (form.get("copy_from") or "").strip()
    src = None
    if src_id:
        src = RunBatch.objects.filter(pk=src_id).first()
        if src is None:
            return False, "베껴 올 묶음을 찾지 못했습니다."
        recipe = dict(src.recipe or {})
        # 베낀 것에는 **추측 표시를 물려주지 않는다** — 새 묶음의 가중치는
        # 사람이 다시 보는 것이 맞고, 물려주면 경고가 영영 따라다닌다.
        recipe.pop("weights_guessed", None)

    b = RunBatch.objects.create(kind="detect", label=label,
                                note=(form.get("note") or "").strip(),
                                recipe=recipe)
    tail = ""
    if src is not None:
        tail = f" ({src.label} 의 조리법을 베꼈습니다)"
    if not recipe:
        tail += " 조리법이 비어 있어 아직 자동으로 돌지 않습니다."
    return True, (f"묶음 {b.label} 을 만들었습니다.{tail} "
                  f"이미 있는 슬라이드는 사람이 한 번 돌려야 합니다.")


def set_recipe(batch_id: int, form) -> tuple[bool, str]:
    """묶음의 조리법을 적는다 (083).

    **엔진이 비면 조리법을 통째로 비운다** = 그 묶음은 자동으로 안 돈다. 끝난
    회차를 그대로 두는 것이 기본이고, 묶음이 늘 때마다 GPU 시간이 곱으로 늘기
    때문이다.

    **가중치 파일이 없어도 저장은 받는다.** 아직 학습이 안 끝났는데 조리법을
    먼저 적어 둘 수 있어야 한다 — 대신 목록에서 "못 돌림" 으로 뜬다. 저장을
    막으면 사람이 파일을 만들 때까지 아무것도 적어 둘 수 없다.
    """
    b = RunBatch.objects.filter(pk=batch_id).first()
    if b is None:
        return False, "그런 묶음이 없습니다."

    backend = (form.get("backend") or "").strip()
    if not backend:
        if not b.recipe:
            return False, f"{b.label} 은 이미 자동으로 돌지 않습니다."
        b.recipe = {}
        b.save(update_fields=["recipe"])
        return True, f"{b.label} 의 조리법을 비웠습니다 — 자동으로 돌지 않습니다."
    if backend not in BACKENDS:
        return False, f"모르는 엔진입니다: {backend}"

    recipe = {"backend": backend}
    for k in RECIPE_NUM:
        raw = (form.get(k) or "").strip()
        if not raw:
            continue
        try:
            recipe[k] = float(raw) if "." in raw or k == "scale" else int(raw)
        except ValueError:
            return False, f"{k} 가 숫자가 아닙니다: {raw}"
    w = (form.get("weights") or "").strip()
    if w:
        recipe["weights"] = w
    if form.get("all_images"):
        recipe["all_images"] = True

    if backend == "yolo" and not recipe.get("weights"):
        return False, "YOLO 는 가중치가 있어야 합니다."

    b.recipe = recipe
    b.save(update_fields=["recipe"])
    # 파일이 없으면 **저장은 되었지만 못 돈다** — 그것을 여기서 말해 준다.
    from django.conf import settings                                # noqa: PLC0415
    if backend == "yolo":
        path = Path(w) if Path(w).is_absolute() else Path(settings.DATA_ROOT) / w
        if not path.exists():
            return True, (f"{b.label} 의 조리법을 적었습니다 — 다만 가중치 파일이 "
                          f"아직 없습니다({path}). 생기기 전까지는 안 돕니다.")
    return True, f"{b.label} 의 조리법을 적었습니다."


def batches_with_recipe() -> list:
    """조리법 화면이 쓰는 목록 — **검출 묶음 전부**. 조리법이 없는 것도 낸다.

    `batch_choices()` 는 "고를 수 있는 것" 이라 검출이 있는 것만 내는데, 여기는
    **아직 아무것도 안 돌린 새 묶음에도 조리법을 적어야** 하므로 다르다.
    """
    rows = list(RunBatch.objects.filter(kind="detect")
                .annotate(n_detections=Count("runs__detections", distinct=True))
                .order_by("-for_review", "-started_at"))
    return rows


# --- 학습 자료 ---------------------------------------------------------------
def training_overview() -> dict:
    """검토한 것에서 **정답을 얼마나 뽑을 수 있는가** (083).

    `export_yolo.py` 가 쓰는 것과 **같은 기준**으로 센다 — 검토 중인 묶음에서
    검토 완료로 표시한 시야. 다른 기준으로 세면 화면이 "1,046개" 라고 하는데
    내보내면 다른 수가 나오고, 그때 어느 쪽이 맞는지 알 수가 없다.

    슬라이드별로 나누는 이유는 `--holdout-slide` 때문이다. 한 슬라이드가 자료의
    절반을 넘으면 그것을 빼야 검증이 뜻을 갖는다(P04).
    """
    rb = data.review_batch_id()
    label = data.review_batch_label()
    if rb is None:
        return {"batch": "", "n_viewpoints": 0, "slides": [], "n_objects": 0,
                "classes": [], "n_removed": 0}

    done = list(Viewpoint.objects
                .filter(reviews__done=True, reviews__batch_id=rb)
                .select_related("slide").distinct())
    per_slide, n_obj, cls = {}, 0, Counter()
    for vp in done:
        d = data.detection_for_viewpoint(vp)
        row = per_slide.setdefault(vp.slide.slug,
                                   {"slug": vp.slide.slug, "label": vp.slide.name,
                                    "n_viewpoints": 0, "n_objects": 0})
        row["n_viewpoints"] += 1
        if d:
            n = len(d.get("candidates") or [])
            row["n_objects"] += n
            n_obj += n
            for c in d.get("candidates") or []:
                if c.get("cls"):
                    cls[c["cls"]] += 1

    labels = data._labels()
    n_removed = ObjectReview.objects.filter(
        viewpoint__in=done, batch_id=rb, removed=True).count()
    rows = sorted(per_slide.values(), key=lambda r: -r["n_viewpoints"])
    for r in rows:
        # **비중을 여기서 낸다.** 한 슬라이드가 절반을 넘는지가 holdout 을 고르는
        # 근거인데(P04), 템플릿에서는 나눗셈을 못 한다.
        r["share"] = round(r["n_viewpoints"] / max(len(done), 1) * 100)
    return {
        "batch": label,
        "n_viewpoints": len(done),
        "n_objects": n_obj,
        "n_removed": n_removed,
        "classes": [{"key": k, "label": labels.get(k, k), "n": v}
                    for k, v in sorted(cls.items(), key=lambda kv: -kv[1])],
        "slides": rows,
    }


# --- 코어 자료를 사람이 넣는다 (P17 5단계) ---------------------------------
#
# **반입이 건드리는 것과 겹치지 않는다.** `ops/import_coredata.py` 는
# `source='import'` 인 항목만 갈아치우고, 여기서 만드는 것은 전부 `manual` 이다.
# 그 선이 지켜져야 재반입 한 번에 사람이 넣은 값이 안 지워진다.
#
# **층이 다른 것을 한 문으로 받지 않는다** (116). 항목의 속성(이름·단위·기본
# 켜기)과 점 목록은 요청을 가른다 — 이름 한 글자를 고치는 일이 그 항목의 점을
# 갈아치우는 일이 되면 안 된다.

# `key` 는 주소에 실린다(`?series=`). 영문 소문자로 시작하는 식별자만 받는다.
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

# 한 번에 붙여넣을 수 있는 줄 수. 반입기가 내는 가장 큰 항목이 3,575점이라
# 그보다 넉넉히 잡되, 실수로 파일 통째를 붙였을 때는 멈춘다.
MAX_PASTE_LINES = 20000


def parse_points(text: str) -> dict:
    """붙여넣은 것을 `(깊이 mm, 값)` 으로 읽는다. **규칙은 여기 하나뿐이다.**

    화면에서 미리 보이는 것과 저장하는 것이 **같은 파서를 지나야 한다** — 둘로
    나누면 "미리 보기에서는 되는데 저장하면 다르다" 가 생긴다.

    받는 꼴은 `깊이 값` 두 칸이고 사이는 탭·쉼표·빈칸 아무거나다(엑셀에서 두
    칸을 긁으면 탭이다). 깊이는 **cm** 로 받아 mm 정수로 든다 —
    `CorePoint` 가 그렇게 들고, 바꾸는 자리를 늘리지 않는다.

    **버린 줄을 세어서 돌려준다.** 조용히 건너뛰면 몇 점이 왜 안 들어왔는지
    알 수가 없다 — 붙여넣기는 머리글이 따라오는 일이 흔하다.
    """
    rows: dict[int, float] = {}
    skipped: list[str] = []
    clash: list[str] = []
    n_lines = 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        n_lines += 1
        if n_lines > MAX_PASTE_LINES:
            skipped.append(f"{i}행부터: 한 번에 {MAX_PASTE_LINES}줄까지입니다")
            break
        parts = [t for t in re.split(r"[\t,;\s]+", line) if t]
        if len(parts) < 2:
            skipped.append(f"{i}행: 칸이 둘이 아닙니다 ({line[:24]})")
            continue
        try:
            cm, val = float(parts[0]), float(parts[1])
        except ValueError:
            skipped.append(f"{i}행: 숫자가 아닙니다 ({line[:24]})")
            continue
        if cm < 0:
            skipped.append(f"{i}행: 깊이가 음수입니다 ({parts[0]})")
            continue
        mm = round(cm * 10)
        if mm in rows and rows[mm] != val:
            # 반입기(`read_block`)와 같은 규칙이다 — 같은 값이면 한 번만 넣고,
            # 다르면 어느 쪽이 맞는지 사람이 정한다.
            clash.append(f"{cm:g} cm: {rows[mm]:g} 와 {val:g}")
            continue
        rows[mm] = val
    return {"rows": rows, "skipped": skipped, "clash": clash}


def _manual_series(loc: Locality, key: str) -> tuple[CoreSeries | None, str]:
    """사람이 넣은 항목만 내준다.

    **반입 항목에는 점을 못 넣는다.** 넣어 봐야 다음 반입에 지워지는데, 그때
    조용히 사라지면 왜 없어졌는지 알 길이 없다 — 아예 못 하게 하고 이유를 적는다.
    """
    cs = CoreSeries.objects.filter(locality=loc, key=key).first()
    if cs is None:
        return None, f"{loc} 에 항목 {key} 가 없습니다."
    if cs.source != "manual":
        return None, (f"{cs.label} 은 xlsx 에서 반입한 항목이라 여기서 못 고칩니다 "
                      f"— 다시 반입하면 지워집니다. 원본을 고치고 다시 반입하세요.")
    return cs, ""


def preview_points(loc: Locality, key: str, text: str) -> tuple[bool, dict]:
    """저장하면 무엇이 일어나는가. **아무것도 안 쓴다.**

    누르기 전에 보여야 하는 것은 셋이다 — 몇 점이 새로 들어오고, 몇 점이
    이미 있는 깊이를 **덮고**, 몇 줄이 버려지는가 (063 의 지우기 문턱과 같은 줄).
    """
    cs, err = _manual_series(loc, key)
    if cs is None:
        return False, {"error": err}
    got = parse_points(text)
    have = set(CorePoint.objects.filter(series=cs)
               .values_list("depth_mm", flat=True))
    new = [mm for mm in got["rows"] if mm not in have]
    over = [mm for mm in got["rows"] if mm in have]
    depths = sorted(got["rows"])
    return True, {
        "series": cs, "n_have": len(have),
        "n_new": len(new), "n_over": len(over),
        # 갈아치우기를 고르면 이만큼이 사라진다
        "n_gone": len(have - set(got["rows"])),
        "skipped": got["skipped"], "clash": got["clash"],
        "range_cm": (depths[0] / 10, depths[-1] / 10) if depths else None,
        "sample": [(mm / 10, got["rows"][mm]) for mm in depths[:5]],
        "text": text,
    }


def save_points(loc: Locality, key: str, text: str,
                replace: bool) -> tuple[bool, str]:
    """붙여넣은 점을 넣는다. **항목 하나만 건드리는 좁은 문이다.**

    `/review` 처럼 범위를 갈아치우지 않는다 — 017·027·053 계열의 사고가
    구조적으로 안 생긴다.

    **서버가 다시 검사한다.** 미리 보기가 막았다고 여기서 안 보면, 화면을 안
    거친 요청 하나로 그대로 들어온다 (화면에서 막는 것은 막는 것이 아니다).
    """
    cs, err = _manual_series(loc, key)
    if cs is None:
        return False, err
    got = parse_points(text)
    if got["clash"]:
        return False, ("같은 깊이에 값이 둘입니다 — 어느 쪽인지 정해 주세요: "
                       + " · ".join(got["clash"][:3]))
    if not got["rows"]:
        return False, "넣을 점이 없습니다." + (
            " " + got["skipped"][0] if got["skipped"] else "")
    with transaction.atomic():
        if replace:
            CorePoint.objects.filter(series=cs).delete()
            CorePoint.objects.bulk_create(
                [CorePoint(series=cs, depth_mm=mm, value=v)
                 for mm, v in sorted(got["rows"].items())], batch_size=2000)
        else:
            have = dict(CorePoint.objects.filter(
                series=cs, depth_mm__in=list(got["rows"]))
                .values_list("depth_mm", "id"))
            CorePoint.objects.bulk_create(
                [CorePoint(series=cs, depth_mm=mm, value=v)
                 for mm, v in sorted(got["rows"].items()) if mm not in have],
                batch_size=2000)
            for mm, pk in have.items():
                CorePoint.objects.filter(pk=pk).update(value=got["rows"][mm])
    n = CorePoint.objects.filter(series=cs).count()
    tail = f" ({len(got['skipped'])}줄은 못 읽어 버렸습니다)" if got["skipped"] else ""
    return True, f"{cs.label} 에 {len(got['rows'])}점을 넣었습니다 — 이제 {n}점입니다.{tail}"


def create_series(loc: Locality, form) -> tuple[bool, str]:
    """측정 항목을 하나 만든다. **언제나 `manual` 이다.**

    **`key` 는 받아서 소문자로 낮춘다.** 기계 이름이라 대소문자를 가릴 이유가
    없고, 화면에 뜨는 것은 `label` 이다. 다만 **화면의 `pattern` 도 같은 것을
    받아야 한다** — 폼이 막는데 서버가 받으면 둘이 다른 말을 하는 것이고,
    그 어긋남은 나중에 어느 쪽이 규칙인지 모르게 만든다.
    """
    key = (form.get("key") or "").strip().lower()
    label = (form.get("label") or "").strip()
    if not KEY_RE.match(key):
        return False, "이름표(key)는 영문 소문자로 시작하고 영문·숫자·밑줄만 씁니다."
    # **파생 항목과 같은 이름을 못 쓴다** (P17 6절). 같은 `key` 가 둘이면
    # 화면이 어느 쪽을 그리는지가 정렬 순서에 달린다 — 예외도 경고도 없다.
    if key.startswith(data.DERIVED_PREFIX):
        return False, (f"`{data.DERIVED_PREFIX}` 로 시작하는 이름표는 "
                       f"관찰에서 세어 오는 항목의 자리입니다.")
    if not label:
        return False, "화면에 뜰 이름이 필요합니다."
    if CoreSeries.objects.filter(locality=loc, key=key).exists():
        return False, f"{loc} 에 항목 {key} 가 이미 있습니다."
    CoreSeries.objects.create(
        locality=loc, key=key, label=label,
        unit=(form.get("unit") or "").strip()[:24], source="manual",
        default_on=bool(form.get("default_on")),
        # 반입 항목(10~900) 뒤에 놓는다. 사람이 넣은 것이 목록 끝에 모인다
        sort_order=950,
        note=(form.get("note") or "").strip())
    return True, f"항목 {label} 을 만들었습니다 — 이제 점을 넣으세요."


def update_series(loc: Locality, key: str, form) -> tuple[bool, str]:
    """항목의 속성만 고친다. **점은 안 건드린다** (116)."""
    cs, err = _manual_series(loc, key)
    if cs is None:
        return False, err
    label = (form.get("label") or "").strip()
    if not label:
        return False, "화면에 뜰 이름이 필요합니다."
    cs.label = label
    cs.unit = (form.get("unit") or "").strip()[:24]
    cs.default_on = bool(form.get("default_on"))
    cs.note = (form.get("note") or "").strip()
    cs.save(update_fields=["label", "unit", "default_on", "note"])
    return True, f"항목 {cs.label} 을 고쳤습니다."


def delete_series(loc: Locality, key: str) -> tuple[bool, str]:
    """항목을 지운다. 점도 함께 간다 (FK CASCADE).

    **지우는 것은 고치는 것과 다르다.** 반입 항목을 고치면 다음 반입이 덮어
    헛일이 되지만, 지우는 것은 **다시 반입하면 그대로 돌아온다.** 그리고 막아
    두면 반입 자료가 붙은 지점을 영영 못 지운다 — 지우기 문턱이 코어 자료를
    세기 시작했으므로(위 `deletable`) 치울 길이 있어야 한다.

    **몇 점이 함께 지워지는지 화면이 먼저 말한다** (063). 여기서는 지운 수를
    적어 되돌릴 수 없다는 것이 드러나게 한다.
    """
    cs = CoreSeries.objects.filter(locality=loc, key=key).first()
    if cs is None:
        return False, f"{loc} 에 항목 {key} 가 없습니다."
    n = CorePoint.objects.filter(series=cs).count()
    label, src = cs.label, cs.source
    cs.delete()
    tail = " 다시 반입하면 돌아옵니다." if src == "import" else ""
    return True, f"항목 {label} 과 점 {n}개를 지웠습니다.{tail}"
