from __future__ import annotations

from admissions.models import AdmissionAggregate, AdmissionResult


GYOGWA_GRADE_CODES = (
    "STUDENT_GRADE_50_CUT",
    "STUDENT_GRADE_70_CUT",
)
GYOGWA_SCORE_CODES = (
    "CONVERTED_SCORE_50_CUT",
    "CONVERTED_SCORE_70_CUT",
)
CSAT_PERCENTILE_CODES = (
    "CSAT_PERCENTILE_MEAN_50_CUT",
    "CSAT_PERCENTILE_MEAN_70_CUT",
)
CSAT_SCORE_CODES = (
    "CSAT_CONVERTED_SCORE_50_CUT",
    "CSAT_CONVERTED_SCORE_70_CUT",
)


def _pick_pair(rows, preferred_codes, fallback_codes):
    """Pick a 50/70 aggregate pair, preferring weighted aggregates.

    Returns a dictionary with values and the display unit/type. Both values do
    not have to exist; ADIGA disclosures differ by university.
    """
    by_code = {}
    for row in rows:
        current = by_code.get(row.metric_code)
        if current is None:
            by_code[row.metric_code] = row
            continue
        if (
            current.aggregation_method != "WEIGHTED_BY_RECRUITMENT"
            and row.aggregation_method == "WEIGHTED_BY_RECRUITMENT"
        ):
            by_code[row.metric_code] = row

    def pair_for(codes):
        first = by_code.get(codes[0])
        second = by_code.get(codes[1])
        if first is None and second is None:
            return None
        return first, second

    pair = pair_for(preferred_codes)
    mode = "preferred"
    if pair is None:
        pair = pair_for(fallback_codes)
        mode = "fallback"
    if pair is None:
        return None

    first, second = pair
    return {
        "value_50": first.value if first else None,
        "value_70": second.value if second else None,
        "mode": mode,
    }


def build_admission_hover(university):
    """Return compact latest-year admissions data for a VS university card.

    교과는 학생부 등급을 우선하고, 대학이 등급을 공개하지 않은 경우
    환산점수로 fallback한다. 정시는 대학이 직접 공개한 공식 평균백분위를
    우선하고, 없는 경우 수능 환산점수로 fallback한다.
    """
    latest_year = (
        AdmissionResult.objects.filter(university=university)
        .order_by("-admission_year")
        .values_list("admission_year", flat=True)
        .first()
    )

    empty = {
        "year": latest_year,
        "has_data": False,
        "gyogwa": None,
        "csat": None,
    }
    if not latest_year:
        return empty

    codes = set(
        GYOGWA_GRADE_CODES
        + GYOGWA_SCORE_CODES
        + CSAT_PERCENTILE_CODES
        + CSAT_SCORE_CODES
    )
    aggregates = list(
        AdmissionAggregate.objects.filter(
            university=university,
            admission_year=latest_year,
            metric_code__in=codes,
        ).order_by("aggregation_method")
    )

    gyogwa_rows = [
        row
        for row in aggregates
        if row.admission_phase == "SUSI" and row.selection_category == "학생부교과"
    ]
    csat_rows = [
        row
        for row in aggregates
        if row.admission_phase == "JEONGSI" and row.selection_category == "수능"
    ]

    gyogwa = _pick_pair(gyogwa_rows, GYOGWA_GRADE_CODES, GYOGWA_SCORE_CODES)
    if gyogwa:
        if gyogwa["mode"] == "preferred":
            gyogwa.update({"label": "교과 등급", "unit": "등급"})
        else:
            gyogwa.update({"label": "교과 환산", "unit": "점"})

    csat = _pick_pair(csat_rows, CSAT_PERCENTILE_CODES, CSAT_SCORE_CODES)
    if csat:
        if csat["mode"] == "preferred":
            csat.update({"label": "수능 평백", "unit": "백분위"})
        else:
            csat.update({"label": "수능 환산", "unit": "점"})

    return {
        "year": latest_year,
        "has_data": bool(gyogwa or csat),
        "gyogwa": gyogwa,
        "csat": csat,
    }


def attach_admission_hover(universities):
    """Attach `admission_hover` to University instances for template use."""
    for university in universities:
        university.admission_hover = build_admission_hover(university)
    return universities
