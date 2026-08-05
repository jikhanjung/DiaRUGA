"""템플릿이 늘 쓰는 값 — 판 번호와 미리보기로 가는 길.

**판을 화면에 띄우는 이유**: 배포가 실제로 갈렸는지, 지금 보는 화면이 어느
판인지를 눈으로 확인할 수 있어야 한다. 오늘만 뷰어를 여섯 번 구웠고, 그중
한 번은 판 번호가 파이프라인을 끌고 가 자동 수집을 4시간 반 멈추게 했다
(devlog 026). 그런 일이 났을 때 "지금 뭐가 떠 있나" 를 묻는 데가 있어야 한다.

값은 `.env` 의 `IMAGE_TAG` 에서 온다 — compose 가 `env_file` 로 통째로 넘긴다.
배포 스크립트가 그 한 줄을 고치므로 **배포한 것과 화면에 뜨는 것이 같은 값**이다.
개발 서버처럼 그 변수가 없는 자리에서는 아무것도 안 보인다.

## 미리보기

바꾼 화면을 찍어 둔 **정지 화면 갤러리**가 80 의 `/DiaRUGA-preview/` 에 날짜별로
쌓여 있다(`tools/publish_preview.py`, 실제 자리는 `/srv/paleolab/DiaRUGA-preview/`).
거기로 가는 길이 화면에 없으면 주소를 직접 쳐야 한다 — 머리글 오른쪽 구석에
작게 낸다.

**경로를 템플릿에 박지 않는다.** 이 앱의 URL 이 아니라 nginx 가 정하는 이웃
자리라 `reverse()` 로 못 만든다 — 그래서 환경변수로 받는다. 비우면 안 보인다.
"""
import os

# `tools/publish_preview.py` 가 내보내는 자리다. 규칙이 갈라지면 버튼이 404 로
# 간다 — 고칠 때 그 스크립트와 함께 본다.
DEFAULT_PREVIEW_URL = "/DiaRUGA-preview/"


def version(request):
    return {
        "image_tag": os.environ.get("IMAGE_TAG", ""),
        "preview_url": os.environ.get("DIARUGA_PREVIEW_URL",
                                      DEFAULT_PREVIEW_URL).strip(),
    }
