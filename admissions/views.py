from collections import defaultdict
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from admissions.services.metrics import metric_label, metric_unit
from universities.models import University

from .models import AdmissionAggregate, AdmissionMetric, AdmissionResult


RESULTS_PER_PAGE = 60
UNIVERSITY_RESULTS_PER_PAGE = 60


def _build_procollege_metric_ranking(
    *,
    admission_year,
    admission_phase,
    metric_code,
    unit,
    ascending=True,
    limit=10,
):
    """전문대 지표를 동일 단위끼리만 대학 단위로 안전하게 집계한다.

    AdmissionAggregate에는 unit 컬럼이 없기 때문에 전문대 대표지표는
    AdmissionMetric 원본에서 직접 계산한다. 모집인원이 있는 모집단위는
    모집인원 가중평균, 없으면 단순평균을 사용한다.
    """
    metrics = AdmissionMetric.objects.filter(
        result__admission_year=admission_year,
        result__admission_phase=admission_phase,
        result__source__source_type="PROCOLLEGE",
        metric_code=metric_code,
    )

    if metric_code.startswith("COLLEGE_CSAT_") and unit == "백분위":
        # 일부 Procollege 행은 점수산출기준이 비어 있지만
        # 9 초과 100 이하의 수능 평균/최저값을 제공한다.
        # DB 보정 전에도 해당 행을 대표 백분위 목록에서 누락시키지 않는다.
        metrics = metrics.filter(
            Q(unit="백분위")
            | Q(unit="", value__gt=9, value__lte=100)
        )
    else:
        metrics = metrics.filter(unit=unit)

    metrics = (
        metrics
        .select_related("result", "result__university")
        .order_by("result__university__name", "metric_id")
    )

    groups = defaultdict(list)
    universities = {}

    for metric in metrics:
        result = metric.result
        universities[result.university_id] = result.university
        groups[result.university_id].append(
            (metric.value, result.recruitment_count)
        )

    rows = []

    for university_id, values in groups.items():
        weighted = [
            (value, weight)
            for value, weight in values
            if weight and weight > 0
        ]

        if weighted:
            total_weight = sum(Decimal(weight) for _, weight in weighted)
            value = (
                sum(
                    metric_value * Decimal(weight)
                    for metric_value, weight in weighted
                )
                / total_weight
            )
            sample_count = len(weighted)
        else:
            value = sum(value for value, _ in values) / Decimal(len(values))
            sample_count = len(values)

        rows.append(
            {
                "university": universities[university_id],
                "university_id": university_id,
                "value": value,
                "sample_count": sample_count,
                "unit": unit,
            }
        )

    rows.sort(
        key=lambda item: (
            item["value"] if ascending else -item["value"],
            item["university"].name,
        )
    )
    return rows[:limit]



def _overview_result_context(request, selected_year):
    """입시 메인 하단 검색/필터 결과 공통 컨텍스트."""
    source_kind = request.GET.get("kind", "").strip().lower()
    if source_kind not in {"", "four", "college"}:
        source_kind = ""

    selected_phase = request.GET.get("phase", "").strip().upper()
    if selected_phase not in {"", "SUSI", "JEONGSI"}:
        selected_phase = ""

    query = request.GET.get("q", "").strip()

    if not selected_year:
        return {
            "recent_results": AdmissionResult.objects.none(),
            "page_obj": None,
            "filtered_result_count": 0,
            "query": query,
            "source_kind": source_kind,
            "selected_phase": selected_phase,
            "pagination_query": "",
        }

    results = (
        AdmissionResult.objects.filter(admission_year=selected_year)
        .select_related(
            "university",
            "recruitment_unit",
            "source",
        )
        .prefetch_related("metrics")
    )

    if source_kind == "four":
        results = results.filter(source__source_type="ADIGA")
    elif source_kind == "college":
        results = results.filter(source__source_type="PROCOLLEGE")

    if selected_phase:
        results = results.filter(admission_phase=selected_phase)

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
    paginator = Paginator(results, RESULTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)

    return {
        "recent_results": page_obj.object_list,
        "page_obj": page_obj,
        "filtered_result_count": filtered_result_count,
        "query": query,
        "source_kind": source_kind,
        "selected_phase": selected_phase,
        "pagination_query": pagination_params.urlencode(),
    }


def overview_results(request):
    """입시 메인 하단 결과만 반환하는 AJAX 엔드포인트."""
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
    context.update({
        "selected_year": selected_year,
        "years": years,
    })
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

    if requested_year in years:
        selected_year = requested_year
    else:
        selected_year = latest_year

    source_kind = ""
    selected_phase = ""
    query = ""

    coverage_count = 0
    result_count = 0
    filtered_result_count = 0

    four_year_coverage = 0
    college_coverage = 0
    four_year_result_count = 0
    college_result_count = 0

    susi_rows = AdmissionAggregate.objects.none()
    jeongsi_rows = AdmissionAggregate.objects.none()

    college_susi_rows = []
    college_jeongsi_rows = []
    college_jeongsi_metric_label = "수능 합격자 평균"
    college_jeongsi_unit = "백분위"

    recent_results = AdmissionResult.objects.none()
    page_obj = None
    pagination_query = ""

    if selected_year:
        year_results = AdmissionResult.objects.filter(
            admission_year=selected_year
        )

        coverage_count = (
            year_results.values("university_id").distinct().count()
        )
        result_count = year_results.count()

        four_year_results = year_results.filter(
            source__source_type="ADIGA"
        )
        college_results = year_results.filter(
            source__source_type="PROCOLLEGE"
        )

        four_year_coverage = (
            four_year_results.values("university_id").distinct().count()
        )
        college_coverage = (
            college_results.values("university_id").distinct().count()
        )
        four_year_result_count = four_year_results.count()
        college_result_count = college_results.count()

        # 4년제 대표 지표
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

        # 전문대 대표 지표
        # 대표 화면은 가장 직관적인 2개 지표만 고정 노출한다.
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
        college_jeongsi_metric_label = "수능 합격자 평균"
        college_jeongsi_unit = "백분위"

        result_context = _overview_result_context(
            request,
            selected_year,
        )
        recent_results = result_context["recent_results"]
        page_obj = result_context["page_obj"]
        filtered_result_count = result_context["filtered_result_count"]
        query = result_context["query"]
        source_kind = result_context["source_kind"]
        selected_phase = result_context["selected_phase"]
        pagination_query = result_context["pagination_query"]


    context = {
        "latest_year": latest_year,
        "selected_year": selected_year,
        "years": years,

        "coverage_count": coverage_count,
        "result_count": result_count,
        "filtered_result_count": filtered_result_count,

        "four_year_coverage": four_year_coverage,
        "college_coverage": college_coverage,
        "four_year_result_count": four_year_result_count,
        "college_result_count": college_result_count,

        "susi_rows": susi_rows,
        "jeongsi_rows": jeongsi_rows,
        "college_susi_rows": college_susi_rows,
        "college_jeongsi_rows": college_jeongsi_rows,
        "college_jeongsi_metric_label": college_jeongsi_metric_label,
        "college_jeongsi_unit": college_jeongsi_unit,

        "recent_results": recent_results,
        "page_obj": page_obj,

        "query": query,
        "source_kind": source_kind,
        "selected_phase": selected_phase,
        "pagination_query": pagination_query,

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
