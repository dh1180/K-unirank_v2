"""Exact double-1.00 student-grade outlier rule for published admissions.

A result is suspect ONLY if it has BOTH student-grade 50 and 70 percentile
cut metrics set to exactly Decimal(1). One valid cutoff over 1.00 must survive.
Medicine/dentistry/Korean medicine/pharmacy/veterinary medicine are exempt.

This is deliberately scoped per AdmissionResult, not per university or major:
other admissions rounds, years, and metrics must not be conflated.
"""
from decimal import Decimal

from django.db.models import Q, Subquery

from admissions.models import AdmissionMetric

GRADE_50 = "STUDENT_GRADE_50_CUT"
GRADE_70 = "STUDENT_GRADE_70_CUT"
ONE = Decimal("1.0")

# Specific professional-major names, not loosely matching biomedical,
# nursing, dental hygiene or pharmaceutical engineering programs.
PROTECTED_MAJOR_MARKERS = (
    "의예", "의학과", "의학부", "의학전공", "의학계열", "의과대학",
    "치의예", "치의학", "치과대학",
    "한의예", "한의학", "한의과대학",
    "약학", "제약학과", "제약학부",
    "수의예", "수의학", "수의과대학",
)


def protected_professional_major_query(prefix="result__"):
    q = Q()
    for marker in PROTECTED_MAJOR_MARKERS:
        q |= Q(**{f"{prefix}recruitment_unit__name__icontains": marker})
        q |= Q(**{f"{prefix}recruitment_unit__college_name__icontains": marker})
    return q


def double_one_cut_result_ids():
    """DB subquery yielding only truly suspect non-protected result IDs."""
    seventies = AdmissionMetric.objects.filter(
        metric_code=GRADE_70, value=ONE
    ).values("result_id")
    return (
        AdmissionMetric.objects.filter(
            metric_code=GRADE_50, value=ONE, result_id__in=Subquery(seventies),
        )
        .exclude(protected_professional_major_query())
        .values("result_id")
    )


def without_invalid_double_one_results(queryset):
    return queryset.exclude(pk__in=Subquery(double_one_cut_result_ids()))


def without_invalid_double_one_metrics(queryset):
    return queryset.exclude(result_id__in=Subquery(double_one_cut_result_ids()))
