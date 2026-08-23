from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path

from admissions import filter_views as admission_filter_views
from rankings.views import health
from users.forms import LoginForm

from .sitemaps import sitemaps


def ads_txt(request):
    return HttpResponse(
        "google.com, pub-3862816878614020, DIRECT, f08c47fec0942fa0\n",
        content_type="text/plain; charset=utf-8",
    )


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "Disallow: /health/",
        "Disallow: /result/",
        "",
        "Sitemap: https://www.k-unirank.com/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")


urlpatterns = [
    # v84: 입결 찾기를 사이트의 canonical root/home으로 사용
    path("", admission_filter_views.overview, name="home"),
    path("ads.txt", ads_txt, name="ads_txt"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
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
