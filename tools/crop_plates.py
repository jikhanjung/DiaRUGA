"""도판 쪽에서 그림 하나하나를 찾아 잘라낸다 (P20 · 논문 도판).

    python tools/crop_plates.py --paper 1936_skvortzov_ampen_neogene --page 47 --probe
    python tools/crop_plates.py --paper … --page 47 --cut          # 실제로 자른다

## 왜 도구를 만드나

`Diadiction/plate/` 는 지금까지 **손으로 하나씩** 잘라 왔다(README 의 작업 순서).
그런데 1936 한 편만 그림이 **79개**이고, 1985 는 도판이 40쪽이다. 손으로는
안 끝난다.

## 무엇을 자동으로 하고 무엇을 사람이 하나

**도구는 상자를 찾기만 한다. 어느 상자가 몇 번 그림인지는 사람이 짚는다.**
도판의 그림 번호는 활자가 작고 그림에 겹쳐 있어 기계가 읽으면 틀린다 —
**틀린 번호는 예외가 안 나고 그냥 다른 종의 도판이 된다.**

그래서 `--probe` 가 **번호를 매긴 대조 시트**를 내고, 사람이 그것을 보고
`ASSIGN` 에 `상자 번호 → Fig 번호` 를 적는다. `--cut` 은 그 표대로만 자른다.

## 펼친 책이라 맞은편 쪽이 들어온다

스캔이 펼친 책이라 도판 쪽 옆에 **맞은편 캡션 쪽과 제본 그림자**가 붙어 있다.
`--margin` 이 그것을 먼저 걷는다. 안 걷으면 그림자가 제일 큰 상자가 되고,
맞은편 글자가 그림으로 잡힌다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_worms import DIADICTION  # noqa: E402
from plate_figs import (ASSIGN, CAPTIONS, MANUAL_BOXES, PARAMS, SOURCE,  # noqa: E402
                        UNCROPPED)

PAPERS = DIADICTION / "papers"
PLATE_OUT = DIADICTION / "plate"


def render(pdf: Path, page: int, dpi: int) -> Image.Image:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi),
                        "-png", "-gray", str(pdf), f"{td}/p"], check=True,
                       capture_output=True)
        f = next(Path(td).iterdir())
        return Image.open(f).convert("L").copy()


def trim(im: Image.Image, margin: tuple[float, float, float, float]) -> tuple[Image.Image, tuple[int, int]]:
    """맞은편 쪽·제본 그림자를 걷는다. 비율로 받는다 (좌·상·우·하)."""
    w, h = im.size
    l, t, r, b = margin
    box = (int(w * l), int(h * t), int(w * (1 - r)), int(h * (1 - b)))
    return im.crop(box), (box[0], box[1])


def boxes(im: Image.Image, thr: int, grow: int, min_area: int,
          min_side: int, drop_nested: bool = True) -> list[tuple[int, int, int, int]]:
    """짙은 화소를 이어 붙여 상자를 찾는다.

    **선그림은 속이 비어 있다** — 윤곽선만 짙다. `grow`(팽창)로 striae 사이를
    메워야 한 덩어리가 된다. 안 하면 그림 하나가 수십 조각으로 갈린다.
    """
    g = im.filter(ImageFilter.MinFilter(grow)) if grow >= 3 else im
    a = np.asarray(g) < thr

    # 이어진 덩어리에 번호를 붙인다 (합집합 찾기 — scipy 없이)
    h, w = a.shape
    lab = np.zeros((h, w), np.int32)
    parent: list[int] = [0]

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    nxt = 1
    for y in range(h):
        row, prev = a[y], a[y - 1] if y else None
        for x in range(w):
            if not row[x]:
                continue
            up = lab[y - 1, x] if y and prev[x] else 0
            left = lab[y, x - 1] if x and row[x - 1] else 0
            if up and left:
                lab[y, x] = min(up, left)
                union(up, left)
            elif up or left:
                lab[y, x] = up or left
            else:
                lab[y, x] = nxt
                parent.append(nxt)
                nxt += 1

    root = np.array([find(i) for i in range(nxt)], np.int32)
    lab = root[lab]

    out = []
    for i in np.unique(lab):
        if i == 0:
            continue
        ys, xs = np.nonzero(lab == i)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bw * bh < min_area or max(bw, bh) < min_side:
            continue
        out.append((int(x0), int(y0), int(x1), int(y1)))
    # **다른 상자 안에 통째로 들어간 것은 그림이 아니다** — 사진 타일 안쪽의
    # 밝은 자리가 덩어리를 갈라 놓아 생긴 조각이다(1993 PLATE 1 의 fig 2 가
    # 셋으로 갈렸다). 감싸는 상자가 이미 그 그림을 다 담고 있다
    keep = []
    for i, b in enumerate(out):
        if not drop_nested:
            keep.append(b); continue
        t = 4   # 스캔 잡티로 한두 화소 삐져나오는 것을 봐준다
        inside = any(i != j and c[0] <= b[0]+t and c[1] <= b[1]+t
                     and c[2] >= b[2]-t and c[3] >= b[3]-t
                     and (c[2]-c[0])*(c[3]-c[1]) > (b[2]-b[0])*(b[3]-b[1])
                     for j, c in enumerate(out))
        if not inside:
            keep.append(b)
    out = keep
    # 위에서 아래로, 왼쪽에서 오른쪽으로 (사람이 시트를 읽는 순서)
    out.sort(key=lambda b: (b[1] // 50, b[0]))
    return out


def contact(im: Image.Image, bs: list, path: Path) -> None:
    """상자마다 번호를 적은 대조 시트. **사람이 이걸 보고 Fig 번호를 짚는다.**"""
    rgb = im.convert("RGB")
    d = ImageDraw.Draw(rgb)
    for i, (x0, y0, x1, y1) in enumerate(bs, 1):
        d.rectangle([x0, y0, x1, y1], outline=(220, 0, 0), width=3)
        d.text((x0 + 4, y0 + 4), str(i), fill=(220, 0, 0))
    rgb.save(path)



def slug(name: str) -> str:
    """파일 이름에 쓸 ASCII. **학명의 표기는 지키되 기호만 걷는다.**"""
    import re
    s = name
    for a, b in (("(", ""), (")", ""), ("?", ""), (".", ""), (",", "")):
        s = s.replace(a, b)
    s = re.sub(r"\s+", "_", s.strip())
    return re.sub(r"[^A-Za-z0-9_\-]", "", s)


def cut_plate(im, bs, paper, page, pad, outdir):
    """`ASSIGN` 이 짚어 준 대로만 자른다. 표가 없으면 아무것도 안 한다."""
    a = ASSIGN.get((paper, page))
    if a is None:
        print(f"\n**`ASSIGN[({paper!r}, {page})]` 가 없다** — 대조 시트를 보고 "
              f"`tools/plate_figs.py` 에 상자 {len(bs)}개의 Fig 번호를 적어라.")
        return 1
    if len(a) != len(bs):
        print(f"\n**상자가 {len(bs)}개인데 표는 {len(a)}개다.** "
              f"`--thr`·`--grow`·`--margin` 을 바꿨으면 표도 다시 짚어야 한다.")
        return 1
    plate = next((k for k, (_, pg) in SOURCE[paper].items() if pg == page), None)
    if plate is None:
        print(f"\n`SOURCE[{paper!r}]` 에 도판 쪽 {page} 가 없다.")
        return 1
    caps = CAPTIONS[paper][plate]
    outdir.mkdir(parents=True, exist_ok=True)
    w, h = im.size
    made = 0
    for box, fig in zip(bs, a):
        if fig is None:
            continue
        # **이름이 없어도 자른다.** 그림을 버리면 나중에 이름을 알아도 다시
        # 도판을 떠야 한다 — 빠진 것은 파일 이름에 드러나게 둔다
        name = caps.get(fig, "__unnamed")
        x0, y0, x1, y1 = box
        # **번호 라벨이 잘리면 안 된다**(Diadiction README 의 작업 순서) — 여유를 둔다
        b = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
        tag = f"{paper.split('_')[0]}{paper.split('_')[1][:3]}"
        f = outdir / f"plate_{tag}_pl{plate}_fig{fig:02d}_{slug(name)}.png"
        im.crop(b).save(f)
        made += 1
    # **닿아서 자동으로 못 가른 자리는 사람이 잰 사각형을 쓴다.** `ASSIGN` 은
    # 그 상자를 이미 `None` 으로 걷어 뒀다 — 여기서 덧붙인다
    for fig, box in MANUAL_BOXES.get((paper, page), {}).items():
        x0, y0, x1, y1 = box
        b = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
        name = caps.get(fig, "__unnamed")
        tag = f"{paper.split('_')[0]}{paper.split('_')[1][:3]}"
        f = outdir / f"plate_{tag}_pl{plate}_fig{fig:02d}_{slug(name)}.png"
        im.crop(b).save(f)
        made += 1
        a = a + [fig]   # UNCROPPED 계산에서 "이미 있다" 로 세이지 위해

    got = {f for f in a if f is not None}
    unnamed = sorted(got - set(caps))
    if unnamed:
        print(f"   **이름이 아직 없는 그림 {len(unnamed)}: {unnamed}** "
              f"(`__unnamed` 로 잘라 뒀다)")
    miss = sorted(set(caps) - got)
    print(f"\n{made}장을 잘랐다 → {outdir}")
    if miss:
        print(f"**캡션에 있는데 안 잘린 그림 {len(miss)}: {miss}**")
        for f in miss:
            why = UNCROPPED.get((paper, page, f), "이유가 안 적혀 있다")
            print(f"   Fig {f}: {why}  — {caps[f]}")
    return 0


def grid(im, bs, path: Path, cell: int = 230, cols: int = 7, pad: int = 30) -> None:
    """상자를 하나씩 잘라 격자로 붙인다. **짚기는 이걸 보고 한다.**

    도판 위에 번호를 그리면 **인쇄된 그림 번호와 겹쳐** 어느 쪽이 무엇인지
    헷갈린다(실제로 그래서 못 짚었다). 조각으로 갈라 놓으면 조각 안에 그
    그림의 인쇄 번호가 통째로 들어와 **읽는 데 애매함이 없다.**
    """
    w, h = im.size
    tiles = []
    for x0, y0, x1, y1 in bs:
        b = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
        t = im.crop(b)
        t.thumbnail((cell, cell))
        tiles.append(t)
    rows = (len(tiles) + cols - 1) // cols
    lab = 22
    out = Image.new("RGB", (cols * cell, rows * (cell + lab)), (255, 255, 255))
    d = ImageDraw.Draw(out)
    for i, t in enumerate(tiles):
        cx, cy = (i % cols) * cell, (i // cols) * (cell + lab)
        d.rectangle([cx, cy, cx + cell - 2, cy + lab - 2], fill=(240, 240, 240))
        d.text((cx + 6, cy + 5), f"box {i+1}", fill=(200, 0, 0))
        out.paste(t.convert("RGB"), (cx + (cell - t.width) // 2, cy + lab))
        d.rectangle([cx, cy, cx + cell - 2, cy + lab + cell - 2], outline=(200, 200, 200))
    out.save(path)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--thr", type=int, default=170, help="이보다 어두우면 그림이다")
    ap.add_argument("--grow", type=int, default=9, help="팽창 크기 (홀수)")
    ap.add_argument("--min-area", type=int, default=4000)
    ap.add_argument("--min-side", type=int, default=60)
    ap.add_argument("--margin", default="0,0,0,0", help="좌,상,우,하 비율")
    ap.add_argument("--probe", action="store_true", help="대조 시트만 낸다")
    ap.add_argument("--cut", action="store_true", help="ASSIGN 대로 자른다")
    ap.add_argument("--pad", type=int, default=40, help="번호 라벨이 잘리지 않게")
    # 짚기 시트만 좁게 볼 때. **이웃의 번호가 같이 들어와 헷갈릴 때 줄인다**
    ap.add_argument("--grid-pad", type=int, default=30)
    # **감싸인 상자를 걷는 것이 쪽마다 다르게 문다.** 사진 타일은 안쪽이
    # 갈라져 조각이 생기므로 걷어야 하고(1993 PLATE 1 의 fig 2), 선그림은
    # 큰 그림의 상자가 이웃을 통째로 감싸서 걷으면 이웃이 사라진다(1936 fig 13)
    ap.add_argument("--no-drop-nested", dest="drop_nested",
                    action="store_false", default=True)
    ap.add_argument("--out", type=Path,
                    default=Path("/tmp/claude-1006/-home-sclee-projects-DiaRUGA/"
                                 "71c428bd-2503-422e-8032-e047be395e81/scratchpad/plates"))
    args = ap.parse_args()

    pr = PARAMS.get((args.paper, args.page), {})
    for k, v in pr.items():
        if getattr(args, k) == ap.get_default(k):
            setattr(args, k, v)
    pdf = PAPERS / f"{args.paper}.pdf"
    im = render(pdf, args.page, args.dpi)
    m = tuple(float(x) for x in args.margin.split(","))
    im, off = trim(im, m)
    bs = boxes(im, args.thr, args.grow, args.min_area, args.min_side,
               args.drop_nested)
    if pr:
        print(f'   설정: {pr}')
    print(f"{args.paper} p.{args.page} · {im.size[0]}x{im.size[1]} · 상자 {len(bs)}개")
    for i, b in enumerate(bs, 1):
        print(f"  {i:3d}  x{b[0]:5d} y{b[1]:5d}  {b[2]-b[0]:4d}x{b[3]-b[1]:4d}")
    args.out.mkdir(parents=True, exist_ok=True)
    sheet = args.out / f"probe_{args.paper}_p{args.page}.png"
    contact(im, bs, sheet)
    gsheet = args.out / f"grid_{args.paper}_p{args.page}.png"
    grid(im, bs, gsheet, pad=args.grid_pad)
    print(f"\n→ {sheet}\n→ {gsheet}  ← **짚기는 이걸 본다**")
    (args.out / f"boxes_{args.paper}_p{args.page}.json").write_text(
        json.dumps({"paper": args.paper, "page": args.page, "dpi": args.dpi,
                    "offset": off, "boxes": bs}, indent=1), encoding="utf-8")
    if args.cut:
        return cut_plate(im, bs, args.paper, args.page, args.pad, PLATE_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
