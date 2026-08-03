"""EPSG:5179 (Korea 2000 / Unified CS, "UTM-K") 정·역변환.

한국 지도를 굽는 데만 쓴다. `proj.py`(EPSG:3031, 남극)와 같은 자리에 두지만
투영이 아예 다르다 — 남극은 극심 입체(polar stereographic), 한국은 횡메르카토르
(transverse Mercator)다.

EPSG:5179 를 고른 이유: **국내에서 실제로 쓰는 좌표계**다(국가공간정보포털·
브이월드가 이것이다). 위경도를 그대로 x·y 로 쓰면 위도 37도에서 가로가 약 1.25배
늘어나 한반도가 뚱뚱해진다.

    타원체   GRS80 (a=6378137, 1/f=298.257222101)
    원점     38°N 127.5°E
    축척     0.9996
    가원점   E 1,000,000 · N 2,000,000

**`python3 -c "import proj_kr"` 만으로는 아무것도 검증되지 않는다.** 아래
`_selftest()` 를 돌릴 것 — 원점 일치·왕복·축척을 함께 본다.
"""
import math

A = 6378137.0
F = 1 / 298.257222101
E2 = 2 * F - F * F
EP2 = E2 / (1 - E2)

LAT0 = math.radians(38.0)
LON0 = math.radians(127.5)
K0 = 0.9996
FE, FN = 1_000_000.0, 2_000_000.0


def _meridian_arc(phi: float) -> float:
    """적도에서 위도 phi 까지의 자오선 호 길이."""
    return A * ((1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256) * phi
                - (3 * E2 / 8 + 3 * E2**2 / 32 + 45 * E2**3 / 1024)
                * math.sin(2 * phi)
                + (15 * E2**2 / 256 + 45 * E2**3 / 1024) * math.sin(4 * phi)
                - (35 * E2**3 / 3072) * math.sin(6 * phi))


M0 = _meridian_arc(LAT0)


def fwd(lon: float, lat: float) -> tuple[float, float]:
    """위경도(도) → EPSG:5179 (m)."""
    phi, lam = math.radians(lat), math.radians(lon)
    sp, cp, tp = math.sin(phi), math.cos(phi), math.tan(phi)
    n = A / math.sqrt(1 - E2 * sp * sp)
    t = tp * tp
    c = EP2 * cp * cp
    a_ = (lam - LON0) * cp

    x = FE + K0 * n * (a_ + (1 - t + c) * a_**3 / 6
                       + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a_**5 / 120)
    y = FN + K0 * (_meridian_arc(phi) - M0 + n * tp
                   * (a_**2 / 2 + (5 - t + 9 * c + 4 * c * c) * a_**4 / 24
                      + (61 - 58 * t + t * t + 600 * c - 330 * EP2)
                      * a_**6 / 720))
    return x, y


def inv(x: float, y: float) -> tuple[float, float]:
    """EPSG:5179 (m) → 위경도(도). 왕복 검산에 쓴다."""
    m = M0 + (y - FN) / K0
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    mu = m / (A * (1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256))
    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
            + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
            + (151 * e1**3 / 96) * math.sin(6 * mu)
            + (1097 * e1**4 / 512) * math.sin(8 * mu))

    sp, cp, tp = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = EP2 * cp * cp
    t1 = tp * tp
    n1 = A / math.sqrt(1 - E2 * sp * sp)
    r1 = A * (1 - E2) / (1 - E2 * sp * sp) ** 1.5
    d = (x - FE) / (n1 * K0)

    phi = phi1 - (n1 * tp / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2
           - 3 * c1 * c1) * d**6 / 720)
    lam = LON0 + (d - (1 + 2 * t1 + c1) * d**3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2
                     + 24 * t1 * t1) * d**5 / 120) / cp
    return math.degrees(lam), math.degrees(phi)


def _selftest() -> None:
    ok = True

    def check(name, got, want, tol, unit=""):
        nonlocal ok
        bad = abs(got - want) > tol
        ok = ok and not bad
        print(f"  {'✗' if bad else '·'} {name}: {got:.4f} (기대 {want}{unit}, "
              f"허용 ±{tol})")

    print("1. 투영 원점은 가원점으로 정확히 떨어져야 한다")
    x, y = fwd(127.5, 38.0)
    check("x", x, FE, 1e-6)
    check("y", y, FN, 1e-6)

    # 계열 전개라 중앙자오선에서 멀수록 벌어진다. ±3도 안에서는 0.1 mm 이고,
    # 최악은 독도(131.9°E, 중앙자오선에서 4.4도)의 5 mm 다. 지도에서 1 px 이
    # 800 m 쯤이므로 상관없는 크기이고, **허용치를 사실에 맞춰 둔다** —
    # 통과시키려고 느슨하게 잡은 것이 아니라 실제 오차가 이만큼이라는 기록이다.
    print("2. 왕복 (한국 전역 격자, 독도까지) — 1 cm 안")
    worst, where = 0.0, None
    for lat in [33.0, 34.5, 36.0, 37.5, 38.7]:
        for lon in [125.0, 126.5, 128.0, 129.5, 131.9]:
            gx, gy = fwd(lon, lat)
            blon, blat = inv(gx, gy)
            d = math.hypot((blat - lat) * 111_320,
                           (blon - lon) * 111_320 * math.cos(math.radians(lat)))
            if d > worst:
                worst, where = d, (lat, lon)
    check(f"최대 왕복 오차 (위도 {where[0]} 경도 {where[1]})", worst, 0.0,
          1e-2, " m")

    print("3. 축척 — 중앙자오선 위 거리는 실제보다 0.04% 짧아야 한다 (k0=0.9996)")
    x1, y1 = fwd(127.5, 36.0)
    x2, y2 = fwd(127.5, 37.0)
    grid = math.hypot(x2 - x1, y2 - y1)
    true = _meridian_arc(math.radians(37.0)) - _meridian_arc(math.radians(36.0))
    check("격자거리/실거리", grid / true, K0, 1e-9)

    print("4. 알려진 지점이 그럴듯한 자리에 오는가")
    # 서울시청 37.5665N 126.9780E. 중앙자오선에서 서쪽 0.522도(≈46 km)이고
    # 원점보다 남쪽 0.4335도(≈48 km)다 — 대략 (954000, 1952000) 근처여야 한다.
    x, y = fwd(126.9780, 37.5665)
    check("서울시청 x", x, 953_700, 1_500, " m")
    check("서울시청 y", y, 1_952_400, 1_500, " m")

    print("\n" + ("전부 통과" if ok else "실패한 검사가 있다"))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    _selftest()
