from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("img", views.image, name="image"),
    path("crop", views.crop, name="crop"),
    path("healthz", views.healthz, name="healthz"),
    path("review", views.save_review, name="save_review"),
    path("d/<slug:slug>/", views.dataset, name="dataset"),
    path("d/<slug:slug>/edit/", views.dataset_edit, name="dataset_edit"),
    path("d/<slug:slug>/detections/", views.detections, name="detections"),
    path("d/<slug:slug>/crops/", views.crops, name="crops"),
    path("thresholds/", views.threshold_page, name="thresholds_all"),
    path("d/<slug:slug>/thresholds/", views.threshold_page, name="thresholds"),
    path("api/threshold/preview", views.threshold_preview, name="threshold_preview"),
    path("api/threshold/apply", views.threshold_apply, name="threshold_apply"),
    path("api/threshold/masks", views.threshold_masks, name="threshold_masks"),
    path("api/threshold/history", views.threshold_history, name="threshold_history"),
    path("d/<slug:slug>/g/<int:gid>/", views.group, name="group"),
    path("api/d/<slug:slug>.json", views.api_dataset, name="api_dataset"),
]
