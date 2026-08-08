from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, render

from admissions.models import AdmissionAggregate, AdmissionResult
from rankings.models import UniversityRating

from .models import University, UniversityCampus


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

    latest_admission_year = (
        AdmissionResult.objects.filter(university=university)
        .order_by("-admission_year")
        .values_list("admission_year", flat=True)
        .first()
    )

    admission_aggregates = AdmissionAggregate.objects.none()
    if latest_admission_year:
        admission_aggregates = (
            AdmissionAggregate.objects.filter(
                university=university,
                admission_year=latest_admission_year,
            )
            .exclude(
                metric_code__in={
                    "CSAT_PERCENTILE_REFERENCE_MEAN_50_CUT",
                    "CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT",
                }
            )
            .order_by("admission_phase", "selection_category", "metric_code")[:30]
        )

    return render(
        request,
        "universities/university_detail.html",
        {
            "university": university,
            "ratings": ratings,
            "admission_aggregates": admission_aggregates,
            "latest_admission_year": latest_admission_year,
        },
    )
