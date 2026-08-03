"""Natural Earth 해안선을 EPSG:3031 로 투영해 SVG path 로 굽는다.

한 번만 돌리고 결과를 템플릿에 박는다 — 뷰어에 지오 라이브러리를 들이지 않기
위해서다(이 뷰어는 정적 파일이 하나도 없고 CSS·JS 를 전부 인라인으로 들고 있다).
"""
import json, math, sys
import proj

VIEW = 4.6e6        # 화면에 담을 반경(m). 남위 약 55도까지.

def simplify(pts, tol):
    """Douglas-Peucker. 정점 2,805개를 그대로 넣으면 HTML 이 무거워진다."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]; bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    worst, wi = -1.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = (abs(dy * px - dx * py + bx * ay - by * ax) / n) if n else math.hypot(px - ax, py - ay)
        if d > worst:
            worst, wi = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[:wi + 1], tol)[:-1] + simplify(pts[wi:], tol)

def rings(geom):
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    return [r for poly in geom["coordinates"] for r in poly]

def main(src, tol_m):
    d = json.load(open(src))
    out = []
    kept = raw = 0
    for f in d["features"]:
        g = f["geometry"]
        for ring in rings(g):
            if not ring or max(p[1] for p in ring) > -55:   # 남극권 밖은 버린다
                continue
            xy = [proj.fwd(lon, lat) for lon, lat in ring]
            raw += len(xy)
            s = simplify(xy, tol_m)
            if len(s) < 4:
                continue
            kept += len(s)
            out.append(s)
    # SVG 좌표: 화면은 y 가 아래로 커진다. 지도의 북(+y)이 위로 가게 뒤집는다.
    def sv(p):
        return f"{p[0] / 1000:.0f},{-p[1] / 1000:.0f}"
    paths = ["M" + "L".join(sv(p) for p in r) + "Z" for r in out]
    sys.stderr.write(f"고리 {len(out)}개 · 정점 {raw} → {kept} ({100*kept/raw:.0f}%)\n")
    return " ".join(paths)

if __name__ == "__main__":
    print(main(sys.argv[1], float(sys.argv[2])))
