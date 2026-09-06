from django.urls import path

from . import views


app_name = "rankings"

urlpatterns = [
    path("", views.home, name="home"),
    path("rankings/", views.ranking_hub, name="ranking_hub"),
    path("vs/", views.vote_page, {"slug": "overall"}, name="vote_default"),
    path("vs/<slug:slug>/", views.vote_page, name="vote"),
    path("vs/<slug:slug>/submit/", views.submit_vote, name="submit_vote"),
    path("ranking/", views.ranking_page, {"slug": "overall"}, name="ranking_default"),
    path("ranking/<slug:slug>/", views.ranking_page, name="ranking"),
    path("result/create/<slug:slug>/", views.create_personal_result, name="create_personal_result"),
    path("result/<uuid:result_id>/", views.personal_result, name="personal_result"),
    path("api/v1/boards/<slug:slug>/next/", views.api_next_pair, name="api_next_pair"),
    path("api/v1/boards/<slug:slug>/vote/", views.api_vote, name="api_vote"),
    path("api/v1/boards/<slug:slug>/ranking/", views.api_ranking, name="api_ranking"),
]
