"""
규조류 뷰어 설정.

ORM 을 쓰지 않는다. 그룹핑 결과(groups_*.json)와 검출 결과(out/*.json)를
파일에서 직접 읽으므로 DATABASES 는 비워 둔다. 마이그레이션도 필요 없다.
"""
import os
from pathlib import Path

# web/diatomweb/settings.py -> web/ -> 프로젝트 루트
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

# 사내망 분석용 뷰어. 인증이 없으므로 공개망에 그대로 올릴 물건이 아니다.
SECRET_KEY = os.environ.get("DIATOM_SECRET_KEY", "dev-only-not-a-secret")
DEBUG = os.environ.get("DIATOM_DEBUG", "1") == "1"

# 이 서버가 실제로 응답할 이름만 명시한다. "*" 로 두면 DEBUG=True 와 겹칠 때
# Host 헤더 스푸핑을 그대로 받아들이게 된다.
# 다른 호스트명으로 붙어야 하면 DIATOM_HOSTS 에 콤마로 구분해 넣는다.
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "172.16.112.150",   # 이 서버의 사내망 주소
    "jikhanserver",
]
ALLOWED_HOSTS += [h.strip() for h in os.environ.get("DIATOM_HOSTS", "").split(",") if h.strip()]

# 폼이 없어 CSRF 표면은 없지만, DEBUG 를 끄고 쓸 때를 위해 맞춰 둔다.
CSRF_TRUSTED_ORIGINS = [
    f"http://{h}:9090" for h in ALLOWED_HOSTS if not h.startswith("[")
]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "viewer",
]

# 인증/세션이 없으므로 미들웨어도 최소한만.
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]

ROOT_URLCONF = "diatomweb.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

WSGI_APPLICATION = "diatomweb.wsgi.application"

DATABASES = {}

STATIC_URL = "static/"

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# --- 뷰어 전용 설정 -------------------------------------------------------

# 원본 이미지와 산출물이 놓인 곳. 이미지 서빙은 이 목록 안으로만 허용한다.
DATA_ROOT = PROJECT_ROOT
IMAGE_DIRS = ["260729", "stacked", "out", "out_hi"]

# 검출 결과(<stem>_candidates.json)를 찾을 순서.
DETECT_DIRS = ["out_hi", "out"]

# focus_stack.py 기본 출력 위치.
STACK_DIR = "stacked"

# 사람이 교정한 결과(오검출 제거 / 누락 복구). 산출물이 아니라 사람의 판단이므로
# out/ 과 달리 재생성되지 않는다 — 지우면 복구할 수 없다.
REVIEW_DIR = "review"

# 썸네일 캐시. 원본이 2752x2208 이라 그리드에 원본을 그대로 물리면 못 쓴다.
THUMB_CACHE = BASE_DIR / ".thumbcache"
