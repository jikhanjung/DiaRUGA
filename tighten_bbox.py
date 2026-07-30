#!/usr/bin/env python3
"""bbox 를 마스크 본체에 맞게 다시 잡는다. SAM2 를 다시 돌리지 않는다.

SAM 이 준 bbox 는 마스크의 **모든** 픽셀을 감싼다. 후처리를 끄고 돌렸으므로
(`apply_postprocessing=False`, `min_mask_region_area=0`) 본체에서 수십 px 떨어진
1~2 픽셀짜리 조각이 남아 있고, bbox 는 그것까지 감싸느라 크게 벌어진다.
실측으로 통과분의 27.5% 가 본체보다 10 px 넘게 큰 bbox 를 갖고 있었다.

반면 `shape_metrics()` 는 가장 큰 윤곽 하나만 쓰므로 **폴리곤과 형태 지표는 이미
본체 기준**이다. 그래서 폴리곤 범위로 bbox 를 다시 잡으면 재추론 없이 맞출 수 있다.

이것이 고치는 것:
  - 클릭 판정·크롭이 빈 자리를 잡는 문제
  - 채움율(면적/bbox)이 부풀린 bbox 때문에 낮게 나오는 문제
  - **중복 정리.** 상호 포함율 0.8 문턱을 bbox 로 재는데, 벌어진 bbox 때문에
    같은 물체의 중복이 0.794 로 문턱을 아슬아슬하게 피해 살아남았다

**bbox 는 교정 기록(review/)의 키다.** 그래서 이 스크립트가 키까지 함께 옮긴다.
원래 SAM bbox 는 `bbox_sam` 으로 남겨 되짚을 수 있게 한다.

    python tighten_bbox.py --dry-run     # 무엇이 바뀌는지만 본다
    python tighten_bbox.py               # out/ 과 review/ 를 함께 옮긴다

옮긴 뒤에는 중복 정리를 다시 돌려야 한다 (문턱은 그대로):

    python refilter.py out/
"""
import argparse
import json
import shutil
import time
from pathlib import Path


def polygon_box(c):
    """폴리곤(가장 큰 윤곽)의 외접 사각형. 이것이 본체의 bbox 다."""
    p = c.get("polygon") or []
    if len(p) < 6:
        return None
    xs, ys = p[0::2], p[1::2]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def key_of(box):
    """review/ 의 키 규칙과 같아야 한다 (data.cand_key / 뷰어 keyOf)."""
    return "_".join(str(int(round(v))) for v in box)


def retighten(c, um_per_px):
    """bbox 와 bbox 에서 파생된 값들을 본체 기준으로 다시 계산한다.

    (바뀌었는가, 옛 키, 새 키) 를 돌려준다.
    """
    new = polygon_box(c)
    if new is None:
        return False, None, None
    old = c["bbox_xywh"]
    if [int(v) for v in old] == [int(v) for v in new]:
        return False, key_of(old), key_of(old)

    # 원래 값을 남긴다 — 나중에 "왜 bbox 가 이 값인가" 를 되짚을 수 있게.
    c.setdefault("bbox_sam", [int(v) for v in old])
    c["bbox_xywh"] = [int(v) for v in new]
    x, y, w, h = new
    c["center_xy"] = [int(x + w / 2), int(y + h / 2)]
    # bbox 에서 파생되는 값들. long_side_um 은 refilter 의 크기 관문이 쓴다.
    c["long_side_um"] = round(max(w, h) * um_per_px, 2)
    c["short_side_um"] = round(min(w, h) * um_per_px, 2)
    c["aspect_ratio"] = round(max(w, h) / max(min(w, h), 1), 2)
    if c.get("area_px") is not None:
        c["fill_ratio"] = round(c["area_px"] / max(w * h, 1), 3)
    return True, key_of(old), key_of(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default="out",
                    help="검출 JSON 디렉토리 (기본 out/)")
    ap.add_argument("--review", default="review", help="교정 기록 디렉토리")
    ap.add_argument("--dry-run", action="store_true", help="확인만, 저장 안 함")
    ap.add_argument("--no-backup", action="store_true",
                    help="review/ 백업을 만들지 않는다 (권장하지 않음)")
    args = ap.parse_args()

    target = Path(args.target)
    files = sorted(target.glob("*_candidates.json"))
    if not files:
        raise SystemExit(f"검출 JSON 을 찾지 못했다: {target}")

    keymap = {}        # stem -> {옛 키: 새 키}
    n_rec = n_changed = 0
    shrink = []
    payloads = {}

    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        um = payload.get("um_per_pixel") or 0.0
        stem = f.name[: -len("_candidates.json")]
        m = {}
        for pool in ("candidates", "rejected"):
            for c in payload.get(pool) or []:
                n_rec += 1
                changed, old_key, new_key = retighten(c, um)
                if old_key:
                    m[old_key] = new_key
                if changed:
                    n_changed += 1
                    ob = [int(v) for v in c["bbox_sam"]]
                    nb = c["bbox_xywh"]
                    shrink.append((ob[2] * ob[3]) / max(nb[2] * nb[3], 1))
        keymap[stem] = m
        payloads[f] = payload

    shrink.sort()
    print(f"{len(files)}개 파일 · 개체 {n_rec}개 중 {n_changed}개의 bbox 를 줄인다 "
          f"({100 * n_changed / max(n_rec, 1):.1f}%)")
    if shrink:
        print(f"  면적 축소 배율: 중앙 {shrink[len(shrink) // 2]:.2f}배 "
              f"p90 {shrink[int(0.9 * len(shrink))]:.2f}배 최대 {shrink[-1]:.2f}배")

    # --- 교정 기록의 키 옮기기 ---------------------------------------------
    rv_dir = Path(args.review)
    rv_files = sorted(rv_dir.glob("*_review.json")) if rv_dir.is_dir() else []
    moved = kept = orphan = 0
    new_reviews = {}
    for rf in rv_files:
        rv = json.loads(rf.read_text(encoding="utf-8"))
        m = keymap.get(rv.get("stem"), {})
        out = dict(rv)
        for field in ("removed", "accepted"):
            keys = rv.get(field) or []
            mapped = []
            for k in keys:
                if k in m:
                    mapped.append(m[k])
                    if m[k] != k:
                        moved += 1
                    else:
                        kept += 1
                else:
                    # 검출 결과에서 사라진 키 — 그대로 두면 아무 개체에도 붙지 않는다.
                    mapped.append(k)
                    orphan += 1
            out[field] = sorted(set(mapped))
        new_reviews[rf] = out

    print(f"교정 기록 {len(rv_files)}개 파일: 키 {moved}개 이동 · {kept}개 그대로 · "
          f"{orphan}개는 대응 개체를 찾지 못함")
    if orphan:
        print("  (찾지 못한 키는 손대지 않는다 — 검출을 다시 돌려 없어진 개체일 수 있다)")

    if args.dry_run:
        print("\ndry-run — 파일은 변경하지 않았다.")
        print("적용 후에는 중복 정리를 다시 돌린다: python refilter.py out/")
        return

    if rv_files and not args.no_backup:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        backup = rv_dir.with_name(f"{rv_dir.name}.bak_{stamp}")
        shutil.copytree(rv_dir, backup)
        print(f"교정 기록을 {backup} 로 백업했다 (재생성 불가한 자료다)")

    for f, payload in payloads.items():
        f.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for rf, body in new_reviews.items():
        tmp = rf.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(rf)

    print(f"저장했다. 이어서 중복 정리를 다시 돌린다: python refilter.py {target}/")


if __name__ == "__main__":
    main()
