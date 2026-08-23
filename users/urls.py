from django.urls import path

from . import views


app_name = "users"
urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("me/", views.mypage, name="mypage"),
    path("me/vs-history/", views.vs_history, name="vs_history"),
    path(
        "favorites/university/<int:university_id>/toggle/",
        views.toggle_favorite_university,
        name="toggle_favorite_university",
    ),
    path(
        "favorites/recruitment-unit/<int:recruitment_unit_id>/toggle/",
        views.toggle_favorite_recruitment_unit,
        name="toggle_favorite_recruitment_unit",
    ),
]
