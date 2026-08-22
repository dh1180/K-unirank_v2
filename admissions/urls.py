from django.urls import path
from django.views.generic import RedirectView

from . import views


app_name = "admissions"

urlpatterns = [
    # /admissions/는 중복 콘텐츠를 만들지 않고 canonical root / 로 이동
    path(
        "",
        RedirectView.as_view(pattern_name="home", permanent=True, query_string=True),
        name="overview",
    ),
    path("results/", views.overview_results, name="overview_results"),
    path("ranking/", views.admission_ranking, name="ranking"),
    path("university/<int:university_id>/", views.university_admissions, name="university"),
]
