#!/usr/bin/env python3
"""논문·도감 PDF 를 사내 OCR 서버에 넣고 쪽마다 파일로 떨어뜨린다
(devlog/20260828_P21_ocr-server.md 의 설계 7절 · 첫 시험 가동).

    python tools/ocr_pdf.py Diadiction/papers/1996_lee_bransfield_cores.pdf

**NAS 를 보므로 `tools/` 자리다** — `render_atlas_pages.py` 와 같은 이유로
컨테이너가 `/nfs/temp-share` 를 못 봐서 `/srv` 로 안 간다.

## 떨어뜨릴 때 그 자리에서 하는 것 둘 (설계 4장 1·3번)

- **쪽 번호 +1** — 서버 응답은 0-based(`page: 0`), 이 저장소는 전부 1-based
  (`pNNNN.png`). 파일 이름에서 한 번만 더하고 안에서는 다시 안 만진다
- **`data-label="Image"` 안의 산문·`<img alt>` 를 걷는다** — 도판면을 보고
  없는 학명을 지어내는 자리라 자료가 아니다(같은 devlog 2절). 원본은
  `.raw.html` 로 같이 남겨 나중에 확인할 수 있게 한다

## `client_id` 를 고정하는 이유 (설계 4장 6번)

같은 PDF 를 다시 올려도 LLM 표집이라 매번 같은 글자가 안 나온다. `client_id`
를 `diaruga` 로 못 박아 두면 **완료된 job 은 그대로 재사용**되고(dedup),
**`job_id` 를 `job.json` 에 남겨 "이 값이 어디서 왔나" 를 물을 자리를 만든다.**
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE_URL = "http://172.16.112.150:8080"
CLIENT_ID = "diaruga"


def post_pdf(pdf: Path, client_id: str) -> dict:
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(pdf.name)[0] or "application/pdf"
    parts = []
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="client_id"\r\n\r\n'
        f"{client_id}\r\n".encode()
    )
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{pdf.name}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n".encode()
    )
    parts.append(pdf.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        f"{BASE_URL}/ocr", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def get_job(job_id: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}/ocr/{job_id}", timeout=60) as r:
        return json.loads(r.read())


def get_stats() -> dict:
    with urllib.request.urlopen(f"{BASE_URL}/api/stats", timeout=10) as r:
        return json.loads(r.read())


# 도판면 산문·<img alt> 를 걷는다. 정규식 하나로는 중첩을 못 세므로
# div 깊이를 세는 얕은 스캐너를 쓴다 — 이 서버 출력이 div 중심이라 이걸로 충분하다
_DIV_OPEN = re.compile(r"<div\b[^>]*>", re.I)
_DIV_CLOSE = re.compile(r"</div\s*>", re.I)
_IMAGE_LABEL = re.compile(r'data-label="(Image|Figure)"', re.I)


def strip_image_prose(html: str) -> str:
    out = []
    i = 0
    n = len(html)
    while i < n:
        m = _DIV_OPEN.match(html, i)
        if m and _IMAGE_LABEL.search(m.group(0)):
            depth = 1
            j = m.end()
            while depth and j < n:
                om = _DIV_OPEN.match(html, j)
                cm = _DIV_CLOSE.match(html, j)
                if om:
                    depth += 1
                    j = om.end()
                elif cm:
                    depth -= 1
                    j = cm.end()
                else:
                    j += 1
            i = j
            continue
        out.append(html[i])
        i += 1
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--client-id", default=CLIENT_ID)
    ap.add_argument("--out", type=Path, default=None,
                     help="기본: Diadiction/ocr/<pdf stem>/ (pdf 와 같은 부모의 형제)")
    ap.add_argument("--poll-interval", type=float, default=5.0)
    args = ap.parse_args()

    pdf = args.pdf.resolve()
    out = args.out or (pdf.parent.parent / "ocr" / pdf.stem)
    out.mkdir(parents=True, exist_ok=True)

    stats = get_stats()
    print(f"서버 상태: mode={stats['mode']} · 동시성 권장 {stats['recommended_concurrency']} "
          f"· 대기 {stats['counts']['queued']}·처리중 {stats['counts']['processing']}")

    t0 = time.monotonic()
    res = post_pdf(pdf, args.client_id)
    job_id = res["job_id"]
    print(f"제출: {pdf.name} → job {job_id} (cached={res['cached']})")

    while True:
        job = get_job(job_id)
        elapsed = time.monotonic() - t0
        print(f"  {elapsed:6.1f}s  {job['done_pages']}/{job['total_pages']} 쪽 "
              f"({job['status']})")
        if job["status"] in ("done", "done_with_errors", "failed"):
            break
        time.sleep(args.poll_interval)

    elapsed = time.monotonic() - t0
    (out / "job.json").write_text(json.dumps(
        {"job_id": job_id, "client_id": args.client_id, "status": job["status"],
         "elapsed_s": round(elapsed, 1), "total_pages": job["total_pages"],
         "done_pages": job["done_pages"], "failed_pages": job["failed_pages"]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    made, failed = 0, 0
    for page in job["pages"]:
        if page is None:
            continue
        pdf_page = page["page"] + 1  # 0-based → 1-based
        if page["status"] != "ok":
            failed += 1
            (out / f"p{pdf_page:04d}.error.txt").write_text(
                page.get("error", ""), encoding="utf-8")
            continue
        raw = page["markdown"]
        (out / f"p{pdf_page:04d}.raw.html").write_text(raw, encoding="utf-8")
        (out / f"p{pdf_page:04d}.html").write_text(strip_image_prose(raw), encoding="utf-8")
        made += 1

    print(f"\n{pdf.name}: {elapsed:.1f}초 · {made}쪽 성공 · {failed}쪽 실패 → {out}")
    return 0 if job["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
