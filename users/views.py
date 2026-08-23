from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from admissions.models import RecruitmentUnit
from universities.models import University

from .forms import SignUpForm
from .models import FavoriteRecruitmentUnit, FavoriteUniversity


def _safe_next(request, fallback="users:mypage"):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return reverse(fallback)


def signup(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(_safe_next(request))
    else:
        form = SignUpForm()

    return render(
        request,
        "registration/signup.html",
        {
            "form": form,
            "next": request.POST.get("next") or request.GET.get("next", ""),
        },
    )


@login_required
def mypage(request):
    favorite_universities = list(
        FavoriteUniversity.objects.filter(user=request.user)
        .select_related("university")
        .order_by("-created_at", "university__name")
    )
    favorite_units = list(
        FavoriteRecruitmentUnit.objects.filter(user=request.user)
        .select_related(
            "recruitment_unit",
            "recruitment_unit__university",
            "recruitment_unit__campus",
        )
        .order_by("-created_at", "recruitment_unit__university__name", "recruitment_unit__name")
    )

    return render(
        request,
        "users/mypage.html",
        {
            "favorite_universities": favorite_universities,
            "favorite_units": favorite_units,
        },
    )


@login_required
@require_POST
def toggle_favorite_university(request, university_id):
    university = get_object_or_404(
        University,
        pk=university_id,
        is_active=True,
    )
    favorite, created = FavoriteUniversity.objects.get_or_create(
        user=request.user,
        university=university,
    )
    if not created:
        favorite.delete()
    return redirect(_safe_next(request))


@login_required
@require_POST
def toggle_favorite_recruitment_unit(request, recruitment_unit_id):
    recruitment_unit = get_object_or_404(
        RecruitmentUnit.objects.select_related("university"),
        pk=recruitment_unit_id,
        is_active=True,
        university__is_active=True,
    )
    favorite, created = FavoriteRecruitmentUnit.objects.get_or_create(
        user=request.user,
        recruitment_unit=recruitment_unit,
    )
    if not created:
        favorite.delete()
    return redirect(_safe_next(request))
