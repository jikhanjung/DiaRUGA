#!/usr/bin/env python3
r"""배포 전 화면(스크린샷)을 80 포트로 내보낸다 — 날짜별로 쌓는다.

    http://172.16.116.98/DiaRUGA-preview/            ← 날짜 목록
    http://172.16.116.98/DiaRUGA-preview/20260805/   ← 그날 찍은 것

**NAS 에도 같은 것을 둔다** — `N:\DiaRUGA\preview\20260805\`
(`/nfs/temp-share/DiaRUGA/preview/`). 웹은 훑어보는 자리고, NAS 는 파일로
가져가는 자리다. 보고서(`.docx`)가 같은 공유로 나가는 것과 같은 길이다.

**왜 80 인가.** 사내 VPN 이 80 말고는 통과시키지 않는다 — `:9090` 이
`/DiaRUGA/` 로 옮겨진 것과 같은 이유다(devlog 018). `runserver` 를 8099 에
띄워 봐야 밖에서는 안 보인다.

**왜 sudo 가 없어도 되는가.** nginx 의 80 루트(`/srv/paleolab`)가 `paleoadmin`
소유다. 거기 디렉토리를 하나 두면 `location /` 의 `try_files` 가 그대로 낸다.
살아 있는 화면(nginx 프록시)은 `deploy/nginx/DiaRUGA-preview.conf` 쪽이고
그건 sudo 가 필요하다 — **이 스크립트는 정지 화면만 낸다.**

**날짜 디렉토리를 지우지 않는다.** 지난 판이 어떻게 생겼는지가 그 자체로
기록이다. 치울 때는 사람이 통째로 지운다(`rm -rf`).

쓰는 법
-------

    # 찍어 둔 PNG 들이 있는 디렉토리를 통째로 올린다
    python tools/publish_preview.py <PNG 디렉토리> --devlog 049 \
        --title "어제 담은 다섯 + 코어 페이지"

PNG 이름은 `01-무엇.png` 꼴로 둔다 — **앞의 번호가 곧 순서다.** 설명은 같은
디렉토리의 `captions.txt` 에서 읽는다(`파일이름<탭>설명`, 없으면 이름만 낸다).

    01-list-dark<TAB>목록 — 코어로 묶고 접기
    02-list-light<TAB>같은 화면, 밝은 테마

날짜를 주지 않으면 오늘이다(`--date 20260805`). 같은 날 두 번 올리면 그
디렉토리를 갈아치운다 — 하루에 두 판을 나눠 남기려면 날짜를 손으로 준다.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from datetime import date
from pathlib import Path

ROOT = Path("/srv/paleolab/DiaRUGA-preview")
# N:\DiaRUGA\preview — 윈도우에서 파일로 가져가는 자리. 보고서(.docx)가 나가는
# 공유와 같은 곳이다. **웹과 같은 것을 둔다** — 한쪽만 새것이면 어느 쪽이 지금인지
# 알 수 없다.
NAS = Path("/nfs/temp-share/DiaRUGA/preview")


def _load_captions(src: Path) -> dict[str, str]:
    """`captions.txt` — `파일이름<탭>설명`. 없으면 빈 표다."""
    f = src / "captions.txt"
    if not f.is_file():
        return {}
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, _, cap = line.partition("\t")
        out[name.strip().removesuffix(".png")] = cap.strip()
    return out


# 화면은 어두운 테마가 기본이라 이 페이지도 그렇게 둔다. 뷰어의 색을 그대로
# 쓰지 않는다 — 여기는 뷰어가 아니라 뷰어를 **찍은 것**을 보는 자리다.
_CSS = """
  body { margin:0; font:14px/1.6 ui-sans-serif,system-ui,"Noto Sans KR",sans-serif;
         background:#0f1115; color:#e6e9ef; }
  a { color:#5ac8fa; text-decoration:none; }
  a:hover { text-decoration:underline; }
  header { padding:14px 20px; border-bottom:1px solid #262b36; background:#171a21;
           position:sticky; top:0; z-index:5; }
  h1 { font-size:15px; margin:0 0 6px; }
  h1 .sub { font-weight:400; color:#8b93a3; margin-left:8px; }
  nav { display:flex; flex-wrap:wrap; gap:4px 10px; font-size:12px; }
  main { padding:16px 20px 60px; max-width:1560px; margin:0 auto; }
  .warn { font-size:12.5px; color:#ffe9b8; background:#4a3a12; border:1px solid #7d6222;
          padding:8px 12px; border-radius:6px; margin:10px 20px 0; }
  figure { margin:0 0 30px; scroll-margin-top:92px; }
  figcaption { font-size:13px; color:#8b93a3; margin-bottom:7px; }
  figcaption b { color:#5ac8fa; margin-right:6px; }
  img { width:100%; display:block; border:1px solid #262b36; border-radius:8px; }
  ul.days { list-style:none; padding:0; margin:0; }
  ul.days li { padding:11px 0; border-bottom:1px solid #262b36; display:flex;
               gap:12px; align-items:baseline; flex-wrap:wrap; }
  ul.days .d { font-weight:650; font-size:15px; min-width:104px; }
  ul.days .n { color:#8b93a3; font-size:12px; margin-left:auto; }
"""


def _page(title: str, body: str, head_extra: str = "") -> str:
    return (f"<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            f"<title>{html.escape(title)}</title>\n<style>{_CSS}</style>\n"
            f"{head_extra}</head><body>\n{body}\n</body></html>\n")


def _mirror_to_nas(day: str, out: Path) -> Path | None:
    """웹에 올린 그대로를 NAS 공유에 복사한다.

    **공유가 안 붙어 있으면 조용히 넘어간다.** 미리보기를 내는 일이 NAS 마운트
    상태에 매달리면 안 된다 — 웹 쪽은 이미 올라갔다.
    """
    if not NAS.parent.is_dir():
        print(f"NAS 공유가 없다 — 건너뛴다 ({NAS.parent})")
        return None
    dst = NAS / day
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(out, dst)
    return dst


def publish(src: Path, day: str, title: str, devlog: str) -> Path:
    shots = sorted(p for p in src.glob("*.png"))
    if not shots:
        raise SystemExit(f"PNG 이 없다: {src}")
    caps = _load_captions(src)

    out = ROOT / day
    if out.exists():
        shutil.rmtree(out)          # 같은 날 다시 올리면 갈아치운다
    out.mkdir(parents=True)

    for p in shots:
        shutil.copy(p, out / p.name)
    # 날짜 목록이 읽을 한 줄. 디렉토리를 훑어 다시 그릴 때 쓴다.
    (out / "meta.txt").write_text(
        f"{title}\n{devlog}\n", encoding="utf-8")

    nav = "\n".join(f'<a href="#{p.stem}">{html.escape(p.stem[3:] or p.stem)}</a>'
                    for p in shots)
    figs = "\n".join(
        f'<figure id="{p.stem}"><figcaption><b>{html.escape(p.stem[:2])}</b> '
        f'{html.escape(caps.get(p.stem, p.stem))}</figcaption>'
        f'<a href="{p.name}" target="_blank"><img src="{p.name}" '
        f'alt="{html.escape(caps.get(p.stem, p.stem))}"></a></figure>'
        for p in shots)

    body = f"""<header>
  <h1><a href="../">DiaRUGA 미리보기</a> / {html.escape(day)}
    <span class="sub">{html.escape(title)}{f' · devlog {html.escape(devlog)}' if devlog else ''}</span></h1>
  <nav>{nav}</nav>
</header>
<div class="warn"><b>정지 화면입니다.</b> 눌러 볼 수 있는 미리보기는 nginx 조각
  (<code>deploy/nginx/DiaRUGA-preview.conf</code>)을 얹어야 열립니다 — 사내 VPN 이
  80 말고는 통과시키지 않아 <code>:8099</code> 로는 밖에서 닿지 않습니다.
  그림을 누르면 원본 크기로 열립니다.</div>
<main>{figs}</main>"""
    (out / "index.html").write_text(_page(f"DiaRUGA {day} 미리보기", body),
                                    encoding="utf-8")
    return out


def reindex() -> None:
    """날짜 디렉토리를 훑어 첫 페이지를 다시 그린다. **최신이 위다.**"""
    days = sorted((d for d in ROOT.iterdir()
                   if d.is_dir() and re.fullmatch(r"\d{8}", d.name)),
                  key=lambda d: d.name, reverse=True)
    rows = []
    for d in days:
        title, devlog = "", ""
        meta = d / "meta.txt"
        if meta.is_file():
            lines = meta.read_text(encoding="utf-8").splitlines()
            title = lines[0] if lines else ""
            devlog = lines[1] if len(lines) > 1 else ""
        n = len(list(d.glob("*.png")))
        pretty = f"{d.name[:4]}-{d.name[4:6]}-{d.name[6:]}"
        rows.append(
            f'<li><span class="d"><a href="{d.name}/">{pretty}</a></span>'
            f'<span>{html.escape(title)}</span>'
            f'{f"<span>· devlog {html.escape(devlog)}</span>" if devlog else ""}'
            f'<span class="n">화면 {n}장</span></li>')

    body = f"""<header>
  <h1>DiaRUGA 미리보기 <span class="sub">배포 전 화면을 날짜별로 쌓아 둔 자리</span></h1>
</header>
<main>
  <p style="color:#8b93a3;font-size:13px">사본 DB 로 찍은 정지 화면입니다.
    운영 뷰어는 <a href="/DiaRUGA/">/DiaRUGA/</a> 입니다.</p>
  <ul class="days">
{chr(10).join(rows) if rows else '<li>아직 올린 것이 없습니다.</li>'}
  </ul>
</main>"""
    (ROOT / "index.html").write_text(_page("DiaRUGA 미리보기", body),
                                     encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", type=Path,
                    help="PNG 이 든 디렉토리. 주지 않으면 첫 페이지만 다시 그린다")
    ap.add_argument("--date", default=date.today().strftime("%Y%m%d"),
                    help="날짜 디렉토리 이름 (기본: 오늘)")
    ap.add_argument("--title", default="", help="그날 무엇을 만들었는가 (한 줄)")
    ap.add_argument("--devlog", default="", help="딸린 devlog 번호 (예: 049)")
    a = ap.parse_args()

    ROOT.mkdir(parents=True, exist_ok=True)
    if a.src:
        out = publish(a.src, a.date, a.title, a.devlog)
        print(f"올렸다: {out}")
        nas = _mirror_to_nas(a.date, out)
        if nas:
            print(f"NAS:   {nas}  (N:\\DiaRUGA\\preview\\{a.date})")
    reindex()
    print("http://172.16.116.98/DiaRUGA-preview/")


if __name__ == "__main__":
    main()
