#!/usr/bin/env python3
"""DB 의 무결성을 검사한다. **예외가 나지 않고 그냥 틀린 상태**를 잡는 것이 목적이다.

    python check_db.py
    python check_db.py --slide rs23
    python check_db.py -v          # 어긋난 것의 예를 보여준다

`verify_db.py` 와 다르다. 그쪽은 이전이 맞았는지 **JSON 과 대조**하는 것이고 7단계
(JSON 을 원본에서 내리기)가 끝나면 역할이 사라진다. 이쪽은 JSON 과 무관하게
**DB 스스로 앞뒤가 맞는가**를 보므로 계속 유효하다.

여기서 잡는 종류는 화면만 봐서는 알 수 없다. 개수도 그럴듯하고 예외도 나지 않는데
숫자가 틀린다 — 그리고 그 숫자가 논문에 실릴 개수다.

돌려야 할 때:
  - `refilter`·`segment_diatoms` 를 돌린 뒤
  - `judge.py` 의 판정 규칙을 고친 뒤 (재판정을 잊으면 옛 결과가 남는다)
  - 이상한 숫자를 봤을 때
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diatomweb.settings")
django.setup()

from django.db.models import Count                                  # noqa: E402

import judge                                                        # noqa: E402
from viewer.models import (Candidate, ClassDef, Detection, Frame,    # noqa: E402
                           ObjectReview, Slide, Stack, Viewpoint,
                           ViewpointReview)

VERBOSE = False
problems = []


def report(name, bad, total, why="", examples=()):
    """검사 하나의 결과. bad 가 0 이어야 한다."""
    ok = bad == 0
    mark = "  " if ok else "!!"
    print(f"{mark} {name:46s} {'OK' if ok else f'{bad}건'}"
          f"{'' if ok else '  <-- ' + why}")
    if not ok:
        problems.append((name, bad, why))
        if VERBOSE:
            for e in list(examples)[:5]:
                print(f"       {e}")
    return ok


def dets(slug=None):
    qs = (Detection.objects.filter(is_current=True)
          .select_related("thresholds", "viewpoint", "viewpoint__slide"))
    if slug:
        qs = qs.filter(viewpoint__slide__slug=slug)
    return qs


# --- 1. 판정이 (지표 + 문턱) 과 맞는가 --------------------------------------
def check_verdicts(slug=None):
    """`passed`·`cls`·`reject` 는 저장된 사실이 아니라 **순수 함수의 캐시**다.

    지표(불변) + 문턱(파라미터) 이면 판정이 결정된다. 그러니 다시 계산해서 저장된
    값과 같아야 한다. 어긋나는 경우:

      - refilter 가 도는 중에 끊겼다 (일부만 새 문턱)
      - Detection.thresholds 만 바꾸고 Candidate 를 안 고쳤다 (또는 반대)
        -> "1500 이라고 적혀 있는데 실제 판정은 2000 짜리" 가 된다
      - judge.py 의 규칙을 고치고 재판정을 잊었다 -> 옛 규칙의 결과가 남는다
    """
    bad = total = 0
    ex = []
    for det in dets(slug).prefetch_related("candidates"):
        th = judge.Thresholds(**(det.thresholds.as_dict() if det.thresholds
                                 else judge.DEFAULTS))
        cands = list(det.candidates.all())
        total += len(cands)
        recs = [{
            "_pk": c.pk, "bbox_xywh": c.bbox_xywh, "area_px": c.area_px,
            "shape_ok": c.shape_ok, "major_um": c.major_um, "texture": c.texture,
            "elongation": c.elongation, "ellipse_iou": c.ellipse_iou,
            "solidity": c.solidity,
        } for c in cands]
        kept, rejected = judge.apply(recs, th)
        want = {r["_pk"]: (True, r["cls"] or "", "") for r in kept}
        for r in rejected:
            want[r["_pk"]] = (False, r.get("cls") or "", r["reject"])

        for c in cands:
            w = want.get(c.pk)
            if w is None:
                continue
            got = (c.passed, c.cls or "", c.reject or "")
            if got != w:
                bad += 1
                if len(ex) < 5:
                    ex.append(f"{det.viewpoint} {c.mask_key}: 저장 {got} != 계산 {w}")
    report("판정 == 지표 + 문턱 (캐시가 맞는가)", bad, total,
           "재판정이 필요하다: python refilter.py", ex)


# --- 2. 시야마다 현재 검출이 정확히 하나인가 ---------------------------------
def check_current(slug=None):
    """뷰어는 `is_current=True` 인 것만 본다. 둘이면 어느 것을 보여줄지 모르고,
    없으면 검출이 사라진 것처럼 보인다. 6단계에서 깨지기 쉬운 자리다."""
    qs = Viewpoint.objects.all()
    if slug:
        qs = qs.filter(slide__slug=slug)
    counts = dict(Detection.objects.filter(is_current=True,
                                           viewpoint__in=qs)
                  .values_list("viewpoint").annotate(n=Count("id")))
    many = [vp for vp in qs if counts.get(vp.id, 0) > 1]
    report("시야마다 현재 검출이 하나 이하", len(many), qs.count(),
           "is_current 가 둘 이상이다 — 어느 것을 보여줄지 알 수 없다",
           [f"{vp}: {counts[vp.id]}개" for vp in many])

    # 검출이 아예 없는 시야는 정상일 수 있다(아직 안 돌린 것). 세어만 둔다.
    none = [vp for vp in qs if counts.get(vp.id, 0) == 0]
    if none:
        print(f"     (검출이 없는 시야 {len(none)}개 — 아직 돌리지 않았다면 정상)")


# --- 3. 교정이 실제 개체에 붙어 있는가 ---------------------------------------
def check_reviews(slug=None):
    """교정이 현재 검출의 개체를 가리키고 있는가.

    **`mask_key` 가 맞는지로 보면 안 된다.** 검출을 다시 돌리면 SAM2 가 미세하게
    다른 마스크를 내서 키가 어긋나는데, 그때 `rebind.py` 가 IoU 로 다시 맺어 준다
    (실측: 재검출 한 번에 67건 중 exact 26 · iou 40 · 고아 1). 키만 보면 정상적으로
    맺힌 40건이 전부 고아로 잡힌다.

    진짜 고아는 **가리키는 개체가 아예 없는 것**이다. 지우지 않는다 —
    재생성 불가한 자료이고 `geom` 에 기하를 스스로 들고 있다.
    """
    qs = ObjectReview.objects.select_related("viewpoint")
    if slug:
        qs = qs.filter(viewpoint__slide__slug=slug)
    reviews = list(qs)

    # 현재 검출에 속한 개체 id 집합. 교정이 이 밖을 가리키면 옛 검출에 남은 것이다.
    current = set(Candidate.objects.filter(
        detection__is_current=True,
        **({"detection__viewpoint__slide__slug": slug} if slug else {})
    ).values_list("id", flat=True))

    orphan, mismatch, nogeom = [], [], []
    for o in reviews:
        if o.candidate_id is None:
            orphan.append(o)
        elif o.candidate_id not in current:
            mismatch.append(o)
        if not o.geom:
            nogeom.append(o)

    report("교정이 현재 검출에 붙어 있다", len(orphan), len(reviews),
           "고아 교정 — 지우지 말 것. 8단계(고아 화면)에서 다시 맺는다",
           [f"{o.viewpoint} {o.mask_key}" for o in orphan])
    report("교정의 candidate 링크가 맞다", len(mismatch), len(reviews),
           "옛 검출의 개체를 가리킨다 — 재바인딩이 중간에 끊겼는가",
           [f"{o.viewpoint} {o.mask_key}" for o in mismatch])
    report("교정이 기하(geom)를 갖고 있다", len(nogeom), len(reviews),
           "검출기가 바뀌면 그릴 것이 없어진다 (P02 §2.7)",
           [f"{o.viewpoint} {o.mask_key}" for o in nogeom])

    # bind_method 분포는 정보로만
    dist = Counter(o.bind_method for o in reviews)
    print(f"     바인딩: {dict(dist)}")


# --- 4. 분류가 정의된 것인가 -------------------------------------------------
def check_classes(slug=None):
    """`ClassDef` 에 없는 분류가 붙어 있으면 화면에서 이름도 색도 없이 나온다."""
    known = set(ClassDef.objects.values_list("key", flat=True))
    qs = Candidate.objects.filter(detection__is_current=True).exclude(cls="")
    if slug:
        qs = qs.filter(detection__viewpoint__slide__slug=slug)
    used = Counter(qs.values_list("cls", flat=True))
    bad = {k: v for k, v in used.items() if k not in known}
    report("개체 분류가 ClassDef 에 있다", len(bad), len(used),
           f"정의되지 않은 분류: {list(bad)}", [f"{k}: {v}개" for k, v in bad.items()])

    lab = Counter(ObjectReview.objects.exclude(label="")
                  .values_list("label", flat=True))
    bad2 = {k: v for k, v in lab.items() if k not in known}
    report("사람이 지정한 분류가 ClassDef 에 있다", len(bad2), len(lab),
           f"정의되지 않은 분류: {list(bad2)}")


# --- 5. 뼈대가 성한가 --------------------------------------------------------
def check_skeleton(slug=None):
    """경로가 실제 파일을 가리키는가, 배율이 있는가.

    파일이 없으면 화면이 깨진 이미지를 보여줄 뿐 예외가 나지 않는다.
    배율이 없으면 계측값이 통째로 뜻을 잃는다.
    """
    from django.conf import settings
    root = Path(settings.DATA_ROOT)

    qs = Detection.objects.filter(is_current=True)
    if slug:
        qs = qs.filter(viewpoint__slide__slug=slug)
    dl = list(qs)
    noscale = [d for d in dl if not d.um_per_pixel]
    report("검출에 배율(µm/px)이 있다", len(noscale), len(dl),
           "계측값이 뜻을 잃는다", [d.image_path for d in noscale])

    missing = [d for d in dl if not (root / d.image_path).exists()]
    report("검출 이미지 파일이 있다", len(missing), len(dl),
           "화면이 깨진 이미지를 보여준다", [d.image_path for d in missing])

    sq = Stack.objects.all()
    if slug:
        sq = sq.filter(viewpoint__slide__slug=slug)
    st = list(sq)
    sm = [s for s in st if not (root / s.focused_path).exists()]
    report("합성본 파일이 있다", len(sm), len(st), "", [s.focused_path for s in sm])

    fq = Frame.objects.all()
    if slug:
        fq = fq.filter(slide__slug=slug)
    fl = list(fq)
    fm = [f for f in fl if not (root / f.path).exists()]
    report("원본 프레임 파일이 있다", len(fm), len(fl), "", [f.path for f in fm])

    # 배율이 섞이면 계측값을 한데 모아 비교할 수 없다
    scales = {round(d.um_per_pixel, 9) for d in dl if d.um_per_pixel}
    if len(scales) > 1:
        print(f"!!   배율이 {len(scales)}가지로 섞여 있다: {sorted(scales)}")
        print("       <-- 계측값을 한데 모아 비교하면 안 된다")
        problems.append(("배율 혼재", len(scales), ""))
    else:
        print(f"   배율이 하나다 ({list(scales)[0] if scales else '-'} µm/px)")


# --- 6. 문턱이 갈라져 있는가 -------------------------------------------------
def check_thresholds(slug=None):
    """시야마다 문턱이 다르면 개수를 서로 비교할 수 없다.

    스키마는 시야 단위 문턱을 허용한다(이력과 예외를 정직하게 기록하려고).
    다만 **깊이별·지역별 비교가 이 시료의 목적**이므로 갈라져 있으면 알려야 한다.
    """
    qs = dets(slug)
    ids = Counter(d.thresholds_id for d in qs)
    n = len(ids)
    if n <= 1:
        print(f"   문턱이 하나다 (검출 {sum(ids.values())}개)")
        return
    print(f"!! 문턱이 {n}가지로 갈라져 있다  <-- 시야 간 개수를 비교할 수 없다")
    for tid, cnt in ids.most_common():
        print(f"       #{tid}: 검출 {cnt}개")
    problems.append(("문턱 혼재", n, "하나로 맞추는 것이 좋다"))


def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--slide", help="이 슬러그만")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="어긋난 것의 예를 보여준다")
    args = ap.parse_args()
    VERBOSE = args.verbose

    if args.slide and not Slide.objects.filter(slug=args.slide).exists():
        raise SystemExit(f"슬라이드를 찾지 못했다: {args.slide}")

    print("=== 1. 판정 캐시 ===")
    check_verdicts(args.slide)
    print("\n=== 2. 현재 검출 ===")
    check_current(args.slide)
    print("\n=== 3. 교정 ===")
    check_reviews(args.slide)
    print("\n=== 4. 분류 ===")
    check_classes(args.slide)
    print("\n=== 5. 뼈대 ===")
    check_skeleton(args.slide)
    print("\n=== 6. 문턱 ===")
    check_thresholds(args.slide)

    print()
    if problems:
        print(f"문제 {len(problems)}건:")
        for name, n, why in problems:
            print(f"  {name}: {n}건 {why}")
        return 1
    print("DB 가 앞뒤가 맞는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
