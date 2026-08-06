"""브라우저 시험의 바닥. `LiveServerTestCase` + playwright.

**`pageerror` 를 기본으로 건다.** 045 에서 `?shot=last` 가 JS 를 죽이고 있었는데
화면은 200 이었다 — 콘솔을 안 보면 "떴다" 와 "돈다" 를 구별할 수 없다. 그래서
모든 시험이 끝날 때 **JS 오류가 하나라도 있으면 실패**한다. 시험마다 기억해서
확인하게 두면 빠뜨리는 시험이 생긴다.
"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

# **playwright 의 동기 API 는 이벤트 루프 위에서 돈다.** 그래서 Django 의
# `async_unsafe` 검사가 ORM 호출을 `SynchronousOnlyOperation` 으로 막는다 —
# 시험 본체가 아니라 픽스처·flush 같은 뒤처리에서 터져서 원인이 잘 안 보인다.
# 여기서 푸는 것이 맞다: 진짜 async 서버가 아니라 **시험이 만든 루프**이고,
# 이 모듈은 브라우저 시험만 임포트한다.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag

from ..base import assert_test_db, assert_sandboxed_root, _TMP_PREFIX

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                     # pragma: no cover
    sync_playwright = None


@tag("browser")
class BrowserTestCase(StaticLiveServerTestCase):
    """진짜 크로미움으로 이 앱을 연다.

    **`browser` 로 표를 달아 둔다.** 1~3겹만 돌릴 때
    `--exclude-tag browser` 로 뺀다 — 이 겹은 크로미움이 있어야 하고 30배
    느리다. 표가 없으면 `manage.py test viewer` 가 늘 함께 끌고 간다.

    `_SafeRootsMixin` 을 상속하지 않고 뿌리 갈이를 다시 적는다 —
    `StaticLiveServerTestCase` 는 `setUpClass` 에서 서버까지 띄우므로 순서가
    한 겹 더 있고, 그것을 섞으면 어느 쪽이 먼저인지가 안 보인다. **순서를 잘못
    잡아 시험이 `/data3` 에 쓴 적이 있다** (`..base` 머리말).
    """

    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise unittest.SkipTest("playwright 가 없다 — requirements-dev.txt")

        assert_test_db()
        cls._tmp = Path(tempfile.mkdtemp(prefix=_TMP_PREFIX))
        cls._saved = {k: getattr(settings, k)
                      for k in ("DATA_ROOT", "THUMB_CACHE", "OUTCROP_DIR")}
        settings.DATA_ROOT = cls._tmp / "data"
        settings.THUMB_CACHE = cls._tmp / "thumbs"
        settings.OUTCROP_DIR = cls._tmp / "없는-노두-공유"
        for d in settings.DATA_ROOT, settings.THUMB_CACHE:
            d.mkdir(parents=True, exist_ok=True)
        assert_sandboxed_root()

        try:
            super().setUpClass()            # 여기서 서버가 뜨고 픽스처가 돈다
            cls._pw = sync_playwright().start()
            try:
                cls._browser = cls._pw.chromium.launch()
            except Exception as e:          # 크로미움을 안 깔았다
                cls._pw.stop()
                raise unittest.SkipTest(
                    f"크로미움을 못 띄웠다 ({e}) — `playwright install chromium`")
        except Exception:
            cls._restore()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "_browser", None):
                cls._browser.close()
            if getattr(cls, "_pw", None):
                cls._pw.stop()
            super().tearDownClass()
        finally:
            cls._restore()

    @classmethod
    def _restore(cls):
        for k, v in getattr(cls, "_saved", {}).items():
            setattr(settings, k, v)
        shutil.rmtree(getattr(cls, "_tmp", ""), ignore_errors=True)

    # --- 각 시험 ----------------------------------------------------------

    def setUp(self):
        # **`setUpTestData` 를 쓸 수 없다.** `LiveServerTestCase` 는
        # `TransactionTestCase` 라서 표를 시험마다 비운다 — 클래스 한 번만
        # 만든 자료는 두 번째 시험에서 사라진다. 픽스처는 여기서 세운다.
        self.make_data()
        self.errors = []
        self.ctx = self._browser.new_context(viewport={"width": 1400,
                                                       "height": 900})
        self.page = self.ctx.new_page()
        # **이 두 줄이 이 겹의 값어치다.** 화면이 200 이어도 JS 가 죽어 있으면
        # 아무 버튼도 안 듣는다 (045).
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.on("console", lambda m: (
            self.errors.append(f"console.error: {m.text}")
            if m.type == "error" else None))

    def tearDown(self):
        errors = list(self.errors)
        self.ctx.close()
        self.assertEqual(errors, [], f"JS 오류가 났다:\n" + "\n".join(errors))

    def make_data(self):
        """시험마다 세울 자료. 하위 클래스가 채운다."""

    def open(self, path):
        """앱의 주소 하나를 연다. `path` 는 `reverse()` 가 낸 것."""
        self.page.goto(f"{self.live_server_url}{path}", wait_until="load")
        return self.page
