from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from admissions.services.metrics import metric_label, metric_unit
from universities.models import University

from .models import AdmissionAggregate, AdmissionResult


RESULTS_PER_PAGE = 100
UNIVERSITY_RESULTS_PER_PAGE = 60


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

    if requested_year in years:
        selected_year = requested_year
    else:
        selected_year = latest_year

    coverage_count = 0
    result_count = 0
    susi_rows = AdmissionAggregate.objects.none()
    jeongsi_rows = AdmissionAggregate.objects.none()
    recent_results = AdmissionResult.objects.none()
    page_obj = None

    if selected_year:
        year_results = AdmissionResult.objects.filter(admission_year=selected_year)
        coverage_count = year_results.values("university_id").distinct().count()
        result_count = year_results.count()

        susi_rows = (
            AdmissionAggregate.objects.filter(
                admission_year=selected_year,
                admission_phase="SUSI",
                selection_category="학생부교과",
                metric_code="STUDENT_GRADE_70_CUT",
            )
            .select_related("university")
            .order_by("value", "university__name")[:30]
        )

        jeongsi_rows = (
            AdmissionAggregate.objects.filter(
                admission_year=selected_year,
                admission_phase="JEONGSI",
                selection_category="수능",
                metric_code="CSAT_PERCENTILE_MEAN_70_CUT",
            )
            .select_related("university")
            .order_by("-value", "university__name")[:30]
        )


        recent_results_query = (
            year_results.select_related(
                "university",
                "recruitment_unit",
                "source",
            )
            .prefetch_related("metrics")
            .order_by(
                "university__name",
                "admission_phase",
                "selection_category",
                "selection_name",
                "recruitment_unit__name",
                "result_id",
            )
        )

        paginator = Paginator(recent_results_query, RESULTS_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get("page", 1))
        recent_results = page_obj.object_list

    context = {
        "latest_year": latest_year,
        "selected_year": selected_year,
        "years": years,
        "coverage_count": coverage_count,
        "result_count": result_count,
        "susi_rows": susi_rows,
        "jeongsi_rows": jeongsi_rows,
        "recent_results": recent_results,
        "page_obj": page_obj,
        "metric_label": metric_label,
        "metric_unit": metric_unit,
    }
    return render(request, "admissions/overview.html", context)


def university_admissions(request, university_id):
    university = get_object_or_404(
        University,
        pk=university_id,
        is_active=True,
    )

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

    phase = request.GET.get("phase", "").upper()
    if phase not in {"SUSI", "JEONGSI"}:
        phase = ""
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
    paginator = Paginator(results, UNIVERSITY_RESULTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    years = available_years

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
            "years": years,
            "selected_year": year,
            "selected_phase": phase,
            "show_all_years": show_all_years,
            "aggregates": aggregates[:120],
            "metric_label": metric_label,
            "metric_unit": metric_unit,
        },
    )
