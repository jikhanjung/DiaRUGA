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
# **저장소에서는 한 단계 위가 뿌리다** (스크립트가 pipeline/·ops/·migrate/
# 안에 있다). `/srv/DiaRUGA/scripts` 처럼 저장소 밖에서 돌 때는 그 짐작이
# 안 맞으므로 `DIARUGA_APP` 이 알려 준다 — 컨테이너에서는 이미지 안의 /app 이다.
APP = Path(os.environ.get("DIARUGA_APP")
          or Path(__file__).resolve().parent.parent)
# **`APP` 은 Django 코드를 찾는 자리일 뿐이다** (100). `sys.path` 앞에 통째로
# 밀어 넣으면 **이미지 안의 옛 `judge.py`·`zen_meta.py` 가 자기 옆의 것을 가린다**
# — `/srv/DiaRUGA/scripts` 로 밀어 넣은 새 규칙이 안 먹는 채로 돌았다(실측).
# 그래서 **뒤에 붙인다**: 스크립트 자신의 디렉토리(파이썬이 `sys.path[0]` 에
# 놓는다)가 먼저이고, Django 는 그 뒤에서 찾힌다.
sys.path.insert(0, str(APP / "web"))
sys.path.append(str(APP))
# **`pipeline/` 의 모듈을 함께 쓴다.** 판정 규칙(`judge`)·촬영 XML(`zen_meta`)·
# 실행 기록(`runlog`)은 파이프라인과 이쪽이 같은 것을 봐야 한다 — 규칙이 둘이면
# 검출과 검사가 다른 말을 한다. `/srv/DiaRUGA/scripts` 는 평평해서 이 줄이 없어도
# 되지만, 저장소에서는 디렉토리가 갈려 있어 알려 줘야 한다.
sys.path.insert(0, str(APP / "pipeline"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diarugaweb.settings")
django.setup()

from django.db.models import Count                                  # noqa: E402

import judge                                                        # noqa: E402
from viewer.models import (Candidate, ClassDef, Detection, DiatomObject,
                           Frame,    # noqa: E402
                           Locality, ObjectReview,
                           RunBatch, Sample, Slide, Stack, Viewpoint,
                           ViewpointReview)
# **번호 규칙은 뷰어 코드에 있다** (`web/viewer/catalog.py`). 그래서 이 검사만
# **뷰어 이미지를 올린 뒤에 돈다** — 057 이 말하는 "함께 올려야 하는 축" 이고,
# `dbrun.sh` 는 `/app` 안의 코드를 돌리므로 판이 낡으면 그 파일이 없다.
#
# **그때 도구가 죽으면 안 된다.** 이 스크립트의 나머지 여덟 검사는 그 코드와
# 무관하고, 무결성 검사가 배포 순서에 매달리면 정작 필요한 날 못 돌린다.
# 그렇다고 조용히 건너뛰면 **덮은 줄 알게 된다** — 그래서 아래에서 크게 적는다.
try:
    from viewer import catalog                                       # noqa: E402
except ImportError:                                                  # 낡은 판
    catalog = None

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
    """**뷰어가 보여줄 검출** — 검토 대상 묶음의, 그 묶음 안 최신 것 (P10).

    `is_current` 만 걸면 나란히 쌓아 둔 다른 엔진의 검출까지 잡혀, 판정 캐시
    검사가 **지금 화면과 무관한 것**까지 본다.
    """
    qs = (Detection.objects.reviewing()
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
    """뷰어가 보여줄 검출이 **이미지마다 하나 이하**인가 (P10).

    예전에는 "시야마다 하나" 였다. 프레임별 검출이 올라오면 시야 하나에 여럿이
    정상이다(합성본 하나 + 프레임마다 하나) — 세는 단위가 **이미지**로 내려간다.
    한 이미지에 둘이면 화면이 어느 것을 그릴지 모르고, 그 상태는 예외가 안 난다.

    **검토 대상 묶음 안에서만 센다.** 나란히 쌓아 둔 다른 엔진의 검출은 같은
    이미지에 있는 것이 정상이고, 그것까지 세면 이 검사가 늘 빨갛다.
    """
    qs = Viewpoint.objects.all()
    if slug:
        qs = qs.filter(slide__slug=slug)
    counts = dict(Detection.objects.reviewing().filter(viewpoint__in=qs)
                  .values_list("image").annotate(n=Count("id")))
    many = {i: n for i, n in counts.items() if n > 1}
    report("이미지마다 보여줄 검출이 하나 이하", len(many), len(counts) or 1,
           "한 이미지에 둘 이상이다 — 어느 것을 보여줄지 알 수 없다",
           [f"image #{i}: {n}개" for i, n in list(many.items())[:5]])

    # **검토 대상이 정해져 있는가** (P10). 없으면 뷰어가 아무것도 안 보여준다 —
    # 500 도 404 도 아니고 그냥 빈 화면이라, 세어 보기 전에는 알 수가 없다.
    from viewer.models import RunBatch
    n_rev = RunBatch.objects.filter(for_review=True).count()
    report("검토 대상 묶음이 하나 정해져 있다", 0 if n_rev == 1 else 1, 1,
           f"검토 대상이 {n_rev}개다 — 0이면 화면이 비고, 둘이면 제약이 막았어야 한다",
           [] if n_rev == 1 else [f"for_review={n_rev}"])

    # **검토 완료 줄이 제 자리에 있는가** (073). 줄이 두 종류다 —
    # `batch` 가 있는 줄은 "그 묶음을 다 봤다", `batch=NULL` 인 줄은 시야
    # 코멘트다. 섞이면 예외는 안 나고 **완료 표시가 묶음을 넘어 새거나
    # 코멘트가 묶음마다 갈라진다.**
    misplaced = list(ViewpointReview.objects
                     .filter(batch__isnull=True, done=True)[:5])
    report("코멘트 줄에 완료 표시가 없다",
           ViewpointReview.objects.filter(batch__isnull=True,
                                          done=True).count(),
           ViewpointReview.objects.count(),
           "묶음 없는 줄이 done=True 다 — 어느 묶음을 다 봤다는 말인지 알 수 없다",
           [f"vp #{r.viewpoint_id}" for r in misplaced])
    noted = list(ViewpointReview.objects
                 .filter(batch__isnull=False).exclude(note="")[:5])
    report("완료 줄에 코멘트가 없다",
           ViewpointReview.objects.filter(batch__isnull=False)
           .exclude(note="").count(),
           ViewpointReview.objects.count(),
           "묶음에 달린 줄이 코멘트를 들고 있다 — 묶음을 갈면 사람이 쓴 글이 사라진다",
           [f"vp #{r.viewpoint_id}" for r in noted])

    # 검출이 아예 없는 시야는 정상일 수 있다(아직 안 돌린 것). 세어만 둔다.
    with_det = set(Detection.objects.reviewing().filter(viewpoint__in=qs)
                   .values_list("viewpoint_id", flat=True))
    none = [vp for vp in qs if vp.id not in with_det]
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

    ## 무엇을 세지 않는가 (P09 0단계)

    - **사람이 그린 개체**(`source="manual"`)는 후보가 없는 것이 정상이다.
      세면 마스크 편집을 쓰는 만큼 이 검사가 빨개진다
    - **지금 안 보고 있는 묶음의 교정**도 고아가 아니다. YOLO 로 갈아타면 SAM2
      시절 교정이 통째로 "현재 검출 밖" 이 되는데 그것은 **보존이지 고장이
      아니다**(P09 5.1). 현재 검출이 속한 묶음의 교정만 본다
    """
    qs = ObjectReview.objects.select_related("viewpoint")
    if slug:
        qs = qs.filter(viewpoint__slide__slug=slug)
    all_reviews = list(qs)

    # 현재 검출에 속한 개체 id 집합. 교정이 이 밖을 가리키면 옛 검출에 남은 것이다.
    cur_det = Detection.objects.reviewing().filter(
        **({"viewpoint__slide__slug": slug} if slug else {}))
    current = set(Candidate.objects.filter(detection__in=cur_det)
                  .values_list("id", flat=True))
    # 지금 화면이 보고 있는 묶음들. 이 밖의 교정은 다른 회차의 기록이다.
    cur_batches = {b for b in cur_det.select_related("run")
                   .values_list("run__batch_id", flat=True) if b}

    reviews = [o for o in all_reviews
               if o.source != "manual" and o.batch_id in cur_batches]
    other = len(all_reviews) - len(reviews)

    orphan, mismatch, nogeom = [], [], []
    for o in reviews:
        if o.candidate_id is None:
            orphan.append(o)
        elif o.candidate_id not in current:
            mismatch.append(o)
    for o in all_reviews:            # geom 은 모든 행이 들고 있어야 한다
        if not o.geom:
            nogeom.append(o)

    report("교정이 현재 검출에 붙어 있다", len(orphan), len(reviews),
           "고아 교정 — 지우지 말 것. 8단계(고아 화면)에서 다시 맺는다",
           [f"{o.viewpoint} {o.mask_key}" for o in orphan])
    report("교정의 candidate 링크가 맞다", len(mismatch), len(reviews),
           "옛 검출의 개체를 가리킨다 — 재바인딩이 중간에 끊겼는가",
           [f"{o.viewpoint} {o.mask_key}" for o in mismatch])
    report("교정이 기하(geom)를 갖고 있다", len(nogeom), len(all_reviews),
           "검출기가 바뀌면 그릴 것이 없어진다 (P02 §2.7)",
           [f"{o.viewpoint} {o.mask_key}" for o in nogeom])
    if other:
        print(f"     (위 셋에서 뺀 교정 {other}건 — 사람이 그린 것과 지금 안 "
              f"보고 있는 묶음의 것. 고장이 아니다)")

    # --- batch·source 가 서로 맞는가 (P09 0단계) -----------------------------
    # 두 칸을 따로 둔 값이 여기서 나온다 — 한쪽만 맞는 행은 어딘가에서 잘못
    # 만든 것이고, **예외는 안 나고 그냥 틀린 상태**로 남는다.
    bad_src = [o for o in all_reviews
               if (o.source == "manual") != (o.batch_id is None)]
    report("사람이 그린 교정만 묶음이 비어 있다", len(bad_src), len(all_reviews),
           "`source` 와 `batch` 가 어긋난다 — 엔진 교정이 사람이 그린 자리에 "
           "앉았거나 그 반대다 (P09 5.2)",
           [f"{o.viewpoint} {o.mask_key} source={o.source} batch={o.batch_id}"
            for o in bad_src])

    # bind_method 분포는 정보로만
    dist = Counter(o.bind_method for o in reviews)
    print(f"     바인딩: {dict(dist)}")


# --- 4. 분류가 정의된 것인가 -------------------------------------------------
def check_classes(slug=None):
    """`ClassDef` 에 없는 분류가 붙어 있으면 화면에서 이름도 색도 없이 나온다."""
    known = set(ClassDef.objects.values_list("key", flat=True))
    qs = Candidate.objects.filter(
        detection__in=Detection.objects.reviewing()).exclude(cls="")
    if slug:
        qs = qs.filter(detection__viewpoint__slide__slug=slug)
    used = Counter(qs.values_list("cls", flat=True))
    bad = {k: v for k, v in used.items() if k not in known}
    report("개체 분류가 ClassDef 에 있다", len(bad), len(used),
           f"정의되지 않은 분류: {list(bad)}", [f"{k}: {v}개" for k, v in bad.items()])

    lab = Counter(DiatomObject.objects.exclude(label="")
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

    qs = Detection.objects.reviewing()
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
def check_layers(slug=None):
    """층이 앞뒤가 맞는가 — 지역 → 지점 → 시료 → 관찰 (P07).

    **여기서 잡는 것은 예외가 안 나고 그냥 틀린 상태다.** 소속을 잃은 관찰은
    어느 권역 탭에도 안 나와 화면에서 통째로 사라진다(`BP09-0901 (1)` 이 그랬다).
    500 도 404 도 아니고, 목록을 세어 보기 전에는 알 수가 없다.
    """
    qs = Slide.objects.all()
    if slug:
        qs = qs.filter(slug=slug)
    sl = list(qs.select_related("sample__locality__site"))

    orphan = [s for s in sl if not s.sample_id]
    report("관찰에 시료가 붙어 있다", len(orphan), len(sl),
           "어느 권역 탭에도 안 나와 화면에서 사라진다",
           [s.slug for s in orphan])

    # 지점 유형과 시료의 위치 칸이 맞는가. 노두인데 깊이가 있거나 그 반대면
    # 정렬이 엉키고 축이 없는 값을 그리려 든다.
    sm = Sample.objects.select_related("locality")
    if slug:
        sm = sm.filter(slides__slug=slug).distinct()
    sm = list(sm)
    bad = [x for x in sm
           if (x.locality.kind == "outcrop" and x.depth_cm is not None)
           or (x.locality.kind == "core" and x.sample_no is not None)]
    report("시료의 위치 칸이 지점 유형과 맞는다", len(bad), len(sm),
           "노두에 깊이가 있거나 시추코어에 단면 번호가 있다",
           [f"{x.locality.code}/{x.code}" for x in bad])

    # 위치가 아예 없는 시료. 정렬에서 뒤로 밀리고 축에 안 놓인다 — 틀린 것은
    # 아니지만 사람이 채워야 할 자리라 세어 준다.
    nopos = [x for x in sm if x.position is None]
    report("시료에 위치가 있다", len(nopos), len(sm),
           "축에 안 놓이고 정렬에서 뒤로 밀린다",
           [f"{x.locality.code}/{x.code}" for x in nopos])

    # 시료가 하나도 없는 지점. 지우다 만 자리이거나 사람이 미리 만든 것이다.
    empty = [c for c in Locality.objects.all() if not c.samples.exists()]
    if not slug:
        report("지점에 시료가 있다", len(empty), Locality.objects.count(),
               "빈 지점이 목록·지도에 자리만 차지한다",
               [f"{c.site.code}/{c.code}" for c in empty])


def check_links(slug=None):
    """같은 개체 묶음이 앞뒤가 맞는가 (P11).

    묶음은 사람이 프레임마다 골라 만든 것이라 재생성 불가다 — 어긋나면
    교정과 같은 무게로 잃는다. **여기서 잡는 것은 예외가 안 나고 그냥 틀린
    상태다**: 대표가 없는 묶음은 학습 자료로 뽑을 때 얼굴이 없고, 남의 시야
    이미지를 문 멤버는 화면에 안 그려져 조용히 사라진다.
    """
    # **묶음은 멤버가 둘 이상인 개체다** (P12). 판정마다 개체가 하나씩 서므로
    # 거르지 않으면 개체 수천 개를 훑고, "혼자인 묶음" 검사가 전부 걸린다.
    qs = (DiatomObject.objects.annotate(n_members=Count("members"))
          .filter(n_members__gte=2))
    if slug:
        qs = qs.filter(viewpoint__slide__slug=slug)
    links = list(qs.prefetch_related("members__image"))
    if not links:
        if VERBOSE:
            print("   (묶음이 아직 없다)")
        return

    # 대표가 정확히 하나인가. "둘 이상" 은 DB 제약이 막지만 **0개는 못 막는다** —
    # 저장 쪽이 지키는 약속이고, 여기가 그것을 센다.
    norep = [l for l in links if sum(1 for m in l.members.all() if m.is_rep) != 1]
    report("묶음마다 대표가 하나다", len(norep), len(links),
           "대표가 없으면 학습 자료로 뽑을 때 얼굴이 없다",
           [f"obj#{l.pk}" for l in norep])

    # **멤버가 하나도 없는 개체** (P12). 판정을 지우면 개체가 유령으로 남는데
    # 예외는 안 나고 개체를 세는 자리마다 하나씩 는다 — `data.prune_objects`
    # 를 안 지난 삭제 경로가 있다는 뜻이다.
    ghosts = list(DiatomObject.objects.filter(members__isnull=True)
                  .values_list("pk", flat=True)[:20])
    n_ghost = DiatomObject.objects.filter(members__isnull=True).count()
    report("개체마다 판정이 하나 이상 있다", n_ghost,
           DiatomObject.objects.count(),
           "멤버 없는 개체는 유령이다 — prune_objects 를 안 지난 삭제가 있다",
           [f"obj#{p}" for p in ghosts])

    # **묶음 안의 지운 마스크.** 제약으로 못 막는 자리다(개체는 지워도 남는다) —
    # "이 개체는 오검출이면서 실재한다" 가 되고 학습 자료가 모순이 된다.
    bad_rm = [f"obj#{l.pk}" for l in links
              if any(m.removed for m in l.members.all())]
    report("묶음에 지운 마스크가 없다", len(bad_rm), len(links),
           "오검출로 지운 판이 묶음에 남아 있다",
           bad_rm)

    # 멤버의 이미지가 묶음의 시야에 속하는가. 어긋나면 화면이 못 그린다.
    stray = [l for l in links
             if any(m.image.viewpoint_id != l.viewpoint_id
                    for m in l.members.all())]
    report("멤버가 묶음의 시야 안에 있다", len(stray), len(links),
           "남의 시야 이미지를 문 멤버는 화면에 안 그려진다",
           [f"obj#{l.pk}" for l in stray])

    # 멤버가 실재하는 마스크를 가리키는가 — 그 (image, batch) 현재 검출의
    # 통과 후보이거나, 사람이 그린 교정(geom)이거나.
    dangling = []
    for l in links:
        for m in l.members.all():
            if m.batch_id is None:
                ok = ObjectReview.objects.filter(
                    image_id=m.image_id, batch__isnull=True,
                    mask_key=m.mask_key).exists()
            else:
                ok = Candidate.objects.filter(
                    detection__image_id=m.image_id,
                    detection__is_current=True,
                    detection__run__batch_id=m.batch_id,
                    mask_key=m.mask_key).exists()
            if not ok:
                dangling.append(f"obj#{l.pk}/{m.mask_key}")
    report("멤버의 마스크가 실재한다", len(dangling),
           sum(l.members.count() for l in links),
           "재검출로 사라진 마스크다 — geom 스냅샷으로만 남아 있다",
           dangling)


def check_catalog(slug=None):
    """카탈로그 번호가 **날 수 있는가, 그리고 겹치지 않는가** (개체 카탈로그).

    번호는 저장하지 않고 층·시야·`mask_key`·묶음 코드로 그때그때 만든다. 그래서
    어긋날 수가 없는 대신 **재료가 빠지면 번호가 아예 안 난다** — 화면은 "번호
    없음" 이라고 적지만, 그 상태로 며칠이 지나면 그 관찰만 동정을 못 한 채 남는다.
    여기서 세는 것이 그것이다.

    그리고 **겹치는 번호는 논문에 실린 뒤에는 못 고친다.** 규칙상 겹칠 수 없지만
    (`mask_key` 가 `(detection, mask_key)` 유일 제약을 타고, 묶음 코드에 유일
    제약이 있다) 층 코드를 정규화하면서 두 지점이 한 토막으로 누울 수는 있다
    (`GC-03` 과 `GC03` 이 다 `GC03` 이다) — 그 갈래를 기계로 본다.
    """
    if catalog is None:
        # 조용히 건너뛰지 않는다 — 안 돈 검사를 OK 로 읽으면 안 된다.
        print("!! 개체 카탈로그 검사를 못 돌렸다                       "
              "<-- 이 이미지에 viewer/catalog.py 가 없다 (뷰어 판을 올릴 것)")
        return

    # 1) 묶음 코드. 비면 그 묶음의 개체는 번호가 하나도 안 난다.
    batches = list(RunBatch.objects.filter(kind="detect")
                   .values("id", "label", "code", "for_review"))
    if not batches:
        if VERBOSE:
            print("   (검출 묶음이 아직 없다)")
        return

    used = [b for b in batches
            if Detection.objects.filter(is_current=True,
                                        run__batch_id=b["id"]).exists()]
    nocode = [b["label"] for b in used if not (b["code"] or "").strip()]
    report("검출이 있는 묶음에 카탈로그 코드가 있다", len(nocode), len(used),
           "코드가 없으면 그 묶음의 개체는 번호가 하나도 안 난다", nocode)

    # `M` 은 손그림 자리다 (`catalog.MANUAL_CODE`). DB 제약이 막지만 옛 판으로
    # 들어온 행이 있을 수 있어 함께 센다 — 막는 것과 확인하는 것은 다른 일이다.
    manual = [b["label"] for b in batches
              if (b["code"] or "").upper() == catalog.MANUAL_CODE]
    report("묶음 코드가 M 이 아니다", len(manual), len(batches),
           "M 은 사람이 그린 개체 자리다 — 섞이면 한 번호 아래 둘이 된다", manual)

    # 2) 층 코드가 정규화되면서 뭉개지는가. `GC-03` 과 `GC03` 이 한 토막이 된다.
    seen = defaultdict(set)
    for loc in Locality.objects.select_related("site"):
        try:
            key = (catalog.part(loc.site.code), catalog.part(loc.code))
        except ValueError:
            key = None
        if key:
            seen[key].add(f"{loc.site.code}-{loc.code}")
    clash = {k: v for k, v in seen.items() if len(v) > 1}
    report("지역·지점 코드가 번호에서 안 뭉개진다", len(clash), len(seen),
           "두 지점이 한 토막으로 누우면 서로 다른 개체가 같은 번호를 받는다",
           [f"{'-'.join(k)} <- {sorted(v)}" for k, v in clash.items()])

    # 3) 실제로 번호가 나는가. **검토 대상 묶음만** 본다 — 화면이 그것을 연다.
    slides = Slide.objects.select_related("sample__locality__site")
    if slug:
        slides = slides.filter(slug=slug)
    codes = {b["id"]: (b["code"] or "") for b in batches}
    # **행은 안 훑는다.** 번호가 나는지는 층이 있는지로 갈린다 — 슬라이드 12개에
    # 개체 3만이라, 세려고 자료를 물질화하지 말라는 것과 같은 이야기다.
    noloc = [sl.slug for sl in slides
             if not (sl.sample and sl.sample.locality
                     and sl.sample.locality.site)]
    report("관찰이 카탈로그 번호를 만들 층을 갖고 있다", len(noloc),
           slides.count(),
           "소속을 잃은 관찰은 번호가 안 난다 — 화면에서 동정을 못 적는다",
           noloc)

    # 4) 종명이 붙은 교정 행이 묶음에 들어 있는가. 손그림(NULL)은 제 자리다.
    named = ObjectReview.objects.exclude(diatom_object__species="")
    if slug:
        named = named.filter(viewpoint__slide__slug=slug)
    n_named = named.count()
    if n_named:
        orphan = [o.mask_key for o in
                  named.filter(batch__isnull=True).exclude(source="manual")[:20]]
        report("종명이 붙은 교정이 묶음에 들어 있다", len(orphan), n_named,
               "묶음 없는 엔진 교정은 어느 판의 동정인지 알 수 없다", orphan)
        nocode2 = [o.mask_key for o in named.select_related("batch")
                   if o.batch_id and not codes.get(o.batch_id, "")]
        report("동정한 개체의 묶음에 코드가 있다", len(nocode2), n_named,
               "코드가 없으면 그 동정을 부를 번호가 없다", nocode2[:20])
    elif VERBOSE:
        print("   (아직 동정한 개체가 없다)")


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
    print("\n=== 7. 층 (지역·지점·시료·관찰) ===")
    check_layers(args.slide)
    print("\n=== 8. 같은 개체 묶음 ===")
    check_links(args.slide)
    print("\n=== 9. 개체 카탈로그 (번호·동정) ===")
    check_catalog(args.slide)

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
