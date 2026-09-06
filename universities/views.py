from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from admissions.models import AdmissionAggregate, AdmissionResult
from rankings.models import UniversityRating

from .models import University, UniversityCampus, UniversityIndicator
from .services.indicators import (
    CORE_INDICATOR_CODES,
    CORE_INDICATOR_SLUG_MAP,
    build_core_indicator_cards,
    format_indicator_value,
)


CORE_ADMISSION_SPECS = [
    ("JEONGSI", "수능", "CSAT_PERCENTILE_MEAN_50_CUT", "정시 백분위 50% 컷", "백분위"),
    ("JEONGSI", "수능", "CSAT_PERCENTILE_MEAN_70_CUT", "정시 백분위 70% 컷", "백분위"),
    ("SUSI", "학생부교과", "STUDENT_GRADE_50_CUT", "학생부교과 50% 컷", "등급"),
    ("SUSI", "학생부교과", "STUDENT_GRADE_70_CUT", "학생부교과 70% 컷", "등급"),
    ("SUSI", "학생부종합", "STUDENT_GRADE_50_CUT", "학생부종합 50% 컷", "등급"),
    ("SUSI", "학생부종합", "STUDENT_GRADE_70_CUT", "학생부종합 70% 컷", "등급"),
]


def university_list(request):
    query = request.GET.get("q", "").strip()
    selected_region = request.GET.get("region", "").strip()

    universities = University.objects.filter(is_active=True).order_by("name")

    if query:
        universities = universities.filter(
            Q(name__icontains=query)
            | Q(short_name__icontains=query)
            | Q(address__icontains=query)
        )

    active_locations = list(
        University.objects.filter(is_active=True).only(
            "university_id",
            "region",
            "address",
        )
    )

    regions = sorted(
        {
            university.location_label
            for university in active_locations
            if university.location_label != "지역 미상"
        }
    )

    if selected_region:
        region_ids = [
            university.pk
            for university in active_locations
            if university.location_label == selected_region
        ]
        universities = universities.filter(pk__in=region_ids)

    paginator = Paginator(universities, 36)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "universities/university_list.html",
        {
            "universities": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "regions": regions,
            "selected_region": selected_region,
            "total_count": paginator.count,
        },
    )


def indicator_ranking(request, indicator_slug):
    spec = CORE_INDICATOR_SLUG_MAP.get(indicator_slug)
    if spec is None:
        raise Http404("지원하지 않는 공식 지표입니다.")

    base = UniversityIndicator.objects.filter(
        indicator_code=spec["code"],
        source="ACADEMYINFO",
        university__is_active=True,
        value__gt=0,
    ).select_related("university")

    years = list(
        base.order_by("-year")
        .values_list("year", flat=True)
        .distinct()
    )

    selected_year = None
    requested_year = request.GET.get("year", "").strip()
    if requested_year:
        try:
            requested_year_value = int(requested_year)
        except ValueError:
            requested_year_value = None
        if requested_year_value in years:
            selected_year = requested_year_value
    if selected_year is None and years:
        selected_year = years[0]

    ranked_rows = base
    if selected_year is not None:
        ranked_rows = ranked_rows.filter(year=selected_year)

    value_order = "value" if spec["ranking_order"] == "asc" else "-value"
    ranked_rows = ranked_rows.order_by(value_order, "university__name")

    # 대학명/지역으로 좁혀도 전체 대학 기준 원래 순위 번호를 유지한다.
    rank_by_indicator_id = {
        indicator_id: rank
        for rank, indicator_id in enumerate(
            ranked_rows.values_list("pk", flat=True),
            start=1,
        )
    }

    query = request.GET.get("q", "").strip()
    selected_region = request.GET.get("region", "").strip()

    indicator_universities = list(
        University.objects.filter(
            is_active=True,
            official_indicators__indicator_code=spec["code"],
            official_indicators__source="ACADEMYINFO",
        )
        .distinct()
        .only("university_id", "region", "address")
    )
    regions = sorted(
        {
            university.location_label
            for university in indicator_universities
            if university.location_label != "지역 미상"
        }
    )

    rows = ranked_rows
    if selected_region:
        region_ids = [
            university.pk
            for university in indicator_universities
            if university.location_label == selected_region
        ]
        rows = rows.filter(university_id__in=region_ids)

    if query:
        rows = rows.filter(
            Q(university__name__icontains=query)
            | Q(university__short_name__icontains=query)
            | Q(university__address__icontains=query)
        )

    paginator = Paginator(rows, 60)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    ranking_rows = list(page_obj.object_list)

    for row in ranking_rows:
        display_value, display_unit = format_indicator_value(row, spec)
        row.display_value = display_value
        row.display_unit = display_unit
        row.rank_number = rank_by_indicator_id.get(row.pk)

    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)

    return render(
        request,
        "universities/indicator_ranking.html",
        {
            "indicator": spec,
            "ranking_rows": ranking_rows,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "years": years,
            "selected_year": selected_year,
            "regions": regions,
            "selected_region": selected_region,
            "query": query,
            "pagination_query": pagination_params.urlencode(),
        },
    )


def university_detail(request, university_id):
    career_campuses = UniversityCampus.objects.filter(source="CAREER_NET").order_by(
        "-is_primary",
        "campus_id",
    )

    university = get_object_or_404(
        University.objects.prefetch_related(
            Prefetch(
                "campuses",
                queryset=career_campuses,
                to_attr="display_campuses",
            )
        ),
        university_id=university_id,
        is_active=True,
    )

    ratings = (
        UniversityRating.objects.filter(university=university)
        .select_related("board")
        .order_by("board__display_order")
    )

    official_indicator_rows = list(
        UniversityIndicator.objects.filter(
            university=university,
            indicator_code__in=CORE_INDICATOR_CODES,
        ).order_by("indicator_code", "-year", "-updated_at")
    )
    official_indicator_cards = build_core_indicator_cards(official_indicator_rows)

    latest_admission_year = (
        AdmissionResult.objects.filter(university=university)
        .order_by("-admission_year")
        .values_list("admission_year", flat=True)
        .first()
    )

    admission_summary_items = []
    if latest_admission_year:
        metric_codes = {spec[2] for spec in CORE_ADMISSION_SPECS}
        candidates = list(
            AdmissionAggregate.objects.filter(
                university=university,
                admission_year=latest_admission_year,
                metric_code__in=metric_codes,
            ).order_by("aggregate_id")
        )

        for phase, category, metric_code, label, unit in CORE_ADMISSION_SPECS:
            matches = [
                item
                for item in candidates
                if item.admission_phase == phase
                and category in (item.selection_category or "")
                and item.metric_code == metric_code
            ]
            if not matches:
                continue

            matches.sort(
                key=lambda item: (
                    item.aggregation_method != "WEIGHTED_BY_RECRUITMENT",
                    -item.sample_count,
                    item.aggregate_id,
                )
            )
            item = matches[0]
            admission_summary_items.append(
                {
                    "aggregate": item,
                    "label": label,
                    "unit": unit,
                    "category": category,
                    "phase": phase,
                    "phase_label": "정시" if phase == "JEONGSI" else "수시",
                }
            )

    return render(
        request,
        "universities/university_detail.html",
        {
            "university": university,
            "ratings": ratings,
            "official_indicator_cards": official_indicator_cards,
            "admission_summary_items": admission_summary_items,
            "latest_admission_year": latest_admission_year,
        },
    )