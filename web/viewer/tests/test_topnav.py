"""최상위 길 — **시스템 설정**(톱니)과 그 안의 **미리보기** 탭 (089).

시스템 설정은 데이터셋 목록과 같은 층의 최상위 메뉴다(사용자 방침 2026-08-08).
그래서 목록 화면의 제목 옆이 아니라 **머리줄 오른쪽 끝**에 톱니로 서고,
어느 화면에서나 같은 자리에 있다. `/manage/` 는 **소속을 잃은 관찰을 잡아 주는
유일한 화면**이라(063) 길이 끊기면 그 화면이 없는 것과 같다.

여기서 지키는 것 셋.

1. **모든 화면에 톱니가 있다** — `base.html` 에 있으니 당연할 것 같지만, 머리줄은
   블록이 여럿이라 한 화면이 통째로 덮어쓸 수 있다
2. **미리보기 탭이 실제로 나온다** — `_managenav.html` 을 `only` 로 include 하는데,
   그것이 바깥 컨텍스트를 끊어 컨텍스트 프로세서의 `preview_url` 이 안 들어간다.
   **안 넘기면 탭이 예외도 경고도 없이 사라진다** — 실제로 그렇게 한 번 짰다
3. **경로가 없으면 탭도 없다** — 죽은 탭을 내보이면 눌러 보고서야 안다
"""
import re

from django.test import Client, override_settings
from django.urls import reverse

from .base import DiaRUGATestCase
from . import factories as fx


class TopNavTest(DiaRUGATestCase):

    @classmethod
    def setUpTestData(cls):
        fx.make_classes()
        cls.w = fx.make_world(slug="rs23", n_candidates=2)

    def setUp(self):
        self.c = Client()

    def pages(self):
        slug = self.w.slide.slug
        return [("데이터셋 목록", reverse("index")),
                ("시야 목록", reverse("dataset", args=[slug])),
                ("검출 갤러리", reverse("crops", args=[slug])),
                ("계측 표", reverse("detections", args=[slug])),
                ("시야 화면", reverse("group", args=[slug, self.w.vp.idx])),
                ("시스템 설정 · 자료", reverse("system_settings")),
                ("시스템 설정 · 운영", reverse("system_settings_ops"))]

    def test_모든_화면에_시스템_설정_톱니가_있다(self):
        for name, url in self.pages():
            with self.subTest(화면=name):
                html = self.c.get(url).content.decode()
                m = re.search(r'<a class="gearlink"[^>]*>', html)
                self.assertIsNotNone(m, f"{name} 에 톱니가 없다")
                self.assertIn(reverse("system_settings"), m.group(0))
                # 아이콘만 있는 링크라 읽어 줄 이름이 따로 있어야 한다
                self.assertIn("시스템 설정", m.group(0))

    def test_목록_제목_옆의_옛_관리_링크는_없다(self):
        """최상위 메뉴가 목록의 하위처럼 보이면 안 된다."""
        html = self.c.get(reverse("index")).content.decode()
        head = html[html.index("<h2>데이터셋"):]
        self.assertNotIn("관리 →", head[:400])

    def test_미리보기_탭이_시스템_설정에_나온다(self):
        """**`only` 가 컨텍스트를 끊는다.** `preview_url` 을 손으로 안 넘기면
        탭이 조용히 사라진다 — 예외도 경고도 없다."""
        for url in (reverse("system_settings"), reverse("system_settings_ops"),
                    reverse("system_settings_dataset")):
            with self.subTest(화면=url):
                html = self.c.get(url).content.decode()
                nav = re.search(r'<nav class="mnav">.*?</nav>', html, re.S)
                self.assertIsNotNone(nav, f"{url} 에 탭줄이 없다")
                self.assertIn("미리보기", nav.group(0), "미리보기 탭이 없다")
                self.assertIn("/DiaRUGA-preview/", nav.group(0))

    def test_미리보기는_머리줄에서_빠졌다(self):
        """시스템 설정 안으로 옮겼다 — 두 자리에 있으면 어느 쪽이 정본인지 묻게 된다."""
        html = self.c.get(reverse("index")).content.decode()
        self.assertNotIn('class="envlink"', html)

    def test_경로가_없으면_탭도_없다(self):
        with override_settings():
            import os
            old = os.environ.get("DIARUGA_PREVIEW_URL")
            os.environ["DIARUGA_PREVIEW_URL"] = ""
            try:
                html = self.c.get(reverse("system_settings")).content.decode()
                nav = re.search(r'<nav class="mnav">.*?</nav>', html, re.S).group(0)
                self.assertNotIn("미리보기", nav,
                                 "경로가 없는데 죽은 탭이 나온다")
            finally:
                if old is None:
                    os.environ.pop("DIARUGA_PREVIEW_URL", None)
                else:
                    os.environ["DIARUGA_PREVIEW_URL"] = old

    # --- 옛 주소 ----------------------------------------------------------

    def test_옛_manage_주소가_새_주소로_넘긴다(self):
        """`/manage/` → `/settings/`. **지우지 않는다** — 사내에 퍼진 링크와
        브라우저 기록이 조용히 깨진다. `core/` → `loc/` 와 같은 갈래다."""
        for old, name in [("/manage/", "system_settings"),
                          ("/manage/ops/", "system_settings_ops"),
                          ("/manage/dataset/", "system_settings_dataset")]:
            with self.subTest(옛주소=old):
                r = self.c.get(old)
                self.assertIn(r.status_code, (301, 302), r.status_code)
                self.assertEqual(r["Location"], reverse(name))

    def test_리다이렉트가_쿼리를_잃지_않는다(self):
        """저장 뒤 `?msg=…` 로 돌아오는 길이 있다 — 옛 주소를 북마크한 사람이
        그 메시지를 잃으면 "저장이 됐나" 를 묻게 된다."""
        r = self.c.get("/manage/ops/?msg=%ED%99%95%EC%9D%B8&x=1")
        self.assertEqual(r["Location"],
                         reverse("system_settings_ops") + "?msg=%ED%99%95%EC%9D%B8&x=1")
