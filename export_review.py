#!/usr/bin/env python3
"""사람의 교정을 `review/` 로 내보낸다 — git 에 남길 감사 기록 (P02 5단계 · P06).

    python export_review.py                        # 저장소 review/ 로
    python export_review.py --check                # 파일 ↔ DB 대조 (안 쓴다)
    python export_review.py --slide 260731_am22-gc10b_25cm
    python export_review.py --db backup/DiaRUGA_20260804_114433.db --out /tmp/before

교정(삭제·되살림·분류·코멘트 6,700여 건)은 사람이 시야를 하나씩 보며 만든 것이고
**다시 만들 수 없다.** 지금 안전망은 `backup_db.py` 하나인데, 백업은 "몇 행이었나"
는 알려 주지만 **"무엇이 달라졌나" 는 못 알려 준다** — 027 을 알아챈 것도 숫자였지
내용이 아니었다. 이 스크립트가 그 자리를 맡는다.

세 가지를 다 해야 한다. 하나라도 빠지면 다른 물건이 된다.

1. **감사 기록** — git 에 남아 `diff` 로 언제 무엇이 달라졌는지 보인다
2. **안전망** — DB 가 상해도 사람의 판단을 되살릴 수 있다
3. **대조 도구** — 두 시점(백업 파일 포함)의 교정을 견줄 수 있다

## Django 를 임포트하지 않는다

`backup_db.py` 와 같은 자리다. 규약("DB 는 컨테이너 문 하나로만")이 막으려는 것은
**같은 파일을 두 벌의 환경이 만지는 것**인데, 여기는 Django 를 안 쓰고 원본을
**읽기 전용**으로만 열어서 그 상황이 성립하지 않는다.

그래서 얻는 것이 셋이다.

- **저장소에 바로 쓴다.** 컨테이너는 `/srv/DiaRUGA/db` 와 `/data3` 만 물고
  저장소를 안 문다. 내보낸 뒤 사람이 옮겨야 하는 감사 기록은 아무도 안 돌린다
- **`models.py` 가 흔들려도 돈다.** 감사 기록이 코드 판에 매이면 안 된다 —
  특히 `Image` 정규화(P06 2~5단계)로 **스키마가 바뀌는 동안에도 같은 도구로
  견줘야 한다**
- **백업 파일을 그대로 읽는다.** 두 시점을 견주는 일이 이것 하나로 된다

## 파일 이름은 `(슬라이드, 시야 번호)` 다

예전 형식은 `review/<stem>_review.json` 이었다. **쓸 수 없다** — 싱글턴 시야는
stem 이 곧 프레임 이름이고 **프레임 이름은 슬라이드끼리 겹친다**(143종). 053 에서
저장이 남의 시야로 가던 것과 같은 원인이고, 여기서는 **파일이 서로를 덮어쓰는**
모습으로 나타난다.

`(슬라이드 슬러그, 시야 번호)` 는 겹치지 않는다 — `Viewpoint` 에 `(slide, idx)`
유일 제약이 있고, 주소(`/d/<slug>/g/<n>/`)와도 같은 열쇠다.

## `geom` 을 반드시 넣는다

`removed`·`accepted` 만 있던 옛 형식으로는 **되살릴 수 없다.** 키(`mask_key`)는
bbox 문자열이라 검출이 바뀌면 안 맞고, 그때 다시 붙이는 근거가 `geom` 이다.
**`geom` 이 빠진 내보내기는 감사 기록이지 안전망이 아니다.** 크기는 문제가 안
된다 — 6,732행에 1.4 MB 다(폴리곤이 `approxPolyDP` 로 단순화돼 점이 10~20개).

## diff 가 읽히게 쓴다

감사 기록의 값은 `git diff` 가 읽히는가에 달렸다. **개체 하나가 한 줄**이라야
"이 개체의 분류가 바뀌었다" 가 한 줄로 보인다. `mask_key` 로 정렬하고(dict 순서가
아니라), 한글 코멘트가 그대로 보이게 `ensure_ascii=False` 로 쓴다.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _env(key, default):
    """환경변수 → `.env` → 기본값.

    `backup_db.py` 에도 같은 것이 있다. 일부러 나눠 뒀다 — 두 스크립트 다
    **다른 것이 전부 망가졌을 때 쓰는 물건**이라 혼자 돌아야 한다.
    """
    if key in os.environ:
        return os.environ[key]
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    except OSError:
        pass
    return default


DB = Path(_env("DIARUGA_DB", str(ROOT / "DiaRUGA.db")))
OUT = ROOT / "review"

# 내보내는 형식의 판. **올릴 때는 읽는 쪽을 함께 본다** — 감사 기록이라
# 옛 파일이 계속 남아 있고, 판이 없으면 어느 형식인지 알 수 없다.
FORMAT = 2


def connect(path: Path) -> sqlite3.Connection:
    """**읽기 전용으로만 연다.** `immutable=1` 은 주지 않는다 — 운영 DB 는 WAL 로
    계속 쓰이고 있어서, 그렇게 열면 `-wal` 에 있는 최근 쓰기를 못 본다.
    """
    if not path.exists():
        sys.exit(f"DB 가 없다: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch(conn, slide_slug=None) -> dict:
    """시야마다의 교정을 `{(슬러그, idx): payload}` 로.

    한 번의 질의로 다 읽어 파이썬에서 묶는다. 시야 452개에 교정 6,732행이라
    시야마다 질의를 던질 이유가 없다.
    """
    where, args = "", []
    if slide_slug:
        where = "WHERE s.slug = ?"
        args = [slide_slug]

    views = {}
    for r in conn.execute(f"""
        SELECT v.id, v.idx, v.tag, s.slug
          FROM viewer_viewpoint v JOIN viewer_slide s ON s.id = v.slide_id
          {where}
    """, args):
        views[r["id"]] = {"slide": r["slug"], "gid": r["idx"], "tag": r["tag"],
                          "done": False, "note": "", "objects": [],
                          # 이 시야의 교정이 걸쳐 있는 이미지들. 아래에서 센다.
                          "images": set()}

    for r in conn.execute("SELECT viewpoint_id, done, note FROM viewer_viewpointreview"):
        v = views.get(r["viewpoint_id"])
        if v is not None:
            v["done"] = bool(r["done"])
            v["note"] = r["note"] or ""

    # `image_id` 는 P06 2단계(0019)에서, `batch_id`·`source`·`geom_edited` 는
    # P09 0단계(0025)에서 생겼다. **옛 DB(백업 파일)에는 없다** — 이 스크립트는
    # 두 시점을 견주는 도구라 옛 판도 읽어야 한다.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(viewer_objectreview)")}

    def col(name, default="NULL"):
        return name if name in cols else f"{default} AS {name}"

    img_col = col("image_id")
    batch_col = col("batch_id")
    src_col = col("source", "'engine'")
    edit_col = col("geom_edited", "0")

    # **묶음은 id 가 아니라 이름으로 적는다.** 감사 기록은 사람이 읽고 두 DB 를
    # 견주는 물건이라, 저장소마다 달라지는 id 를 적으면 diff 가 거짓말을 한다.
    batch_name = {}
    if "batch_id" in cols:
        try:
            batch_name = {r[0]: r[1] for r in
                          conn.execute("SELECT id, label FROM viewer_runbatch")}
        except sqlite3.Error:
            pass

    for r in conn.execute(f"""
        SELECT viewpoint_id, mask_key, removed, accepted, label, note,
               geom, bind_method, bind_score, {img_col}, {batch_col},
               {src_col}, {edit_col}
          FROM viewer_objectreview
    """):
        v = views.get(r["viewpoint_id"])
        if v is None:
            continue
        # **키가 먼저 오게 짓는다.** 한 줄로 쓰므로 줄 앞머리가 무엇에 대한
        # 기록인지를 바로 말해야 diff 가 읽힌다.
        obj = {
            "key": r["mask_key"],
            # **어느 검출을 보고 한 판단인가** (P09 5.1). 키의 일부다.
            # 사람이 그린 개체는 어느 묶음에도 안 속해 빈 문자열이 온다.
            "batch": batch_name.get(r["batch_id"], "") if r["batch_id"] else "",
            "removed": bool(r["removed"]),
            "accepted": bool(r["accepted"]),
            "label": r["label"] or "",
            "note": r["note"] or "",
            "bind": r["bind_method"] or "",
        }
        if (r["source"] or "engine") != "engine":
            obj["source"] = r["source"]
        if r["geom_edited"]:
            obj["geom_edited"] = True
        if r["bind_score"] is not None:
            obj["bind_score"] = round(r["bind_score"], 4)
        # 기하는 마지막이다 — 길고, 사람이 눈으로 읽는 것이 아니다.
        try:
            obj["geom"] = json.loads(r["geom"]) if r["geom"] else {}
        except (TypeError, ValueError):
            obj["geom"] = {}
        v["objects"].append(obj)
        # **열쇠가 `(image, batch, mask_key)` 라 짝으로 센다** (P09 5.1).
        # 이미지가 하나여도 묶음이 둘이면 format 2 는 같은 병을 앓는다 —
        # 파일 하나 안에서 `key` 가 겹치고 어느 검출의 판단인지 사라진다.
        v["images"].add((r["image_id"], r["batch_id"]))

    # **표시가 하나도 없는 시야는 내보내지 않는다.** 452개 중 432개만 자료가
    # 있는데, 빈 파일 20개를 두면 "아직 안 본 것" 과 "봤는데 고칠 게 없던 것" 이
    # 파일 있음/없음으로 구분되지 않는다. 후자는 `done` 이 켜져 있다.
    out, spread = {}, []
    for v in views.values():
        if not v["objects"] and not v["done"] and not v["note"]:
            continue
        if len(v["images"]) > 1:
            spread.append((v["slide"], v["gid"], len(v["images"])))
        v["objects"].sort(key=lambda o: o["key"])
        out[(v["slide"], v["gid"])] = v

    # **format 2 는 시야 하나에 `(이미지, 묶음)` 하나를 전제한다.** 프레임별
    # 검토를 쓰거나 **묶음을 갈아타면** 그 전제가 깨지고, 이 형식은 **조용히
    # 못 쓰게 된다**:
    #
    #   - 파일 하나 안에서 `key` 가 겹친다 (mask_key 가 프레임끼리 45% 겹치고,
    #     묶음이 둘이면 같은 개체에 판단이 둘이다)
    #   - 어느 이미지·어느 검출을 보고 한 판단인지 안 남는다 → 되살릴 수 없다
    #   - `done`·`note` 가 시야당 하나라 이미지별 검토 완료를 못 담는다
    #
    # `batch` 칸을 개체마다 적는 것은 **이름을 남기는 것**이지 이 전제를 푸는
    # 것이 아니다. 푸는 것은 형식 3 이다.
    #
    # 셋 다 **예외 없이 그럴듯한 파일이 나오는** 종류라 여기서 세워야 한다.
    # 형식을 올릴 때(2 → 3) 이 검사도 함께 걷는다.
    if spread:
        head = ", ".join(f"{s} g{g}({n}개)" for s, g, n in spread[:5])
        sys.exit(
            f"교정이 (이미지, 묶음) 여럿에 걸친 시야가 {len(spread)}개다: {head}\n"
            "  format 2 는 시야 하나에 그 짝 하나를 전제한다 — 그대로 쓰면\n"
            "  한 파일 안에서 key 가 겹치고 어느 검출의 판단인지 사라진다.\n"
            "  형식을 3 으로 올려야 한다 (P06 5단계 · P09 1단계).")
    return out


def render(v: dict) -> str:
    """개체 하나가 한 줄인 JSON. `json.dumps(indent=…)` 로는 안 된다 —
    폴리곤 좌표까지 한 줄씩 쪼개져 개체 하나가 40줄이 된다.
    """
    head = {"format": FORMAT, "slide": v["slide"], "gid": v["gid"],
            "tag": v["tag"], "done": v["done"], "note": v["note"],
            "n_objects": len(v["objects"])}
    lines = ["{"]
    for k, val in head.items():
        lines.append(f"  {json.dumps(k)}: {json.dumps(val, ensure_ascii=False)},")
    lines.append('  "objects": [')
    for i, o in enumerate(v["objects"]):
        comma = "" if i == len(v["objects"]) - 1 else ","
        lines.append("    " + json.dumps(o, ensure_ascii=False,
                                         separators=(", ", ": ")) + comma)
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def path_for(out_dir: Path, slug: str, gid: int) -> Path:
    return out_dir / slug / f"g{gid:03d}.json"


def main():
    ap = argparse.ArgumentParser(description="교정을 review/ 로 내보낸다")
    ap.add_argument("--db", default=str(DB), help=f"기본 {DB}")
    ap.add_argument("--out", default=str(OUT), help=f"기본 {OUT}")
    ap.add_argument("--slide", help="슬라이드 슬러그 하나만")
    ap.add_argument("--check", action="store_true",
                    help="쓰지 않고 파일과 DB 를 대조한다")
    args = ap.parse_args()

    out_dir = Path(args.out)
    conn = connect(Path(args.db))
    try:
        views = fetch(conn, args.slide)
    finally:
        conn.close()

    n_obj = sum(len(v["objects"]) for v in views.values())
    print(f"{args.db}\n  시야 {len(views)} · 교정 {n_obj}")

    want = {path_for(out_dir, slug, gid): render(v)
            for (slug, gid), v in views.items()}

    # 지금 있는 파일. **슬라이드 하나만 볼 때는 그 아래만 본다** — 안 그러면
    # 나머지 슬라이드의 파일이 전부 "남는 것" 으로 잡힌다.
    #
    # **`<슬라이드>/g*.json` 만 본다.** `rglob` 로 훑으면 옛 평면 형식
    # (`review/g000_…_focused_review.json`)까지 걸리는데, 그 이름이 `g` 로
    # 시작하는 것은 우연이다. 우연에 기대 지우면 형식을 또 바꿀 때 조용히
    # 다르게 군다 — 옛것은 아래에서 이름으로 따로 처리한다.
    slides = [out_dir / args.slide] if args.slide else \
        [d for d in sorted(out_dir.glob("*")) if d.is_dir()]
    have = {p for d in slides if d.exists() for p in d.glob("g*.json")}

    # 옛 평면 형식. stem 이 슬라이드끼리 겹쳐 파일이 서로를 덮어쓰므로 버렸다
    # (머리말). 새 형식과 섞여 있으면 어느 쪽이 진짜인지 알 수 없다.
    legacy = sorted(out_dir.glob("*_review.json")) if not args.slide else []

    added = [p for p in want if p not in have]
    gone = sorted(have - set(want))
    changed, same = [], 0
    for p in sorted(set(want) & have):
        if p.read_text(encoding="utf-8") == want[p]:
            same += 1
        else:
            changed.append(p)

    def rel(p):
        try:
            return p.relative_to(out_dir)
        except ValueError:
            return p

    if args.check:
        # **대조는 아무것도 쓰지 않는다.** 이것이 P06 2~5단계의 안전장치다 —
        # 마이그레이션 전후로 돌려 같은지 본다.
        for label, items in (("새로 생김", sorted(added)), ("달라짐", changed),
                             ("파일만 남음", gone), ("옛 형식", legacy)):
            for p in items[:20]:
                print(f"  {label}: {rel(p)}")
            if len(items) > 20:
                print(f"  {label}: … 외 {len(items) - 20}개")
        ok = not (added or changed or gone or legacy)
        print(f"  같음 {same} · 새로 생김 {len(added)} · 달라짐 {len(changed)} "
              f"· 파일만 남음 {len(gone)} · 옛 형식 {len(legacy)}")
        print("대조 통과 — 다른 것 없음" if ok else "대조 실패 — 위를 볼 것")
        return 0 if ok else 1

    for p, text in want.items():
        if p in have and p.read_text(encoding="utf-8") == text:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    # **DB 에 없는 시야의 파일은 지운다.** 남겨 두면 "지금 DB 의 모습" 이 아니라
    # "언젠가 있었던 것들의 합집합" 이 되어 감사 기록으로 못 쓴다. 지운 것은
    # git 이 기억한다.
    for p in gone + legacy:
        p.unlink()
    for d in sorted({p.parent for p in gone}):
        if d.exists() and not any(d.iterdir()):
            d.rmdir()

    print(f"  그대로 {same} · 새로 씀 {len(added)} · 고쳐 씀 {len(changed)} "
          f"· 지움 {len(gone)}"
          + (f" · 옛 형식 걷음 {len(legacy)}" if legacy else ""))
    print(f"  -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
