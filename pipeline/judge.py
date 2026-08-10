"""규조각 판정 규칙. **여기가 유일한 정의다.**

`segment_diatoms.py`(검출 직후)와 `refilter.py`(문턱 재조정)가 같은 함수를 쓴다 —
두 곳에 적어 두면 어긋나고, 어긋나면 "다시 걸렀더니 결과가 달라졌다" 는 일이 조용히
생긴다.

**torch·cv2 에 기대지 않는다.** 문턱 재조정은 GPU 가 필요 없는 일이고, 뷰어와 처리를
갈라 담을 때(P01 §5) 이 규칙은 가벼운 쪽에 있어야 한다.

받는 레코드는 dict 다. 필요한 값: `shape_ok · major_um · texture · elongation ·
ellipse_iou · solidity · bbox_xywh · area_px`.
"""

# 판정 문턱의 기본값. segment_diatoms.py 의 argparse 와 DB 의 ThresholdSet 이
# 이 값을 함께 쓴다.
DEFAULTS = {
    "min_um": 10.0,
    "max_um": 150.0,
    "texture_min": 1000.0,
    "round_max_elong": 1.4,
    "round_min_iou": 0.85,
    "round_min_solidity": 0.92,
    # 원형은 areolae 를 더 무겁게 본다 — 형태로는 밋밋한 원반을 가려낼 수 없다
    "round_texture_min": 1500.0,
    "rod_min_elong": 2.0,
    "rod_max_elong": 20.0,
    "rod_min_iou": 0.72,
    "rod_min_solidity": 0.85,
}
FIELDS = tuple(DEFAULTS)


class Thresholds:
    """문턱 묶음. argparse.Namespace 처럼 속성으로 읽힌다.

    classify() 가 args 를 속성으로 읽으므로 Namespace 도 이 클래스도 그대로 쓸 수
    있다 — 스크립트와 DB 양쪽에서 같은 함수를 부를 수 있어야 한다.
    """

    def __init__(self, **kw):
        for f in FIELDS:
            setattr(self, f, kw.get(f, DEFAULTS[f]))

    def as_dict(self):
        return {f: getattr(self, f) for f in FIELDS}

    def __eq__(self, other):
        return isinstance(other, Thresholds) and self.as_dict() == other.as_dict()

    def __repr__(self):
        return f"Thresholds({self.as_dict()})"


def classify(r, args):
    """
    (분류, 탈락사유). 분류가 None 이면 규조각 후보가 아니다.

    텍스처가 1차 관문("규조각인가"), 형태가 2차("어떤 형태인가").
    둘 다 필요하다 — 텍스처만 쓰면 쇄설물 조각이, 형태만 쓰면 구조 없는
    티끌이 들어온다. 실측으로 확인했다.
    """
    if not r.get("shape_ok"):
        return None, "형태측정불가"
    # 크기는 적합 타원의 장축으로 다시 본다. bbox 긴 변은 비스듬히 누운 물체에서
    # 실제보다 커지므로, 그것만 보면 4 µm 짜리가 10 µm 관문을 통과한다.
    major = r.get("major_um")
    if major is not None and not (args.min_um <= major <= args.max_um):
        return None, "장축범위밖"
    if r.get("texture") is not None and r["texture"] < args.texture_min:
        return None, "텍스처부족"

    e, iou, sol = r["elongation"], r["ellipse_iou"], r["solidity"]
    if e < args.round_max_elong:
        # 원형은 areolae 를 봉상보다 무겁게 본다. 밋밋한 원반·기포·쇄설물 조각은
        # 형태만으로 걸러지지 않는다 — 실측에서 원형 통과분의 형태 지표는 텍스처
        # 세기와 무관하게 평평했다(IoU 중앙 0.886~0.898, 볼록성 0.957~0.966).
        # 형태로 가려낼 수 없으므로 areolae 세기 자체를 관문으로 둔다.
        round_tex = getattr(args, "round_texture_min", None)
        if round_tex and r.get("texture") is not None and r["texture"] < round_tex:
            return None, "원형areolae부족"
        if iou >= args.round_min_iou and sol >= args.round_min_solidity:
            return "round", None
        return None, "원형기준미달"
    if args.rod_min_elong <= e <= args.rod_max_elong:
        if iou >= args.rod_min_iou and sol >= args.rod_min_solidity:
            return "rod", None
        return None, "봉상기준미달"
    return None, "신장비범위밖"


def _cover(a, b):
    """a 의 bbox 가 b 안에 들어간 비율 (a 면적 기준)."""
    ax, ay, aw, ah = a["bbox_xywh"]
    bx, by, bw, bh = b["bbox_xywh"]
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy / max(aw * ah, 1)


def collapse_boxes(records):
    """**bbox 가 같은 레코드를 하나로 접는다.** `(남긴 것, 버린 수)` 를 돌려준다.

    판정을 하기 **전에** 불러야 한다. DB 의 열쇠가 `mask_key`(= bbox 문자열)라
    같은 bbox 는 한 행밖에 못 들어가는데, 예전에는 **판정한 뒤에** 넣으면서
    버렸다(`segment_diatoms.save_detection` 의 `seen`). 그러면 판정은 34개를
    보고 내렸는데 DB 에는 33개가 앉는다 —

    - `dedupe` 가 A 로 B 를 눌렀는데 **A 가 저장되지 않으면**, 남은 자료만으로
      다시 계산할 때 B 가 살아난다. 저장된 판정과 어긋난다
    - `check_db.py` 의 "판정 == 지표 + 문턱" 이 그것을 잡는데, **자료가 상한
      것이 아니라 본 집합이 다른 것**이라 아무리 다시 계산해도 안 맞는다

    실측(2026-08-07, 배포 v0.8.0 직전): `yolo-3차` 의 검출 1,799개 중 18개가
    넣을 때 하나씩 잃었고, **판정이 어긋난 8개가 전부 그 안에 있었다.** 전부
    이미지 오른쪽 끝(x≈2700, 폭 2752)의 봉상 조각이다 — 가장자리에서 잘린
    마스크를 `keep_largest_body` 로 본체만 남기면 서로 다른 마스크가 같은
    bbox 로 수렴한다.

    **면적이 큰 것을 남긴다.** 같은 자리를 가리키는 둘 중에서는 마스크가 더
    많이 잡힌 쪽이 근거가 많다. 같으면 먼저 온 것을 둔다(정렬이 안정적이라
    입력 순서가 곧 기준이다) — 어느 쪽이든 **결정적**이어야 한다는 것이 요점이다.
    """
    seen, out, dropped = {}, [], 0
    for r in records:
        key = tuple(int(v) for v in r["bbox_xywh"])
        prev = seen.get(key)
        if prev is None:
            seen[key] = len(out)
            out.append(r)
            continue
        dropped += 1
        if (r.get("area_px") or 0) > (out[prev].get("area_px") or 0):
            out[prev] = r
    return out, dropped


def dedupe(selected):
    """
    중첩 마스크 정리.

    SAM2 AMG 는 격자 포인트마다 다중 스케일 마스크를 내므로 최대 6단계까지
    중첩된다. NMS 는 IoU 기반이라 이걸 못 잡는다 — 작은 것이 큰 것 안에 들면
    IoU 는 오히려 작아진다 (실측 중앙값 0.07).

    큰 쪽을 남기면 덩어리가 내부 규조각을 전부 삼키므로, 집합체를 골라 버리고
    개별 물체를 남긴다.
    """
    keep = []
    for a in selected:
        kids = [b for b in selected
                if b is not a and b["area_px"] < a["area_px"] and _cover(b, a) > 0.85]
        # 자식 2개 이상이 자기 면적의 절반 이상을 설명하면 개별 물체가 아니다.
        if len(kids) >= 2 and sum(b["area_px"] for b in kids) > 0.5 * a["area_px"]:
            continue
        keep.append(a)

    # 거의 같은 마스크는 하나로 — 텍스처가 높은 쪽을 남긴다.
    keep.sort(key=lambda r: -(r.get("texture") or 0))
    out = []
    for r in keep:
        if not any(_cover(r, k) > 0.8 and _cover(k, r) > 0.8 for k in out):
            out.append(r)
    return out


def apply(records, args):
    """레코드 묶음에 판정을 건다. (통과분, 탈락분) 을 돌려준다.

    크기 관문은 **타원 장축**으로 본다(classify 안에서). bbox 긴 변으로 한 번 더
    거르지 않는다 — README 가 정한 규칙이고, 두 관문이 어긋나면 장축 11 µm 짜리가
    bbox 9.6 µm 로 떨어지는 일이 생긴다.
    """
    passed, rejected = [], []
    for r in records:
        cls, why = classify(r, args)
        if cls:
            r["cls"] = cls
            passed.append(r)
        else:
            r["cls"] = None
            r["reject"] = why
            rejected.append(r)

    kept = dedupe(passed)
    keep_ids = {id(r) for r in kept}
    for r in passed:
        if id(r) not in keep_ids:
            # 중첩정리로 떨어진 것은 판정을 통과한 뒤 정리된 것이라 cls 를 남긴다
            r["reject"] = "중첩정리"
            rejected.append(r)
    return kept, rejected
