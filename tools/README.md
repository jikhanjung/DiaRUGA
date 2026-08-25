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

## 도감 색인 → JSON (`parse_atlas.py` · `harvest_worms.py` · `annotate_index.py`)

**P15 반입의 1단계다.** 색인은 NAS(`Diadiction/md/*.md`)에 있고 뷰어 컨테이너는
그 공유를 못 보므로(P14 4.4), **호스트에서 JSON 으로 뽑아 저장소에 박아 둔다.**
2단계(JSON → DB)는 `dbrun.sh` 로 컨테이너에서 돈다 — 자세한 것은 devlog 128.

```bash
python tools/parse_atlas.py              # atlas/*.json 으로 뽑는다
python tools/parse_atlas.py --dry-run    # 안 쓰고 검산만
python3 tools/test_parse_atlas.py        # NAS 없이 도는 시험 (합성 색인)
```

- **원본은 md 이고 `atlas/*.json` 은 사본이다** (P15 4.2). 언제든 지우고 다시
  만든다. 색인이 바뀌면 다시 돌리고, **바뀐 것은 diff 로 보인다**
- **이름을 뽑는 규칙은 `harvest_worms.binomial` 하나뿐이다.** 표시를 붙이는
  `annotate_index.py` 도, 이 파서도 거기를 부른다. 실제로 세 벌의 이명법
  집합이 **한 글자도 안 다르다**(128 에서 확인) — 두 벌이 되면 대조표와 붙는
  자리가 어긋난다
- **표시를 걷는 규칙도 하나뿐이다** (`annotate_index.MARK`). 색인에는 `〔…〕`
  가 두 가지 있고 **하나는 색인의 자료다**(`〔Tafel 아님 …〕` · 21건).
  아무 `〔…〕` 나 걷으면 그것이 조용히 사라진다
- **검산이 어긋나면 아무것도 안 쓴다.** 파일에서 직접 센 것 · 색인 머리말이
  적어 둔 수 · 속별 목록 셋을 본다

## 도감 오프라인 꾸러미 (`build_offline_atlas.py` · `offline_assets/`)

색인 셋·도판·학명 대조표를 **서버도 인터넷도 없이** 볼 수 있게 굽는다
(devlog 156). `index.html` 하나가 옆의 `data/`·`pages/`·`thumbs/` 를 참조한다.

```bash
python tools/build_offline_atlas.py --version 1.0.0             # 완전판 (1.1 GB · 3분)
python tools/build_offline_atlas.py --version 1.0.0 --limit 8   # 눌러 볼 때 (권마다 8쪽)
python tools/build_offline_atlas.py --version 1.0.0 --no-images # 글자만
```

- **`fetch` 를 안 쓴다.** `file://` 에서는 로컬 JSON 이 CORS 로 막힌다 —
  자료가 `data/*.js` 로 나가 전역에 값을 놓는다
- **한 파일에 다 못 담는다.** 도판 1.1 GB 를 base64 로 넣으면 1.5 GB 문서가
  되어 브라우저가 죽는다. 진짜 단일 파일이 필요하면 같이 나오는
  `diadiction-index-v*.html`(글자만 2.4 MB)을 쓴다
- **쪽 이름·권 코드 규칙은 `web/viewer/atlas.py` 를 임포트해서 쓴다.** 여기서
  다시 만들면 넷째 도감에서 갈린다
- **꾸러미에 안 실린 쪽은 링크를 안 낸다** — 뷰어와 갈리는 자리다(뷰어는
  링크마다 디스크를 안 짚는다). 번호는 남긴다: 안 실린 것과 색인이 안 적은
  것은 다른 말이다
- 다시 돌리면 **이미 구운 쪽은 건너뛴다**(`--force` 로만 다시 굽는다)
