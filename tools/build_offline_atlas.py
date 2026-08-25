#!/usr/bin/env python3
"""도감 색인·도판·학명 대조표를 **오프라인 꾸러미**로 굽는다 (156).

서버도 인터넷도 없는 자리에서 `index.html` 하나를 브라우저로 열면 도감 색인
2,059항목을 찾고, 도판 1,336쪽을 넘겨 보고, 학명 대조표를 뒤질 수 있다.

## 왜 이 모양인가

- **`fetch` 를 안 쓴다.** `file://` 에서는 브라우저가 로컬 파일을 다른 출처로 봐
  JSON 을 못 읽는다. 그래서 자료가 `data/*.js` 로 나가 전역에 값을 놓는다 —
  웹서버 없이 열리는 것이 이 꾸러미의 존재 이유라 여기서 물러설 수 없다
- **한 파일에 다 담지 않는다.** 도판이 1.1 GB 라 base64 로 넣으면 1.5 GB 짜리
  문서가 되고 브라우저가 파싱하다 죽는다. `index.html` 이 옆 폴더를 참조하고,
  들고 다닐 때는 폴더째(또는 zip 하나) 옮긴다. 도판이 필요 없으면
  `--text-only-file` 이 내는 **진짜 단일 HTML**(2.5 MB)을 쓴다
- **이름 규칙을 다시 만들지 않는다.** 쪽 파일 이름과 권 코드는
  `web/viewer/atlas.py` 하나뿐이라 그것을 임포트해서 쓴다 (`vol_code` 머리말) —
  여기서 `.lower()` 를 한 번 더 쓰면 넷째 도감에서 갈린다
- **PNG 를 그대로 안 싣는다.** 2.4 GB 다. 300 dpi 를 지키면서 JPEG 로만 바꿔
  1.1 GB 가 된다 — 해상도를 줄이면 Schmidt 도판의 세선이 뭉갠다

## 자료가 어디서 오나

    atlas/*.json                     색인 셋 (저장소 · `tools/parse_atlas.py` 산물)
    /data3/DiaRUGA/atlas/            쪽 PNG (`tools/render_atlas_pages.py` 산물)
    …/names/worms/worms_master_*.tsv 학명 대조표 (WoRMS·AlgaeBase)

**DB 를 안 본다.** 셋 다 파일이고, 운영 DB 를 여는 것은 그 자체가 함정이다
(CLAUDE.md · 132). 색인 JSON 은 `ops/import_atlas.py` 가 DB 에 넣는 것과 같은
파일이라 화면에 뜨는 것과 같은 자료다.

사용:

    python tools/build_offline_atlas.py --version 1.0.0
    python tools/build_offline_atlas.py --version 1.0.0 --limit 12   # 눌러 보기
    python tools/build_offline_atlas.py --version 1.0.0 --no-images  # 글자만
    python tools/build_offline_atlas.py --version 1.0.0 --force      # 이미지 다시 굽는다

다시 돌려도 된다 — **이미 구운 쪽은 건너뛴다**(`--force` 로만 다시 굽는다).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "tools" / "offline_assets"
KST = timezone(timedelta(hours=9))

# **이름 규칙은 뷰어 하나뿐이다.** `settings` 를 건드리는 것은 `_root()` 뿐이라
# 임포트만으로는 Django 설정이 필요 없다.
sys.path.insert(0, str(REPO / "web"))
from viewer import atlas as atlas_mod  # noqa: E402

PAGE_DIR, THUMB_DIR = "pages", "thumbs"


# ── 자잘한 것 ────────────────────────────────────────────────────

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


def js_var(name: str, obj) -> str:
    """전역에 값 하나. **`</script` 를 막는다** — 자료 안의 문자열이 문서를
    닫아 버리면 그 뒤가 통째로 안 돈다."""
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    body = body.replace("</", "<\\/")
    return f"window.{name} = {body};\n"


def rel_page(key: str, volume, page, have=None) -> tuple[str, str, str]:
    """(권 경로, 쪽 JPEG 상대경로, 축소본 상대경로). 못 만들면 셋 다 빈 문자열.

    **경로를 여기서 짓지 않는다** — `atlas.rel_of` 가 지은 것에서 확장자와
    앞머리만 바꾼다. 그래야 규칙이 한 자리에 남는다.

    **꾸러미에 안 실린 쪽은 경로를 안 낸다** (`have`). 뷰어는 링크마다 디스크를
    짚지 않는데(한 판에 수백 번이 된다) 여기는 굽는 자리라 이미 다 알고 있고,
    오프라인에서 안 열리는 링크는 **"안 구웠다" 가 아니라 고장으로 읽힌다**.
    화면은 번호를 링크가 아닌 표로 남긴다 — 자리는 색인이 짚어 준 것이다.
    """
    try:
        n = int(page)
    except (TypeError, ValueError):
        return "", "", ""
    if n < 1:
        return "", "", ""
    vol = atlas_mod.vol_code(volume)
    if have is not None and (key, vol, n) not in have:
        return f"{key}/{vol}", "", ""
    rel = atlas_mod.rel_of(key, vol, n)            # atlas/<도감>/<권>/pNNNN.png
    tail = rel.split("/", 1)[1][:-4] + ".jpg"      # <도감>/<권>/pNNNN.jpg
    return f"{key}/{vol}", f"{PAGE_DIR}/{tail}", f"{THUMB_DIR}/{tail}"


# ── 자료 읽기 ────────────────────────────────────────────────────

def read_indexes(paths: list[Path], have=None) -> tuple[list[dict], list[dict], dict, int]:
    """색인 JSON 셋 → (도감 메타, 항목, 출처 해시, 안 실린 자리 수)."""
    books, entries, hashes, missing = [], [], {}, 0
    for p in sorted(paths):
        doc = json.loads(p.read_text(encoding="utf-8"))
        a = doc["atlas"]
        books.append({
            "key": a["key"], "title": a["title"], "short": a["short"],
            "note": a.get("note") or "", "count": len(doc["entries"]),
            "sort_order": a.get("sort_order", 99),
            "source": a.get("source") or "", "source_sha256": a.get("source_sha256") or "",
        })
        hashes[p.name] = sha256(p)
        for e in doc["entries"]:
            places = []
            for pl in e.get("placements") or []:
                vol_path, t_rel, t_thumb = rel_page(a["key"], pl.get("volume"),
                                                    pl.get("pdf_page"), have)
                _, p_rel, p_thumb = rel_page(a["key"], pl.get("volume"),
                                             pl.get("pdf_plate_page"), have)
                if have is not None:
                    missing += ((1 if pl.get("pdf_page") and not t_rel else 0)
                                + (1 if pl.get("pdf_plate_page") and not p_rel else 0))
                places.append({
                    # 뷰어 `_placement_dict` 와 같은 모양이다. `plate` 를 단독으로
                    # 찍지 않는다 — `note` 가 그것을 뒤집는 자리가 21건이다.
                    "where": f"pl.{pl['plate']}" if pl.get("plate")
                             else (pl.get("plate_label") or ""),
                    "figures": pl.get("figures") or "",
                    "volume": pl.get("volume") or "",
                    "book_page": pl.get("book_page"),
                    "note": pl.get("note") or "",
                    "pdf_page": pl.get("pdf_page"),
                    "pdf_plate_page": pl.get("pdf_plate_page"),
                    "vol_path": vol_path,
                    "text_rel": t_rel, "text_thumb": t_thumb,
                    "plate_rel": p_rel, "plate_thumb": p_thumb,
                })
            entries.append({
                "atlas": a["key"], "name": e["name"], "binomial": e.get("binomial") or "",
                "genus": e.get("genus") or "", "authority": e.get("authority") or "",
                "item_no": e.get("item_no"), "rank": e.get("rank") or "",
                "genus_guess": bool(e.get("genus_guess")),
                # **`line` 은 뺀다** — 색인 md 의 생김새이고 여기서 쓸 데가 없다
                "extra": e.get("extra") or {},
                "places": places,
            })
    books.sort(key=lambda b: (b["sort_order"], b["key"]))
    return books, entries, hashes, missing


def read_names(tsv: Path) -> dict:
    """학명 대조표 → {cols, rows}. **칸을 안 고른다** — 오프라인에서 되물을 곳이
    없으니 표를 통째로 들고 간다."""
    import csv
    with open(tsv, encoding="utf-8", newline="") as f:
        r = csv.reader(f, delimiter="\t")
        cols = next(r)
        rows = [row + [""] * (len(cols) - len(row)) for row in r if any(row)]
    return {"cols": cols, "rows": [row[:len(cols)] for row in rows]}


def scan_pages(root: Path) -> dict:
    """구워 둔 쪽 PNG 를 훑는다 → {도감: {권: [쪽 번호…]}}.

    **목록 파일(`atlases.json`)을 믿고 세지 않는다** — 우리가 싣는 것은 디스크에
    있는 것이고, 둘이 어긋나면 그 사실을 말해야 한다(굽다 만 자리가 있다).
    """
    out = {}
    if not root.is_dir():
        return out
    for adir in sorted(root.iterdir()):
        if not adir.is_dir():
            continue
        vols = {}
        for vdir in sorted(adir.iterdir()):
            if not vdir.is_dir():
                continue
            nums = sorted(int(m.group(1)) for m in
                          (atlas_mod.PAGE.match(p.name) for p in vdir.iterdir())
                          if m)
            if nums:
                vols[vdir.name] = nums
        if vols:
            out[adir.name] = vols
    return out


# ── 이미지 ───────────────────────────────────────────────────────

def _one(job):
    """쪽 하나 — 원본 PNG → JPEG + 축소본. 워커에서 돈다."""
    src, dst, thumb, quality, tw, tq, force = job
    from PIL import Image
    if not force and os.path.exists(dst) and os.path.exists(thumb):
        return 0, 0
    im = Image.open(src)
    im.load()
    if im.mode not in ("L", "RGB"):
        im = im.convert("RGB")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.makedirs(os.path.dirname(thumb), exist_ok=True)
    # **dpi 를 적어 둔다** — 인쇄하거나 재보는 사람이 배율을 되짚을 수 있어야 한다
    im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True,
            dpi=(300, 300))
    w = max(1, tw)
    th = im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)
    th.save(thumb, "JPEG", quality=tq, optimize=True)
    return os.path.getsize(dst), os.path.getsize(thumb)


def bake_images(pages: dict, src_root: Path, out: Path, args) -> tuple[int, int]:
    jobs = []
    for akey, vols in pages.items():
        for vcode, nums in vols.items():
            for n in nums:
                name = f"p{n:04d}"
                jobs.append((
                    str(src_root / akey / vcode / f"{name}.png"),
                    str(out / PAGE_DIR / akey / vcode / f"{name}.jpg"),
                    str(out / THUMB_DIR / akey / vcode / f"{name}.jpg"),
                    args.quality, args.thumb_width, args.thumb_quality, args.force))
    total = len(jobs)
    print(f"  쪽 {total}장을 굽는다 (일꾼 {args.jobs})…", flush=True)
    done = big = small = 0
    t0 = time.time()
    with mp.Pool(args.jobs) as pool:
        for a, b in pool.imap_unordered(_one, jobs, chunksize=4):
            done += 1
            big += a
            small += b
            if done % 50 == 0 or done == total:
                el = time.time() - t0
                print(f"    {done}/{total} · {human(big + small)} · {el:.0f}초"
                      f" · 남은 {el / done * (total - done):.0f}초", flush=True)
    return big, small


# ── 굽기 ─────────────────────────────────────────────────────────

def render_html(title: str, css: str, js: str, data_html: str) -> str:
    shell = (ASSETS / "shell.html").read_text(encoding="utf-8")
    return (shell.replace("{{TITLE}}", title).replace("{{CSS}}", css)
            .replace("{{DATA}}", data_html).replace("{{JS}}", js))


def main() -> int:
    ap = argparse.ArgumentParser(description="도감 오프라인 꾸러미를 굽는다")
    ap.add_argument("--version", default="1.0.0", help="꾸러미 판 (기본 1.0.0)")
    ap.add_argument("--out", default="/nfs/temp-share/DiaRUGA/Diadiction/offline",
                    help="꾸러미가 놓일 자리")
    ap.add_argument("--pages-root", default="/data3/DiaRUGA/atlas",
                    help="구워 둔 쪽 PNG 의 뿌리")
    ap.add_argument("--index-dir", default=str(REPO / "atlas"),
                    help="색인 JSON (atlas/*.json)")
    ap.add_argument("--names", default="", help="학명 대조표 TSV (없으면 최신을 찾는다)")
    ap.add_argument("--names-dir", default="/nfs/temp-share/DiaRUGA/Diadiction/names/worms")
    ap.add_argument("--quality", type=int, default=80, help="쪽 JPEG 품질")
    ap.add_argument("--thumb-width", type=int, default=220, help="축소본 가로 픽셀")
    ap.add_argument("--thumb-quality", type=int, default=72)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--no-images", action="store_true", help="글자만 담는다")
    ap.add_argument("--limit", type=int, default=0, help="쪽 몇 장만 (눌러 볼 때)")
    ap.add_argument("--force", action="store_true", help="이미 구운 쪽도 다시 굽는다")
    ap.add_argument("--no-zip", action="store_true", help="zip 을 안 만든다")
    ap.add_argument("--no-text-only-file", action="store_true",
                    help="글자만 담은 단일 HTML 을 안 만든다")
    args = ap.parse_args()

    out_root = Path(args.out)
    pkg = out_root / f"diadiction-offline-v{args.version}"
    pkg.mkdir(parents=True, exist_ok=True)
    built = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    # 1) 쪽을 먼저 훑는다 — **색인이 짚는 자리가 꾸러미에 있는지**를 알아야
    #    링크를 낼지 말지가 정해진다.
    pages = {} if args.no_images else scan_pages(Path(args.pages_root))
    if args.limit:
        pages = {a: {v: n[:args.limit] for v, n in vols.items()}
                 for a, vols in pages.items()}
    have = {(a, v, n) for a, vols in pages.items() for v, ns in vols.items() for n in ns}

    # 2) 색인
    idx_paths = sorted(Path(args.index_dir).glob("*.json"))
    idx_paths = [p for p in idx_paths if p.name != "atlases.json"]
    if not idx_paths:
        print(f"색인 JSON 이 없다: {args.index_dir}", file=sys.stderr)
        return 1
    books, entries, idx_hashes, missing = read_indexes(idx_paths, have)
    print(f"색인 {len(books)}권 · 항목 {len(entries)}개")
    if missing and not args.no_images:
        print(f"  색인이 짚는데 꾸러미에 없는 쪽 {missing}자리 — 번호만 남기고"
              f" 링크를 안 낸다")

    # 3) 학명 대조표
    names_path = Path(args.names) if args.names else None
    if names_path is None:
        cand = sorted(Path(args.names_dir).glob("worms_master_*.tsv"))
        cand = [p for p in cand if p.suffix == ".tsv"]
        names_path = cand[-1] if cand else None
    if names_path is None or not names_path.exists():
        print("학명 대조표를 못 찾았다 — 종 검색이 빈다", file=sys.stderr)
        names = {"cols": [], "rows": []}
        names_src = ""
    else:
        names = read_names(names_path)
        names_src = names_path.name
        print(f"학명 대조표 {len(names['rows'])}건 ({names_src})")

    # 4) 도감·권 목록
    manifest_pages = {}
    mf = Path(args.pages_root) / "atlases.json"
    if mf.exists():
        try:
            manifest_pages = json.loads(mf.read_text(encoding="utf-8")).get("atlases") or {}
        except json.JSONDecodeError:
            manifest_pages = {}

    dia_books, page_count = {}, 0
    for b in books:
        vols = pages.get(b["key"]) or {}
        mfa = manifest_pages.get(b["key"]) or {}
        mfv = {v.get("code"): v for v in (mfa.get("volumes") or [])}
        vlist = []
        for vcode, nums in sorted(vols.items()):
            vlist.append({
                "code": vcode,
                "label": (mfv.get(vcode) or {}).get("label") or vcode,
                "pages": nums,
                "page_dir": f"{PAGE_DIR}/{b['key']}/{vcode}/",
                "thumb_dir": f"{THUMB_DIR}/{b['key']}/{vcode}/",
            })
            page_count += len(nums)
        if not vlist:
            continue
        first = vlist[0]
        dia_books[b["key"]] = {
            "code": b["key"], "label": b["title"],
            # 좌우 판정은 도감마다 다르다 (뷰어 `atlas.left_parity`)
            "left_parity": (mfa.get("left_parity") or "odd"),
            "volumes": vlist,
            "rendered": sum(len(v["pages"]) for v in vlist),
            "cover": first["thumb_dir"] + f"p{first['pages'][0]:04d}.jpg"
                     if first["pages"] else "",
        }
    if pages:
        print(f"쪽 {page_count}장" + (f" (--limit {args.limit})" if args.limit else ""))

    meta = {
        "version": args.version, "built": built,
        "images": bool(dia_books), "page_count": page_count,
        "dpi": 300, "quality": args.quality,
        "names_source": names_src,
        "atlases": [{k: b[k] for k in ("key", "title", "short", "note", "count")}
                    for b in books],
    }

    # 5) 이미지
    big = small = 0
    if dia_books:
        want = {k: {v["code"]: v["pages"] for v in b["volumes"]}
                for k, b in dia_books.items()}
        big, small = bake_images(want, Path(args.pages_root), pkg, args)
        print(f"  쪽 {human(big)} · 축소본 {human(small)}")

    # 6) 화면
    css = (ASSETS / "app.css").read_text(encoding="utf-8")
    js = (ASSETS / "app.js").read_text(encoding="utf-8")
    data_dir = pkg / "data"
    data_dir.mkdir(exist_ok=True)
    for name, var, obj in (("meta.js", "DIA_META", meta),
                           ("books.js", "DIA_BOOKS", dia_books),
                           ("entries.js", "DIA_ENTRIES", entries),
                           ("names.js", "DIA_NAMES", names)):
        (data_dir / name).write_text(js_var(var, obj), encoding="utf-8")
    data_html = "\n".join(f'<script src="data/{n}"></script>'
                          for n in ("meta.js", "books.js", "entries.js", "names.js"))
    (pkg / "index.html").write_text(
        render_html(f"Diadiction 도감 — 오프라인 v{args.version}", css, js, data_html),
        encoding="utf-8")

    # 7) 글자만 담은 **진짜 단일 파일**
    single = out_root / f"diadiction-index-v{args.version}.html"
    if not args.no_text_only_file:
        tmeta = dict(meta, images=False, page_count=0)
        inline = "<script>\n" + "".join(
            js_var(v, o) for v, o in (("DIA_META", tmeta), ("DIA_BOOKS", {}),
                                      ("DIA_ENTRIES", entries), ("DIA_NAMES", names))
        ) + "</script>"
        single.write_text(
            render_html(f"Diadiction 도감 색인 (글자만) v{args.version}", css, js, inline),
            encoding="utf-8")
        print(f"단일 HTML: {single.name} · {human(single.stat().st_size)}")

    # 8) 안내·목록
    (pkg / "README.txt").write_text(readme(meta, books, dia_books, names_src),
                                    encoding="utf-8")
    files = [p for p in pkg.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    (pkg / "MANIFEST.json").write_text(json.dumps({
        "package": pkg.name, "version": args.version, "built": built,
        "entries": len(entries), "names": len(names["rows"]),
        "pages": page_count, "files": len(files), "bytes": total_bytes,
        "missing_placements": missing,
        "index_sha256": idx_hashes,
        "names_source": names_src,
        "names_sha256": sha256(names_path) if names_path and names_path.exists() else "",
        "git": git_head(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"꾸러미: {pkg} · 파일 {len(files)}개 · {human(total_bytes)}")

    # 9) zip — **JPEG 는 안 눌러 담는다.** 이미 눌린 것이라 시간만 든다
    if not args.no_zip:
        zpath = out_root / f"{pkg.name}.zip"
        t0 = time.time()
        with zipfile.ZipFile(zpath, "w", allowZip64=True) as z:
            for p in sorted(files):
                arc = f"{pkg.name}/{p.relative_to(pkg).as_posix()}"
                z.write(p, arc, compress_type=(zipfile.ZIP_STORED if p.suffix == ".jpg"
                                               else zipfile.ZIP_DEFLATED))
        print(f"zip: {zpath.name} · {human(zpath.stat().st_size)}"
              f" · {time.time() - t0:.0f}초")
    return 0


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def readme(meta, books, dia_books, names_src) -> str:
    lines = [
        f"Diadiction 오프라인 꾸러미 v{meta['version']}",
        f"구운 날: {meta['built']}",
        "",
        "여는 법",
        "  index.html 을 브라우저로 연다 (더블클릭). 서버도 인터넷도 필요 없다.",
        "  옆의 data/ · pages/ · thumbs/ 폴더를 함께 들고 다녀야 한다 —",
        "  index.html 만 떼어 내면 자료가 안 붙는다.",
        "  도판이 필요 없으면 옆에 있는 diadiction-index-v*.html 한 파일이면 된다.",
        "",
        "무엇이 들었나",
    ]
    for b in books:
        lines.append(f"  · {b['title']} — 항목 {b['count']}개")
    lines += [
        f"  · 학명 대조표 {names_src} (WoRMS·AlgaeBase 대조)",
        f"  · 도판 {meta['page_count']}쪽 · 300 dpi JPEG (품질 {meta['quality']})"
        if meta["images"] else "  · 도판 없음 (글자만)",
        "",
        "화면",
        "  색인 검색  학명·속으로 찾는다. 결과의 '해설 p.N' · '도판 p.N' 을 누르면 그 쪽이 열린다",
        "  종 검색    학명 대조표. 유효명·저자·과·목 어느 칸으로도 찾는다",
        "  쪽 보기    ← → 넘기기 · g 격자 · s 한 장/두 쪽 · 휠 확대 · 끌어서 옮기기",
        "",
        "인용할 때",
        "  색인 표제어는 OCR 산물이라 철자가 흔들린다. 그대로 인용하지 말고",
        "  도판 쪽을 열어 원문 표기를 눈으로 확인한다.",
        "  PDF 쪽이 안 적힌 자리(한국 도감 201건)는 링크가 안 나온다 —",
        "  '안 구운 것' 이 아니라 색인이 원래 안 적은 것이다.",
        "",
        "원본",
        "  색인 md·PDF: Diadiction/md/ · Diadiction/origin/",
        "  쪽 PNG: /data3/DiaRUGA/atlas/ (tools/render_atlas_pages.py 가 굽는다)",
        "  이 꾸러미: tools/build_offline_atlas.py (DiaRUGA 저장소)",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
