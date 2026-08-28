# 논문 도판 — 1993 남해 서부연안 (171)

`tools/plate_figs.py` · `tools/crop_plates.py` · P22, 169·170 다음(셋째)

## 결과

```
도판 2장(Plate 1·2) · 그림 40개(판마다 20개) · 잘라낸 것 40장(전부) · 이름 40개(전부)
```

`Diadiction/plate/plate_1993bae_pl<1|2>_fig<01-20>_<학명>.png`

## 텍스트 레이어가 없다 — 도판·캡션이 번갈아 온다

1994 와 같은 사정(순수 스캔)이라 16쪽을 훑었다. **1994(캡션 11 → 도판
12, 한 방향)와 다르게 이 논문은 캡션·도판이 번갈아 온다**: PDF p.12(쪽
126) 뒤쪽 절반에 PLATE 1 캡션 → p.13(쪽 127) PLATE 1 도판 → p.14(쪽
128) PLATE 2 캡션 → p.15(쪽 129) PLATE 2 도판. `SOURCE
["1993_bae_lee_south_sea_surface"] = {1: (12, 13), 2: (14, 15)}`.

## 이번에도 자동 검출을 안 썼다

1994 처럼 그림 크기가 크게 널뛰지는 않지만(대체로 200~300px 원형), 번호
활자·스캔 잡티가 상자로 잡혀 **PLATE 1 은 26개(그림 20개인데), PLATE 2
는 37개**로 쪼개졌다 — 그것도 몇 군데는 서로 다른 그림이 한 상자로
합쳐진 채였다. [170](devlog/20260828_170_paper-plates-1994.md)에서
정한 대로 **손으로 재는 쪽을 먼저 썼다** — 격자 눈금 사본에 원본 좌표
(1489×2071, 200dpi)를 읽어 두 쪽 다 `MANUAL_BOXES` 에 20개씩 적었다.
`ASSIGN` 은 여기서도 상자 수만 맞춰 전부 `None`(PLATE 1 은 26개,
PLATE 2 는 37개짜리 자리를 만들어 뒀다 — 값 자체는 버린다).

**확인** — 애매했던 자리(fig 19·20 처럼 나란히 붙은 바늘 모양 둘, girdle
view 인 fig 11)를 잘라낸 뒤 직접 열어 대조했다. 전부 제 번호로 맞았다.

## 한 논문 안에서 학명이 스스로 안 맞는 자리 둘

캡션을 그대로 옮기다 눈에 띈 것 — **고치지 않고 원문 그대로 두되 여기
적어 둔다.**

- **`splendens` 의 속이 갈린다.** PLATE 2 Fig 2 는 `Actinocyclus
  splendens`, Fig 19 는 `Actinoptychus splendens` — 같은 논문, 같은
  판 안에서 속이 다르다. 대조표는 `Actinoptychus splendens` 만
  확정으로 갖고 있다(`Actinocyclus splendens` 는 없다) — 오식일
  가능성이 높지만 판단은 조회 때로 미룬다
- **`surirella` 의 이명 표기가 흔들린다.** 이 논문(PLATE 2 Fig 11)은
  `Delphineis surirella (=Rhaphoneis surirella)` — **h 가 있다.**
  1994 남양만(같은 저자 이영길, fig 25)은 `(=Rhaponeis surirella)` —
  **h 가 없다.** 두 논문이 같은 이명을 다르게 찍었다

## AlgaeBase 대조 — 겹치는 이름이 많다

`worms_master_20260814.tsv` 로 확인(28개 형태, `sp.` 둘은 제외).
**있다 19 · 없다 9.** 없는 9개 중 **6개는 2017·1994 에 이미 나온
것들이다**(`Thalassiosira eccentrica`·`Tryblioptychus cocconeiformis`·
`Grammatophora marina`·`Nitzschia granulata`·`Delphineis surirella`·
`Thalassiosira lineata`) — 세 논문이 계속 같은 현생 연안종들에서 표와
어긋난다. 순수 신규는 3개(`Coscinodiscus oculus-iridis`·`Aulidiscus
caelatus`·`Actinocyclus splendens`). 전부 `Diadiction/names/algaebase/
paper_plates_pending.md` 에 얹었다 — **조회는 안 한다**(7편이 다
끝나면 몰아서, 169 에서 정한 방침).

## 다음

**2001 브랜스필드 고환경**(Park 외, 남극, Plate 1·2) — P22 순서대로.
