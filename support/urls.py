from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.index, name="index"),
    path("submitted/<uuid:pledge_id>/", views.submitted, name="submitted"),
]
