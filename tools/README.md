# tools — 한 번 돌리고 결과를 박아 두는 것들

여기 있는 것은 뷰어나 파이프라인이 **실행 중에 부르지 않는다.** 결과를 굽고
저장소에 박아 두면 그만인 일이다. 다시 구울 일이 생겼을 때 어떻게 만들었는지
알 수 있게 남긴다.

## 남극 지도 (`proj.py` · `build_map.py`)

`web/viewer/antarctica.py` 를 만든 것들이다. 자세한 것은 devlog 021.

```bash
cd tools
curl -sSL -o ne_50m_land.geojson \
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson
python3 build_map.py ne_50m_land.geojson 10000    # 10 km 허용오차
```

- `proj.py` — EPSG:3031 정·역변환. **`python3 -c "import proj"` 만으로는 검증이
  안 된다** — devlog 021 의 왕복·기준점 검사를 함께 볼 것
- `build_map.py` — GeoJSON → 투영 → Douglas-Peucker → SVG path

`ne_50m_land.geojson`(1.6 MB)은 커밋하지 않는다. 위 명령으로 언제든 받는다.

## 남한 지도 (`proj_kr.py` · `build_map_kr.py`)

`web/viewer/korea.py` 를 만든 것들이다. 자세한 것은 devlog 024.

```bash
cd tools
curl -sSL -o ne_10m_admin_0_countries.geojson \
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson
python3 proj_kr.py                                        # 먼저 검산 (원점·왕복·축척)
python3 build_map_kr.py ne_10m_admin_0_countries.geojson 400
```

- `proj_kr.py` — EPSG:5179(UTM-K) 정·역변환. `__main__` 이 검산이다. **왕복
  오차 5 mm 는 정상**이고 전부 독도(중앙자오선에서 4.4도) 한 곳이다
- **해안선이 아니라 국가 경계를 쓴다.** 남한만 그리려면 휴전선이 필요하다
- **10m 자료다.** 50m 로는 남해안 섬들이 뭉개진다 (13 MB, 커밋하지 않는다)
- 나온 좌표는 **m** 단위다. 남극(km)과 달라서 `views._map_ctx()` 가 마커를
  `scale()` 로 키운다

**작은 섬은 단순화하지 않는다.** 독도는 가로 200 m 라 허용오차 400 m 로 줄이면
두 점이 되어 통째로 사라진다 — `build_map_kr.py` 가 면적으로 걸러 낸다.

**주의:** 나온 path 문자열을 파이썬 소스에 넣을 때 **줄바꿈이 좌표 한가운데
떨어지면 안 된다.** 인접 리터럴이 이어지면서 공백이 남고, SVG 파서가 경로를
통째로 버린다 — 오류 없이 백지가 된다. 서브패스(`M`)마다 한 줄씩 쓴다.
