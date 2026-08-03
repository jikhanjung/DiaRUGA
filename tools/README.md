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

**주의:** 나온 path 문자열을 파이썬 소스에 넣을 때 **줄바꿈이 좌표 한가운데
떨어지면 안 된다.** 인접 리터럴이 이어지면서 공백이 남고, SVG 파서가 경로를
통째로 버린다 — 오류 없이 백지가 된다. 서브패스(`M`)마다 한 줄씩 쓴다.
