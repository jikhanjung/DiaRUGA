# 119 — Schmidt 색인의 속명 복원이 지나가는 이름을 집는다

2026-08-13 · `sclee` · 계획은 [P15](20260813_P15_atlas-db.md) · 앞의 것은 [117](20260813_117_east-antarctic-plate-index.md)

**색인을 DB 로 넣기 전에 자료를 믿을 수 있는지 물었더니, 못 믿을 자리가 나왔다.**
Schmidt Atlas 색인이 **속명을 잘못 편 항목**을 들고 있고, 그것이 `(속명 추정)`
으로 표시돼 있지 않다.

---

## 1. 어디서 나왔나 — 없는 이름을 세다가

P15 5절의 순서대로 색인 셋의 이명법 **1,845개**를 WoRMS 에 물었다
(`tools/harvest_worms.py`). **1,585개가 규조로 확인되고 260개가 안 나왔다.**

처음에는 그 260개를 **오타 목록**으로 읽으려 했다. 그런데 동남극 도판집 쪽
5개를 먼저 보니 그게 아니었다:

```
Actinocyclus ingens · Denticulopsis hustedtii
Rouxia constricta · Rouxia leventerae · Rouxia naviculoides
```

전부 **실재하는, 잘 알려진 화석 규조**다. 그리고 그 설명면은 117 에서 내가 300 dpi
로 직접 읽은 것이라 **전사가 맞다는 것을 안다.**

**"DB 에 없다" 를 "틀렸다" 로 읽으면 안 된다.** 이 다섯이 그것을 값싸게 알려
줬다 — 근거가 있는 자료를 먼저 본 덕이다.

> **정정 (같은 날 저녁).** 여기서 안 나오는 이유를 *"WoRMS 가 화석 분류군을 덜
> 담고 있다"* 로 적었는데 **그것이 틀렸다. 담고 있는데 내 질의가 걸러 냈다.**
> WoRMS REST 는 2025-02-28 부터 `extant_only` 를 받고 **안 주면 기본이 현생종만**
> 이다. `harvest_worms.py` 가 그걸 빠뜨렸다.
>
> | 이름 | 기본 조회 | `extant_only=false` |
> |---|---|---|
> | *Actinocyclus ingens* | 없음 | 있음 · `isExtinct=1` |
> | *Denticulopsis hustedtii* | 없음 | 있음 · `isExtinct=1` |
>
> 고쳐서 다시 돌리니 **미확인이 260 → 205개**로 줄었다. Schmidt 는 화석 해양규조
> 비중이 큰 도감이라 이 한 글자가 결과를 크게 바꾼다. **결론("DB 에 없다를
> 틀렸다로 읽지 마라")은 그대로지만 근거가 달랐다** — 남의 DB 가 비어 있다고
> 말하기 전에 **내 질의부터 의심할 자리였다.**
>
> 잡아 준 것은 Windows 앱 쪽 조회 세션이다(`temp/worms_fuzzy_pass1_20260813.md`).
> **질의 조건이 바뀌면 "없음" 은 더 이상 근거가 아니다** — 그래서 도구에
> `--retry-misses` 를 붙여 못 찾았던 것만 다시 묻게 했다.

## 2. PDF 가 갈라 주는 것

그러면 260개는 무엇인가. **셋이 섞여 있고, 고치는 법이 다르다.**

| | 무엇 | 어떻게 고치나 |
|---|---|---|
| (가) 우리 OCR 이 잘못 읽음 | `mesolepla` ← `mesolepta` | 색인을 고친다 |
| (나) 도감이 그렇게 인쇄함 | 옛 이름·원문 오류 | **그대로 두고** 정정을 함께 적는다 |
| (다) DB 의 빈자리 | 화석 분류군 | 아무것도 안 한다 |

**갈라 주는 것은 PDF 뿐이다.** 그래서 열었다. 그런데 (가)~(다) 어디에도 안
들어가는 **넷째**가 나왔다.

## 3. Tafel 26 — 열셋이 남의 속으로 가 있었다

Schmidt 미확인 213개가 해설면 141쪽에 앉아 있는데 **Band1 p.68 한 쪽에 열셋**이
몰려 있었다. 거기부터 열었다.

**그 쪽(Tafel 26)의 속은 처음부터 끝까지 *Amphora* 다.** fig 1 이
`Amphora lyrata Gregory` 이고 이후는 전부 `A.` 로 줄여 쓴다. 그런데 색인은
열셋을 ***Amphiprora*** 로 적고 있었다.

원인이 쪽에 그대로 있다 — fig 37–39 해설에 이런 문장이 한 번 나온다:

```
… Stauroneis amphoroïdes Grunow, O. E. soll = Amphiprora constricta E. sein;
```

**복원 규칙이 이 `Amphiprora` 를 집었다.** 그 뒤의 `A.` 가 전부 Amphiprora 로
펴졌다. WoRMS 에 되물으니 **열셋 다 *Amphora* 로 존재하고, 명명자까지 쪽과 맞는다**:

| 쪽에 적힌 것 | WoRMS |
|---|---|
| `A. arcta A. S.` | *Amphora arcta* Schmidt in Schmidt et al., **1875** |
| `A. composita Janisch. O. E.` | *Amphora composita* Janisch in Schmidt et al., **1875** |
| `A. subinflata Grunow. O. E.` | *Amphora subinflata* Grunow ex A.Schmidt, **1875** |
| `A. globulosa Schumann` | *Amphora globulosa* J.Schumann |
| `A. quadricostata Rbh.` | *Amphora quadricostata* Rabenhorst, 1853 |

덤으로 색인의 `Amphiprora libyea` 는 쪽의 `A. libyca E.` 다 — **속을 잘못 편 것
위에 OCR 의 `c`→`e` 가 겹쳐 있었다.**

## 4. 같은 고장을 기계로 찾는 법

한 번이면 우연이다. **같은 Tafel 에 있는 다른 속으로 종소명을 되물어 보면**
기계가 후보를 낸다 — 질의는 254개뿐이었다.

**색인의 이름 33개가 같은 Tafel 의 다른 속으로는 존재한다.** 다만 이것은
후보다 — *Terpsinoe* 하나에 후보 속이 셋씩 붙는 것은 종소명이 흔해서 나는
잡음이다. **한 쪽에서 여럿이 같은 속으로 몰리는 것**만 진짜다:

```
Amphiprora   → Amphora        12    ← Tafel 26 (PDF 로 확인함)
Cosmiodiscus → Coscinodiscus   5    ← Tafel 57 (PDF 로 확인함)
Craspedodiscus → Coscinodiscus 3
Amphiprora   → Stauroneis      3
Cosmiodiscus → Actinocyclus    3
```

## 5. Tafel 57 — 이번엔 괄호 안의 이명을 집었다

`Cosmiodiscus` 는 P15 가 **AlgaeBase 로 넘긴 3개 중 하나**였다(WoRMS 에 없고,
*Coscinodiscus* 와 0.88 로 붙지만 실재하는 화석 규조속이라 단정하면 안 된다고
적었다). 쪽을 여니 **AlgaeBase 없이 갈렸다.**

**Tafel 57 은 전부 *Coscinodiscus* 다.** 그리고 fig 4 에 이렇게 적혀 있다:

```
4. Richmond, Virgin. 990:1, Coscinodiscus armatus Grev. var.
   (= Cosmiodiscus armatus Grev. 1866.)
```

**괄호 안의 이명이 한 번 나온 것**을 복원 규칙이 집었다. 이후 `C. marginulatus`
· `C. fasciculatus` · `C. subtilis` · `C. denarius` · `C. senarius` ·
`C. symmetricus` 가 전부 Cosmiodiscus 로 펴졌다. **색인의 `Cosmiodiscus` 8개
중 7개가 Coscinodiscus 다** (나머지 하나 `C. elegans` 는 Tafel 229 라 따로 봐야 한다).

## 6. 그래서 무엇이 틀렸나 — 표시가 없다는 것

복원 규칙은 **"같은 Tafel 안 앞선 전체 표기에서 복원한다"** 였고, 근거를 못 찾은
69건에 `(속명 추정)` 을 붙였다. 폴더 문서는 **나머지 1,899건은 확정**이라고
적어 두었다.

**그 문장이 틀렸다.** 여기서 나온 스물은 `(속명 추정)` 이 안 붙은 것들이다.
규칙이 **"같은 쪽에 그 속명이 글자로 있었는가" 만 보고, 그것이 번호 붙은 항목의
속인지는 안 봤다.** 그래서 **지나가는 언급**(fig 37–39 의 비교 문장)이나
**괄호 안의 이명**(fig 4)이 근거로 통과했다 — 규칙이 보기에는 "찾았다" 이므로
추정 표시가 붙을 이유가 없었다.

**값을 못 믿는 것과, 못 믿는다는 것을 값이 말해 주지 않는 것은 다르다.**
`(속명 추정)` 69건은 사람이 의심할 수 있다. 이 스물은 의심할 표시가 없다.

이 저장소가 겪은 것과 같은 모양이다 — **제약이 있다는 것과 조회가 그걸 쓰는
것은 다르다**(053), **판이 여럿이라는 것과 검사가 그걸 아는 것도 다르다**(103).

## 7. 고친 것 / 안 고친 것

**색인은 아직 안 고쳤다.** 확인한 것이 두 쪽뿐이고, 나머지 후보는 PDF 로
확인하기 전까지는 후보다. **표시를 먼저 했다** — 색인 머리말과 `notes/02` 에
경고를 넣어, 지금 이 색인을 읽는 사람이 속명을 그대로 믿지 않게 했다.

**P15 에는 이것이 반입 전 관문으로 들어간다.** 속명이 틀린 채로 DB 에 들어가면
`ClassDef` 와 맞추는 자리에서 **없는 속으로 조용히 빠진다** — P14 4.1 이 걱정한
"도감에 없음" 이 이렇게도 난다.

## 8. 남은 것

- **후보 33개 중 확인한 것은 두 쪽 분(20개).** 나머지는 해당 Tafel 을 열어야 한다.
  **후보 목록도 다시 뽑아야 한다** — `extant_only` 를 빠뜨린 채로 만든 것이라
  화석 55개가 빠져 있었다
- **미확인이 205개다**(260 에서 줄었다). 이번에 20개가 (넷째 갈래)로 갈렸고,
  나머지는 (가)~(다) 중 어디인지 아직 모른다
- **`Cosmiodiscus` 는 속으로는 유효하다** — AlgaeBase·WoRMS 둘 다 확인했다
  (Greville, 1866 · 화석속). **그런데 우리 색인의 8종 중 7종은 그 속이 아니다.**
  Tafel 229 의 *C. elegans* 하나만 진짜다. **속이 실재하는가와 그 항목들이 그
  속인가는 다른 물음이다** — 앞엣것만 보고 "그대로 두면 된다" 로 가면 일곱이
  틀린 채로 남는다
- **한국 도감 41개 · 동남극 5개**는 성격이 다르다. 동남극은 (다)로 확인됐고,
  한국 도감 쪽은 `outputs/png/` 에 **p.191–270 이 이미 렌더돼 있다**(README 함정 2)
- **`Cosmiodiscus` 는 AlgaeBase 목록에서 뺀다** — 여기서 갈렸다. 남은 것은
  *Pyrgodiscus* · *Porodiscus* 둘
