from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from rankings.views import health
from users.forms import LoginForm


urlpatterns = [
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
