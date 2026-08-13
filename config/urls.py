from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import include, path

from rankings.views import health
from users.forms import LoginForm


def ads_txt(request):
    return HttpResponse(
        "google.com, pub-3862816878614020, DIRECT, f08c47fec0942fa0\n",
        content_type="text/plain; charset=utf-8",
    )


urlpatterns = [
    path("ads.txt", ads_txt, name="ads_txt"),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=LoginForm,
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("users.urls")),
    path("universities/", include("universities.urls")),
    path("admissions/", include("admissions.urls")),
    path("health/", health, name="health"),
    path("", include("rankings.urls")),
]
