from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("img", views.image, name="image"),
    path("crop", views.crop, name="crop"),
    path("healthz", views.healthz, name="healthz"),
    path("review", views.save_review, name="save_review"),
    # 지점 하나 — 위치 방향으로 본 화면. **지점 코드는 지역마다 겹칠 수 있다**
    # (`Locality` 의 unique 가 `(site, code)` 다). 주소도 그 짝이어야 한다.
    path("loc/<str:site_code>/<str:core_code>/", views.core_page, name="core"),
    # 옛 주소. **지우지 않는다** — 적어 둔 링크와 브라우저 기록이 깨진다.
    # 이름(`core`)은 그대로 둔다: 템플릿의 `{% url 'core' %}` 가 새 주소를 낸다.
    path("core/<str:site_code>/<str:core_code>/", views.core_redirect),
    # **시스템 설정** — 층을 만들고 고치고 지운다. 쓰기는 전부 POST 다.
    # 화면 셋 (083). 묻는 것이 달라 갈랐다 — `_managenav.html` 머리말.
    #
    # **데이터셋 목록과 같은 층의 최상위 메뉴다** (사용자 방침 2026-08-08).
    # 그래서 주소도 `/manage/` 에서 옮겼고, 머리줄 오른쪽 끝의 톱니가 어느
    # 화면에서나 여기로 온다.
    #
    # **주소는 붙임표, 파이썬 이름은 밑줄이다.** 주소 쪽은 이 저장소의
    # `mark-all/` 과 같은 관례이고, 이름 쪽은 식별자라 밑줄이어야 한다.
    #
    # **`settings` 를 안 쓴다.** `django.conf.settings` 와 부딪혀서 뷰 함수를
    # 그 이름으로 둘 수 없고, 그러면 주소·URL 이름과 함수 이름이 갈린다.
    # `system_settings` 는 아무것도 안 가려서 **끝까지 같은 이름**으로 간다
    # (주소 · URL 이름 · 뷰 함수 · 템플릿 파일).
    path("system-settings/", views.system_settings, name="system_settings"),
    path("system-settings/ops/", views.system_settings_ops,
         name="system_settings_ops"),
    path("system-settings/dataset/", views.system_settings_dataset,
         name="system_settings_dataset"),
    path("system-settings/pipeline/", views.system_settings_pipeline,
         name="system_settings_pipeline"),
    # 옛 주소. **지우지 않는다** — 적어 둔 링크와 브라우저 기록이 깨진다.
    # `core/` 와 같은 갈래이고 같은 이유로 302 다(301 은 브라우저가 캐시해서
    # 나중에 규칙을 다시 손볼 때 되돌릴 방법이 없다).
    #
    # **`/settings/` 는 안 남긴다.** 오늘 몇 분 동안 테스트 인스턴스에만
    # 있었고 운영에 나간 적이 없다 — 아무도 적어 두지 않은 주소를 영구히
    # 이고 갈 이유가 없다.
    path("manage/", views.settings_redirect),
    path("manage/ops/", views.settings_redirect, {"tab": "ops"}),
    path("manage/dataset/", views.settings_redirect, {"tab": "dataset"}),
    # 노두 현장 사진. **파일 이름이 주소에 없다** — 지점과 순번으로만 짚는다.
    path("loc/<str:site_code>/<str:core_code>/photo/<int:index>",
         views.outcrop_photo, name="outcrop_photo"),
    # 올리기·지우기. POST 전용이다.
    path("loc/<str:site_code>/<str:core_code>/photos/",
         views.outcrop_edit, name="outcrop_edit"),
    path("d/<slug:slug>/", views.dataset, name="dataset"),
    path("d/<slug:slug>/edit/", views.dataset_edit, name="dataset_edit"),
    # 시야 전체를 검토/미검토로. **POST 전용이다** — 주소를 누르는 것만으로
    # 슬라이드 하나의 판단이 뒤집히면 안 된다.
    path("d/<slug:slug>/mark-all/", views.mark_all, name="mark_all"),
    path("d/<slug:slug>/detections/", views.detections, name="detections"),
    path("d/<slug:slug>/crops/", views.crops, name="crops"),
    path("thresholds/", views.threshold_page, name="thresholds_all"),
    path("d/<slug:slug>/thresholds/", views.threshold_page, name="thresholds"),
    path("api/threshold/preview", views.threshold_preview, name="threshold_preview"),
    path("api/threshold/apply", views.threshold_apply, name="threshold_apply"),
    path("api/threshold/masks", views.threshold_masks, name="threshold_masks"),
    path("api/threshold/history", views.threshold_history, name="threshold_history"),
    path("d/<slug:slug>/g/<int:gid>/", views.group, name="group"),
    # 같은 개체 묶음 (P11) — 묶음 하나 단위. /review 에 안 싣는 이유는
    # views.save_object_link 머리말에 있다.
    path("d/<slug:slug>/g/<int:gid>/link", views.save_object_link,
         name="save_link"),
    # 시야 가르기. POST 전용이고 confirm=1 인 두 번째 POST 만 실제로 고친다.
    path("d/<slug:slug>/g/<int:gid>/split", views.split_group,
         name="split_group"),
    path("api/d/<slug:slug>.json", views.api_dataset, name="api_dataset"),
]
