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
from collections import Counter, defaultdict
from pathlib import Path

import django

# 이 스크립트는 저장소 밖(/srv/DiaRUGA/scripts)에 복사해 두고 컨테이너 안에서
# 돌릴 수도 있다. 그때 Django 코드가 어디 있는지는 DIARUGA_APP 이 알려 준다 —
# 이미지 안의 /app 이고, 뷰어 컨테이너가 쓰는 바로 그 코드다. 저장소에서 그냥
# 돌리면 예전처럼 자기 옆의 web/ 을 본다.
APP = Path(os.environ.get("DIARUGA_APP") or Path(__file__).resolve().parent)
sys.path.insert(0, str(APP / "web"))
sys.path.insert(0, str(APP))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
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

    # 분류를 더하면서 단축키를 안 준 것. 예외가 나지 않고 그냥 **그 분류만
    # 메뉴로만 지정된다** — 시야 하나를 훑는 속도가 분류마다 달라지고, 왜
    # 느린지는 화면에 안 보인다. 검토 화면의 안내에도 안 나온다.
    active = list(ClassDef.objects.filter(active=True)
                  .values("key", "hotkey", "color"))
    nokey = [c["key"] for c in active if not (c["hotkey"] or "").strip()]
    report("활성 분류에 단축키가 있다", len(nokey), len(active),
           f"단축키 없음: {nokey}")

    # 색이 비면 마스크가 투명하게 그려진다 — "지정은 되는데 화면에서 안 보이는"
    # 상태다. 색이 CSS 에도 있어야 하는 것은 아직 기계로 못 본다(TODO).
    nocolor = [c["key"] for c in active if not (c["color"] or "").strip()]
    report("활성 분류에 색이 있다", len(nocolor), len(active),
           f"색 없음: {nocolor}")


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

    # 배율은 **슬라이드 안에서** 하나여야 한다.
    #
    # 슬라이드끼리 다른 것은 정상이다 — 대물렌즈를 바꿔 찍는다(260729 는 40x 로
    # 0.1126, 260731 은 100x 로 0.045 µm/px). 전체를 한 덩어리로 보면 그것까지
    # 문제로 잡혀서, 정작 한 슬라이드 안이 어긋난 진짜 사고를 못 본다.
    #
    # 계측값을 여러 슬라이드에 걸쳐 비교하는 것은 여전히 조심할 일이지만, 그건
    # µm 단위 값(major_um 등)으로 하면 되고 배율이 같을 필요는 없다. 배율에
    # 딸려가는 지표(texture)는 슬라이드마다 문턱을 따로 잡아야 한다 — devlog 013.
    by_slide = defaultdict(set)
    for d in dl:
        if d.um_per_pixel:
            by_slide[d.viewpoint.slide.slug].add(round(d.um_per_pixel, 9))

    mixed = {s: v for s, v in by_slide.items() if len(v) > 1}
    if mixed:
        print(f"!!   슬라이드 안에서 배율이 섞였다 — {len(mixed)}개")
        for s, v in sorted(mixed.items()):
            print(f"       {s}: {sorted(v)}")
        print("       <-- 한 슬라이드는 한 배율로 찍힌다. 사이드카나 XML 을 볼 것")
        problems.append(("슬라이드 내 배율 혼재", len(mixed), ""))
    else:
        print(f"   슬라이드마다 배율이 하나다 ({len(by_slide)}개 슬라이드)")
    if VERBOSE or len(by_slide) > 1:
        for s, v in sorted(by_slide.items()):
            print(f"     {s:<28} {list(v)[0]:.9f} µm/px")


# --- 6. 문턱이 갈라져 있는가 -------------------------------------------------
def check_thresholds(slug=None):
    """문턱은 **슬라이드 안에서** 하나여야 한다.

    스키마는 시야 단위 문턱을 허용한다(이력과 예외를 정직하게 기록하려고).
    한 슬라이드 안에서 갈라지면 시야 간 개수를 비교할 수 없으므로 알린다.

    **슬라이드끼리 다른 것은 정상이다.** 배율이 다르면 텍스처 문턱도 달라야 한다 —
    같은 시료를 40x 와 100x 로 찍으면 texture 중앙값이 1,903 대 109 로 나온다
    (devlog 013). 크기(µm)와 비율 지표는 배율과 무관하니 그대로 비교하면 된다.
    """
    qs = dets(slug)
    per = defaultdict(Counter)
    for d in qs:
        per[d.viewpoint.slide.slug][d.thresholds_id] += 1

    mixed = {s: c for s, c in per.items() if len(c) > 1}
    if not mixed:
        sets = {tid for c in per.values() for tid in c}
        print(f"   슬라이드마다 문턱이 하나다 "
              f"({len(per)}개 슬라이드 · 문턱 조합 {len(sets)}가지)")
        if len(sets) > 1:
            for s, c in sorted(per.items()):
                print(f"     {s:<28} 문턱 #{next(iter(c))}")
        return
    print(f"!! 슬라이드 안에서 문턱이 갈라졌다 — {len(mixed)}개"
          f"  <-- 시야 간 개수를 비교할 수 없다")
    for s, c in sorted(mixed.items()):
        detail = " · ".join(f"#{t}:{n}" for t, n in c.most_common())
        print(f"       {s}: {detail}")
    problems.append(("슬라이드 내 문턱 혼재", len(mixed),
                     "refilter.py --slide 로 맞출 것"))


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
