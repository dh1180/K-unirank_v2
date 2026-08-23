from django.shortcuts import get_object_or_404, render

from .models import AdmissionResult, RecruitmentUnit



def recruitment_unit_detail(request, recruitment_unit_id):
    recruitment_unit = get_object_or_404(
        RecruitmentUnit.objects.select_related("university", "campus"),
        pk=recruitment_unit_id,
        is_active=True,
        university__is_active=True,
    )

    results = (
        AdmissionResult.objects.filter(recruitment_unit=recruitment_unit)
        .select_related("source", "university", "recruitment_unit", "recruitment_unit__campus")
        .prefetch_related("metrics")
        .order_by(
            "-admission_year",
            "admission_phase",
            "selection_category",
            "selection_name",
            "result_id",
        )
    )

    latest_year = results.values_list("admission_year", flat=True).first()
    available_years = list(
        results.values_list("admission_year", flat=True)
        .distinct()
        .order_by("-admission_year")
    )

    return render(
        request,
        "admissions/recruitment_unit.html",
        {
            "recruitment_unit": recruitment_unit,
            "university": recruitment_unit.university,
            "results": results[:200],
            "result_count": results.count(),
            "latest_year": latest_year,
            "available_years": available_years,
        },
    )
