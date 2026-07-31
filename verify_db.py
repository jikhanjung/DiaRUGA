#!/usr/bin/env python3
"""DB 와 JSON 이 같은 답을 내는지 대조한다. P02 §5-3 의 관문이다.

    python verify_db.py

**이전(migration) 직후에 한 번 쓰는 검사다.** 그때는 한 칸이라도 어긋나면 멈춰야
했다 — 교정 기록은 재생성 불가한 자료이고, 어긋난 채로 뷰어를 DB 로 옮기면 무엇이
맞는지 알 수 없게 되기 때문이다.

**지금은 교정 항목이 어긋나는 것이 정상이다.** DB 가 원본이 됐고 `review/*.json` 은
이전 시점 스냅샷이라, 그 뒤로 사람이 교정한 만큼 벌어진다(내보내기는 P02 5단계).
검출 개체·지표는 여전히 일치해야 한다.

DB 자체의 앞뒤가 맞는지는 **`check_db.py`** 가 본다 — 그쪽은 JSON 과 무관하므로
계속 유효하다.

세는 것: 슬라이드·시야·프레임·합성본, 검출별 개체 수와 지표 합, 분류별 개수,
교정(삭제·되살림·분류·코멘트·검토완료), 그리고 뷰어가 실제로 쓰는 파생값
(교정을 반영한 통과분, 유령, 되살리기 후보).
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diatomweb.settings")
django.setup()

from django.conf import settings                                    # noqa: E402
from django.db.models import Count, Q, Sum                          # noqa: E402

from viewer.models import (Candidate, Detection, Frame,              # noqa: E402
                          ObjectReview, Slide, Stack, Viewpoint,
                          ViewpointReview)

ROOT = Path(settings.DATA_ROOT)
fails = []
checks = 0


def check(label, want, got):
    global checks
    checks += 1
    ok = want == got
    if not ok:
        fails.append((label, want, got))
    mark = "  " if ok else "!!"
    print(f"{mark} {label:44s} JSON {str(want):>12s}  DB {str(got):>12s}"
          f"{'' if ok else '   <-- 어긋남'}")


def mask_key(bbox):
    return "_".join(str(int(v)) for v in bbox)


# --- JSON 쪽에서 센다 -----------------------------------------------------
groups = {}
for p in sorted(ROOT.glob("groups_*.json")):
    slug = p.stem.removeprefix("groups_").lower()
    groups[slug] = json.loads(p.read_text(encoding="utf-8"))

j_slides = len(groups)
j_vps = sum(len(g["groups"]) for g in groups.values())
j_frames = sum(sum(len(x["images"]) for x in g["groups"]) for g in groups.values())
j_stacks = len(list((ROOT / settings.STACK_DIR).glob("*_focused.jpg")))

dets = {}
for p in sorted((ROOT / "out").glob("*_candidates.json")):
    dets[p.name[: -len("_candidates.json")]] = json.loads(
        p.read_text(encoding="utf-8"))

reviews = {}
for p in sorted((ROOT / settings.REVIEW_DIR).glob("*_review.json")):
    reviews[p.name[: -len("_review.json")]] = json.loads(
        p.read_text(encoding="utf-8"))

print("=== 1. 뼈대 ===")
check("슬라이드", j_slides, Slide.objects.count())
check("시야", j_vps, Viewpoint.objects.count())
check("프레임", j_frames, Frame.objects.count())
check("합성본", j_stacks, Stack.objects.count())
check("검출", len(dets), Detection.objects.filter(is_current=True).count())

print("\n=== 2. 개체 (검출 JSON 원본 그대로) ===")
j_cand = sum(len(d["candidates"]) for d in dets.values())
j_rej = sum(len(d["rejected"]) for d in dets.values())
db_cand = Candidate.objects.filter(detection__is_current=True)
check("통과분(자동 판정)", j_cand, db_cand.filter(passed=True).count())
check("탈락분", j_rej, db_cand.filter(passed=False).count())
check("합계", j_cand + j_rej, db_cand.count())

# 지표 합 — 값이 옮겨졌는지 (개수만 맞고 값이 틀리는 경우를 잡는다)
def jsum(field, pool=("candidates", "rejected")):
    s = 0.0
    for d in dets.values():
        for k in pool:
            for c in d[k]:
                v = c.get(field)
                if v is not None:
                    s += v
    return round(s, 3)


for f in ("area_px", "area_um2", "major_um", "texture", "ellipse_iou", "solidity"):
    got = db_cand.aggregate(s=Sum(f))["s"] or 0
    check(f"{f} 합", jsum(f), round(float(got), 3))

j_poly = sum(len(c.get("polygon") or []) for d in dets.values()
             for k in ("candidates", "rejected") for c in d[k])
db_poly = sum(len(c) for c in db_cand.values_list("polygon", flat=True))
check("폴리곤 좌표 수", j_poly, db_poly)

j_keys = sum(len({mask_key(c["bbox_xywh"]) for c in d["candidates"] + d["rejected"]})
             for d in dets.values())
check("mask_key 개수(중복 제거)", j_keys, db_cand.count())

print("\n=== 3. 자동 판정 분류별 ===")
jc = Counter()
for d in dets.values():
    for c in d["candidates"]:
        jc[c.get("cls") or ""] += 1
dbc = dict(db_cand.filter(passed=True).values_list("cls")
           .annotate(n=Count("id")).values_list("cls", "n"))
for k in sorted(set(jc) | set(dbc)):
    check(f"cls={k or '(없음)'}", jc.get(k, 0), dbc.get(k, 0))

print("\n=== 4. 교정 ===")
print("   (DB 가 원본이므로 이전 시점 이후의 교정은 JSON 에 없다 —")
print("    여기서 어긋나는 것은 그동안 사람이 더 교정했다는 뜻이다.")
print("    DB 자체의 앞뒤가 맞는지는 check_db.py 가 본다)")
j_removed = sum(len(r.get("removed") or []) for r in reviews.values())
j_accepted = sum(len(r.get("accepted") or []) for r in reviews.values())
j_labels = sum(len(r.get("labels") or {}) for r in reviews.values())
j_notes = sum(len(r.get("notes") or {}) for r in reviews.values())
j_done = sum(1 for r in reviews.values() if r.get("done"))
j_gnote = sum(1 for r in reviews.values() if (r.get("note") or "").strip())
j_rows = sum(len(set(r.get("removed") or []) | set(r.get("accepted") or [])
                 | set(r.get("labels") or {}) | set(r.get("notes") or {}))
             for r in reviews.values())

check("시야 교정 파일", len(reviews), ViewpointReview.objects.count())
check("검토 완료", j_done, ViewpointReview.objects.filter(done=True).count())
check("시야 코멘트", j_gnote, ViewpointReview.objects.exclude(note="").count())
check("개체 교정 행", j_rows, ObjectReview.objects.count())
check("삭제", j_removed, ObjectReview.objects.filter(removed=True).count())
check("되살림", j_accepted, ObjectReview.objects.filter(accepted=True).count())
check("분류 지정", j_labels, ObjectReview.objects.exclude(label="").count())
check("개체 코멘트", j_notes, ObjectReview.objects.exclude(note="").count())

jl = Counter()
for r in reviews.values():
    for v in (r.get("labels") or {}).values():
        jl[v] += 1
dbl = dict(ObjectReview.objects.exclude(label="").values_list("label")
           .annotate(n=Count("id")).values_list("label", "n"))
for k in sorted(set(jl) | set(dbl)):
    check(f"label={k}", jl.get(k, 0), dbl.get(k, 0))

print("\n=== 5. 바인딩 (이전 직후에는 전부 exact 여야 한다) ===")
bind = dict(ObjectReview.objects.values_list("bind_method")
            .annotate(n=Count("id")).values_list("bind_method", "n"))
check("exact", j_rows, bind.get("exact", 0))
check("orphan", 0, bind.get("orphan", 0))
check("geom 없는 행", 0, ObjectReview.objects.filter(geom={}).count())

print("\n=== 6. 뷰어가 쓰는 파생값 (data.py 와 같은 답인가) ===")
sys.path.insert(0, str(ROOT / "web"))
from viewer import data as filedata                                 # noqa: E402

j_kept = j_gone = j_rejpool = 0
for stem in dets:
    det = filedata.detection_for(stem)
    j_kept += det["n_candidates"]
    j_gone += len(det["removed_candidates"])
    j_rejpool += len(det["rejected"])

db_kept = db_gone = db_rejpool = 0
for vp in Viewpoint.objects.prefetch_related("detections", "object_reviews"):
    det = vp.detections.filter(is_current=True).first()
    if not det:
        continue
    rv = {o.mask_key: o for o in vp.object_reviews.all()}
    removed = {k for k, o in rv.items() if o.removed}
    accepted = {k for k, o in rv.items() if o.accepted}
    passed = list(det.candidates.filter(passed=True))
    rejected = list(det.candidates.filter(passed=False))
    db_kept += sum(1 for c in passed if c.mask_key not in removed)
    db_kept += sum(1 for c in rejected if c.mask_key in accepted)
    db_gone += sum(1 for c in passed if c.mask_key in removed)
    db_gone += sum(1 for c in rejected
                   if c.mask_key in removed and c.mask_key not in accepted)
    db_rejpool += sum(1 for c in rejected
                      if c.mask_key not in accepted and c.mask_key not in removed)

check("교정 반영 통과분", j_kept, db_kept)
check("유령(지운 것)", j_gone, db_gone)
check("되살리기 후보", j_rejpool, db_rejpool)

print()
if fails:
    print(f"검사 {checks}개 중 {len(fails)}개 어긋났다 — 다음 단계로 가면 안 된다:")
    for label, want, got in fails:
        print(f"  {label}: JSON {want} != DB {got}")
    sys.exit(1)
print(f"검사 {checks}개 전부 일치. DB 가 JSON 과 같은 답을 낸다.")
