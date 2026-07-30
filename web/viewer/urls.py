from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("img", views.image, name="image"),
    path("crop", views.crop, name="crop"),
    path("healthz", views.healthz, name="healthz"),
    path("review", views.save_review, name="save_review"),
    path("d/<slug:slug>/", views.dataset, name="dataset"),
    path("d/<slug:slug>/detections/", views.detections, name="detections"),
    path("d/<slug:slug>/crops/", views.crops, name="crops"),
    path("d/<slug:slug>/g/<int:gid>/", views.group, name="group"),
    path("api/d/<slug:slug>.json", views.api_dataset, name="api_dataset"),
]
