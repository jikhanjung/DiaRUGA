# 논문 도판 1991 연일층군 — P22 여덟 편의 마지막 (177)

`tools/plate_figs.py` · `tools/crop_plates.py` · 175(OCR 첫 실행)·
176(1996, OCR 초안+렌더 대조로 처음 완주) 다음. 사용자가 "1991년 거
이제 보자" 고 해서 미뤄 뒀던 마지막 한 편을 끝냈다.

## 결과

```
도판 5장(Plate I~V: 19·17·18·32·33개) · 그림 119개 · 잘라낸 것 119장(전부)
· 이름 119개(전부) · AlgaeBase 대조 있다 26 · 없다 68
```

`Diadiction/plate/plate_1991lee_pl<1-5>_fig<NN>_<학명>.png`

## 캡션 — OCR 초안 + 200dpi 렌더 전수 대조

175 가 이미 Plate I 캡션 19개 중 2개(fig8·14)를 확정해 뒀다. 이번에
**Plate II~V 도 전부 판마다 캡션 쪽을 200dpi 로 다시 렌더해 눈으로
대조했다**(176 의 방침 그대로). **119개 중 25개(21%)** 를 원문대로
고쳤다 — 1996(89개 중 5개, 5.6%)보다 훨씬 높다. 표본이 커질수록
오차율이 안정된다던 176 의 추측과 반대로, 이 논문은 원문 인쇄 상태
자체가 더 나쁘다(스캔이 흐리고 활자가 작다).

| 판 | 확인 | 고침 |
|---|---|---|
| I | 19 | 2 (fig8 `(Bail)`→OCR`(Bai)`, fig14 `Janish`→OCR`Janich`) |
| II | 17 | 4 (fig1 `oculus`→`oclus`, fig3 `Actincyclus`/`Pritchand`→`Actincylcus`/`Pritchard`, fig7 `Actinocylus`→`Actinocyclus`, fig16 `Pseudoporosira`→`Pseudoporosa`) |
| III | 18 | 2 (fig2 `splendia`→`splendida`, fig14 `Bidduliphia`→`Biddulphia`) |
| IV | 32 | 10 (fig2·11 `Hermialus`→`Hermialis`, fig6·17 `(Lyng.)`→`(Lytng.)`, fig10 `Rhizooslenia`→`Rhizosolenia`, fig15 `tenus`→`tenuis`, fig18·19·20 `Rhitzosolenia`/`hiemialus`→`Rhithzosolenia`/`hiemialis`, fig31 `longissima`→`longestissima`) |
| V | 33 | 7 (fig2 `Eherenberg`/`haeckel`→`Ehrenberg`, fig7·9 `(Ehr,)`→`(Ehr.)`, fig12 `Cannoplus`→`Cannopilus`, fig18 `schulzii`/`Deflandre`→`schulzzii`/`Delfandre`, fig22 `Perch-Nielson`→`Perth-Nielson`, fig25 `Ammodchium`→`Ammochdium`) |

(화살표 왼쪽이 원문·오른쪽이 OCR — 전부 OCR 이 조용히 정상화하거나
글자를 흘린 자리다.)

**원문 자체가 흔들리는 자리는 그대로 두 벌 다 옮겼다** — Plate IV
fig13·14 는 `nitzschioides`/`nitzschiodes` 로 같은 쪽 안에서 철자가
다르고, **fig14 는 원문이 같은 캡션을 두 줄로 겹쳐 찍었다**(인쇄
오류이지 사진이 둘이 아니다 — 그림 수는 32 그대로). Plate II 는
`Actincyclus`(fig3)/`Actinocyclus`(fig14) 가 한 쪽 안에서 갈린다.

## 도판 크롭 — 다섯 판 다 손으로 쟀다, Plate II 만 예외

TODOs 에 미리 적어 둔 자동 검출 상자 수(20·21·35·37·54)는 이번에
다시 돌려 보니 23·17·24·41·37 로 나왔다(문턱 기본값이 그때와 달랐던
것으로 보인다). **Plate II 만 자동 상자 17개가 그림 17개와 정확히
맞아** 대부분 그대로 썼다 — 순서가 인쇄 번호와 달라(상자 6→fig9,
상자 9→fig7 식) `ASSIGN` 으로 짚었고, fig6(대비가 낮아 자동이
완전히 놓쳤다) 만 `MANUAL_BOXES` 로 보탰다.

**나머지 넷은 전부 손으로 쟀다** — 자동 상자가 이웃과 합쳐지거나
(Plate I fig4+5), 여러 조각으로 쪼개지거나(Plate III fig6·7 leaf
모양, Plate IV 전체), 저대비라 아예 안 잡혔다(Plate I fig6). 200dpi
렌더에 100px 격자를 얹어 눈으로 재는 방법으로 갔다 — 자동 상자를
역산하는 것보다 처음부터 재는 것이 이 판들에서는 더 빨랐다.

**겹침 검사가 실측 오류 넷을 잡았다**(174 의 방법을 좌표 단계에
바로 적용): Plate V fig24·26·27 을 한 줄 밀려 읽어 fig27 이 fig25 와
거의 통째로 겹쳐 있었고, Plate V fig11·12·13 도 이웃 상자를 밀려
읽어 fig11 이 실은 fig13 의 별모양 개체 자리였다. 둘 다 원본을 다시
확대해 재고 나서야 맞았다 — **격자를 대고 잰 좌표도 사람이 줄을
잘못 짚으면 틀린다**는 것을 다시 확인했다.

**119장을 다 자르고 판마다 6열 대조 시트로 훑어 확인했다** — 이상
없음(인쇄 번호가 안 보이는 자리 몇은 이웃 상자의 번호가 pad 안으로
넘어온 것이고, 자기 그림 내용은 어긋나지 않았다).

## AlgaeBase 대조

`sp.` 를 뺀 95개 형태(원문 표기가 흔들리는 자리·오식은 따로따로
셌다)로 로컬 대조표(`Diadiction/names/algaebase/algaebase_day*.md`,
1,845종)를 grep 대조했다. **있다 26 · 없다 68.**

`Coscinodiscus oculus-iridis` 가 이 대조표에 없고, 이 논문에는
`Thalassiosira eccentrica` 가 안 나온다 — 지금까지 여섯 논문에서 반복된
"대조표가 못 담는 흔한 원양종" 패턴은 계속 확인된다. 나머지 없다
목록은 `Diadiction/names/algaebase/paper_plates_pending.md` 의
1991 항목에 얹었다.

## P22 여덟 편이 다 끝났다

2017·1994·1993남해·2001·1975·1986·1996·1991. 다음은 `pending.md` 를
`algaebase_worklist.py` 류의 배치 조회로 몰아서 넘기는 일이다 — 사용자가
정한 "7(→8)편이 다 끝나면 한 번에 몰아서 조회한다" 는 방침을 여기서
지킨다.
