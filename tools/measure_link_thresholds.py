"""P11 0단계 — 같은 자리 후보의 IoU·중심거리 분포 실측 (yolo-3차, 읽기 전용).

묻는 것 셋:
  1. 근접 창(기준 bbox 의 K배) 안에 후보가 몇 개 드는가 — 팝업 줄 길이
  2. 최선 후보의 IoU 분포 — 미리 고르기 문턱
  3. 최선과 차선의 간격 — 미리 고르기가 틀린 것을 집을 위험
"""
import sqlite3, statistics, json

c = sqlite3.connect("file:/srv/DiaRUGA/db/DiaRUGA.db?mode=ro", uri=True)

# yolo-3차의 현재 검출 + 통과 후보. 이미지의 정체(kind·seq)도 같이.
rows = c.execute("""
  select d.viewpoint_id, d.image_id, i.kind, coalesce(f.seq, -1),
         ca.bbox_x, ca.bbox_y, ca.bbox_w, ca.bbox_h
  from viewer_candidate ca
  join viewer_detection d on d.id = ca.detection_id and d.is_current = 1
  join viewer_run r on r.id = d.run_id
  join viewer_runbatch b on b.id = r.batch_id
  join viewer_image i on i.id = d.image_id
  left join viewer_frame f on f.id = i.frame_id
  where b.label = 'yolo-3차' and ca.passed = 1
""").fetchall()

# 시야 → 이미지 → [bbox]
from collections import defaultdict
vps = defaultdict(lambda: defaultdict(list))
meta = {}
for vp, img, kind, seq, x, y, w, h in rows:
    vps[vp][img].append((x, y, w, h))
    meta[img] = (kind, seq)

def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax+aw, bx+bw) - max(ax, bx))
    iy = max(0, min(ay+ah, by+bh) - max(ay, by))
    inter = ix * iy
    return inter / (aw*ah + bw*bh - inter) if inter else 0.0

def center(b): return (b[0]+b[2]/2, b[1]+b[3]/2)

def in_window(anchor, cand, k):
    """후보의 중심이 기준 bbox 를 k배로 키운 창 안인가."""
    ax, ay, aw, ah = anchor
    cx, cy = center(cand)
    mx, my = aw*(k-1)/2, ah*(k-1)/2
    return ax-mx <= cx <= ax+aw+mx and ay-my <= cy <= ay+ah+my

strip_15, strip_20 = [], []       # 창 안 후보 수 (K=1.5 · 2.0)
best_ious, margins = [], []       # 최선 IoU · (최선-차선)
no_match = 0
pairs = 0

for vp, imgs in vps.items():
    if len(imgs) < 2: continue
    ids = sorted(imgs, key=lambda i: meta[i][1])
    # 기준: 각 이미지의 각 후보 → 다른 이미지 하나(인접 프레임 or 합성본↔첫 프레임)
    for a_img, b_img in zip(ids, ids[1:]):
        for anchor in imgs[a_img]:
            cands = imgs[b_img]
            n15 = sum(1 for cb in cands if in_window(anchor, cb, 1.5))
            n20 = sum(1 for cb in cands if in_window(anchor, cb, 2.0))
            strip_15.append(n15); strip_20.append(n20)
            ious = sorted((iou(anchor, cb) for cb in cands), reverse=True)
            pairs += 1
            if not ious or ious[0] == 0:
                no_match += 1; continue
            best_ious.append(ious[0])
            margins.append(ious[0] - (ious[1] if len(ious) > 1 else 0.0))

def pct(xs, p):
    xs = sorted(xs); return xs[int(len(xs)*p/100)]

print(f"기준 후보(이웃 이미지 쌍) {pairs:,}")
print(f"\n[1] 창 안 후보 수 — 팝업 줄 길이")
for name, s in [("K=1.5", strip_15), ("K=2.0", strip_20)]:
    d = defaultdict(int)
    for n in s: d[min(n,4)] += 1
    tot = len(s)
    print(f"  {name}: 0개 {d[0]/tot:5.1%} · 1개 {d[1]/tot:5.1%} · 2개 {d[2]/tot:5.1%}"
          f" · 3개 {d[3]/tot:5.1%} · 4개+ {d[4]/tot:5.1%}")
print(f"\n[2] 최선 IoU (겹침이 아예 없던 기준 {no_match/pairs:.1%} 제외)")
print(f"  중앙 {statistics.median(best_ious):.2f} · p25 {pct(best_ious,25):.2f} · p75 {pct(best_ious,75):.2f}")
for t in (0.3, 0.5, 0.7):
    print(f"  IoU ≥ {t}: {sum(1 for x in best_ious if x >= t)/len(best_ious):5.1%}")
print(f"\n[3] 최선-차선 간격 (미리 고르기의 안전)")
amb = sum(1 for m in margins if m < 0.2)
print(f"  간격 < 0.2 (헷갈리는 자리): {amb/len(margins):5.1%}")
print(f"  최선 IoU ≥ 0.5 이면서 간격 ≥ 0.3: "
      f"{sum(1 for i,m in zip(best_ious,margins) if i>=0.5 and m>=0.3)/len(best_ious):5.1%}")
