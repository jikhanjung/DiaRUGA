#!/usr/bin/env python3
"""도감 색인 셋을 JSON 으로 뽑는다 — P15 반입의 **1단계**.

    md (NAS)  →  이 스크립트  →  atlas/*.json (저장소)  →  2단계 반입  →  DB

**왜 두 단계인가** (P15 7절). 뷰어 컨테이너는 NAS 공유를 못 보고(P14 4.4),
DB 를 만지는 것은 `dbrun.sh` 로만 들어간다(CLAUDE.md). 두 규칙이 한 스크립트
안에서 부딪히므로 갈랐다 — 이쪽은 **호스트에서 돌고 Django 를 안 쓴다**
(`ops/export_review.py`·`backup_db.py` 와 같은 자리). 산출 JSON 을 저장소에
커밋하면 NAS 가 없는 자리에서도 반입이 돌고, **색인이 바뀐 것이 diff 로 보인다.**

**원본은 md 이고 이 JSON 은 사본이다**(P15 4.2). 언제든 지우고 다시 만든다.

## 이 파서가 지키는 것

- **이름을 뽑는 규칙은 `harvest_worms.binomial` 하나뿐이다.** 여기서 가져다
  쓴다 — 두 벌이 되면 대조표·표시와 붙는 자리가 어긋난다(`annotate_index.py`
  머리말과 같은 자리)
- **표제어를 고치지 않는다.** 색인은 OCR 산물이라 기계가 고쳐 쓰면 인용이
  원문과 어긋난다(`Triceratium venustun` 은 원문이 그렇게 찍혀 있다 · 126).
  `name` 은 색인에 적힌 그대로이고, 맞추는 데 쓸 이름은 `binomial` 이 따로 든다
- **사람이 만든 판정은 안 담는다**(P15 4.3). 항목 끝의 〔WoRMS …〕 표시는
  `annotate_index.py` 가 붙인 것이고 그 원본은 `names/worms/*.tsv` 와
  `md/name_validity_log.md` 다. **여기 실으면 사본이 두 벌이 된다** — 걷어
  버리고 몇 개였는지만 센다(`marked_entries`). 유효성은 나중에 `TaxonName`
  으로 따로 들어간다
- **빈 것을 채우지 않는다**(P15 9절). 항목 680 은 도판이 없고 동남극 그림 둘은
  깊이가 없다 — `null` 로 둔다. 채우면 추론이 자료가 된다

## 함정

- **Tafel 번호는 열쇠가 아니다**(126 · `schmidt-tafel-not-a-key`). 해설 OCR 이
  번호를 묶음째로 잘못 읽어 114건이 틀려 있었다. **쪽(`pdf_page`)으로 짚는다** —
  `tafel` 은 인용에 적는 값이지 조회 열쇠가 아니다
- **속명이 잘못 펴진 항목이 있다**(119 · 후보 30개가 남았다). 파서는 **안
  고친다** — `genus` 는 색인에 적힌 그대로다. `(속명 추정)` 표시가 있는 것만
  `genus_guess` 로 갈라 담고, **표시가 없는데도 틀린 것이 있다**는 것이
  119 의 요점이다
- **표제어가 곧 종은 아니다.** `sp.`·`group` 은 속까지만 내려간 항목이고
  (`rank: "genus_only"`), 한국 도감에는 `var.`·`subsp.` 가 136건 있다
  (`rank: "infraspecies"`)
- **검산이 없으면 조용히 틀린다.** 색인 머리말이 스스로 적어 둔 수(표제어·출현
  기록·속·그림)와 파싱 결과를 맞춰 보고, **어긋나면 아무것도 안 쓰고 멈춘다.**
  127 에서 번호 검산이 다섯 줄을 살렸다

사용:

    python tools/parse_atlas.py                 # atlas/*.json 으로 뽑는다
    python tools/parse_atlas.py --dry-run       # 안 쓰고 검산만 한다
    python tools/parse_atlas.py --root <경로>   # Diadiction 이 다른 자리에 있을 때
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION, binomial  # noqa: E402
# **표시를 걷는 규칙도 하나뿐이다.** 붙이는 쪽에서 가져다 쓴다 — `〔…〕` 가
# 색인에 둘 있어서다(`tafel_numbering.py` 의 `〔Tafel 아님 …〕`은 색인의 자료다).
# 여기서 `〔[^〕]*〕` 로 새로 짜면 그 자료를 조용히 지운다
from annotate_index import MARK  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "atlas"

# **색인에 없는 자리를 여기서 가져온다** (147). 한국 도감 색인은 자리 표기를
# 넷으로 못박아 두어 **도판이 PDF 몇 쪽인지 적는 칸이 없고**, 481~680 은 쪽
# 이미지로 판독한 구간이라 `PDF p.` 도 안 따라왔다. 색인은 안 고치고
# (인용의 근거다 · P15 4.2) 잰 것을 표로 따로 두었다. 머리말이 근거를 든다
KR_PAGES = OUT / "korean_pages.toml"

INFRA = re.compile(r"\b(var\.|subsp\.|f\.)\s")


def strip_mark(line: str) -> tuple[bool, str]:
    """`annotate_index.py` 가 붙인 〔WoRMS …〕 만 뗀다. (있었나, 뗀 줄)"""
    return bool(MARK.search(line)), MARK.sub("", line).rstrip()


def section(text: str, title: str) -> str:
    """`## 제목` 부터 다음 `## ` 앞까지."""
    rest = text.split(title, 1)[1]
    return rest.split("\n## ", 1)[0]


def head_of(text: str, title: str) -> tuple[str, int]:
    """본문과, 그 본문이 파일의 몇 번째 줄에서 시작하는지."""
    before, body = text.split(title, 1)
    return body, before.count("\n") + 1


# `sp.`·`group` 은 동정을 속까지만 내린 것이다 — 이름이 상한 것과 다르다
GENUS_ONLY = {"sp.", "sp", "spp.", "group"}


def name_fields(headword: str) -> dict:
    """표제어 하나에서 공통 칸을 뽑는다. **표제어 자체는 안 고친다.**

    `rank` 가 넷이다. **`genus_only` 와 `unreadable` 을 가르는 것이 요점이다** —
    앞엣것은 도감이 속까지만 내려간 것이고(`Navicula sp.`), 뒤엣것은 **이름이
    상해서 우리가 못 읽는 것**이다(`Synedra cyclopиm` — 종소명에 키릴 и 가
    섞였다). 한 칸에 담으면 화면이 둘을 같은 말로 하게 되고, 그것이 P15 8.4 가
    갈라 말하라고 한 자리다.
    """
    plain = headword.replace("*", "").strip()
    words = plain.split()
    m = INFRA.search(plain)
    bino = binomial(plain)
    # **수준을 먼저 가른다.** `Rhizosolenia group` 은 `group` 이 종소명 꼴이라
    # 이명법 규칙을 그냥 통과한다 — 색인에서는 `***Rhizosolenia*** group` 처럼
    # 표제어 밖에 있어 `harvest_worms` 가 애초에 안 묻는 이름이다. 여기서
    # 이명법으로 세우면 **없는 종이 하나 생긴다**
    if GENUS_ONLY & set(words[1:]):
        rank, bino = "genus_only", None
    elif bino:
        rank = "infraspecies" if m else "species"
    else:
        rank = "unreadable"
    return {
        "name": plain,
        "genus": words[0] if words else None,
        "binomial": bino,
        "rank": rank,
        "infra": plain[m.start():] if m else None,
    }


def entry(seq: int, line_no: int, headword: str, **kw) -> dict:
    """항목 하나. 도감이 달라도 칸의 모양은 같다 (P15 4.1)."""
    e = {"seq": seq, "item_no": None}
    e.update(name_fields(headword))
    e.update({"authority": None, "genus_guess": False,
              "placements": [], "extra": {}})
    e.update(kw)
    e["line"] = line_no
    return e


def place(plate=None, plate_label=None, figures=None, book_page=None,
          pdf_page=None, pdf_plate_page=None, volume=None, note=None) -> dict:
    """자리 하나. **공통으로 뽑히는 것만 칸으로 둔다** (P15 4.1).

    `note` 는 색인이 그 자리에 달아 둔 주석이다 — Schmidt 21건의
    `〔Tafel 아님 · 권 뒤 Verzeichnis(색인) 쪽에서 왔다〕` 가 여기 온다.
    **`plate` 는 색인에 적힌 그대로 두고** 주석이 그것을 뒤집는다.
    """
    return {"plate": plate, "plate_label": plate_label, "figures": figures,
            "book_page": book_page, "pdf_page": pdf_page,
            "pdf_plate_page": pdf_plate_page, "volume": volume, "note": note}


def num(s: str | None) -> int | None:
    return int(s) if s else None


def figs(s: str | None) -> str | None:
    """그림 번호는 범위·목록이 섞여 원문 그대로 든다 (`11–13` · `1—8` · `4, 6`).

    `fig.. 24,25` 처럼 OCR 부스러기가 앞에 붙은 것만 걷는다.
    """
    if not s:
        return None
    s = s.strip(" .,")
    return s or None


# ─────────────────────────────────────────────────────────── 한국동식물도감

KR_SECT = re.compile(r"^### (.+?)\s*$")
KR_HEAD = re.compile(r"^\*\*(\d+)\.\s*\*(.+?)\*\*\*\s*$")
KR_SUB = re.compile(r"^<sub>(.*?)</sub>\s*$")
KR_BODY = re.compile(r"^- (생태|분포|비고):\s*(.*)$")
KR_FIELD = {"생태": "ecology", "분포": "distribution", "비고": "note"}


def kr_pages() -> dict:
    """`atlas/korean_pages.toml` — 잰 쪽 대응. 없으면 멈춘다."""
    if not KR_PAGES.exists():
        raise SystemExit(f"쪽 대응표가 없다: {KR_PAGES}")
    d = tomllib.loads(KR_PAGES.read_text(encoding="utf-8"))
    return {"offset": d["offset"]["book_minus_pdf"],
            "pages": d["source"]["pages"],
            "plates": {int(k): v for k, v in d["plates"].items()}}


def parse_korean(text: str) -> tuple[list[dict], int]:
    """`**169. *이름***` + `<sub>자리</sub>` + `- 생태/분포/비고:` 세 줄짜리다."""
    pages = kr_pages()
    body, offset = head_of(text, "## 종별 상세")
    entries: list[dict] = []
    sect = None
    marked = 0
    for i, raw in enumerate(body.splitlines(), start=offset):
        m = KR_SECT.match(raw.rstrip())
        if m:
            sect = m.group(1)
            continue
        has_mark, line = strip_mark(raw.rstrip())
        m = KR_HEAD.match(line)
        if m:
            marked += has_mark
            e = entry(len(entries) + 1, i, m.group(2), item_no=m.group(1))
            if sect:
                e["extra"]["section"] = sect
            entries.append(e)
            continue
        if not entries:
            continue
        m = KR_SUB.match(line)
        if m:
            p = place()
            for tok in (t.strip() for t in m.group(1).split("·")):
                if tok.startswith("pl."):
                    p["plate"] = num(tok[3:].strip())
                elif tok.startswith("책 p."):
                    p["book_page"] = num(tok[4:].strip())
                elif tok.startswith("PDF p."):
                    p["pdf_page"] = num(tok[6:].strip())
            # **색인에 없는 둘을 여기서 채운다** (147 · `korean_pages.toml`).
            # `pdf_page` 는 **잰 옵셋**이지 짐작이 아니다 — 도판이 책 쪽번호를
            # 함께 먹어서 옵셋이 도판을 지나도 안 밀린다(표 머리말에 근거).
            # **색인이 적어 온 값은 안 덮는다** — 어긋나면 `check` 가 말한다
            # **발췌본 밖으로 나가면 안 채운다** — 항목 680 이 그 자리다.
            # 책 p.370 인데 발췌본이 369(PDF 270)에서 끝나 그 설명이 안 실려
            # 있다. 셈만 하면 PDF 271 이 나오는데 **그런 쪽은 없다.**
            # 빈 것을 채우지 않는다(P15 9절 · `AtlasPlacement` 머리말)
            if p["pdf_page"] is None and p["book_page"] is not None:
                n = p["book_page"] - pages["offset"]
                if 1 <= n <= pages["pages"]:
                    p["pdf_page"] = n
            if p["plate"] is not None:
                p["pdf_plate_page"] = pages["plates"].get(p["plate"])
            entries[-1]["placements"].append(p)
            continue
        m = KR_BODY.match(line)
        if m:
            entries[-1]["extra"][KR_FIELD[m.group(1)]] = m.group(2).strip()
    return entries, marked


# ────────────────────────────────────────────────────────── Schmidt Atlas

SC_HEAD = re.compile(
    r"^- \*\*\*(.+?)\*\*\*(\s*\*\(속명 추정\)\*)?\s*—\s*(.+?)\s*$")
SC_OCC = re.compile(
    r"^Tafel\s+(\d+)(?:\s*fig\.(.*?))?\s*\(Band(\d+)\s*PDF\s*p\.(\d+)/(\d+)\)$")
# 색인이 인용에 직접 단 주석. **`annotate_index` 의 표시와 다른 것이다** — 이쪽은
# 색인의 자료라 버리지 않고 그 자리에 싣는다 (`tafel_numbering.py` · 121)
SC_NOTE = re.compile(r"\s*〔(Tafel 아님[^〕]*)〕\s*")


def parse_schmidt(text: str) -> tuple[list[dict], int]:
    """한 줄에 표제어와 자리가 다 있다. 자리가 여럿이면 `;` 로 잇는다."""
    body, offset = head_of(text, "## 학명 색인 (알파벳순)")
    entries: list[dict] = []
    marked = 0
    for i, raw in enumerate(body.splitlines(), start=offset):
        has_mark, line = strip_mark(raw.rstrip())
        m = SC_HEAD.match(line)
        if not m:
            continue
        marked += has_mark
        e = entry(len(entries) + 1, i, m.group(1),
                  genus_guess=bool(m.group(2)))
        for occ in m.group(3).split(";"):
            occ = occ.strip()
            note = None
            if nm := SC_NOTE.search(occ):
                note, occ = nm.group(1), SC_NOTE.sub("", occ).strip()
            om = SC_OCC.match(occ)
            if not om:
                e["extra"].setdefault("unparsed", []).append(occ)
                continue
            e["placements"].append(place(
                plate=num(om.group(1)), figures=figs(om.group(2)),
                volume=f"Band{om.group(3)}", note=note,
                pdf_page=num(om.group(4)), pdf_plate_page=num(om.group(5))))
        entries.append(e)
    return entries, marked


# ─────────────────────────────────────────────────────── 동남극 도판집

EA_HEAD = re.compile(r"^\*\*\*(.+?)\*\*\*\s*(.*?)\s*$")
EA_SUB = re.compile(r"^<sub>(.*?)</sub>\s*$")
EA_PLACE = re.compile(r"^(?:pl\.\s*(\d+)|(SEM))(?:\s*fig\.\s*(.+))?$")
EA_PDF = re.compile(r"^PDF p\.(\d+)/(\d+)$")
EA_NOTE = re.compile(r"^- 원문 표기:\s*(.*)$")
EA_LEAD = re.compile(r"^-\s*(?:pl\.(\d+)|(SEM))\s*—\s*(.+)$")
EA_FIG = re.compile(r"^(\d+)\.\s*(.+)$")
EA_SEC = re.compile(r"sec\.([\d-]+),\s*([\d.]+)\s*cm")
EA_MAG = re.compile(r"×\s*([\d,]*\d)")   # `×1800, bar …` 의 쉼표를 물지 않는다


def parse_east(text: str) -> tuple[list[dict], int]:
    """표제어 · `<sub>자리</sub>` · 그림마다의 시료(구간·깊이 cm)."""
    body = section(text, "## 학명별 색인 (알파벳순)")
    offset = text[:text.index("## 학명별 색인 (알파벳순)")].count("\n") + 1
    entries: list[dict] = []
    marked = 0
    for i, raw in enumerate(body.splitlines(), start=offset):
        has_mark, line = strip_mark(raw.rstrip())
        if line.startswith("***"):
            m = EA_HEAD.match(line)
            marked += has_mark
            tail = m.group(2).strip()
            # `sp.`·`group`·`(?) sp.` 는 저자가 아니라 동정 수준이다
            head = m.group(1) + (" " + tail if tail.startswith(("sp.", "group", "(?)")) else "")
            e = entry(len(entries) + 1, i, head)
            if tail and not tail.startswith(("sp.", "group", "(?)")):
                e["authority"] = tail
            entries.append(e)
            continue
        if not entries:
            continue
        m = EA_SUB.match(line)
        if m:
            for tok in (t.strip() for t in m.group(1).split("·")):
                pm = EA_PLACE.match(tok)
                if pm:
                    entries[-1]["placements"].append(place(
                        plate=num(pm.group(1)),
                        plate_label=pm.group(2), figures=figs(pm.group(3))))
                    continue
                dm = EA_PDF.match(tok)
                if dm and entries[-1]["placements"]:
                    entries[-1]["placements"][-1]["pdf_page"] = num(dm.group(1))
                    entries[-1]["placements"][-1]["pdf_plate_page"] = num(dm.group(2))
            continue
        m = EA_NOTE.match(line)
        if m:
            entries[-1]["extra"]["original_note"] = m.group(1).strip()
            continue
        if line.startswith("- "):
            m = EA_LEAD.match(line)
            plate, label, rest = (num(m.group(1)), m.group(2), m.group(3)) if m \
                else (None, None, line[2:])
            # 시료 줄은 `- 11. sec…` 이나 `- pl.5 — 1. sec…` 이다. 그 모양이
            # 아닌 것은 색인이 손으로 적은 비고다 (크롭 있음 · 원문 단서 …)
            if not m and not EA_FIG.match(rest.strip()):
                entries[-1]["extra"].setdefault("notes", []).append(rest.strip())
                continue
            for tok in (t.strip() for t in rest.split("·")):
                fm = EA_FIG.match(tok)
                if not fm:
                    entries[-1]["extra"].setdefault("unparsed", []).append(tok)
                    continue
                sm = EA_SEC.search(fm.group(2))
                mm = EA_MAG.search(fm.group(2))
                entries[-1]["extra"].setdefault("samples", []).append({
                    "plate": plate, "plate_label": label,
                    "figure": int(fm.group(1)),
                    # 깊이가 빠진 그림 둘은 **빈 채로 둔다** (P15 9절)
                    "section": sm.group(1) if sm else None,
                    "depth_cm": float(sm.group(2)) if sm else None,
                    "magnification": mm.group(1) if mm else None,
                    "raw": fm.group(2).strip(),
                })
    return entries, marked


# ───────────────────────────────────────────────────────────── 도감 셋

# 도감 코드. **JSON 이름·`/data3/DiaRUGA/atlas/<코드>/` 의 이미지 폴더·
# `Atlas.key` 가 전부 이 값이다** — 화면 쪽(129)과 맞춘 것이라 함부로 안 바꾼다.
ATLASES = [
    {
        "key": "korean",
        "title": "한국동식물도감 제9권(담수조류) — 규조강",
        "short": "한국 도감",
        "source": "md/korean_flora_diatom_index.md",
        "parse": parse_korean,
        "genus_section": "## 속(屬)별 빠른 색인",
        "body": "## 종별 상세",
        "raw": {"표제어": r"^\*\*\d+\.", "자리": r"^<sub>"},
        "note": "종 169–480 은 PDF 텍스트 레이어에서, 481–679 는 쪽 이미지 판독으로 "
                "뽑았다. 169–480 구간은 한자가 깨져 있어 생태·분포를 그대로 인용하지 않는다.",
    },
    {
        "key": "schmidt",
        "title": "A. Schmidt, Atlas der Diatomaceenkunde (1874–1959)",
        "short": "Schmidt Atlas",
        "source": "md/schmidt_atlas_name_index.md",
        "parse": parse_schmidt,
        "genus_section": "## 속별 종 수",
        "body": "## 학명 색인 (알파벳순)",
        "raw": {"표제어": r"^- \*\*\*", "자리": r"\(Band\d+ PDF p\."},
        # **머리말의 "출현 기록 1968건" 이 색인 본문과 안 맞는다** (128 에서 확인).
        # 본문의 인용 조각은 1911 이고, 121 이전 사본(`names/index_backup_20260814/`)
        # 도 1911 이라 **117 이 색인을 만들 때부터 안 맞았다** — 121 의 Tafel 고침이
        # 떨어뜨린 것이 아니다. 아래 수로 검산하고, 색인을 다시 만들면 여기부터 본다
        "stated_override": {"출현 기록": 1911},
        "note": "전량 OCR 이다. 속명은 원문의 머리글자 축약을 편 것이라 "
                "잘못 펴진 자리가 있고(119), 그중에는 `(속명 추정)` 표시가 없는 것도 있다. "
                "**Tafel 번호가 아니라 `pdf_page` 로 짚는다**(126).",
    },
    {
        "key": "east-antarctic",
        "title": "플라이스토세 중기 이후 동남극 규조 (도판집)",
        "short": "동남극 도판집",
        "source": "md/east_antarctic_plates_index.md",
        "parse": parse_east,
        "genus_section": "## 속별 빠른 색인",
        "body": "## 학명별 색인 (알파벳순)",
        "raw": {"표제어": r"^\*\*\*", "자리": r"PDF p\.\d+/\d+"},
        "note": "본문 없이 도판·학명·시료 위치만 실린 발췌본이다. PDF 에 텍스트 "
                "레이어가 없어 300 dpi 렌더를 사람이 판독해 만들었고, 원문 오류 11건은 "
                "색인이 원문 표기를 함께 든다.",
    },
]

GENUS_ROW = re.compile(r"^- \*\*([A-Za-zÀ-ÿ]+)\*\*\s*(?:\((\d+)\)|—\s*(\d+))")


def genus_table(text: str, title: str) -> dict[str, int]:
    """색인이 스스로 세어 놓은 속별 항목 수. 검산의 근거다."""
    out = {}
    for line in section(text, title).splitlines():
        m = GENUS_ROW.match(line.rstrip())
        if m:
            out[m.group(1)] = int(m.group(2) or m.group(3))
    return out


def stated(text: str) -> dict[str, int]:
    """색인 머리말이 스스로 적어 둔 수."""
    out = {}
    if m := re.search(r"총\s*(\d+)\s*항목", text):
        out["표제어"] = int(m.group(1))
    if m := re.search(r"고유 학명\s*(\d+)개", text):
        out["표제어"] = int(m.group(1))
    if m := re.search(r"출현 기록\s*(\d+)건", text):
        out["출현 기록"] = int(m.group(1))
    if m := re.search(r"속\s*(\d+)개", text):
        out["속"] = int(m.group(1))
    if m := re.search(r"그림\s*(\d+)개", text):
        out["그림"] = int(m.group(1))
    return out


def check(spec: dict, text: str, entries: list[dict]) -> list[str]:
    """검산 셋. **하나라도 어긋나면 아무것도 안 쓴다.**

    1. **파일에서 직접 센 것과 맞는가** — 파서를 안 거치는 셈이라 파서가 줄을
       통째로 건너뛰면 여기서 걸린다. 머리말이 낡아도 이 검산은 안 낡는다
    2. **머리말이 스스로 적어 둔 수와 맞는가** — 색인을 만든 쪽의 셈이다
    3. **속별 목록과 맞는가** — 속은 `ClassDef` 와 잇는 열쇠 층이다 (P15 8.2)
    """
    bad = []
    body = section(text, spec["body"])
    for k, pat in spec["raw"].items():
        n = len(re.findall(pat, body, re.M))
        got = len(entries) if k == "표제어" else \
            sum(len(e["placements"]) for e in entries)
        if got != n:
            bad.append(f"{k}: 파일에는 {n} 인데 파서는 {got}")
    want = stated(text) | spec.get("stated_override", {})
    got = {
        "표제어": len(entries),
        "출현 기록": sum(len(e["placements"]) for e in entries),
        "속": len({e["genus"] for e in entries}),
        "그림": sum(len(e["extra"].get("samples", [])) for e in entries),
    }
    for k, n in want.items():
        if got[k] != n:
            bad.append(f"{k}: 색인은 {n} 인데 파서는 {got[k]}")

    counts: dict[str, int] = {}
    for e in entries:
        counts[e["genus"]] = counts.get(e["genus"], 0) + 1
    table = genus_table(text, spec["genus_section"])
    for g, n in sorted(table.items()):
        if counts.get(g, 0) != n:
            bad.append(f"속 {g}: 색인은 {n} 인데 파서는 {counts.get(g, 0)}")
    for g in sorted(set(counts) - set(table)):
        bad.append(f"속 {g}: 색인의 속 목록에 없다 ({counts[g]}건)")

    for e in entries:
        if e["extra"].get("unparsed"):
            bad.append(f"#{e['seq']} {e['name']}: 못 읽은 자리 {e['extra']['unparsed']}")
        if not e["placements"] and e["seq"] != len(entries):
            bad.append(f"#{e['seq']} {e['name']}: 자리가 하나도 없다")
    if spec["key"] == "korean":
        bad += check_korean(entries)
    return bad


def check_korean(entries: list[dict]) -> list[str]:
    """쪽 대응표가 아직 맞는가 (147).

    표는 사람이 재서 커밋한 것이고 색인은 따로 바뀐다. **둘이 어긋나는 날이
    오는데 그날 조용하면 안 된다** — 화면이 엉뚱한 쪽을 열어도 예외가 안 난다.
    그래서 돌 때마다 셋을 다시 본다.

    1. **번호가 PDF 차례대로 오르는가** — 도판 번호를 하나 잘못 읽으면 여기서
       걸린다. `Tafel` 114건이 틀렸던 자리가 그 꼴이다(126 · 119)
    2. **색인이 부르는 도판이 표에 다 있는가**
    3. **색인이 적어 온 `PDF p.` 가 잰 옵셋과 맞는가** — 어긋나면 색인의
       `책 p.` 나 `PDF p.` 둘 중 하나가 틀린 것이다. 지금 둘 알고 있다
       (#238 · #424 · 표의 `[[typo]]`). **고치지 않고 말만 한다**
    """
    pages = kr_pages()
    bad = []
    nums = sorted(pages["plates"])
    if [pages["plates"][n] for n in nums] != sorted(pages["plates"][n] for n in nums):
        bad.append("쪽 대응표: 도판 번호와 PDF 쪽의 차례가 어긋난다")
    for n in range(nums[0], nums[-1] + 1):
        if n not in pages["plates"]:
            bad.append(f"쪽 대응표: Plate {n} 이 빠져 있다")
    off, known = pages["offset"], {238, 424}
    for e in entries:
        for p in e["placements"]:
            if p["plate"] is not None and p["plate"] not in pages["plates"]:
                bad.append(f"#{e['item_no']}: Plate {p['plate']} 이 쪽 대응표에 없다")
            if p["pdf_page"] is not None and not 1 <= p["pdf_page"] <= pages["pages"]:
                bad.append(f"#{e['item_no']}: PDF p.{p['pdf_page']} 는 "
                           f"발췌본 {pages['pages']}쪽 밖이다")
            if p["book_page"] is None or p["pdf_page"] is None:
                continue
            if p["book_page"] - p["pdf_page"] != off and int(e["item_no"]) not in known:
                bad.append(f"#{e['item_no']}: 책 p.{p['book_page']} · "
                           f"PDF p.{p['pdf_page']} 가 옵셋 {off} 과 안 맞는다")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DIADICTION, help="Diadiction 폴더")
    ap.add_argument("--out", type=Path, default=OUT, help="JSON 을 쓸 자리")
    ap.add_argument("--dry-run", action="store_true", help="안 쓰고 검산만 한다")
    args = ap.parse_args()

    if not args.root.exists():
        print(f"Diadiction 을 못 찾는다: {args.root}\n"
              f"  NAS 공유가 안 붙었을 수 있다 — 이 단계는 호스트에서 돈다 (P15 7절)",
              file=sys.stderr)
        return 2

    failed = False
    for order, spec in enumerate(ATLASES):
        path = args.root / spec["source"]
        text = path.read_text(encoding="utf-8")
        entries, marked = spec["parse"](text)
        bad = check(spec, text, entries)
        print(f"\n{spec['short']} — 표제어 {len(entries)} · "
              f"자리 {sum(len(e['placements']) for e in entries)} · "
              f"속 {len({e['genus'] for e in entries})} · 표시 {marked}")
        for b in bad:
            print(f"  ✗ {b}")
        if bad:
            failed = True
            continue
        print("  ✓ 색인이 스스로 말하는 수와 맞는다")
        if spec["key"] == "korean":
            ps = [p for e in entries for p in e["placements"]]
            print(f"  · 쪽 대응표로 채운 것 — 도판 쪽 "
                  f"{sum(1 for p in ps if p['pdf_plate_page'])}/{len(ps)} · "
                  f"해설 쪽 {sum(1 for p in ps if p['pdf_page'])}/{len(ps)}")
        if args.dry_run:
            continue
        args.out.mkdir(parents=True, exist_ok=True)
        doc = {
            "atlas": {
                "key": spec["key"], "title": spec["title"], "short": spec["short"],
                "source": spec["source"],
                "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "entry_count": len(entries),
                # 화면에 놓이는 차례. **파일 이름 정렬을 안 타게 값으로 든다** —
                # 127 이 겪은 것이 그 모양이다(`day10` 이 `day7` 보다 앞이었다)
                "sort_order": order,
                # 걷어 버린 〔…〕 표시가 몇 개였나. **판정은 안 담는다** (머리말)
                "marked_entries": marked,
                "note": spec["note"],
            },
            "entries": entries,
        }
        out = args.out / f"{spec['key']}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        print(f"  → {out} ({out.stat().st_size // 1024} KB)")

    if failed:
        print("\n검산이 어긋났다 — 아무것도 안 썼다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
