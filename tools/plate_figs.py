"""도판의 그림 번호 ↔ 학명. **사람이 원문을 읽은 기록이다** (P20 · 논문 도판).

`render_verify.VERIFIED` 와 같은 자리다 — 도구가 다시 계산하지 않고 값을 그대로
들고 있다. 근거는 각 논문의 도판 캡션 쪽이고 `SOURCE` 에 쪽을 적어 두었다.

**학명은 캡션에 찍힌 그대로다.** 고쳐 쓰지 않는다 — `Stepanodiscus` 는 원문이
그렇게 찍혀 있다(보통은 *Stephanodiscus*). 현재 통용명은 AlgaeBase 대조표가
말한다(사용자 2026-08-26).

**`sp. nov.`·`var. nov.`·`fo. nov.` 는 그 논문이 세운 이름이다** — 도감 셋에
없을 가능성이 높고, 사용자가 "논문에서만 언급되는 종" 이라고 한 것이 이것이다.
"""

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
}


# **상자 순서 → Fig 번호.** `crop_plates.py --probe` 가 낸 대조 시트를 사람이
# 보고 적는다. `None` 은 그림이 아니다(제본 그림자·맞은편 쪽 글자).
# **기계가 번호를 읽게 하지 않는다** — 틀리면 예외가 안 나고 다른 종의 도판이 된다.
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
}

# **자동으로는 못 갈린 그림.** 이웃과 붙어 한 상자가 됐다 — 손으로 잘라야 한다.
# **적어 두지 않으면 조용히 빠진다.**
UNCROPPED = {
    ("1936_skvortzov_ampen_neogene", 41, 12):
        "Fig 7(큰 원반)과 한 덩어리가 됐다 — 둘이 닿아 있다",
    ("1993_lee_chaetoceros_yeonil", 16, 6):
        "검출이 못 잡았다 — 타일이 흐려 문턱을 넘지 못했다",
}
