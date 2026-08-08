from django.urls import path

from . import views


app_name = "admissions"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("university/<int:university_id>/", views.university_admissions, name="university"),
]
