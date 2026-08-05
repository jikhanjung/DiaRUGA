from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("img", views.image, name="image"),
    path("crop", views.crop, name="crop"),
    path("healthz", views.healthz, name="healthz"),
    path("review", views.save_review, name="save_review"),
    # 코어 하나 — 깊이 방향으로 본 화면. **코어 코드는 지역마다 겹칠 수 있다**
    # (`Core` 의 unique 가 `(site, code)` 다). 주소도 그 짝이어야 한다.
    path("core/<str:site_code>/<str:core_code>/", views.core_page, name="core"),
    path("d/<slug:slug>/", views.dataset, name="dataset"),
    path("d/<slug:slug>/edit/", views.dataset_edit, name="dataset_edit"),
    path("d/<slug:slug>/detections/", views.detections, name="detections"),
    path("d/<slug:slug>/crops/", views.crops, name="crops"),
    # 시험용 — is_current 가 아닌 검출(다른 엔진)을 보는 길. 읽기 전용이다.
    path("engine/", views.engine_index, name="engine_index"),
    path("engine/<int:run_id>/", views.engine_run, name="engine_run"),
    path("engine/<int:run_id>/<slug:slug>/<int:gid>/", views.engine_view,
         name="engine_view"),
    path("thresholds/", views.threshold_page, name="thresholds_all"),
    path("d/<slug:slug>/thresholds/", views.threshold_page, name="thresholds"),
    path("api/threshold/preview", views.threshold_preview, name="threshold_preview"),
    path("api/threshold/apply", views.threshold_apply, name="threshold_apply"),
    path("api/threshold/masks", views.threshold_masks, name="threshold_masks"),
    path("api/threshold/history", views.threshold_history, name="threshold_history"),
    path("d/<slug:slug>/g/<int:gid>/", views.group, name="group"),
    # 시야 가르기. POST 전용이고 confirm=1 인 두 번째 POST 만 실제로 고친다.
    path("d/<slug:slug>/g/<int:gid>/split", views.split_group,
         name="split_group"),
    path("api/d/<slug:slug>.json", views.api_dataset, name="api_dataset"),
]
