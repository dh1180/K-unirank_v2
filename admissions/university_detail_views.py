from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from admissions.services.metrics import metric_label, metric_unit
from universities.models import University

from .filter_views import (
    TRACK_CHOICES,
    UNIVERSITY_RESULTS_PER_PAGE,
    _apply_track_filter,
    _normalize_track,
    _phase_for_track,
)
from .models import AdmissionAggregate, AdmissionResult


def _pick_aggregate(university, year, phase, category, metric_code):
    """핵심 입결 카드에 사용할 대학 단위 집계값 하나를 고른다.

    동일 지표가 여러 집계 방식으로 존재하면 모집인원 가중평균을 우선한다.
    카테고리는 정확 일치를 먼저 찾고, 출처별 표현 차이를 위해 부분 일치를
    보조적으로 허용한다.
    """
    base = AdmissionAggregate.objects.filter(
        university=university,
        admission_year=year,
        admission_phase=phase,
        metric_code=metric_code,
    )

    candidates = base.filter(selection_category=category)
    if not candidates.exists():
        candidates = base.filter(selection_category__icontains=category)

    weighted = (
        candidates.filter(aggregation_method="WEIGHTED_BY_RECRUITMENT")
        .order_by("-sample_count", "aggregate_id")
        .first()
    )
    if weighted:
        return weighted

    return candidates.order_by("-sample_count", "aggregate_id").first()


def _build_core_summary(university, year):
    if not year:
        return []

    definitions = [
        {
            "key": "student",
            "title": "학생부교과",
            "phase": "수시",
            "phase_code": "SUSI",
            "category": "학생부교과",
            "metric_50": "STUDENT_GRADE_50_CUT",
            "metric_70": "STUDENT_GRADE_70_CUT",
            "unit": "등급",
        },
        {
            "key": "holistic",
            "title": "학생부종합",
            "phase": "수시",
            "phase_code": "SUSI",
            "category": "학생부종합",
            "metric_50": "STUDENT_GRADE_50_CUT",
            "metric_70": "STUDENT_GRADE_70_CUT",
            "unit": "등급",
        },
        {
            "key": "csat",
            "title": "수능",
            "phase": "정시",
            "phase_code": "JEONGSI",
            "category": "수능",
            "metric_50": "CSAT_PERCENTILE_MEAN_50_CUT",
            "metric_70": "CSAT_PERCENTILE_MEAN_70_CUT",
            "unit": "백분위",
        },
    ]

    cards = []
    for definition in definitions:
        value_50 = _pick_aggregate(
            university,
            year,
            definition["phase_code"],
            definition["category"],
            definition["metric_50"],
        )
        value_70 = _pick_aggregate(
            university,
            year,
            definition["phase_code"],
            definition["category"],
            definition["metric_70"],
        )

        if value_50 is None and value_70 is None:
            continue

        cards.append(
            {
                **definition,
                "value_50": value_50,
                "value_70": value_70,
            }
        )

    return cards


def university_admissions(request, university_id):
    university = get_object_or_404(University, pk=university_id, is_active=True)

    available_years = list(
        AdmissionResult.objects.filter(university=university)
        .values_list("admission_year", flat=True)
        .distinct()
        .order_by("-admission_year")
    )

    requested_year_raw = request.GET.get("year")
    show_all_years = requested_year_raw == "all"
    requested_year = None
    if requested_year_raw and not show_all_years:
        try:
            requested_year = int(requested_year_raw)
        except ValueError:
            requested_year = None

    if show_all_years:
        year = None
    elif requested_year in available_years:
        year = requested_year
    else:
        year = available_years[0] if available_years else None

    phase = request.GET.get("phase", "").strip().upper()
    if phase not in {"", "SUSI", "JEONGSI"}:
        phase = ""

    selected_track = _normalize_track(request.GET.get("track"))
    phase = _phase_for_track(selected_track, phase)
    query = request.GET.get("q", "").strip()

    results = (
        AdmissionResult.objects.filter(university=university)
        .select_related("recruitment_unit", "source", "recruitment_unit__campus")
        .prefetch_related("metrics")
    )

    if year:
        results = results.filter(admission_year=year)
    if phase:
        results = results.filter(admission_phase=phase)
    results = _apply_track_filter(results, selected_track)

    if query:
        results = results.filter(
            Q(recruitment_unit__name__icontains=query)
            | Q(selection_category__icontains=query)
            | Q(selection_name__icontains=query)
        )

    results = results.order_by(
        "-admission_year",
        "admission_phase",
        "selection_category",
        "selection_name",
        "recruitment_unit__name",
        "result_id",
    )

    result_count = results.count()
    page_obj = Paginator(results, UNIVERSITY_RESULTS_PER_PAGE).get_page(
        request.GET.get("page", 1)
    )

    # 전체 연도를 보고 있을 때도 서로 다른 학년의 집계값을 섞지 않는다.
    # 핵심 요약은 항상 선택 학년도, 또는 가장 최신 학년도 하나만 사용한다.
    summary_year = year or (available_years[0] if available_years else None)
    core_summary_cards = _build_core_summary(university, summary_year)

    return render(
        request,
        "admissions/university.html",
        {
            "university": university,
            "results": page_obj.object_list,
            "page_obj": page_obj,
            "result_count": result_count,
            "query": query,
            "years": available_years,
            "selected_year": year,
            "selected_phase": phase,
            "selected_track": selected_track,
            "show_all_years": show_all_years,
            "summary_year": summary_year,
            "core_summary_cards": core_summary_cards,
            "track_choices": TRACK_CHOICES,
            "metric_label": metric_label,
            "metric_unit": metric_unit,
        },
    )
