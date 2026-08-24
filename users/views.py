from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from admissions.models import AdmissionResult, RecruitmentUnit
from admissions.university_detail_views import _build_core_summary
from rankings.baseline import ranking_university_queryset
from rankings.models import ComparisonVote, RankingBoard, UniversityRating
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


def _unique_ints(values):
    result = []
    seen = set()
    for value in values:
        try:
            value = int(value)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _summary_values(university, year):
    cards = {card["key"]: card for card in _build_core_summary(university, year)} if year else {}

    def value(track, percentile):
        card = cards.get(track)
        if not card:
            return None
        aggregate = card.get(f"value_{percentile}")
        return aggregate.value if aggregate else None

    return {
        "student_50": value("student", 50),
        "student_70": value("student", 70),
        "holistic_50": value("holistic", 50),
        "holistic_70": value("holistic", 70),
        "csat_50": value("csat", 50),
        "csat_70": value("csat", 70),
    }


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
def favorite_university_compare(request):
    selected_ids = _unique_ints(request.GET.getlist("university"))
    selection_error = ""

    if len(selected_ids) < 2:
        selection_error = "관심 대학을 2개 이상 선택해주세요."
    elif len(selected_ids) > 3:
        selection_error = "관심 대학은 최대 3개까지 비교할 수 있습니다."

    favorites = (
        FavoriteUniversity.objects.filter(
            user=request.user,
            university_id__in=selected_ids[:3],
        )
        .select_related("university")
    )
    favorite_map = {favorite.university_id: favorite.university for favorite in favorites}
    universities = [favorite_map[university_id] for university_id in selected_ids[:3] if university_id in favorite_map]

    if selected_ids and len(universities) != min(len(selected_ids), 3):
        selection_error = "현재 관심 대학으로 저장된 대학만 비교할 수 있습니다."
    if len(universities) < 2:
        universities = []

    comparison_items = []
    comparison_year = None
    mixed_years = False

    if universities and not selection_error:
        university_ids = [university.pk for university in universities]
        year_map = {university_id: set() for university_id in university_ids}
        for university_id, admission_year in (
            AdmissionResult.objects.filter(university_id__in=university_ids)
            .values_list("university_id", "admission_year")
            .distinct()
        ):
            year_map[university_id].add(admission_year)

        year_sets = [year_map[university_id] for university_id in university_ids]
        common_years = set.intersection(*year_sets) if year_sets and all(year_sets) else set()
        if common_years:
            comparison_year = max(common_years)
        else:
            mixed_years = True

        rating_map = {}
        board = RankingBoard.objects.filter(slug="overall", is_active=True).first()
        if board:
            eligible_ids = ranking_university_queryset().values_list("university_id", flat=True)
            ratings = (
                UniversityRating.objects.filter(
                    board=board,
                    university_id__in=eligible_ids,
                    match_count__gte=0,
                )
                .select_related("university")
                .order_by("-rating", "university__name")
            )
            for rank, rating in enumerate(ratings, start=1):
                if rating.university_id in university_ids:
                    rating_map[rating.university_id] = {
                        "rank": rank,
                        "rating": rating.rating,
                        "match_count": rating.match_count,
                        "rating_deviation": rating.rating_deviation,
                    }

        for university in universities:
            admission_year = comparison_year
            if admission_year is None and year_map[university.pk]:
                admission_year = max(year_map[university.pk])

            comparison_items.append(
                {
                    "university": university,
                    "admission_year": admission_year,
                    "rating": rating_map.get(university.pk),
                    **_summary_values(university, admission_year),
                }
            )

    return render(
        request,
        "users/university_compare.html",
        {
            "comparison_items": comparison_items,
            "comparison_year": comparison_year,
            "mixed_years": mixed_years,
            "selection_error": selection_error,
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
