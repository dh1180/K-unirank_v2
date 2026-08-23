from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from admissions.services.metrics import metric_label, metric_unit
from universities.models import University

from .models import AdmissionAggregate, AdmissionResult
from .views import _build_procollege_metric_ranking


RESULTS_PER_PAGE = 60
UNIVERSITY_RESULTS_PER_PAGE = 60

TRACK_CHOICES = {
    "student": "학생부교과",
    "holistic": "학생부종합",
    "csat": "수능",
    "essay": "논술",
    "practical": "실기",
}


def _normalize_track(value):
    value = (value or "").strip().lower()
    return value if value in TRACK_CHOICES else ""


def _phase_for_track(track, phase):
    """전형 유형만 고른 경우 자연스러운 모집 구분을 자동 선택한다."""
    if phase:
        return phase
    if track in {"student", "holistic", "essay"}:
        return "SUSI"
    if track == "csat":
        return "JEONGSI"
    return ""


def _apply_track_filter(queryset, track):
    if track == "student":
        return queryset.filter(
            Q(selection_category__icontains="학생부교과")
            | Q(selection_category__icontains="교과")
            | Q(selection_name__icontains="학생부교과")
            | Q(selection_name__icontains="교과")
        ).distinct()

    if track == "holistic":
        return queryset.filter(
            Q(selection_category__icontains="학생부종합")
            | Q(selection_category__icontains="종합")
            | Q(selection_name__icontains="학생부종합")
        ).distinct()

    if track == "csat":
        return queryset.filter(
            Q(selection_category__icontains="수능")
            | Q(selection_name__icontains="수능")
            | Q(
                admission_phase="JEONGSI",
                metrics__metric_code__icontains="CSAT",
            )
        ).distinct()

    if track == "essay":
        return queryset.filter(
            Q(selection_category__icontains="논술")
            | Q(selection_name__icontains="논술")
        ).distinct()

    if track == "practical":
        return queryset.filter(
            Q(selection_category__icontains="실기")
            | Q(selection_category__icontains="실적")
            | Q(selection_name__icontains="실기")
            | Q(selection_name__icontains="실적")
        ).distinct()

    return queryset


def _apply_aggregate_track_filter(queryset, track):
    if track == "student":
        return queryset.filter(
            Q(selection_category__icontains="학생부교과")
            | Q(selection_category__icontains="교과")
        )
    if track == "holistic":
        return queryset.filter(
            Q(selection_category__icontains="학생부종합")
            | Q(selection_category__icontains="종합")
        )
    if track == "csat":
        return queryset.filter(selection_category__icontains="수능")
    if track == "essay":
        return queryset.filter(selection_category__icontains="논술")
    if track == "practical":
        return queryset.filter(
            Q(selection_category__icontains="실기")
            | Q(selection_category__icontains="실적")
        )
    return queryset


def _overview_result_context(request, selected_year):
    source_kind = request.GET.get("kind", "").strip().lower()
    if source_kind not in {"", "four", "college"}:
        source_kind = ""

    selected_phase = request.GET.get("phase", "").strip().upper()
    if selected_phase not in {"", "SUSI", "JEONGSI"}:
        selected_phase = ""

    selected_track = _normalize_track(request.GET.get("track"))
    selected_phase = _phase_for_track(selected_track, selected_phase)
    query = request.GET.get("q", "").strip()

    if not selected_year:
        return {
            "recent_results": AdmissionResult.objects.none(),
            "page_obj": None,
            "filtered_result_count": 0,
            "query": query,
            "source_kind": source_kind,
            "selected_phase": selected_phase,
            "selected_track": selected_track,
            "pagination_query": "",
        }

    results = (
        AdmissionResult.objects.filter(admission_year=selected_year)
        .select_related("university", "recruitment_unit", "source")
        .prefetch_related("metrics")
    )

    if source_kind == "four":
        results = results.filter(source__source_type__in=["ADIGA", "UNIVERSITY"])
    elif source_kind == "college":
        results = results.filter(source__source_type="PROCOLLEGE")

    if selected_phase:
        results = results.filter(admission_phase=selected_phase)

    results = _apply_track_filter(results, selected_track)

    if query:
        results = results.filter(
            Q(university__name__icontains=query)
            | Q(recruitment_unit__name__icontains=query)
            | Q(selection_category__icontains=query)
            | Q(selection_name__icontains=query)
        )

    results = results.order_by(
        "university__name",
        "admission_phase",
        "selection_category",
        "selection_name",
        "recruitment_unit__name",
        "result_id",
    )

    filtered_result_count = results.count()
    page_obj = Paginator(results, RESULTS_PER_PAGE).get_page(request.GET.get("page", 1))

    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)
    if selected_phase:
        pagination_params["phase"] = selected_phase
    if selected_track:
        pagination_params["track"] = selected_track

    return {
        "recent_results": page_obj.object_list,
        "page_obj": page_obj,
        "filtered_result_count": filtered_result_count,
        "query": query,
        "source_kind": source_kind,
        "selected_phase": selected_phase,
        "selected_track": selected_track,
        "pagination_query": pagination_params.urlencode(),
    }


def overview_results(request):
    years = list(
        AdmissionResult.objects.values_list("admission_year", flat=True)
        .distinct()
        .order_by("-admission_year")
    )
    latest_year = years[0] if years else None

    requested_year = request.GET.get("year")
    try:
        requested_year = int(requested_year) if requested_year else None
    except ValueError:
        requested_year = None

    selected_year = requested_year if requested_year in years else latest_year
    context = _overview_result_context(request, selected_year)
    context.update({"selected_year": selected_year, "years": years})
    return render(request, "admissions/partials/overview_results.html", context)


def overview(request):
    years = list(
        AdmissionResult.objects.values_list("admission_year", flat=True)
        .distinct()
        .order_by("-admission_year")
    )
    latest_year = years[0] if years else None

    requested_year = request.GET.get("year")
    if requested_year:
        try:
            requested_year = int(requested_year)
        except ValueError:
            requested_year = None

    selected_year = requested_year if requested_year in years else latest_year

    coverage_count = 0
    result_count = 0
    four_year_coverage = 0
    college_coverage = 0
    four_year_result_count = 0
    college_result_count = 0

    susi_rows = AdmissionAggregate.objects.none()
    jeongsi_rows = AdmissionAggregate.objects.none()
    college_susi_rows = []
    college_jeongsi_rows = []

    result_context = _overview_result_context(request, selected_year)

    if selected_year:
        year_results = AdmissionResult.objects.filter(admission_year=selected_year)
        coverage_count = year_results.values("university_id").distinct().count()
        result_count = year_results.count()

        four_year_results = year_results.filter(
            source__source_type__in=["ADIGA", "UNIVERSITY"]
        )
        college_results = year_results.filter(source__source_type="PROCOLLEGE")

        four_year_coverage = four_year_results.values("university_id").distinct().count()
        college_coverage = college_results.values("university_id").distinct().count()
        four_year_result_count = four_year_results.count()
        college_result_count = college_results.count()

        susi_rows = (
            AdmissionAggregate.objects.filter(
                admission_year=selected_year,
                admission_phase="SUSI",
                selection_category="학생부교과",
                metric_code="STUDENT_GRADE_70_CUT",
            )
            .select_related("university")
            .order_by("value", "university__name")[:10]
        )

        jeongsi_rows = (
            AdmissionAggregate.objects.filter(
                admission_year=selected_year,
                admission_phase="JEONGSI",
                selection_category="수능",
                metric_code="CSAT_PERCENTILE_MEAN_70_CUT",
            )
            .select_related("university")
            .order_by("-value", "university__name")[:10]
        )

        college_susi_rows = _build_procollege_metric_ranking(
            admission_year=selected_year,
            admission_phase="SUSI",
            metric_code="COLLEGE_STUDENT_AVERAGE",
            unit="등급",
            ascending=True,
            limit=10,
        )
        college_jeongsi_rows = _build_procollege_metric_ranking(
            admission_year=selected_year,
            admission_phase="JEONGSI",
            metric_code="COLLEGE_CSAT_AVERAGE",
            unit="백분위",
            ascending=False,
            limit=10,
        )

    context = {
        "latest_year": latest_year,
        "selected_year": selected_year,
        "years": years,
        "coverage_count": coverage_count,
        "result_count": result_count,
        "filtered_result_count": result_context["filtered_result_count"],
        "four_year_coverage": four_year_coverage,
        "college_coverage": college_coverage,
        "four_year_result_count": four_year_result_count,
        "college_result_count": college_result_count,
        "susi_rows": susi_rows,
        "jeongsi_rows": jeongsi_rows,
        "college_susi_rows": college_susi_rows,
        "college_jeongsi_rows": college_jeongsi_rows,
        "college_jeongsi_metric_label": "수능 합격자 평균",
        "college_jeongsi_unit": "백분위",
        "recent_results": result_context["recent_results"],
        "page_obj": result_context["page_obj"],
        "query": result_context["query"],
        "source_kind": result_context["source_kind"],
        "selected_phase": result_context["selected_phase"],
        "selected_track": result_context["selected_track"],
        "pagination_query": result_context["pagination_query"],
        "track_choices": TRACK_CHOICES,
        "metric_label": metric_label,
        "metric_unit": metric_unit,
    }
    return render(request, "admissions/overview.html", context)


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

    aggregates = AdmissionAggregate.objects.filter(university=university).exclude(
        metric_code__in={
            "CSAT_PERCENTILE_REFERENCE_MEAN_50_CUT",
            "CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT",
        }
    )
    if year:
        aggregates = aggregates.filter(admission_year=year)
    if phase:
        aggregates = aggregates.filter(admission_phase=phase)
    aggregates = _apply_aggregate_track_filter(aggregates, selected_track)
    aggregates = aggregates.order_by(
        "-admission_year",
        "admission_phase",
        "selection_category",
        "metric_code",
    )

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
            "aggregates": aggregates[:120],
            "track_choices": TRACK_CHOICES,
            "metric_label": metric_label,
            "metric_unit": metric_unit,
        },
    )
