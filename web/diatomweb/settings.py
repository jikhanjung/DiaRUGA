"""
규조류 뷰어 설정.

데이터와 설정은 SQLite(`diatom.db`)에 모은다. 이전에는 JSON 을 직접 읽었는데
(슬라이드 3장에 첫 화면이 251개 파일을 열었다) NAS 로 사진이 계속 들어오면
선형으로 늘어나고, 실행 이력·처리 상태·문턱 이력을 둘 곳이 없었다.
자세한 것은 devlog/20260730_P02_db-schema.md.

JSON 은 내보내기 형식으로 남는다 — 특히 `review/*.json` 은 사람이 읽고 diff 할
감사 기록이라 계속 git 에 둔다(DB 파일은 gitignore).
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

# GPU 배치가 쓰는 동안 뷰어가 읽어야 하므로 WAL 이 필수다. 기본 journal 모드면
# 쓰기 트랜잭션이 읽기를 막는다.
DIATOM_DB = Path(os.environ.get("DIATOM_DB", PROJECT_ROOT / "diatom.db"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DIATOM_DB,
        "OPTIONS": {
            "timeout": 20,
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA foreign_keys=ON;"
            ),
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
