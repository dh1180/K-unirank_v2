from django.urls import path

from . import views


app_name = "universities"

urlpatterns = [
    path("", views.university_list, name="list"),
    path("indicators/<slug:indicator_slug>/", views.indicator_ranking, name="indicator_ranking"),
    path("<int:university_id>/", views.university_detail, name="detail"),
]
