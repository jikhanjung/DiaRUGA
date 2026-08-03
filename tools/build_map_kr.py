"""Natural Earth 국가 경계에서 **남한만** 뽑아 EPSG:5179 로 투영해 SVG 로 굽는다.

    python3 build_map_kr.py ne_10m_admin_0_countries.geojson 400

`build_map.py`(남극)와 같은 일을 하지만 자료와 투영이 다르다.

- **해안선(`ne_*_land`)이 아니라 국가 경계를 쓴다.** 남한만 그리려면 휴전선이
  필요한데 해안선 자료에는 그것이 없다 — 한반도가 통째로 한 덩어리로 나온다
- **10m 자료다.** 남극은 50m 로 충분했지만(대륙 전체를 한 화면에 담았다) 남한은
  훨씬 작아서 50m 로는 해안선이 각져 보인다
- 투영은 EPSG:5179 (`proj_kr.py`). 먼저 `python3 proj_kr.py` 로 검산할 것

**나온 path 를 파이썬 소스에 넣을 때 줄바꿈이 좌표 한가운데 떨어지면 안 된다.**
인접 리터럴이 이어지며 공백이 남고 SVG 파서가 경로를 통째로 버린다 — 오류 없이
백지가 된다(devlog 021 에서 실제로 당했다). 서브패스(`M`)마다 한 줄씩 쓴다.
"""
import json
import math
import sys

import proj_kr as proj

# 자료의 부스러기만 거른다. 독도(NE 자료에서 0.03 km²)까지 남겨야 하므로 낮게
# 잡는다 — 화면에서는 점 하나지만 **없으면 안 되는 점이다.**
MIN_AREA_KM2 = 0.01


def simplify(pts, tol):
    """Douglas-Peucker. build_map.py 와 같은 구현이다."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    worst, wi = -1.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = (abs(dy * px - dx * py + bx * ay - by * ax) / n) if n \
            else math.hypot(px - ax, py - ay)
        if d > worst:
            worst, wi = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[:wi + 1], tol)[:-1] + simplify(pts[wi:], tol)


def ring_area(pts):
    """신발끈 공식. m² 로 나온다 (좌표가 m 이므로)."""
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def rings(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    return [r for poly in geom["coordinates"] for r in poly]


def main(src, tol_m):
    d = json.load(open(src))
    feat = next((f for f in d["features"]
                 if f["properties"].get("NAME") == "South Korea"), None)
    if feat is None:
        sys.exit("자료에서 South Korea 를 못 찾았다")

    parts, raw, kept = [], 0, 0
    bbox = [1e18, 1e18, -1e18, -1e18]
    dropped = []
    for ring in rings(feat["geometry"]):
        if not ring:
            continue
        xy = [proj.fwd(lon, lat) for lon, lat in ring]
        raw += len(xy)
        km2 = ring_area(xy) / 1e6
        if km2 < MIN_AREA_KM2:
            dropped.append(km2)
            continue
        # **작은 섬은 단순화하지 않는다.** 독도는 가로 200 m 남짓이라 허용오차
        # 400 m 로 줄이면 두 점으로 뭉개져 `len(s) < 4` 에 걸려 통째로 사라진다.
        # 면적 문턱을 낮춰도 여기서 다시 죽어서 한 번 놓쳤다.
        s = simplify(xy, tol_m) if km2 > 10 * (tol_m / 1000) ** 2 else xy
        if len(s) < 4:
            dropped.append(km2)
            continue
        kept += len(s)
        for x, y in s:
            bbox[0] = min(bbox[0], x); bbox[1] = min(bbox[1], y)
            bbox[2] = max(bbox[2], x); bbox[3] = max(bbox[3], y)
        parts.append((km2, s))

    parts.sort(key=lambda p: -p[0])
    print(f"고리 {len(parts)}개 · 정점 {raw} → {kept}", file=sys.stderr)
    print(f"버린 작은 고리 {len(dropped)}개 "
          f"(가장 큰 것 {max(dropped):.2f} km²)" if dropped else "", file=sys.stderr)
    print(f"큰 것 다섯: {[round(a) for a, _ in parts[:5]]} km²", file=sys.stderr)

    # SVG 는 y 가 아래로 자란다. 투영 y 는 위로 자라므로 뒤집는다.
    x0, y0, x1, y1 = bbox
    pad = 20_000
    vb = (x0 - pad, -(y1 + pad), (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad)
    print(f"viewBox {tuple(round(v) for v in vb)}  "
          f"({(x1-x0)/1000:.0f} × {(y1-y0)/1000:.0f} km)", file=sys.stderr)

    print("LAND = (")
    for _, s in parts:
        seg = "M" + "L".join(f"{round(x)},{round(-y)}" for x, y in s) + "Z"
        print(f'    "{seg}"')
    print(")")
    print()
    print("VIEWBOX = (" + ", ".join(str(round(v)) for v in vb) + ")")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 400.0)
