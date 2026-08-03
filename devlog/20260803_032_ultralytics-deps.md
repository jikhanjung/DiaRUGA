# ultralytics 를 운영 이미지에 넣는다 — 상한이 진짜인지 확인하고

**날짜** 2026-08-03
**앞선 문서** `20260803_025_yolo-first-training.md` · `20260803_031_frame-name-collision.md`

`ultralytics` 를 파이프라인 이미지에 넣으려다 빌드가 `ResolutionImpossible` 로
죽었다. 그것이 급한 고침(031)의 배포까지 막아서 일단 뺐다가, 이제 풀었다.

---

## 1. 무엇과 부딪혔나

pip 에게 직접 물었다.

```
$ pip install --dry-run ultralytics==8.4.7
Would install … torch-2.9.1 torchvision-0.24.1 nvidia-*-cu12 … (약 2 GB)
```

**단독으로는 성공한다. 대신 torch 를 2.13.0 → 2.9.1 로 내린다.**
`requirements-pipeline.txt` 는 `torch==2.13.0` 으로 못 박고 있으므로 pip 가
양쪽을 만족시킬 수 없다.

메타데이터를 보면 이유가 한 줄이다.

```
Requires-Dist: torch<2.10,>=1.8.0
```

**상한이다.** ultralytics 가 "2.10 이상에서 안 된다" 를 확인한 것이 아니라,
아직 안 본 판을 막아 둔 것이다.

## 2. 상한이 진짜인지 확인했다

두 가지 증거가 있었다.

**첫째, 이미 돌려 봤다.** 892개 프레임 전부에 YOLO 검출을 돌린 것(025)과
`--no-shape-filter` 판(031 앞)이 전부 이 이미지의 **torch 2.13.0+cu126** 에서
돌았다. 컨테이너에 `pip install ultralytics` 로 얹어 썼는데, 확인해 보니
**pip 가 torch 를 안 내렸다** — 이미 설치된 것을 그대로 두었다.

```
torch 2.13.0+cu126 · torchvision 0.28.0+cu126
/tmp/.local 에 torch 가 따로 깔렸나 → 없음
```

**둘째, 다시 재 봤다.** `--no-deps` 로 넣고 추론을 돌렸다.

```
torch 2.13.0+cu126 · cv2 5.0.0(headless) · ultralytics 8.4.7
YOLO 마스크 1 · VRAM 0.73 GiB
sam2 import OK
```

**상한을 무시해도 된다.** 다만 이것은 **이 판 조합에서 실측한 것**이지 일반적인
보증이 아니다 — ultralytics 나 torch 를 올릴 때 다시 확인해야 한다.
`requirements-yolo.txt` 머리말에 그렇게 적었다.

## 3. `--no-deps` 로 넣고 의존을 손으로 적는다

```
pip install -r requirements-pipeline.txt --extra-index-url …/cu126
pip install --no-deps -r requirements-yolo.txt
```

**파일을 갈랐다.** `--no-deps` 를 한 파일에 섞을 수 없기 때문이다.

`--no-deps` 는 torch 를 지키는 것 말고 하나를 더 막는다. ultralytics 는
`opencv-python`(GUI 판)을 의존성으로 끌고 오는데, **이 슬림 이미지에는 libxcb 가
없어** headless 판을 가리는 순간 죽는다.

```
ImportError: libxcb.so.1: cannot open shared object file
```

실제로 한 번 당했다. `--no-deps` 면 애초에 안 들어온다.

대신 ultralytics 가 실제로 쓰는 것들을 **손으로 적어야 한다** — matplotlib·scipy·
polars·psutil·requests·PyYAML 과 그것들이 끌고 오는 것들(contourpy·fonttools·
urllib3 등). 판을 전부 고정했다. **손으로 적은 목록이라 ultralytics 를 올릴 때
같이 봐야 한다.**

## 4. 빌드 중 root 가 남긴 것이 실행을 방해했다

빌드 끝에 `import ultralytics` 로 확인하는데, 그 import 가 **root 로 돌면서**
`/tmp/Ultralytics` 를 root 소유로 만들어 놓는다. 컨테이너는 `1000:1000` 으로
도므로 실행마다 이렇게 뱉는다.

```
ERROR ❌ Error writing to /tmp/Ultralytics/persistent_cache.json: Permission denied
```

죽지는 않는다. **그래서 더 나쁘다** — 매 실행 로그에 빨간 줄이 하나 늘고, 진짜
문제가 났을 때 그것에 묻힌다.

`YOLO_CONFIG_DIR=/tmp/.ultralytics` 를 잡고, **빌드 끝에 `/tmp` 를 치웠다.**
환경변수만으로는 안 됐다 — 이미 있는 디렉토리를 먼저 보기 때문이다.

## 5. 확인

운영 이미지 안에서 실제 파이프라인 명령을 돌렸다.

```
$ segment_diatoms.py "…/RS23-GC03 231cm" --backend yolo --keep-current --scale 1.0
--keep-current: 새 검출을 is_current 로 올리지 않는다
Snap-22069: raw=5 크기통과=4 최종=1 (봉상 1, 원형 0)
검출 3개 · 개체 17개
```

`sam2` 백엔드도 그대로 import 된다 — 기존 파이프라인은 안 건드렸다.

이미지는 **6.98 GB → 7.21 GB**(+230 MB). matplotlib·scipy·polars 몫이다.

## 남는 것

- **아직 배포하지 않았다.** `.env` 의 `PIPELINE_TAG` 는 `v0.1.1` 이다.
  `v0.1.2` 로 올리면 폴러가 쓰는 이미지에서도 `--backend yolo` 가 된다
- **`requirements-yolo.txt` 는 손으로 적은 목록이다.** ultralytics 를 올릴 때
  `pip install --dry-run` 으로 무엇이 달라졌는지 다시 봐야 한다
- torch 상한을 무시한 것은 **이 판 조합에서의 실측**이다. torch 를 올릴 때
  같은 확인을 다시 한다
