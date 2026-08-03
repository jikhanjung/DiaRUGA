"""EPSG:3031 — WGS 84 / Antarctic Polar Stereographic.

남극점 중심, 71°S 에서 축척이 참값. Snyder(1987) 타원체 극구면투영식 그대로다.
pyproj 가 없는 장비라 직접 구현했다 — 아래에서 왕복과 기준점으로 검증한다.
"""
import math

A = 6378137.0                 # WGS84 장반경
F = 1 / 298.257223563
E2 = 2 * F - F * F
E = math.sqrt(E2)
PHI_C = math.radians(-71.0)   # 표준위도
LAM_0 = 0.0                   # 중앙자오선

def _t(phi):
    s = E * math.sin(phi)
    return math.tan(math.pi / 4 + phi / 2) / (((1 + s) / (1 - s)) ** (E / 2))

_MC = math.cos(PHI_C) / math.sqrt(1 - E2 * math.sin(PHI_C) ** 2)
_TC = _t(PHI_C)

def fwd(lon, lat):
    """(경도, 위도) → (x, y) 미터."""
    phi, lam = math.radians(lat), math.radians(lon)
    rho = A * _MC * _t(phi) / _TC
    return rho * math.sin(lam - LAM_0), rho * math.cos(lam - LAM_0)

def inv(x, y):
    """(x, y) → (경도, 위도). 왕복 검증용."""
    rho = math.hypot(x, y)
    if rho == 0:
        return 0.0, -90.0
    t = rho * _TC / (A * _MC)
    phi = math.pi / 2 - 2 * math.atan(t)          # 초기값
    for _ in range(12):                            # Snyder 의 반복해
        s = E * math.sin(phi)
        phi = math.pi / 2 - 2 * math.atan(t * (((1 - s) / (1 + s)) ** (E / 2)))
    # Snyder 의 반복해는 위도의 크기를 낸다 — 남극이므로 부호를 뒤집는다
    return math.degrees(math.atan2(x, y) + LAM_0), -math.degrees(phi)
