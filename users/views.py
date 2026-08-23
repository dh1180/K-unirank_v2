from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from admissions.models import RecruitmentUnit
from rankings.models import ComparisonVote
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


def _user_vs_votes(user):
    return (
        ComparisonVote.objects.filter(session__user=user)
        .select_related(
            "board",
            "university_a",
            "university_b",
            "selected_university",
        )
        .order_by("-created_at", "-vote_id")
    )


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

    vs_votes = _user_vs_votes(request.user)
    vs_total_count = vs_votes.count()
    vs_skipped_count = vs_votes.filter(skipped=True).count()
    vs_selected_count = vs_total_count - vs_skipped_count
    vs_recent_votes = list(vs_votes[:4])

    return render(
        request,
        "users/mypage.html",
        {
            "favorite_universities": favorite_universities,
            "favorite_units": favorite_units,
            "vs_recent_votes": vs_recent_votes,
            "vs_total_count": vs_total_count,
            "vs_selected_count": vs_selected_count,
            "vs_skipped_count": vs_skipped_count,
        },
    )


@login_required
def vs_history(request):
    vs_votes = _user_vs_votes(request.user)
    vs_total_count = vs_votes.count()
    vs_skipped_count = vs_votes.filter(skipped=True).count()
    vs_selected_count = vs_total_count - vs_skipped_count
    vs_page_obj = Paginator(vs_votes, 20).get_page(request.GET.get("page"))

    return render(
        request,
        "users/vs_history.html",
        {
            "vs_page_obj": vs_page_obj,
            "vs_total_count": vs_total_count,
            "vs_selected_count": vs_selected_count,
            "vs_skipped_count": vs_skipped_count,
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
