"""도판의 그림 번호 ↔ 학명. **사람이 원문을 읽은 기록이다** (P20 · 논문 도판).

`render_verify.VERIFIED` 와 같은 자리다 — 도구가 다시 계산하지 않고 값을 그대로
들고 있다. 근거는 각 논문의 도판 캡션 쪽이고 `SOURCE` 에 쪽을 적어 두었다.

**학명은 캡션에 찍힌 그대로다.** 고쳐 쓰지 않는다 — `Stepanodiscus` 는 원문이
그렇게 찍혀 있다(보통은 *Stephanodiscus*). 현재 통용명은 AlgaeBase 대조표가
말한다(사용자 2026-08-26).

**`sp. nov.`·`var. nov.`·`fo. nov.` 는 그 논문이 세운 이름이다** — 도감 셋에
없을 가능성이 높고, 사용자가 "논문에서만 언급되는 종" 이라고 한 것이 이것이다.
"""

import json as _json
from pathlib import Path as _Path


def _load_ak85_captions():
    """1985 는 그림 600개라 손으로 못 옮긴다 — 텍스트 레이어를 정규식으로
    긁어 부록 38종과 대조까지 마친 결과를 `tools/parse_dsdp87_captions.py`
    가 냈다. **그림 번호가 `1a`·`5A` 처럼 글자를 달고 온다** — 부분 라벨은
    문자열로, 나머지는 정수로 남긴다(다른 논문과 같은 자리를 쓰려고)."""
    raw = _json.loads((_Path(__file__).resolve().parent
                        / "data/ak85_captions.json").read_text(encoding="utf-8"))
    out = {}
    for plate, figs in raw.items():
        out[int(plate)] = {
            (int(fig) if fig.isdigit() else fig): name
            for fig, name in figs.items()
        }
    # Plate 46 는 "6-8, 12. Rouxia cf. peragalli Brun and Héribaud" 구간을
    # 파서가 놓쳤다 — `peragalli` 앞의 "cf." 뒤 저자 인용이 규칙과 안 맞아서다.
    # 부록에 없는 비교종이라 검산에 안 걸려 나중에야 눈에 띄었다. 손으로 채운다
    out[46].update({k: "Rouxia cf. peragalli Brun and Héribaud" for k in (6, 7, 8, 12)})
    return out


# 논문마다 (도판 번호 → (캡션 쪽, 도판 쪽))
SOURCE = {
    "1936_skvortzov_ampen_neogene": {
        1: (40, 41), 2: (43, 44), 3: (46, 47), 4: (49, 50),
    },
    # **캡션 쪽이 없다** — 기재문 안의 `Pl. 1, fig. 1 ; Pl. 2, fig. 4, 7` 줄이
    # 자리를 말한다. 그래서 캡션 쪽 자리를 `None` 으로 둔다
    "1993_lee_chaetoceros_yeonil": {
        1: (None, 12), 2: (None, 16), 3: (None, 24),
    },
    # **캡션 목록이 도판 바로 앞 쪽 아래에 있다** — 기재문의 `[Plate 2, Fig. 7]`
    # 을 긁을 필요가 없었다. 목록 쪽을 먼저 찾을 것
    "1992_lee_galmal_quaternary_flora": {
        1: (8, 9), 2: (12, 13), 3: (16, 17), 4: (18, 19),
    },
    # **캡션이 쪽이 아니라 절이다** — "Explanation of Plates" 가 본문 뒤에
    # 문장으로 붙어 있다(`parse_dsdp87_captions.py`). PDF 쪽 = 도판 번호 + 19
    # (Plate 1 = PDF p.20 … Plate 52 = PDF p.71, 직접 재서 확인했다)
    # **도판이 52장이 아니라 53장이다** — 원문이 "Plate 44" 뒤에 마침표를
    # 빠뜨려 한동안 못 읽었다(캡션 파서 쪽에서 고쳤다). 쪽 옵셋(도판번호+19)은
    # 44번을 포함해 끝까지 그대로 간다 — 53번이 이 논문의 마지막 쪽(72)이다
    "1985_akiba_yanagisawa_dsdp87_zonal_markers": {
        n: (None, n + 19) for n in range(1, 54)
    },
    # **캡션이 도판과 한 쪽에 있다** — 도판 자체가 마지막 쪽(PDF p.13, 본문
    # 쪽번호 357) 아래에 붙어 있어 따로 캡션 쪽이 없다. 그림 번호도 숫자가
    # 아니라 글자(A–T)다 — Fig 라벨이 도판 위에 이미 인쇄돼 있어 그대로 쓴다
    "2017_yun_ulleung_basin": {
        1: (13, 13),
    },
    # **캡션 쪽이 도판 쪽 바로 앞이다** — "PLATE 1" 목록이 p11(쪽번호 36)
    # 뒤쪽 절반에 있고, 도판 자체는 p12(쪽번호 37)다. 텍스트 레이어가 없어
    # (Diadiction README 의 "텍스트 레이어는 셋뿐" 표) 렌더해서 읽었다
    "1994_lee_namyangman_tidal_flat": {
        1: (11, 12),
    },
    # 텍스트 레이어가 없다(1994 와 같은 사정). PLATE 1 캡션은 PLATE 1 도판
    # 바로 앞 쪽(같은 인쇄 쪽 하단), PLATE 2 캡션도 마찬가지로 자기 도판
    # 바로 앞 쪽에 있다 — 도판·캡션이 번갈아 온다(1994 와 다른 배치)
    "1993_bae_lee_south_sea_surface": {
        1: (12, 13), 2: (14, 15),
    },
    # 남극 · 텍스트 레이어 없음. 여기는 **캡션이 도판 뒤에 온다**(1993 남해와
    # 반대 방향) — p10 도판1 → p11 캡션1 → p12 도판2 → p13 캡션2
    "2001_park_bransfield_paleoenv": {
        1: (11, 10), 2: (13, 12),
    },
    # 텍스트 레이어 없음. **두 판의 캡션이 한 쪽(p11)에 같이 있다** — Plate I·II
    # 목록이 위아래로 이어 실렸다. 도판은 p13(Plate I)·p14(Plate II)
    "1975_lee_pohang_gampo_neogene": {
        1: (11, 13), 2: (11, 14),
    },
    # 목록형 캡션이 각자 도판 바로 뒤 쪽에 있다(도판→캡션→3쪽 본문→도판…
    # 이 세 번 반복). 셋 다 그림 수가 캡션 개수와 맞는다(27·22·18)
    "1986_lee_se_korea_neogene": {
        1: (11, 10), 2: (15, 14), 3: (19, 18),
    },
}

# 논문 → 도판 → {그림 번호: 캡션에 찍힌 학명}
CAPTIONS = {
 "1936_skvortzov_ampen_neogene": {
  1: {
   1: "Melosira ambigua (Grun.) O. Mull. status B.",
   2: "Melosira ambigua (Grun.) O. Mull. status B.",
   3: "Melosira distans (Ehr.) Kutz.",
   4: "Melosira varians C. A. Ag. Auxospore",
   5: "Tetracyclus emarginatus (Ehr.) W. Smith",
   6: "Diatoma anceps (Ehr.) Grun.",
   7: "Stepanodiscus carconensis Grun.?",
   8: "Melosira granulata (Ehr.) Ralfs status y.",
   9: "Melosira varians C. A. Ag. Auxospore",
   10: "Tetracyclus emarginatus (Ehr.) W. Smith",
   11: "Synedra Vaucheriae Kutz. var. truncata (Grev.) Grun.",
   12: "Eunotia monodon Ehr. var. koreana var. nov. fo. undulata fo. nov.",
   13: "Eunotia monodon Ehr. var. koreana var. nov.",
   14: "Eunotia monodon Ehr. var. koreana var. nov.",
   15: "Eunotia kocheliensis O. Mull.",
   16: "Melosira varians C. A. Ag. Auxospore",
   17: "Tetracyclus emarginatus (Ehr.) W. Smith",
   18: "Gomphonema vastum Hust. var. elongata Skv.",
   19: "Eunotia monodon Ehr. var. koreana var. nov.?",
   20: "Eunotia monodon Ehr. var. koreana var. nov.",
   21: "Synedra Vaucheriae Kutz. var. truncata (Grev.) Grun.",
   22: "Achnanthes koreana sp. nov.",
   23: "Eunotia monodon Ehr. var. koreana var. nov. fo. undulata fo. nov.",
   24: "Eunotia monodon Ehr. var. koreana var. nov. fo. undulata fo. nov.",
   25: "Eunotia monodon Ehr. var. asiatica var. nov.",
   26: "Melosira varians C. A. Ag. Auxospore",
   27: "Navicula mutica Kutz. var. fossilis var. nov.",
   28: "Navicula mutica Kutz. var. Chonii (Hilse) Grun. forma",
   29: "Gomphonema lanceolatum Ehr. var. insignis (Greg.) Cleve",
   30: "Eunotia monodon Ehr. var. koreana var. nov.",
   31: "Eunotia praerupta Ehr.",
   32: "Eunotia holoturia sp. nov.",
   33: "Eunotia monodon Ehr. var. koreana var. nov.",
   34: "Eunotia holoturia sp. nov.",
   35: "Eunotia monodon Ehr. var. asiatica var. nov.",
   36: "Eunotia pectinalis (Kutz.) Rabh.",
   37: "Eunotia praerupta Ehr.",
  },
  2: {
   1: "Navicula koreana sp. nov.",
   2: "Stauroneis signata (Meister) Skv. nov. com.",
   3: "Eunotia tropica Hust.",
   4: "Eunotia monodon Ehr. var. major (W. Smith) Hust. fo. bidens (W. Smith)",
   5: "Eunotia praerupta Ehr. var. bidens Grun.",
   6: "Eunotia praerupta Ehr. var. bidens Grun.",
   7: "Eunotia monodon Ehr. var. asiatica var. nov.",
   8: "Eunotia praerupta Ehr. var. bidens Grun.",
   9: "Eunotia gracilis (Ehr.) Rabh.",
   10: "Eunotia monodon Ehr. var. major (W. Smith) Hust.",
   11: "Eunotia praerupta Ehr. var. bidens Grun.",
   12: "Eunotia praerupta Ehr.",
   13: "Fragilaria Harrissonii W. Smith var. dubia Grun.",
   14: "Fragilaria virescens Ralfs",
   15: "Eunotia monodon Ehr. var. major (W. Smith) Hust. fo. bidens (W. Smith)",
   16: "Gomphonema parvulum (Kutz.) Grun. var. micropus (Kutz.) Cleve",
   17: "Eunotia praerupta Ehr.",
   18: "Eunotia holoturia sp. nov.",
   19: "Navicula soodensis Krasske.",
  },
  3: {
   1: "Eunotia monodon Ehr. var. asiatica var. nov.",
   2: "Stauroneis javanica Grun.",
   3: "Pinnularia koreana sp. nov.",
   4: "Pinnularia cardinalis (Ehr.) W. Smith",
   5: "Pinnularia distinguenda Cleve fo. angustior fo. nov.",
   6: "Achnanthes inflata Kutz.",
   7: "Pinnularia acrosphaeria Breb.",
   8: "Navicula mutica Kutz. var. fossilis var. nov.",
   9: "Pinnularia isostauron (Ehr?) Grun. var. koreana var. nov.",
   10: "Pinnularia brevicostata Cleve",
   11: "Pinnularia cardinalis (Ehr.) W. Smith",
   12: "Pinnularia appendiculata (Ag.) Cleve var. paeninsulae-koreana var. nov.",
  },
  4: {
   1: "Pinnularia brevicostata Cleve",
   2: "Pinnularia gentilis (Donk.) Cleve var. neogenica var. nov.",
   3: "Nitzschia plana Smith",
   4: "Pinnularia stomatophora Grun.",
   5: "Pinnularia nobilis Ehr. var. parallela var. nov.",
   6: "Pinnularia brevicostata Cleve",
   7: "Pinnularia brevicostata Cleve",
   8: "Pinnularia gibba Ehr. var. linearis Hust.",
   9: "Hantzschia amphioxys (Ehr.) Grun. var. xerophila Grun.",
   10: "Gomphonema constrictum Ehr. with anomal striae",
   11: "Pinnularia episcopalis Cleve fo. neogena fo. nov.",
  },
 },
 # 1993 Chaetoceros — **기재문에서 모았다**(pdf 9~23의 가운데 정렬 줄).
 # 캡션 쪽이 없어서 `종명 줄 + 바로 아래 Pl. 줄` 을 짝지었다.
 # **한 종이 도판 여럿에 나오고 한 도판에 그림 여럿을 갖는다.**
 # `?` 가 붙은 것은 원문이 동정을 의심한 자리다(fig 12·22·24).
 "1993_lee_chaetoceros_yeonil": {
  1: {
   1: "Chaetoceros lauderi Ralfs in Lauder, 1864",
   2: "Chaetoceros subsecundus (Grunow) Hustedt, 1930",
   3: "Chaetoceros subsecundus (Grunow) Hustedt, 1930",
   4: "Chaetoceros subsecundus (Grunow) Hustedt, 1930",
   5: "Chaetoceros compressus Lauder, 1864",
   7: "Chaetoceros amanita Cleve-Euler, 1915",
   9: "Chaetoceros amanita Cleve-Euler, 1915",
   10: "Chaetoceros sp. B",
   6: "Chaetoceros coronatus Gran., 1897",
   8: "Chaetoceros costatus Pavillard, 1911",
   11: "Chaetoceros furcellatus Bail., 1873",
   12: "Chaetoceros costatus Pavillard, 1911",
   13: "Chaetoceros cinctus Gran, 1897",
   15: "Dossetia sp.",
   16: "Stephanopyxis lineata (Ehrenberg) Forti, 1912",
   19: "Pterotheca carinifera (Grunow) Forti, 1909",
   21: "Chaetoceros sp. A",
   24: "Xanthiopyxis acrolopha Forti, 1912",
  },
  2: {
   1: "Goniothecium rogersii Ehrenberg, 1843",
   2: "Stephanogonia hanzawae Kanaya, 1959",
   5: "Chaetoceros dicladia Castracane, 1886",
   6: "Chaetoceros dicladia Castracane, 1886",
   10: "Liradiscus asperulus Andrews, 1976",
   13: "Liradiscus bipolaris Lohman, 1948",
   18: "Cladogramma californicium Ehrenberg, 1854",
   19: "Dossetia sp.",
   27: "Chaetoceros dicladia Castracane, 1886",
   3: "Stephanogonia hanzawae Kanaya, 1959",
   4: "Chaetoceros lauderi Ralfs in Lauder, 1864",
   7: "Chaetoceros lauderi Ralfs in Lauder, 1864",
   8: "Stephanogonia hanzawae Kanaya, 1959",
   9: "Pseudopyxilla americana (Ehr.) Forti, 1909",
   12: "Xanthiopyxis ovalis Lohman, 1938",
   14: "Xanthiopyxis sp. A",
   16: "Goniothecium tenue Brun, 1894",
   17: "Pterotheca carinifera (Grunow) Forti, 1909",
   20: "Stephanopyxis corona (Ehrenberg) Grunow, 1882",
   23: "Liradiscus ovalis Greville, 1865a",
   24: "Goniothecium tenue Brun, 1894",
   25: "Liradiscus ovalis Greville, 1865a",
  },
  3: {
   1: "Stephanogonia actinoptychus (Ehr.) Grunow, 1882",
   2: "Goniothecium odontella Ehrenberg, 1854",
   3: "Stephanopyxis corona (Ehrenberg) Grunow, 1882",
   4: "Pterotheca danica Grunow",
   5: "Chaetoceros sp. C",
   6: "Chaetoceros sp. C",
   8: "Chaetoceros compressus Lauder, 1864",
   9: "Goniothecium rogersii Ehrenberg, 1843",
   10: "Pterotheca carinifera (Grunow) Forti, 1909",
   11: "Chaetoceros vanheurecki Gran, 1897",
   12: "Chaetoceros seiracanthus Gran, 1897",
   15: "Chaetoceros coronatus Gran., 1897",
   16: "Liradiscus bipolaris Lohman, 1948",
   18: "Chaetoceros subsecundus (Grunow) Hustedt, 1930",
   19: "Dossetia sp.",
   22: "Xanthiopyxis globosa Ehrenberg, 1845",
   26: "Goniothecium odontella Ehrenberg, 1854",
   28: "Chaetoceros lorenzianus Grunow, 1863",
   29: "Chaetoceros dicladia Castracane, 1886",
  },
 },
 # 1992 철원 갈말면 제4기 규조토 — 도판 앞 쪽의 `Plate N` 목록에서 옮겼다.
 # **A-I ~ A-V 는 시료 이름이다**(그 그림이 어느 시료에서 나왔나) — 여기서는
 # 이름만 든다. 출현 기록 층으로 갈 값이라 도판 표에 섞지 않는다
 "1992_lee_galmal_quaternary_flora": {
  1: {
   1: "Achnanthes lanceolata (Breb.) Grun. var. dibia Grunow",
   2: "Achnanthes lanceolata (Breb.) Grun. var. omissa Reimer",
   3: "Cyclotella meneghiniana Kutzing",
   4: "Cyclotella stelligrta Cleve and Grunow",
   5: "Cocconeis plancentula (Ehr.) var. euglypta (Ehr.) Cleve",
   6: "Coscinodiscus lacustris Geunow",
   7: "Cocconeis fluviatillis Wallace",
   8: "Amphora pediculus (Kutz.) Grunow",
   9: "Cyclotella sp.",
   10: "Cyclotella comta (Ehr.) Kutzing",
   11: "Cymbella sp. A",
   12: "Cymbella minuta Hilse ex Rabh.",
   13: "Cymbella sinuata Gregory",
   14: "Caloneis sp.",
   15: "Diploneis ovalis (Hilse) Cleve",
   16: "Cymbella sp. B",
   17: "Cymbella hebridica Grunow ex Cleve",
   18: "Cymbella sp. C",
   19: "Cymbella cymbiformis var. nonpunctata Font.",
   20: "Cymbella leptoceros (Ehr.) Grunow",
   21: "Diploneis oblongella (Naeg. ex Kutzing) Ross",
   22: "Diploneis elliptica (Kutz.) Cleve",
   23: "Cymbella turmida (Breb.) Van Heurck",
  },
  2: {
   1: "Diploneis sp.",
   2: "Fragilaria construens var. binodis (Ehr.) Grunow",
   3: "Fragilaria construens (Ehr.) Grunow",
   4: "Fragilaria construens var. venter (Ehr.) Grunow",
   5: "Fragilaria pinnate var. elliptical Schumann",
   6: "Fragilaria pinnate var. minutissima Grunow",
   7: "Fragilaria sp. A",
   8: "Eunotia monodon var. koreana Skvortzov",
   9: "Fragilaria pinnate var. parallel Mayer",
   10: "Gomphonema acuminatum var. coronata (Ehr.) W. Smith",
   11: "Fragilaria pinnate var. parallel Mayer",
   12: "Fragilaria striatula Lyngbye",
   13: "Gomphonema brasiliense Grunow",
   14: "Epithemia sorex Kutzing",
   15: "Gomphonema truncatum Ehrenberg",
   16: "Gomphonema parvulum Kutzing",
   17: "Cocconeis sp. aff. Cocconeis costata Gregory",
   18: "Feagilaria sp. B",
   19: "Gomphonema parvulum Kutzing",
   20: "Gomphonema clevei Fricke",
   21: "Gomphonema acuminatum var. pusilla Grunow",
   22: "Gomphonema sphaerophorum Ehrenberg",
   23: "Gomphonema subtile var. sagitta (Schum.) Cleve",
   24: "Fragilaria vaucheria var. capitellata Peters",
  },
  3: {
   1: "Melosira granulata (Ehr.) Ralfs",
   2: "Melosira granulata var. angustissima Muller",
   3: "Melosira varians Agadh",
   4: "Navicula sp. B",
   5: "Navicula latens Krasske",
   6: "Navicula mourneis Patrick",
   7: "Nitzschia amphibia Grunow",
   8: "Navicula gottlandica Grunow",
   9: "Nitzschia amphibia Grunow",
   10: "Navicula amohibole Cleve",
   11: "Navicula psedoscutiformis Hustedt",
   12: "Synedra parastica (W. Smith) Hustedt",
   13: "Nitzschia frustulum (Kutz.) Grunow",
   14: "Nitzschia palea (Kutz.) W. Smith",
   15: "Nitzschia amphibia Grunow",
   16: "Gomphonema sp.",
   17: "Navivla radiosa var. tenella (Breb. ex Kutzing) Grunow",
   18: "Pinnularia sp. A",
   19: "Synedra sp. B",
   20: "Pinnularia sp. B",
   21: "Surirella sp.",
   22: "Navicula laterostrata Hustedt",
   23: "Navicula pupula fo. rectangularis (Greg.) Grunow",
  },
  4: {
   1: "Synedra arcus Kutzing",
   2: "Tabularia fenestrata (Lynb.) Kutzing",
   3: "Stauroneis sp.",
   4: "Synedra sp. A",
   5: "Nitzschia sp.",
   6: "Pleurosigma salinarum Grunow",
   7: "Fragilaria vaucheria var. capitellata Peters",
   8: "Gomphonema affine var. insigne (Greg.) Andrew",
   9: "Navicula sp. A",
  },
 },
 # 1985 Akiba & Yanagisawa — 캡션 절을 정규식으로 긁은 것(부록 38종 검산 마침).
 # `tools/data/ak85_captions.json` 을 만드는 도구는 `tools/parse_dsdp87_captions.py`
 "1985_akiba_yanagisawa_dsdp87_zonal_markers": _load_ak85_captions(),
 # 2017 울릉분지 — 도판 밑 문장형 캡션에서 그대로 옮겼다("Figs A-C. …").
 # 그림 번호가 글자라 `figtag` 가 그대로 파일 이름에 쓴다
 "2017_yun_ulleung_basin": {
  1: {
   "A": "Coscinodiscus asteromphalus",
   "B": "Coscinodiscus asteromphalus",
   "C": "Coscinodiscus asteromphalus",
   "D": "C. centralis",
   "E": "C. centralis",
   "F": "Actinoptychus senarius",
   "G": "Actinoptychus senarius",
   "H": "Actinocyclus curvatulus",
   "I": "A. octonarius",
   "J": "A. octonarius",
   "K": "Cyclotella sp.",
   "L": "Thalassiosira curviseriata",
   "M": "T. eccentrica",
   "N": "T. mala",
   "O": "Paralia sulcata",
   "P": "Paralia sulcata",
   "Q": "Paralia sulcata",
   "R": "Navicula sp.",
   "S": "Thalassionema faruenfeldii",
   "T": "Th. Nitzschioides",
  },
 },
 # 1994 남양만 — "PLATE 1" 목록(p11)에서 그대로 옮겼다. 원문이 각주에
 # 시료·깊이(VC-8/VC-10/VC-Y1, cm)를 함께 적어 뒀지만 그것은 출현 기록
 # 쪽 일이라 여기 이름에는 안 섞는다(`devlog/20260828_170` 에 표로 남겼다).
 # **Fig 7·27 은 원문 철자가 다르다**(weissflogii vs weissflogia) — 고치지 않았다
 "1994_lee_namyangman_tidal_flat": {
  1: {
   1: "Cyclotella striata",
   2: "Cyclotella striata",
   3: "Podosira stelliger",
   4: "Actinocyclus ehrenbergii",
   5: "Coscinodiscus nitidus",
   6: "Thalassiosira eccentrica",
   7: "Diploneis weissflogii",
   8: "Paralia sulcata",
   9: "Paralia sulcata",
   10: "Actinocyclus curvatulus",
   11: "Actinoptychus undulatus (=A. senarius)",
   12: "Triceratium dubium",
   13: "Paralia sulcata (girdle view)",
   14: "Thalassiosira oestrupii",
   15: "Surirella fastuosa var. recedens",
   16: "Tryblioptychus cocconeiformis",
   17: "Actinoptychus splendens",
   18: "Grammatophora marina",
   19: "Thalassiosira lineata",
   20: "Nitzschia sigmaformis",
   21: "Trachyneis aspera",
   22: "Thalassionema nitzschioides",
   23: "Thalassionema nitzschioides",
   24: "Nitzschia granulata",
   25: "Delphineis surirella (=Rhaponeis surirella)",
   26: "Rhaponeis amphiceros",
   27: "Cymatotheca weissflogia",
   28: "Actinocyclus ehrenbergii var. tenella",
   29: "Thalassiosira decipiens",
   30: "Nitzschia punctata",
   31: "Epithemia turgida",
  },
 },
 # 1993 남해(Bae·Lee) — 두 판 다 자기 도판 바로 앞 쪽 캡션에서 그대로
 # 옮겼다. **Fig2 는 `Actinocyclus splendens`, Fig19 는 `Actinoptychus
 # splendens`다** — 같은 논문 안에서 속이 다르게 찍혔다(오식으로 보이나
 # 원문 그대로 둘 다 남긴다). 괄호 앞 공백도 원문 그대로다(`Podosira`
 # 는 공백 없이, `Delphineis`·`Coscinodiscus oculus - iridis` 는 있다)
 "1993_bae_lee_south_sea_surface": {
  1: {
   1: "Coscinodiscus oculus - iridis",
   2: "Thalassiosira eccentrica",
   3: "Thalassiosira sp. A",
   4: "Coscinodiscus nitidus",
   5: "Cyclotella striata",
   6: "Paralia sulcata",
   7: "Podosira sp. A(= P. stelliger ?)",
   8: "Aulidiscus caelatus",
   9: "Thalassiosira oestrupii",
   10: "Triceratium favus",
   11: "Paralia sulcata(girdle view)",
   12: "Biddulphia pulchella",
   13: "Thalassiosira lineata",
   14: "Paralia sulcata",
   15: "Nitzschia cocconeiformis",
   16: "Surirella fastuosa var. recedens",
   17: "Cocconeis scutellum",
   18: "Thalassionema nitzschioides",
   19: "Trachyneis aspera",
   20: "Nitzschia sigma",
  },
  2: {
   1: "Actinoptychus undulatus",
   2: "Actinocyclus splendens",
   3: "Actinocyclus ehrenbergii",
   4: "Diploneis bombus",
   5: "Tryblioptychus cocconeiformis",
   6: "Rhaphoneis amphiceros",
   7: "Grammatophora marina",
   8: "Actinocyclus ehrenbergii",
   9: "Nitzschia granulata",
   10: "Nitzschia granulata",
   11: "Delphineis surirella (=Rhaphoneis surirella)",
   12: "Arachnoidiscus ehrenbergii",
   13: "Nitzschia cocconeiformis",
   14: "Nitzschia granulata",
   15: "Actinocyclus ehrenbergii",
   16: "Actinocyclus ehrenbergii",
   17: "Cyclotella striata",
   18: "Coscinodiscus oculus - iridis",
   19: "Actinoptychus splendens",
   20: "Actinoptychus undulatus",
  },
 },
 # 2001 브랜스필드(Bak/Park 외) — 남극, 도판 밑에 문장형이 아니라 번호
 # 목록형 캡션이 붙는다(1936 류와 다르다). 원문에 시추공(GC98-08)·깊이·
 # SEM 배율이 함께 있지만 이름에는 안 섞는다(devlog 170 의 1994 와 같은 자리
 # — 나중에 Occurrence 로 갈 값이라 devlog 표로만 남긴다)
 "2001_park_bransfield_paleoenv": {
  1: {
   1: "Actinocyclus actinochilus (Ehrenberg) Simonsen",
   2: "Asterompharus hookeri Ehrenberg",
   3: "Chaetoceros resting spores",
   4: "Chaetoceros resting spores",
   5: "Cocconeis costata Gregory",
   6: "C. fasciolata (Ehrenberg) Brown",
   7: "Actinocyclus ingens Rattray",
   8: "Asterompharus palvulus Karsten",
   9: "Coscinodiscus furcatus Karsten",
   10: "Fragilariopsis seperanda Hustedt",
   11: "Coscinodiscus asteromphalus Ehrenberg",
   12: "Melosira sol (Ehrenberg) Kutzing",
   13: "Thalassiosira elliptipora Donahue",
   14: "Porosira gracilis (Grunow) Jorgensen",
   15: "Eucampia antarctica (Castracane) Mangin",
   16: "Thalassiosira lentignosa Karsten",
   17: "T. eccentrica (Ehrenberg) Cleve",
   18: "T. gracilis (Karsten) Hustedt",
   19: "T. antarctica Comber",
   20: "Actinocyclus actinochilus (Ehrenberg) Simonsen",
   21: "Licomphora abbreviata Agardh",
   22: "Odontella weissflogii (Janisch) Grunow",
   23: "Dactyliosolen antarcticus Castracane",
   24: "Actinocyclus curvatulus Janisch",
   25: "Fragilariopsis ritscheri Hustedt",
   26: "Rhizosolenia hebetata f. bidens Heiden",
   27: "Fragilariopsis sublineata (Van Heurck) Hasle",
   28: "F. obliquecostata (Van Heurck) Hasle",
   29: "Thalassiothrix longissima Cleve and Grunow",
   30: "Acanthes brevipes var. angustata (Cleve) Grunow",
   31: "Gomphonema intricatum Kutzing",
   32: "Cocconeis fasciolata (Ehrenberg) Brown",
  },
  2: {
   1: "Thalassiosira antarctica Comber",
   2: "Actinocyclus actinochilus (Ehrenberg) Simonsen",
   3: "Thalassiosira eccentrica (Ehr.) Cleve",
   4: "Actinocyclus octonarius",
   5: "Porosira glacialis (Grunow) Jorgensen",
   6: "Coscinodiscus furcatus Karsten",
   7: "Fragilariopsis lineata Hasle",
   8: "F. kerguelensis (O'Meara) Hustedt",
   9: "F. cylindrus (Grunow) Krieger",
   10: "F. curta (V. Heurck) Hasle",
   11: "F. ritscheri Hustedt",
   12: "Rhizosolenia styliformis Brightwell",
   13: "Navicula directa Smith",
  },
 },
 # 1975 포항·감포(Lee) — 목록형 캡션(p11, 두 판이 한 쪽에 같이 있다).
 # 표본번호(KUDG-…)·시료·지층·지름·배율이 함께 있지만 이름만 옮긴다
 "1975_lee_pohang_gampo_neogene": {
  1: {
   1: "Actinocyclus ingens Rattray",
   2: "Actinocyclus ingens Rattray",
   3: "Coscinodiscus vetustissimus Pant.",
   4: "Coscinodiscus oculus-iridis Ehr.",
   5: "Coscinodiscus marginatus Ehr.",
   6: "Actinocyclus curvatulus Jan.",
   7: "Coscinodiscus curvatulus Grun.",
   8: "Melosira sulcata (Ehr.) Kütz.",
   9: "Coscinodiscus papillosus Hajós",
   10: "Actinoptychus senarius Ehr.",
   11: "Chaetoceros sp.",
   12: "Coscinodiscus argus Ehr.",
  },
  2: {
   1: "Xanthiopyxis ovalis Lohm.",
   2: "Stephanopyxis turris Ralfs",
   3: "Stephanopyxis cfr. ferox (Grev.) Ralfs",
   4: "Melosira islandica O Müll.",
   5: "Stephanogonia hanzawae Kanaya",
   6: "Fragilaria bituminosa var. curta Pant.",
   7: "Fragilaria bituminosa var. minor Pant.",
   8: "Fragilaria bituminosa var. elongata Pant.",
   9: "Thalassiothrix longissima Cleve & Grun.",
   10: "Thalassionema nitzschioides Grun.",
   11: "Grammatophora strict var. fossilis Grun.",
   12: "Dictyocha crux Ehr.",
   13: "Denticula lauta Bail.",
   14: "Denticula hustedtii Simonsen & Kanaya",
   15: "Biddulphia areolata Hajós",
   16: "Liradiscus bipolaris Lohm.",
   17: "Coscinodiscus lineatus Ehr.",
  },
 },
 # 1986 남한 신제3기(Lee) — 목록형 캡션, 세 판 각자 바로 뒤 쪽에서 옮겼다.
 # 표본번호(RC12-381/383, 피스톤코어)·지름·배율이 함께 있지만 이름만 든다
 "1986_lee_se_korea_neogene": {
  1: {
   1: "Coscinodiscus oculus-iridis Ehrenberg",
   2: "Coscinodiscus marginatus var. fossilis Jouse",
   3: "Coscinodiscus marginatus Ehrenberg",
   4: "Coscinodiscus obscurus Schmidt",
   5: "Thalassiosira antiqua (Grun.) Cleve-Euler",
   6: "Actinocyclus curvatulus Janish in Schmidt",
   7: "Coscinodiscus pilicatus Grunow",
   8: "Thalassiosira eccentricus var. leasareolatus Kanaya",
   9: "Thalassiosira convexa Mukhina",
   10: "Coscinodiscus temperei Brun.",
   11: "Caldogramma california Ehrenberg",
   12: "Coscinodiscus tabularis? Grunow",
   13: "Thalassiosira oestrupii (Osterfeld) Proskina-Lavrenko",
   14: "Stephanopyxis schenckii Kayna",
   15: "Stephanopyxis horridus Koizumi",
   16: "Thalassiosira plicata Schrader",
   17: "Xanthiopyxis ovalis Lohman",
   18: "Hemidiscus simplicissimus Hanna and Grant",
   19: "Coscinodiscus endoi Kanaya",
   20: "Triceratium condercorum Brig.",
   21: "Goniothecium odontella Ehrenberg",
   22: "Nitzschia porteri Frenguelli",
   23: "Denticulopsis kamtschatica (Zabelina) Simonsen",
   24: "Denticulopsis hustedtii (Simonsen and Kanaya) Simonsen",
   25: "Denticulopsis hustedtii (Simonsen and Kanaya) Simonsen",
   26: "Goniothecium tenue Brun.",
   27: "Thalassiothrix longissima Cleve and Grunow",
  },
  2: {
   1: "Actinocylcus ingens (undulated type) Rattray",
   2: "Actinocyclus ingens (flaty type) Rattray",
   3: "Coscinodiscus vetustissima Pantocsek",
   4: "Coscinodiscus lineatus Ehrenberg",
   5: "Actinoptychus undulatus (Bail.) Ralfs",
   6: "Actinocyclus ehrenbergi Ralfs in Pritchard",
   7: "Stephanopyxis corona (Ehr.) Grunow",
   8: "Actinocyclus ehrenbergi var. tenella (Breb.) Hustedt",
   9: "Coscinodiscus stellaris Roper",
   10: "Melosira clavigera Grunow",
   11: "Stephanopyxis lineatus (Ehr.) Forti",
   12: "Melosira sulcata Kutzing",
   13: "Stephanogonia hanzawae Kanaya",
   14: "Coscinodiscus nodulifer Schmidt",
   15: "Coscinodiscus perferatus Ehrenberg",
   16: "Stephanopyxis turris Ralfs",
   17: "Liradiscus asperalus Andrew",
   18: "Denticulopsis praedimorpha Akiba",
   19: "Coscinodiscus lewisianus Greville",
   20: "Liradiscus biopolaris Lohman",
   21: "Denticulopsis hustedtii (Kanaya and Simonsen) Simonsen",
   22: "Denticulopsis lauta (Bailey) Simonsen",
  },
  3: {
   1: "Mastogloria splendida (Gregory) Cleve",
   2: "Craspedodiscus rhombicus Grunow",
   3: "Asteromphalus hungarica Pantocsek",
   4: "Thalassiosira nordenskioeldii Cleve",
   5: "Rhaphoneis amphiceros (Ehr.) Ehrenberg",
   6: "Mediaria splendida Sheshukova-Poretskaya",
   7: "Biddulphia areolata Hajos",
   8: "Goniothecium odontella Ehrenberg",
   9: "Diploneis major Cleve",
   10: "Diploneis crabro Ehrenberg",
   11: "Denticulopsis lauta (Bailey) Simonsen",
   12: "Nitzschia porteri Frenguelli",
   13: "Endictya oceanica Ehrenberg",
   14: "Rhizosolenia miocenica Schrader",
   15: "Nitzschia evenscene Schrader",
   16: "Synedra jouseana Sheshukova-Poretzkaya",
   17: "Grammatophora marina (Lynabye) Kutzing",
   18: "Entopya australis var. gigantea Greville",
  },
 },
}


# **상자 순서 → Fig 번호.** `crop_plates.py --probe` 가 낸 대조 시트를 사람이
# 보고 적는다. `None` 은 그림이 아니다(제본 그림자·맞은편 쪽 글자).
# **기계가 번호를 읽게 하지 않는다** — 틀리면 예외가 안 나고 다른 종의 도판이 된다.
# **한 상자에 그림 둘이 닿아 있으면 자동 검출이 하나로 묶는다.** 그 자리는
# 자동 상자를 걷고(ASSIGN 에서 None) 사람이 잰 사각형을 따로 쓴다.
# 좌표는 `boxes()` 와 같은 자리(트림된 150dpi 이미지)다.
MANUAL_BOXES = {
    ("1992_lee_galmal_quaternary_flora", 9): {
        # PLATE 1 의 fig 12(사방으로 뻗은 것)와 fig 19(길쭉한 것)가 닿아서
        # grow=7 에서 한 상자가 됐다. grow=5 로 갈랐을 때의 상자를 그대로 썼다
        12: (116, 635, 224, 838),
        19: (118, 836, 244, 1335),
    },
    # Fig O 의 라벨(검은 동그라미)이 몸통과 흰 틈으로 떨어져 있어 자동 검출이
    # 둘로 쪼갰다(상자 15 = 몸통, 16 = 라벨). 둘을 합친 사각형을 손으로 썼다
    ("2017_yun_ulleung_basin", 13): {
        "O": (149, 913, 620, 1100),
    },
    # **31개 전부 손으로 쟀다** — 그림 크기가 30x150 부터 300x500 까지 널뛰고
    # (원판 사진 + 선그림 혼재), 촘촘히 붙어 있어 한 팽창값으로는 어떤
    # 그림은 안 갈리고 어떤 그림은 속의 성긴 무늬 때문에 조각나 버렸다
    # (`--probe` 로 몇 번을 돌려도 31 과 안 맞았다). 자동 검출을 아예
    # 안 쓰고(`ASSIGN` 을 전부 `None` 으로 둔다) 격자 눈금을 그은 사본에
    # 대고 1489×2071 원본 좌표를 하나씩 읽었다.
    ("1994_lee_namyangman_tidal_flat", 12): {
        1: (225, 388, 427, 595), 2: (485, 388, 657, 595),
        3: (730, 390, 940, 605), 4: (1000, 390, 1255, 645),
        5: (210, 655, 443, 898), 6: (452, 685, 745, 898),
        7: (760, 620, 900, 865), 8: (925, 675, 1080, 805),
        9: (1105, 675, 1270, 805), 10: (218, 940, 388, 1108),
        11: (420, 940, 600, 1108), 12: (628, 895, 898, 1108),
        13: (928, 883, 1078, 1028), 14: (1095, 855, 1265, 1030),
        15: (215, 1145, 365, 1395), 16: (420, 1125, 560, 1310),
        17: (630, 1105, 895, 1370), 18: (915, 1050, 990, 1370),
        19: (1010, 1065, 1255, 1315), 20: (215, 1395, 265, 1810),
        21: (290, 1420, 365, 1810), 22: (425, 1265, 475, 1510),
        23: (425, 1530, 475, 1810), 24: (525, 1365, 615, 1622),
        25: (510, 1365, 610, 1622), 26: (635, 1395, 755, 1615),
        27: (950, 1395, 1065, 1530), 28: (515, 1645, 675, 1815),
        29: (730, 1655, 885, 1815), 30: (950, 1590, 1065, 1820),
        31: (1065, 1350, 1250, 1840),
    },
    # 1993 남해 — 1994 만큼 빽빽하진 않지만 `--probe` 가 26개(그림 20개보다
    # 많다 — 번호 활자·스캔 잡티가 조각으로 잡혔다)를 냈고 그마저 몇 개는
    # 서로 다른 그림이 한 상자로 묶여 있었다. 손으로 재는 쪽이 더 빨랐다
    ("1993_bae_lee_south_sea_surface", 13): {
        1: (205, 440, 610, 810), 2: (640, 435, 1015, 805),
        3: (1045, 445, 1270, 660), 4: (195, 860, 470, 1095),
        5: (505, 820, 720, 1035), 6: (755, 840, 950, 1035),
        7: (965, 720, 1270, 1020), 8: (225, 1140, 450, 1340),
        9: (460, 1065, 710, 1310), 10: (725, 1060, 970, 1275),
        11: (985, 1050, 1175, 1265), 12: (210, 1340, 420, 1610),
        13: (460, 1315, 705, 1590), 14: (760, 1315, 950, 1520),
        15: (210, 1615, 365, 1870), 16: (405, 1595, 615, 1870),
        17: (660, 1575, 870, 1870), 18: (895, 1520, 980, 1800),
        19: (1040, 1305, 1110, 1790), 20: (1175, 1045, 1240, 1795),
    },
    ("1993_bae_lee_south_sea_surface", 15): {
        1: (210, 415, 490, 715), 2: (540, 400, 895, 750),
        3: (915, 415, 1280, 755), 4: (220, 755, 370, 1015),
        5: (410, 760, 590, 945), 6: (660, 800, 785, 1060),
        7: (855, 770, 945, 1130), 8: (1000, 745, 1280, 1000),
        9: (225, 1015, 365, 1215), 10: (410, 1100, 495, 1215),
        11: (520, 1100, 620, 1200), 12: (195, 1270, 495, 1565),
        13: (530, 1250, 710, 1550), 14: (755, 1195, 950, 1540),
        15: (1015, 1160, 1240, 1360), 16: (975, 1400, 1240, 1560),
        17: (195, 1600, 465, 1815), 18: (500, 1600, 755, 1835),
        19: (780, 1615, 970, 1820), 20: (1000, 1600, 1235, 1825),
    },
    # 2001 브랜스필드 — **검은 바탕**이라 자동 검출과 아예 안 맞는다.
    # `boxes()` 는 "짙은 화소 = 그림" 으로 본다(`thr` 아래가 그림) — 이
    # 도판은 배경이 검고 그림이 밝아 반대다. 판마다 갈 것도 없이 손으로 쟀다
    ("2001_park_bransfield_paleoenv", 10): {
        1: (210, 315, 500, 630), 2: (550, 325, 810, 590),
        3: (840, 335, 1055, 490), 4: (1065, 335, 1250, 610),
        5: (235, 680, 410, 940), 6: (430, 625, 545, 870),
        7: (585, 620, 810, 935), 8: (855, 535, 1000, 690),
        9: (830, 740, 1055, 980), 10: (1130, 610, 1205, 840),
        11: (1085, 900, 1300, 1015), 12: (240, 995, 445, 1230),
        13: (420, 900, 610, 1040), 14: (640, 900, 810, 1060),
        15: (865, 1015, 1040, 1190), 16: (1105, 1115, 1300, 1290),
        17: (215, 1240, 450, 1450), 18: (510, 1090, 600, 1170),
        19: (500, 1230, 610, 1360), 20: (445, 1365, 610, 1585),
        21: (705, 1080, 770, 1410), 22: (805, 1360, 895, 1500),
        23: (965, 1250, 1090, 1410), 24: (975, 1395, 1135, 1585),
        25: (1150, 1295, 1300, 1610), 26: (245, 1500, 410, 1860),
        27: (450, 1575, 560, 1860), 28: (600, 1515, 695, 1860),
        29: (715, 1415, 770, 1860), 30: (805, 1500, 895, 1860),
        31: (950, 1630, 1045, 1860), 32: (1110, 1615, 1280, 1860),
    },
    ("2001_park_bransfield_paleoenv", 12): {
        1: (200, 315, 560, 675), 2: (590, 315, 930, 675),
        3: (975, 325, 1290, 645), 4: (200, 730, 560, 1030),
        5: (590, 725, 930, 1040), 6: (975, 725, 1290, 1085),
        7: (245, 1125, 305, 1685), 8: (345, 1195, 440, 1670),
        9: (545, 1220, 620, 1650), 10: (700, 1175, 770, 1680),
        11: (840, 1210, 915, 1670), 12: (995, 1285, 1065, 1660),
        13: (1120, 1120, 1255, 1685),
    },
    # 1975 포항·감포 — 선그림이라 대비는 옅지만 도판마다 여백이 넉넉해
    # 자동 검출을 먼저 시도했다. 그런데 흐린 그림(Fig 1·2·4·5) 속의
    # 성긴 무늬가 조각나 13개(그림 12개인데)로 갈렸다 — 손으로 다시 쟀다
    ("1975_lee_pohang_gampo_neogene", 13): {
        1: (145, 300, 415, 595), 2: (480, 265, 800, 620),
        3: (840, 295, 1175, 710), 4: (115, 640, 420, 945),
        5: (400, 700, 890, 1230), 6: (925, 770, 1190, 1010),
        7: (165, 1015, 430, 1270), 8: (600, 1270, 750, 1420),
        9: (985, 1150, 1190, 1300), 10: (115, 1365, 495, 1680),
        11: (590, 1525, 820, 1680), 12: (915, 1350, 1205, 1610),
    },
    # Plate II — 9·10·11 은 처음에 잘못 재서(옆 그림 자리를 베꼈다) 원본을
    # 다시 대조해 바로잡았다 — 9(굵은 침상)·10(그 옆의 아주 흐린 침상,
    # 거의 안 보인다)·11(원형 무늬 있는 타원)이 서로 다른 상자다
    ("1975_lee_pohang_gampo_neogene", 14): {
        1: (195, 305, 495, 485), 2: (590, 315, 820, 530),
        3: (915, 315, 1185, 580), 4: (190, 565, 410, 1040),
        5: (435, 590, 635, 795), 6: (480, 825, 600, 1060),
        7: (665, 675, 855, 990), 8: (900, 690, 1170, 950),
        9: (170, 1045, 295, 1670), 10: (370, 1480, 425, 1660),
        11: (385, 1060, 470, 1395), 12: (565, 1090, 665, 1320),
        13: (775, 1055, 870, 1370), 14: (940, 1065, 1040, 1350),
        15: (535, 1415, 820, 1540), 16: (535, 1575, 830, 1680),
        17: (890, 1395, 1160, 1680),
    },
    # 1986 남한 신제3기 — 세 판 다 자동 검출이 안 먹혔다(그림 27·22·18개가
    # 44개 이상으로 쪼개졌다). 4사분면으로 나눠 격자 사본에 대고 잰 뒤
    # 겹침 검사(모든 쌍의 상자 겹침 넓이)로 전사 실수를 걸렀다 — 172·173
    # 에서 당한 것과 같은 실수를 이번엔 짚기 전에 코드로 잡았다
    ("1986_lee_se_korea_neogene", 10): {
        1: (130, 215, 500, 605), 2: (730, 215, 960, 600),
        3: (985, 225, 1365, 600), 4: (95, 655, 455, 1005),
        5: (490, 625, 710, 830), 6: (795, 640, 990, 830),
        7: (1020, 620, 1365, 950), 8: (140, 1050, 440, 1310),
        9: (425, 950, 635, 1110), 10: (650, 950, 865, 1140),
        11: (880, 890, 1045, 1055), 12: (160, 1390, 380, 1590),
        13: (400, 1300, 570, 1445), 14: (570, 1165, 780, 1400),
        15: (835, 1095, 1060, 1300), 16: (1075, 1030, 1325, 1245),
        17: (565, 1445, 780, 1590), 18: (835, 1390, 1030, 1540),
        19: (1055, 1320, 1220, 1505), 20: (150, 1610, 420, 1850),
        21: (405, 1500, 570, 1850), 22: (630, 1630, 710, 1850),
        23: (730, 1600, 820, 1850), 24: (860, 1575, 925, 1850),
        25: (980, 1565, 1050, 1850), 26: (1095, 1530, 1185, 1850),
        27: (1250, 1275, 1295, 1850),
    },
    ("1986_lee_se_korea_neogene", 14): {
        1: (115, 240, 490, 600), 2: (510, 260, 760, 495),
        3: (795, 240, 1080, 545), 4: (1110, 255, 1340, 480),
        5: (200, 640, 460, 950), 6: (470, 550, 760, 810),
        7: (795, 610, 1010, 810), 8: (1035, 540, 1365, 880),
        9: (145, 1000, 475, 1340), 10: (450, 910, 780, 1210),
        11: (810, 895, 1030, 1110), 12: (1065, 950, 1360, 1220),
        13: (175, 1400, 410, 1610), 14: (470, 1275, 700, 1470),
        15: (700, 1240, 1070, 1510), 16: (1095, 1215, 1360, 1510),
        17: (480, 1520, 740, 1650), 18: (875, 1525, 955, 1660),
        19: (165, 1685, 570, 1850), 20: (730, 1685, 945, 1850),
        21: (1030, 1530, 1110, 1850), 22: (1195, 1570, 1275, 1800),
    },
    ("1986_lee_se_korea_neogene", 18): {
        1: (145, 240, 525, 770), 2: (605, 295, 780, 710),
        3: (925, 240, 1225, 610), 4: (150, 820, 470, 1090),
        5: (480, 680, 685, 1020), 6: (730, 700, 870, 1100),
        7: (875, 725, 1325, 860), 8: (940, 920, 1290, 1100),
        9: (225, 1180, 370, 1460), 10: (445, 1095, 590, 1485),
        11: (640, 1140, 775, 1430), 12: (820, 1165, 890, 1365),
        13: (225, 1520, 445, 1800), 14: (530, 1515, 620, 1830),
        15: (730, 1390, 800, 1850), 16: (890, 1390, 965, 1850),
        17: (1025, 1320, 1115, 1820), 18: (1175, 1260, 1280, 1820),
    },
}

ASSIGN = {
 ("1936_skvortzov_ampen_neogene", 41): [
   None, 1, 2, 3, 5, 6, 4, 7, 8, 10, 11, 9, 14, 15, 13, 17, 18, 16, 20, 19,
   21, 22, 23, 24, 26, 29, 25, 28, 27, 30, 36, 37, 35, 34, 31, 33, 32, None],
 ("1936_skvortzov_ampen_neogene", 44): [
   None, 1, 2, 3, 4, 5, 9, 10, 11, 6, 8, 7, 12, 13, 18, 15, 14, 17, 19, 16, None],
 ("1936_skvortzov_ampen_neogene", 47): [1, 2, 3, 4, 5, 8, 6, 7, 10, 11, 12, 9, None],
 ("1936_skvortzov_ampen_neogene", 50): [2, 4, 5, 1, 3, 9, 8, 6, 7, 11, 10, None],
 # 1993 — 사진 타일이라 상자가 깨끗하다. 셋 다 그림 수와 상자 수가 맞았다
 ("1993_lee_chaetoceros_yeonil", 12): [
   1, 2, 3, 4, 6, 7, 8, 9, 5, 13, 11, 12, 10, 15, 14, 20, 16, 17, 18, 19,
   22, 21, 23, 24],
 ("1993_lee_chaetoceros_yeonil", 16): [
   1, 2, 3, 4, 5, 7, 8, 12, 9, 10, 11, 17, 13, 14, 15, 16, 18, 19, 20, 24,
   21, 22, 23, 28, 26, 27, 25],
 ("1993_lee_chaetoceros_yeonil", 24): [
   1, 2, 3, 10, 7, 4, 5, 9, 8, 6, 11, 12, 13, 14, 15, 16, 17, 20, 21, 18,
   19, 25, 22, 23, 24, 26, 27, 28, 29],
 # 1992 철원 — PLATE 1(p9). **fig 12·19 는 여기 없다** — 상자가 닿아서
 # `MANUAL_BOXES` 로 따로 잘랐다. 상자 17(가느다란 조각)은 어느 번호인지
 # 원문만으로 못 정해 `UNCROPPED` 로 넘긴다
 ("1992_lee_galmal_quaternary_flora", 9): [
   None, 1, 2, 3, 5, 6, 7, 14, 4, 8, 11, 9, 10, None, 13, 16, None, 17, 18,
   23, 15, 20, 21, 22],
 # PLATE 2(p13). **title 상자가 없다** — 목록이 1번 그림부터 시작한다.
 # idx11·25 는 그림이 아니다(fig10 목 부분의 조각 · 눈금자)
 ("1992_lee_galmal_quaternary_flora", 13): [
   1, 2, 3, 4, 5, 6, 7, 18, 9, 10, None, 8, 11, 12, 13, 14, 17, 15, 21, 16,
   23, 24, 22, 19, None, 20],
 # PLATE 3(p17). idx7 은 눈금자(폭 10px) — 그림이 아니다
 ("1992_lee_galmal_quaternary_flora", 17): [
   1, 2, 3, 4, 5, 6, None, 8, 10, 7, 11, 12, 23, 9, 17, 18, 19, 15, 14, 20,
   13, 21, 22, 16],
 # PLATE 4(p19) — 그림이 9개뿐이라 한 장씩 크다. idx10 은 눈금자, idx11·12 는
 # fig6·1 의 인쇄 번호 잉크가 valve 와 안 붙어서 따로 상자가 됐다 — 그림이 아니다
 ("1992_lee_galmal_quaternary_flora", 19): [
   1, 2, 5, 3, 4, 6, 7, 8, 9, None, None, None],
 # 1985 Plate 3(p22). "1a"·"1b" 는 한 그림의 두 부분 라벨이다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 22): [
   "1a", "1b", 2, 3, 4, 6, 5, 10, 7, 8, 9, 11],
 # Plate 1(p20). **번호 없는 동반 사진이 있다** — 인쇄된 숫자는 앵커 하나뿐이고
 # 옆에 붙은 사진은 번호가 안 찍힌다. 종 경계(1,2=ikebei · 3~8=kanayae ·
 # 9=nicobarica · 10~12=punctata)만 확실하고, **동반 사진의 정확한 번호는
 # 근사값이다**(`b` 접미사) — 종은 맞고 그림 번호는 대표값일 수 있다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 20): [
   1, "1b", 2, "2b",
   3, "3b", 4, "4b", "4c",
   5, "6", "6b", "6c", "6d", "6e", 7,
   8, "8b",
   10, "10b", 11, 12, "12b",
   9],
 # Plate 2(p21). 대부분 자기 번호가 다 찍혀 있다 — 1936 형에 가깝다. 상자
 # 정렬이 y 를 50 단위로 묶어 가로 순서가 살짝 어긋나 좌표로 다시 짚었다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 21): [
   8, 9, 1, 2, 3, 4, 5, 6, 7, 11, "11b", 19, 14, "14b",
   10, "10b", 12, 13, "13b", 20, 21, "21b", 15, 16, 17, "17b", 18],
 # Plate 4(p23). 도판 전체가 punctata 하나다. "1A-B" 는 자동 파서가 정규화한
 # 대문자 키와 맞춰 그대로 쓴다(plate3 는 소문자를 써도 바탕 숫자로 찾아진다)
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 23): [
   "1A", "1B", 2, 3, 5, 8, 4, 6, 7, 9, "7b"],
 # Plate 5(p24). 도판 전체가 nicobarica 하나 · 상자 순서가 캡션 순서와
 # 그대로 맞아 짚을 것이 없었다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 24): [
   "1A", "1B", "2A", "2B", "3A", "3B",
   "4A", "4B", "5A", "5B", 8, 6, 7, 9],
 # Plate 6(p25). norwegica 하나 · 상자 9개가 캡션 1~9 와 그대로 맞는다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 25): [1,2,3,4,5,6,7,8,9],
 # Plate 7(p26). 44상자 · 캡션 번호가 전부 찍혀 있지만 상자 44개를 그림 29개에
 # 정확히 1:1로 되짚기엔 시간이 너무 든다. **종 경계(1~15=praelauta ·
 # 16~29=lauta, 25번째 상자에서 갈린다)만 확실히 하고** 나머지는 순번으로
 # 근사했다 — 정확한 그림 번호가 아니라 "이 종의 사진 중 하나" 로 읽는다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 26): (
   [f"1p{i:02d}" for i in range(1, 24)] + [f"16p{i:02d}" for i in range(1, 22)]),
 # Plate 8(p27). praelauta 하나 · 순서 그대로
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 27): [
   1, "2A", "2B", "3A", "3B", 4, 6, 8, 5, 7, 9],
 # Plate 9(p28). lauta 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 28): [
   1, 2, 3, "4A", 5, 6, "4B", 7, 9, 8],
 # Plate 10(p29). 32상자 · 종 경계 근사(hyalina/miocaenica) — Plate7 과 같은 방식
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 29): (
   [f"1p{i:02d}" for i in range(1, 23)] + [f"17p{i:02d}" for i in range(1, 11)]),
 # Plate 11(p30). hyalina 하나. 13번째 상자는 캡션 글자 얼룩이라 건너뛴다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 30): [
   "1A", "1B", 2, "3A", "3B", 4, 5, 6, 7, 8, 9, 10, None],
 # Plate 12(p31). hyalina(1-5)/miocaenica(6-9)
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 31): [
   "1A", 4, 5, "1B", "6A", "6B", 8, 2, 3, 7, 9],
 # Plate 13(p32). **도판 전체가 praedimorpha 하나뿐이라** 정확한 그림 번호
 # 대조를 건너뛴다 — 어느 상자든 이름이 같다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 32): [
   f"1p{i:02d}" for i in range(1, 41)],
 # Plate 14(p33) praedimorpha 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 33): [f"1p{i:02d}" for i in range(1, 14)],
 # Plate 15(p34) dimorpha 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 34): [f"1p{i:02d}" for i in range(1, 38)],
 # Plate 16(p35) dimorpha 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 35): [f"1p{i:02d}" for i in range(1, 12)],
 # Plate 18(p37) hustedtii 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 37): [f"1p{i:02d}" for i in range(1, 12)],
 # Plate 17(p36). **처음에 1~10이 상자 순서와 그대로 맞을 거라 짚었다가
 # 몽타주로 확인해 보니 틀렸다** — 쌍이 공유하는 번호가 "(1,2)(3,4)(9,10)"
 # 순서가 아니라 "(1,2)=1·(3,4)=2·(9,10)=3·(5,6)=4·(7,8)=5" 로 자리가 바뀐다.
 # 넷을 직접 열어서 잡았다. **fig6(katayamae)의 정확한 자리는 못 찾았다** —
 # 나머지 26상자(11~36) 안 어딘가에 있을 텐데, 종 하나 차이라 hustedtii 로
 # 근사한 값 안에 섞여 있을 수 있다(다음에 이 도판을 다시 볼 사람에게 남긴다)
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 36): (
   [1, "1b", 2, "2b", 4, "4b", 5, "5b", 3, "3b"]
   + [f"7p{i:02d}" for i in range(1, 27)]),
 # Plate 19(p38). hustedtii(1-5)/katayamae(6-9) — 종 경계로 근사(1,2,3,4 는
 # 상자와 그대로 맞아 확정, 5 는 아래 줄에 따로 있는 걸 확인했다)
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 38): [
   1, 2, 3, 4, "6p1", "6p2", "6p3", "6p4",
   "6p5", 5, "6p6", "6p7"],
 # Plate 20(p39) katayamae 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 39): [f"2p{i:02d}" for i in range(1, 10)],
 # Plate 22(p41) kamtschatica 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 41): [f"3p{i:02d}" for i in range(1, 17)],
 # Plate 23(p42) koizumii 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 42): [f"1p{i:02d}" for i in range(1, 14)],
 # Plate 25(p44) Neodenticula sp. A 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 44): [f"3p{i:02d}" for i in range(1, 11)],
 # Plate 21(p40). 44상자 · 종 넷(rolandii 1-6·kamtschatica 7-21·koizumii 22-28·
 # sp.A 29-31) — 경계를 상자수 비례로 추정하고 경계만 확인한다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 40): (
   [f"1p{i:02d}" for i in range(1, 9)] + [f"7p{i:02d}" for i in range(1, 23)]
   + [f"22p{i:02d}" for i in range(1, 11)] + [f"29p{i:02d}" for i in range(1, 5)]),
 # Plate 24(p43). seminae(1-11)/spA(12-18)/koizumii(19) — 상자수 비례로 추정
 # **경계가 두 번 어긋났다** — 처음엔 너무 일찍(18), 다음엔 너무 늦게(22) 잡았다.
 # 21로 재조정했지만 이 도판은 마지막으로 재확인은 안 했다 — seminae/spA
 # 사이 한두 장이 반대 종으로 남아 있을 수 있다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 43): (
   [f"1p{i:02d}" for i in range(1, 22)] + [f"12p{i:02d}" for i in range(1, 9)]
   + [f"19p{i:02d}" for i in range(1, 4)]),
 # Plate 26(p45) seminae 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 45): [f"2p{i:02d}" for i in range(1, 13)],
 # Plate 28(p47) yabei 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 47): [f"1p{i:02d}" for i in range(1, 10)],
 # Plate 29(p48) grunowii 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 48): [f"1p{i:02d}" for i in range(1, 12)],
 # Plate 30(p49) grunowii 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 49): [f"1p{i:02d}" for i in range(1, 15)],
 # Plate 27(p46). 상자 6개 = 그림 6개, 정확히 1:1
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 46): [1, 2, 3, 4, 5, 6],
 # Plate 31(p50). 상자 8개 = 그림 8개
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 50): [1, 2, 3, 4, 5, 6, 7, 8],
 # Plate 32(p51) cf. brunii 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 51): [f"1p{i:02d}" for i in range(1, 12)],
 # Plate 33(p52) cf. brunii 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 52): [f"1p{i:02d}" for i in range(1, 8)],
 # Plate 35(p54) ingens 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 54): [f"1p{i:02d}" for i in range(1, 11)],
 # Plate 36(p55) carina 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 55): [f"1p{i:02d}" for i in range(1, 18)],
 # Plate 37(p56) carina 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 56): [f"1p{i:02d}" for i in range(1, 19)],
 # Plate 34(p53). ingens(1-7)/var.nodus(8-9) — 상자수 비례로 추정
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 53): (
   [f"1p{i:02d}" for i in range(1, 7)] + [f"8p{i:02d}" for i in range(1, 5)]),
 # Plate 43(p62) praebarboi 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 62): [f"1p{i:02d}" for i in range(1, 10)],
 # Plate 38(p57). ezoensis(1-9)/magnaareolata(10-18) — 상자수 비례 추정
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 57): (
   [f"1p{i:02d}" for i in range(1, 13)] + [f"10p{i:02d}" for i in range(1, 15)]),
 # Plate 39(p58). jouseae(1-6)/miocenica(7-15)
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 58): (
   [f"1p{i:02d}" for i in range(1, 12)] + [f"7p{i:02d}" for i in range(1, 19)]),
 # Plate 40(p59). pliocena(1-7)/reinholdii(8-9)
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 59): (
   [f"1p{i:02d}" for i in range(1, 11)] + [f"8p{i:02d}" for i in range(1, 5)]),
 # Plate 41(p60). 상자 6개 = 그림 6개
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 60): [1, 2, 3, 4, 5, 6],
 # Plate 42(p61). **길쭉한 표본들이 서로 겹쳐 있어** 상자 하나가 표본 여럿을
 # 삼켰다(9상자로 11그림). 종만 위치로 근사했다 — curvirostris(1,2) ·
 # barboi(3,4,5,7,10,11 중 다수) · interposita(6) · praebarboi(8,9).
 # **이 도판은 종 배정도 확신이 낮다** — 겹친 표본 사진이라 자리를 못 가른다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 61): [
   1, 2, 3, 6, 5, 4, 7, 8, 9],
 # Plate 44(p63) barboi 하나 — "Plate 44" 뒤 마침표 누락으로 처음엔 통째로
 # 안 잡히던 도판이다(파서 쪽에서 고쳤다)
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 63): [f"2p{i:02d}" for i in range(1, 10)],
 # Plate 45(p64) curvirostris 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 64): [f"1p{i:02d}" for i in range(1, 8)],
 # Plate 47(p66) Rouxia californica 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 66): [f"1p{i:02d}" for i in range(1, 16)],
 # Plate 49(p68) hirosakiensis 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 68): [f"1p{i:02d}" for i in range(1, 10)],
 # Plate 50(p69) schraderi 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 69): [f"1p{i:02d}" for i in range(1, 12)],
 # Plate 52(p71) antiqua 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 71): [f"1p{i:02d}" for i in range(1, 11)],
 # Plate 53(p72) fraga 하나
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 72): [f"2p{i:02d}" for i in range(1, 10)],
 # Plate 46(p65). 캡션에 6,7,8,12(Rouxia cf. peragalli)가 빠져 있어 위
 # `_load_ak85_captions` 에서 손으로 채웠다. 17번은 캡션에 아예 없다 —
 # 근처 16(Actinocyclus oculatus)의 동반 사진으로 본다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 65): [
   1, 2, 3, 4, 13, 5, 14, 15, 9, 10, 11, 16, 8, 6, 7, "12a", "12b"],
 # Plate 48(p67). 종이 여러 번 뒤섞인다(schraderi/hirosakiensis 를 오간다) —
 # 상자 순서를 그대로 그림 번호로 쓰고 경계만 확인한다
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 67): [
   1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, "16b"],
 # Plate 51(p70). 상자 10개 = 그림 10개
 ("1985_akiba_yanagisawa_dsdp87_zonal_markers", 70): [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
 # 2017 울릉분지 Plate 1(p13). 상자 22개 — A-N·P·Q·R·S·T 는 자동으로 갈렸고,
 # O(15·16번)는 몸통·라벨이 갈라져 `MANUAL_BOXES` 로 뺐다. 19번은 O·P 사이
 # 여백에 낀 잡티(그림이 아니다)
 ("2017_yun_ulleung_basin", 13): [
   "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N",
   None, None, "P", "Q", None, "R", "S", "T"],
 # 1994 남양만 — 자동 검출을 안 쓴다(위 `MANUAL_BOXES` 설명 참고). `PARAMS`
 # 값으로 상자가 몇 개 잡히든 전부 버리는 자리라 개수만 맞춰 `None` 을 채운다
 ("1994_lee_namyangman_tidal_flat", 12): [None] * 6,
 # 1993 남해 — 마찬가지로 자동 검출 결과를 안 쓴다
 ("1993_bae_lee_south_sea_surface", 13): [None] * 26,
 ("1993_bae_lee_south_sea_surface", 15): [None] * 37,
 # 2001 브랜스필드 — 검은 바탕이라 기본값 그대로 도판 전체가 상자 하나로
 # 잡힌다(그것도 안 쓴다. 전부 `MANUAL_BOXES`)
 ("2001_park_bransfield_paleoenv", 10): [None] * 1,
 ("2001_park_bransfield_paleoenv", 12): [None] * 1,
 # 1975 포항·감포 — 마찬가지로 자동 검출 결과를 안 쓴다
 ("1975_lee_pohang_gampo_neogene", 13): [None] * 13,
 ("1975_lee_pohang_gampo_neogene", 14): [None] * 22,
 # 1986 남한 신제3기 — 세 판 다 자동 검출 결과를 안 쓴다
 ("1986_lee_se_korea_neogene", 10): [None] * 44,
 ("1986_lee_se_korea_neogene", 14): [None] * 65,
 ("1986_lee_se_korea_neogene", 18): [None] * 39,
}

# **검출 설정이 쪽마다 다르다.** 도판마다 그림이 붙은 정도가 달라서 한 값으로
# 안 된다 — PLATE IV 는 `grow=9` 로 여섯이 한 덩어리가 됐고, PLATE I 은
# `min_area` 를 안 낮추면 작은 그림 둘(6·28)을 놓친다.
# **`--probe` 로 상자 수를 캡션의 그림 수와 맞춰 놓고 짚는다.**
PARAMS = {
    # **감싸인 상자를 걷으면 Fig 13 이 사라진다** — Fig 7(큰 원반)의 상자가
    # 12·13 을 통째로 감싼다. 여기서는 걷지 않는다
    ("1936_skvortzov_ampen_neogene", 41):
        dict(grow=3, min_area=1200, min_side=30, drop_nested=False),
    ("1936_skvortzov_ampen_neogene", 44): dict(grow=5, min_area=1200, min_side=30),
    ("1936_skvortzov_ampen_neogene", 47): dict(grow=9, min_area=4000, min_side=60),
    ("1936_skvortzov_ampen_neogene", 50): dict(grow=5, min_area=4000, min_side=60),
    ("1993_lee_chaetoceros_yeonil", 12): dict(grow=3, min_area=2500, min_side=40),
    ("1993_lee_chaetoceros_yeonil", 16): dict(grow=3, min_area=2500, min_side=40),
    ("1993_lee_chaetoceros_yeonil", 24): dict(grow=3, min_area=2500, min_side=40),
    ("1992_lee_galmal_quaternary_flora", 9): dict(grow=7, min_area=2500, min_side=40),
    # min_area/min_side 를 낮추면 title 상자가 안 잡히고(1번부터 시작),
    # fig15·20 이 자동으로 갈린다 — 9쪽과 달리 여기는 손대지 않아도 됐다
    ("1992_lee_galmal_quaternary_flora", 13): dict(grow=3, min_area=1200, min_side=30),
    ("1992_lee_galmal_quaternary_flora", 17): dict(grow=3, min_area=1200, min_side=30),
    ("1992_lee_galmal_quaternary_flora", 19): dict(grow=5, min_area=2500, min_side=40),
    # 1985 는 밸브 윤곽선이 아니라 **검은 바탕 SEM 사진 패널**이다 —
    # 흰 화소가 아니라 짙은 화소 덩어리가 곧 상자다. 대비가 뚜렷해 팽창이
    # 거의 필요 없다(`grow=3`). 쪽마다 여백 비율이 조금씩 달라 `margin` 은
    # 도판마다 잰다(아래 MARGIN)
    "__ak85_default__": dict(thr=200, grow=3, min_area=3000, min_side=50),
    # 사진 격자라 대비가 뚜렷하고(`grow=3`), 위아래 여백에 머리말·캡션 문장이
    # 있어 `margin` 으로 걷는다(위 11.1% · 아래 35.4% — 재서 넣었다)
    ("2017_yun_ulleung_basin", 13):
        dict(grow=3, min_area=3000, margin="0,0.111,0,0.354"),
    # 값 자체는 안 쓴다(전부 `MANUAL_BOXES`) — `--probe` 가 상자 6개로
    # 멈추게만 맞췄다(`ASSIGN` 길이와 맞아야 `--cut` 이 안 죽는다)
    ("1994_lee_namyangman_tidal_flat", 12):
        dict(grow=3, min_area=50000, min_side=30),
    # 값 자체는 안 쓴다(전부 `MANUAL_BOXES`) — 그림 20개인데 26개로 쪼개져
    # (번호 활자·스캔 잡티가 상자로 잡혔다) 손으로 재는 쪽이 더 빨랐다
    ("1993_bae_lee_south_sea_surface", 13):
        dict(grow=3, min_area=2000, min_side=30),
    # PLATE 2 는 더 심하다 — 그림 20개가 37개로 쪼개졌다
    ("1993_bae_lee_south_sea_surface", 15):
        dict(grow=3, min_area=2000, min_side=30),
    # 값 자체는 안 쓴다(전부 `MANUAL_BOXES`) — 그림 12개가 13개로 쪼개졌다
    ("1975_lee_pohang_gampo_neogene", 13):
        dict(grow=3, min_area=2000, min_side=30),
    # 그림 17개가 22개로 쪼개졌다
    ("1975_lee_pohang_gampo_neogene", 14):
        dict(grow=3, min_area=2000, min_side=30),
    # 값 자체는 안 쓴다(전부 `MANUAL_BOXES`) — 그림 27·22·18개가
    # 44·65·39개로 쪼개졌다(세 판 다 대비가 낮은 선그림이 많다)
    ("1986_lee_se_korea_neogene", 10):
        dict(grow=3, min_area=1500, min_side=25),
    ("1986_lee_se_korea_neogene", 14):
        dict(grow=3, min_area=1500, min_side=25),
    ("1986_lee_se_korea_neogene", 18):
        dict(grow=3, min_area=1500, min_side=25),
}

# 1985 는 쪽마다 머리말·쪽번호 폭이 달라 한 여백 값으로 안 된다. 없으면
# 기본값(0.05,0.06,0.05,0.12)을 쓴다
AK85_MARGIN = {}

# **자동으로는 못 갈린 그림.** 이웃과 붙어 한 상자가 됐다 — 손으로 잘라야 한다.
# **적어 두지 않으면 조용히 빠진다.**
UNCROPPED = {
    ("1936_skvortzov_ampen_neogene", 41, 12):
        "Fig 7(큰 원반)과 한 덩어리가 됐다 — 둘이 닿아 있다",
    ("1993_lee_chaetoceros_yeonil", 16, 6):
        "검출이 못 잡았다 — 타일이 흐려 문턱을 넘지 못했다",
    ("1992_lee_galmal_quaternary_flora", 9, "box17"):
        "fig 16 과 17 사이의 가느다란 조각 — 원문에 번호가 없다. "
        "fig 16 의 둘째 그림(옆면)일 수 있으나 확정 못 해 건너뛴다",
}
