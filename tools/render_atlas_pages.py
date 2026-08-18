#!/usr/bin/env python3
"""도감 PDF 를 쪽마다 PNG 로 떠서 뷰어가 보는 자리에 놓는다 (P15 §6 · 129).

    python tools/render_atlas_pages.py            # 없는 것만 굽는다
    python tools/render_atlas_pages.py --only schmidt --jobs 4
    python tools/render_atlas_pages.py --dry-run

## 왜 미리 뜨나

P14 4.2 는 "쪽 번호만 알려 주고 사람이 PDF 를 연다" 였다. **사용자 방침이
바뀌었다**(2026-08-18) — 화면에서 도판을 넘겨 보고, 색인에서 바로 그 쪽으로
간다. 뷰어가 2.5 GB PDF 를 렌더할 수는 없으므로 **미리 떠 둔다.**

## 왜 호스트에서 도나

**컨테이너는 `/nfs/temp-share` 를 못 본다**(P14 4.4). 원본 PDF 가 거기 있으므로
굽는 일은 호스트 몫이다. 그래서 이 파일은 `tools/` 다 — `/srv` 로 안 간다.
낸 PNG 는 `/data3/DiaRUGA/atlas/` 에 놓는데, **거기는 뷰어가 이미 보는 자리다.**

## 쪽 번호가 열쇠다

색인 셋이 전부 `PDF p.N` 으로 자리를 짚는다(`Tafel 26 (Band1 PDF p.68/69)`).
그래서 파일 이름을 **그 번호 그대로** 둔다 — `p0068.png`. 색인에서 화면으로
가는 길이 계산 없이 서고, **번호를 옮겨 적는 자리가 안 생긴다.**

## 무채색이면 회색조로 줄인다 — 도감마다 다르므로 쪽마다 본다

Schmidt·한국 스캔은 채널차가 **0** 이라 회색조로 바꿔도 잃는 것이 없고 파일이
절반이 된다. **동남극 도판집은 색이 있다**(채널차 76). 도감을 보고 정하면
넷째 도감에서 틀리므로 **쪽마다 재서 정한다.**

## 몇 번 돌려도 같다

이미 있는 쪽은 건너뛴다. 중간에 멈춰도 다시 부르면 이어 간다. 다시 뜨려면
`--force` 이거나 그 쪽 파일을 지운다.

## 도감을 더하려면

`SOURCES` 에 한 줄 더한다. 그것뿐이다 — 목록·쪽 수·표지는 `atlases.json` 으로
**이 스크립트가 만들어 낸다**(사람이 적지 않는다. 적으면 어긋난다).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# --- 도감 원본 ---------------------------------------------------------------
#
# **`origin/` 것만 쓴다.** 같은 폴더의 `dup/` 는 Schmidt 4권을 합친 중복본이고
# (`Leipzig und Berlin 1874-1959 *.pdf`, 1.2 GB), `div/` 는 한국 도감을 9토막
# 낸 것이다. 둘 다 쪽 번호가 색인과 안 맞으므로 **넣으면 안 된다.**
#
# `volume` 은 PDF 하나다 — 색인이 `Band4 PDF p.174` 처럼 **권마다 따로** 센다.
NAS = Path("/nfs/temp-share/DiaRUGA/Diadiction/origin")

SOURCES = [
    # (도감 코드, 도감 이름, 권 코드, 권 이름, PDF)
    ("korean", "한국동식물도감 제9권 (담수조류)", "main", "본권",
     "korean_flora_diatom.pdf"),
    ("schmidt", "A. Schmidt, Atlas der Diatomaceenkunde", "band1", "Band 1",
     "Band1.pdf"),
    ("schmidt", "A. Schmidt, Atlas der Diatomaceenkunde", "band2", "Band 2",
     "Band2.pdf"),
    ("schmidt", "A. Schmidt, Atlas der Diatomaceenkunde", "band3", "Band 3",
     "Band3.pdf"),
    ("schmidt", "A. Schmidt, Atlas der Diatomaceenkunde", "band4", "Band 4",
     "Band4.pdf"),
    ("east-antarctic", "플라이스토세 중기 이후 동남극 규조 (도판집)", "main", "본권",
     "pleistocene_east_antarctic_plates.pdf"),
]

OUT = Path(os.environ.get("DIARUGA_ATLAS_ROOT", "/data3/DiaRUGA/atlas"))
DPI = 300
# 채널차가 이보다 크면 색이 있는 것으로 본다. 스캔 잡음이 1~2 는 나므로 0 으로
# 못 박지 않는다 — 실측은 무채색 0, 색 있는 쪽 76 이라 사이가 넓다.
CHROMA_TOL = 2


def page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise RuntimeError(f"쪽 수를 못 읽었다: {pdf}")


def render_one(pdf: str, page: int, dest: str, dpi: int) -> tuple[int, int, bool]:
    """쪽 하나. (쪽번호, 바이트, 회색조로 줄였나)"""
    from PIL import Image, ImageChops

    d = Path(dest)
    tmpdir = tempfile.mkdtemp(prefix="atlaspage-", dir=str(d.parent))
    try:
        stem = Path(tmpdir) / "p"
        subprocess.run(
            ["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi),
             "-png", pdf, str(stem)],
            capture_output=True, check=True)
        made = sorted(Path(tmpdir).glob("p*.png"))
        if not made:
            raise RuntimeError(f"렌더가 아무것도 안 냈다: {pdf} p{page}")
        src = made[0]

        with Image.open(src) as im:
            im.load()
            rgb = im.convert("RGB")
            r, g, b = rgb.split()
            chroma = max(ImageChops.difference(r, g).getextrema()[1],
                         ImageChops.difference(g, b).getextrema()[1])
            gray = chroma <= CHROMA_TOL
            if gray:
                im.convert("L").save(src, "PNG", optimize=True)
        # **다 된 뒤에 제 이름을 준다.** 반쯤 쓴 파일이 `p0068.png` 라는 이름을
        # 달면 다음 실행이 "이미 있다" 며 건너뛴다 (034 의 `.part` 와 같은 줄).
        os.replace(src, d)
        return page, d.stat().st_size, gray
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def write_manifest(plan, dpi: int, only: str) -> Path:
    """도감 목록. **손으로 적지 않는다** — 적으면 쪽 수가 어긋나고 화면이 그것을
    그대로 믿는다. 굽기 전과 뒤에 한 번씩 불러서, 도는 중에도 이름이 뜬다.
    """
    manifest = {"dpi": dpi, "atlases": {}}
    for atlas, atlas_name, vol, vol_name, fname, n in plan:
        at = manifest["atlases"].setdefault(
            atlas, {"code": atlas, "label": atlas_name, "volumes": []})
        d = OUT / atlas / vol
        have = len(list(d.glob("p*.png"))) if d.exists() else 0
        at["volumes"].append({"code": vol, "label": vol_name, "source": fname,
                              "pages": n, "rendered": have})
    mf = OUT / "atlases.json"
    if only and mf.exists():
        # 한 도감만 돌렸으면 나머지 도감의 기록을 지우지 않는다
        try:
            prev = json.loads(mf.read_text(encoding="utf-8")).get("atlases", {})
        except (OSError, ValueError):
            prev = {}
        prev.update(manifest["atlases"])
        manifest = {"dpi": dpi, "atlases": prev}
    # 반쯤 쓴 목록을 화면이 읽으면 안 된다 — 다 쓰고 제자리로 옮긴다
    tmp = mf.with_suffix(".json.part")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, mf)
    return mf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="도감 코드 하나만")
    ap.add_argument("--dpi", type=int, default=DPI)
    ap.add_argument("--jobs", type=int, default=6,
                    help="동시에 굽는 수. CPU 를 다 쓰지 않는다 — 파이프라인과 뷰어가 같은 장비다")
    ap.add_argument("--force", action="store_true", help="있는 것도 다시 뜬다")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    todo, plan = [], []
    for atlas, atlas_name, vol, vol_name, fname in SOURCES:
        if a.only and atlas != a.only:
            continue
        pdf = NAS / fname
        if not pdf.exists():
            print(f"!! 원본이 없다: {pdf}", file=sys.stderr)
            return 2
        n = page_count(pdf)
        d = OUT / atlas / vol
        if not a.dry_run:
            d.mkdir(parents=True, exist_ok=True)
        miss = [p for p in range(1, n + 1)
                if a.force or not (d / f"p{p:04d}.png").exists()]
        plan.append((atlas, atlas_name, vol, vol_name, fname, n))
        print(f"  {atlas}/{vol:6} {n:4d}쪽  굽을 것 {len(miss):4d}")
        todo += [(str(pdf), p, str(d / f"p{p:04d}.png")) for p in miss]

    if a.dry_run:
        print(f"\n마른 실행 — 굽을 쪽 {len(todo)}개")
        return 0

    # **굽기 전에 한 번 써 둔다.** 1,336쪽이 15분쯤 걸리는데, 그동안 화면이
    # 목록 파일을 못 찾으면 폴더만 훑어 **도감 이름 대신 코드를 낸다**
    # (`east-antarctic`·`schmidt`). 도는 중에도 사람이 열어 보는 화면이다.
    write_manifest(plan, a.dpi, a.only)

    done = err = grayed = 0
    total_bytes = 0
    if todo:
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(render_one, pdf, p, dest, a.dpi): (pdf, p)
                    for pdf, p, dest in todo}
            for f in as_completed(futs):
                try:
                    _, size, gray = f.result()
                    done += 1
                    total_bytes += size
                    grayed += int(gray)
                except Exception as exc:                      # noqa: BLE001
                    pdf, p = futs[f]
                    print(f"!! {Path(pdf).name} p{p}: {exc}", file=sys.stderr)
                    err += 1
                if done and done % 100 == 0:
                    print(f"  … {done}/{len(todo)}", flush=True)

    write_manifest(plan, a.dpi, a.only)

    mf = write_manifest(plan, a.dpi, a.only)
    print(f"\n구운 쪽 {done}개 (회색조로 줄인 것 {grayed}) · 실패 {err} · "
          f"{total_bytes / 1e9:.2f} GB · 목록 {mf}")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
