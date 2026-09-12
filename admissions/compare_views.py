from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from .models import AdmissionMetric


GRADE_METRICS = ("STUDENT_GRADE_50_CUT", "STUDENT_GRADE_70_CUT")
TRACK_CHOICES = {
    "student": "학생부교과",
    "holistic": "학생부종합",
}
SOURCE_PRIORITY = {"UNIVERSITY": 2, "ADIGA": 1}
RESULTS_PER_PAGE = 60

REGION_CHOICES = (
    ("", "전국"),
    ("서울", "서울"),
    ("경기", "경기"),
    ("인천", "인천"),
    ("부산", "부산"),
    ("대구", "대구"),
    ("광주", "광주"),
    ("대전", "대전"),
    ("울산", "울산"),
    ("세종", "세종"),
    ("강원", "강원"),
    ("충북", "충북"),
    ("충남", "충남"),
    ("전북", "전북"),
    ("전남", "전남"),
    ("경북", "경북"),
    ("경남", "경남"),
    ("제주", "제주"),
)

REGION_FILTERS = {
    "서울": ("서울",),
    "경기": ("경기",),
    "인천": ("인천",),
    "부산": ("부산",),
    "대구": ("대구",),
    "광주": ("광주", "전남광주"),
    "대전": ("대전",),
    "울산": ("울산",),
    "세종": ("세종",),
    "강원": ("강원",),
    "충북": ("충청북", "충북"),
    "충남": ("충청남", "충남"),
    "전북": ("전북", "전라북"),
    "전남": ("전남", "전라남"),
    "경북": ("경상북", "경북"),
    "경남": ("경상남", "경남"),
    "제주": ("제주",),
}


def _parse_grade(raw_value):
    raw_value = str(raw_value or "").strip()
    if not raw_value:
        return None, ""

    try:
        grade = Decimal(raw_value)
    except InvalidOperation:
        return None, "내신 평균등급을 숫자로 입력해 주세요."

    if not grade.is_finite() or grade < Decimal("1.0") or grade > Decimal("9.0"):
        return None, "내신 평균등급은 1.0~9.0 사이로 입력해 주세요."

    return grade.quantize(Decimal("0.01")), ""


def _grade_pct(value):
    value = max(Decimal("1.0"), min(Decimal("9.0"), Decimal(value)))
    return float(((value - Decimal("1.0")) / Decimal("8.0")) * Decimal("100"))


def _position_label(my_grade, cutoff):
    gap = (my_grade - cutoff).quantize(Decimal("0.01"))
    abs_gap = abs(gap)

    if abs_gap <= Decimal("0.10"):
        return "컷과 비슷", "near", gap
    if gap < 0:
        return f"{abs_gap:.2f}등급 앞섬", "ahead", gap
    return f"{abs_gap:.2f}등급 뒤", "behind", gap


def _source_name(source_type):
    if source_type == "UNIVERSITY":
        return "대학 입학처"
    return "대입정보포털 어디가"


def compare_by_grade(request):
    year_values = list(
        AdmissionMetric.objects.filter(
            metric_code__in=GRADE_METRICS,
            result__admission_phase="SUSI",
            result__source__source_type__in=["ADIGA", "UNIVERSITY"],
            result__university__is_active=True,
            result__recruitment_unit__is_active=True,
            value__gte=1,
            value__lte=9,
        )
        .values_list("result__admission_year", flat=True)
        .distinct()
        .order_by("-result__admission_year")
    )
    latest_year = year_values[0] if year_values else None

    try:
        requested_year = int(request.GET.get("year", ""))
    except (TypeError, ValueError):
        requested_year = None
    selected_year = requested_year if requested_year in year_values else latest_year

    track = request.GET.get("track", "student").strip().lower()
    if track not in TRACK_CHOICES:
        track = "student"
    selection_category = TRACK_CHOICES[track]

    scope = request.GET.get("scope", "near").strip().lower()
    if scope not in {"near", "all"}:
        scope = "near"

    query = request.GET.get("q", "").strip()
    query_terms = [term.strip() for term in query.split(",") if term.strip()][:5]

    region = request.GET.get("region", "").strip()
    valid_regions = {value for value, _ in REGION_CHOICES}
    if region not in valid_regions:
        region = ""

    my_grade, grade_error = _parse_grade(request.GET.get("grade", ""))
    range_low = max(Decimal("1.0"), my_grade - Decimal("0.5")) if my_grade else None
    range_high = min(Decimal("9.0"), my_grade + Decimal("0.5")) if my_grade else None

    rows = []
    chart_rows = []
    filtered_count = 0
    page_obj = None
    pagination_query = ""

    if my_grade is not None and selected_year is not None:
        metrics = AdmissionMetric.objects.filter(
            result__admission_year=selected_year,
            result__admission_phase="SUSI",
            result__selection_category=selection_category,
            result__source__source_type__in=["ADIGA", "UNIVERSITY"],
            result__university__is_active=True,
            result__recruitment_unit__is_active=True,
            metric_code__in=GRADE_METRICS,
            value__gte=1,
            value__lte=9,
        )

        if query_terms:
            department_query = Q()
            for term in query_terms:
                department_query |= Q(result__recruitment_unit__name__icontains=term)
            metrics = metrics.filter(department_query)

        if region:
            region_query = Q()
            for token in REGION_FILTERS.get(region, (region,)):
                region_query |= Q(result__university__region__icontains=token)
                region_query |= Q(result__university__address__icontains=token)
            metrics = metrics.filter(region_query)

        metrics = metrics.select_related(
            "result",
            "result__university",
            "result__recruitment_unit",
            "result__source",
        ).order_by("result_id", "metric_code")

        by_result = {}
        for metric in metrics.iterator(chunk_size=2000):
            result = metric.result
            item = by_result.setdefault(
                result.result_id,
                {
                    "result": result,
                    "metrics": {},
                },
            )
            item["metrics"][metric.metric_code] = metric.value

        deduplicated = {}
        for item in by_result.values():
            result = item["result"]
            metric_map = item["metrics"]
            cut_70 = metric_map.get("STUDENT_GRADE_70_CUT")
            cut_50 = metric_map.get("STUDENT_GRADE_50_CUT")
            reference_cut = cut_70 if cut_70 is not None else cut_50
            if reference_cut is None:
                continue

            source_type = result.source.source_type
            row = {
                "result": result,
                "university": result.university,
                "university_id": result.university_id,
                "unit": result.recruitment_unit,
                "selection_name": result.selection_name or "전형명 미확인",
                "selection_category": result.selection_category,
                "cut_50": cut_50,
                "cut_70": cut_70,
                "reference_cut": reference_cut,
                "source_type": source_type,
                "source_name": _source_name(source_type),
            }
            position_label, position_tone, gap = _position_label(my_grade, reference_cut)
            row["position_label"] = position_label
            row["position_tone"] = position_tone
            row["gap"] = gap
            row["abs_gap"] = abs(gap)
            row["cut_pct"] = _grade_pct(reference_cut)
            row["my_pct"] = _grade_pct(my_grade)

            duplicate_key = (
                result.university_id,
                result.recruitment_unit_id,
                result.selection_category,
                (result.selection_name or "").strip().lower(),
            )
            current = deduplicated.get(duplicate_key)
            if current is None:
                deduplicated[duplicate_key] = row
                continue

            current_priority = SOURCE_PRIORITY.get(current["source_type"], 0)
            new_priority = SOURCE_PRIORITY.get(source_type, 0)
            current_metric_count = int(current["cut_50"] is not None) + int(current["cut_70"] is not None)
            new_metric_count = int(cut_50 is not None) + int(cut_70 is not None)
            if (new_priority, new_metric_count) > (current_priority, current_metric_count):
                deduplicated[duplicate_key] = row

        # Resolve the authoritative source before applying the user's range.
        # Otherwise an in-range ADIGA row can replace an out-of-range university row.
        rows = [
            row for row in deduplicated.values()
            if scope == "all" or range_low <= row["reference_cut"] <= range_high
        ]
        rows.sort(
            key=lambda item: (
                item["abs_gap"],
                item["reference_cut"],
                item["university"].name,
                item["unit"].name,
                item["selection_name"],
            )
        )
        filtered_count = len(rows)

        university_groups = defaultdict(list)
        for row in rows:
            university_groups[row["university_id"]].append(row)

        for university_rows in university_groups.values():
            # A 50% cutoff and a 70% cutoff describe different populations.
            # Keep each university's chart average on one cutoff basis.
            chart_sample = [row for row in university_rows if row["cut_70"] is not None]
            reference_label = "70% 컷"
            if not chart_sample:
                chart_sample = university_rows
                reference_label = "50% 컷"
            avg_cut = sum(
                (row["reference_cut"] for row in chart_sample),
                Decimal("0"),
            ) / Decimal(len(chart_sample))
            avg_cut = avg_cut.quantize(Decimal("0.01"))
            position_label, position_tone, gap = _position_label(my_grade, avg_cut)
            chart_rows.append(
                {
                    "university": university_rows[0]["university"],
                    "university_id": university_rows[0]["university_id"],
                    "average_cut": avg_cut,
                    "cut_pct": _grade_pct(avg_cut),
                    "my_pct": _grade_pct(my_grade),
                    "result_count": len(chart_sample),
                    "reference_label": reference_label,
                    "position_label": position_label,
                    "position_tone": position_tone,
                    "abs_gap": abs(gap),
                }
            )

        chart_rows.sort(
            key=lambda item: (
                item["abs_gap"],
                item["average_cut"],
                item["university"].name,
            )
        )
        chart_rows = chart_rows[:16]

        paginator = Paginator(rows, RESULTS_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get("page", 1))
        rows = page_obj.object_list

        pagination_params = request.GET.copy()
        pagination_params.pop("page", None)
        pagination_query = pagination_params.urlencode()

    context = {
        "years": year_values,
        "latest_year": latest_year,
        "selected_year": selected_year,
        "track": track,
        "track_label": selection_category,
        "scope": scope,
        "query": query,
        "query_terms": query_terms,
        "region": region,
        "region_choices": REGION_CHOICES,
        "grade_raw": request.GET.get("grade", ""),
        "grade_error": grade_error,
        "my_grade": my_grade,
        "range_low": range_low,
        "range_high": range_high,
        "rows": rows,
        "chart_rows": chart_rows,
        "filtered_count": filtered_count,
        "page_obj": page_obj,
        "pagination_query": pagination_query,
    }
    return render(request, "admissions/compare.html", context)
