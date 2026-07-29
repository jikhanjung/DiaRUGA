# diatom

극지 퇴적물 코어 시료의 규조류 광학현미경 사진 분석 파이프라인.

## 데이터

ZEISS Axio Imager.A2 + ZEN 3.8.99 로 촬영한 명시야 투과광 사진.
사진마다 `<파일명>.jpg_metadata.xml` 이 동반된다.

| 폴더 | 장수 | 파일 범위 |
|---|---|---|
| WAP13-GC47 116cm | 93 | Snap-21171 ~ 21263 |
| WAP13-GC47 450cm | 101 | Snap-21264 ~ 21364 |
| RS23-GC03 71cm | 151 | Snap-21365 ~ 21515 |

파일 번호가 폴더 간 연속이며 한 세션(`LM - 20260729_135143`)에서 촬영됐다.

### 촬영 조건 (XML에서 추출, 전 사진 동일)

- 대물 Plan-Apochromat 40x/0.95 Korr M27 (air, WD 250 µm)
- Optovar 1.6x, 카메라 어댑터 0.63x → 카메라측 실효배율 40.32x, 접안 기준 640x
- Axiocam 506c, 4.54 µm 픽셀, 14-bit 취득 후 8-bit BGR JPG 저장, binning 1x1
- TL 할로겐 3.13 V, 반사경 none, RL 셔터 닫힘 (투과광 명시야)
- 노출 195.568 ms
- 이미지 2752 x 2208

### 스케일

**0.112599 µm/pixel** (`Scaling/Items/Distance` = 1.1259920634920635e-7 m).
따라서 시야(FOV)는 **309.8 x 248.6 µm**. 크기 측정에 그대로 쓸 수 있다.

### XML의 한계

**스테이지 XY / 포커스 Z 좌표가 기록돼 있지 않다.** `ZPosition` 계열 태그가
나오지만 전부 `FixedZPosition=0` 같은 실험 설정 템플릿 값이고 실측 위치가 아니다.
Snap 단발 촬영이라 Z-stack 으로 기록되지 않았다.

같은 시야를 초점만 바꿔 찍은 두 장(21365, 21366)과 다른 시야의 한 장(21371)의
XML을 diff 하면 **차이가 완전히 동일**하다 — 타임스탬프와 내부 GUID 뿐이다.
즉 XML만으로는 초점 시리즈를 묶을 수 없어서 이미지 내용으로 판단해야 한다.

사진마다 유일하게 의미 있게 달라지는 값은 `AcquisitionDateAndTime` 이다.

## 스크립트

### group_focus_series.py — 초점 시리즈 그룹핑

같은 위치를 초점만 바꿔 찍은 사진들을 묶는다. 축소 + 가우시안 블러로 고주파를
죽인 저주파 지문의 정규화 상관계수를 쓴다. 초점이 달라져도 입자 배치는
그대로이므로 초점 변화에는 둔감하고 시야 이동에는 민감하다.

```
python group_focus_series.py "/mnt/d/260729/RS23-GC03 71cm" -o groups_RS23.json
```

RS23-GC03 71cm 기준 151장 → **34 그룹**. 분리가 매우 깨끗하다:
인접 상관계수가 **0.35 이하 아니면 0.936 이상**으로 양분되고 그 사이에 값이 없어,
기본 임계값 0.55는 빈 구간 한가운데에 놓인다.

그룹마다 Laplacian 분산으로 가장 선명한 장(`sharpest`)을 함께 기록하므로,
그룹당 대표 한 장만 골라 후속 처리하면 작업량이 1/5 로 줄어든다.

### focus_stack.py — all-in-focus 합성 + 깊이 맵

그룹을 ECC로 정렬(초점 브리딩·스테이지 흔들림 보정)한 뒤, 픽셀별 국소 선명도를
가중치로 soft blending 한다.

```
python focus_stack.py groups_RS23.json -o stacked/
python focus_stack.py groups_RS23.json -o stacked/ --only 0 1 2   # 일부만
```

산출물: `<tag>_focused.jpg`, `<tag>_depth.jpg`, `<tag>_depth.npz`.

선명도 비교는 **전역 Laplacian 분산으로 하면 안 된다.** 초점이 크게 어긋난 덩어리는
짙은 그림자가 되어 오히려 분산을 키우므로, 합성이 성공해도 숫자가 내려간다
(실제로 0.77x 로 나왔다). 물체 영역의 국소 선명도로 비교해야 하며, 그 기준으로는
최선 단일 프레임 대비 1.04~1.15x 로 개선된다.

### 깊이 맵에 대해 (현재는 참고용)

픽셀마다 어느 장이 가장 선명했는지가 곧 상대 높이라 깊이 맵이 함께 나온다.
포물선 보간으로 슬라이스 사이를 소수점 단위로 메우고, 초점 정보가 없는 배경은
신뢰도로 마스킹한다. 다만 **한 그룹이 5~6장뿐이고 실제 Z 좌표가 기록돼 있지 않아**
정량적인 높이로 쓸 수는 없다. 등간격 촬영이었는지조차 알 수 없다.
제대로 된 z-stack(Z 위치가 기록된)이 확보되면 그때 본격적으로 쓸 부분이다.

### segment_diatoms.py — object 후보 검출

SAM2.1 AutomaticMaskGenerator 로 클래스 무관 후보 마스크를 뽑고, 픽셀 스케일을
물려 µm 단위 크기·종횡비·채움율까지 계산해 JSON 과 오버레이 이미지로 저장한다.

```
python segment_diatoms.py "/mnt/d/260729/RS23-GC03 71cm/Snap-21368.jpg" -o out --scale 0.5
```

`--backend sam3` 자리를 만들어 뒀으나 `facebook/sam3` 는 HF gated (manual approval)
모델이라 승인된 계정의 `HF_TOKEN` 이 필요하다. 익명 접근은 401이다.

## 성능 메모 (GTX 1050 Ti 4GB, WSL2)

AMG는 격자 포인트마다 디코더를 돌리므로 비용이 `points_per_side^2` 에 비례한다.
게다가 포인트 배치마다 마스크를 **원본 해상도로 업샘플링**해서 메모리를 크게 먹는다.
64포인트 x 2208x2752 x float32 = 텐서 하나에 1.55 GB.

4GB 카드에서 이게 넘치면 WSL2가 시스템 RAM으로 흘려보내(sysmem fallback) 수십 배
느려진다. **입력을 0.5배로 리사이즈**(SAM2는 어차피 인코더 입력을 1024x1024로
리사이즈하므로 인식 품질 손실이 거의 없다)하고 `points_per_batch` 를 낮추면 해결된다.
peak VRAM 7.42 GB → 1.16 GB 로 떨어지면서, 포인트를 4배로 늘리고도 49s → 19s 가 됐다.

| 모델 | scale | pps | 시간 | 마스크 | peak VRAM |
|---|---|---|---|---|---|
| tiny | 0.5 | 32 | 19.3s | 123 | 1.16 GB |
| small | 0.5 | 32 | 19.6s | 101 | 1.23 GB |
| base-plus | 0.5 | 32 | 19.0s | 87 | 1.33 GB |
| base-plus | 0.5 | 48 | 140.9s | 129 | 2.09 GB |
| base-plus | 0.4 | 64 | 238.2s | 151 | 3.38 GB |

모델 크기는 시간에 거의 영향이 없다(비용은 포인트 수가 지배). pps를 48 이상으로
올리면 OOM 경고가 뜨며 sysmem fallback이 시작돼 급격히 느려진다.
**1050 Ti 권장 설정: `--scale 0.5 --points-per-side 32 --points-per-batch 16`** (장당 19s).

Pascal 세대라 bfloat16 미지원, fp16은 FP32 대비 1/64 속도여서 fp32로만 돌아간다.
`autocast_dtype()` 이 compute capability를 보고 자동 판단하므로, Turing 이상
(예: RTX 8000, 48 GB)에서는 fp16 autocast가 켜지고 sysmem fallback도 사라져
훨씬 공격적인 설정(원본 해상도, pps 64, crop layers)을 쓸 수 있다.

## 설치

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu126
```
