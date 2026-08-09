from django.urls import path

from . import views


app_name = "admissions"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("results/", views.overview_results, name="overview_results"),
    path("ranking/", views.admission_ranking, name="ranking"),
    path("university/<int:university_id>/", views.university_admissions, name="university"),
]
