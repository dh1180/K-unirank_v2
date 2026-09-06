from decimal import Decimal


CORE_UNIVERSITY_INDICATORS = [
    {
        "code": "EMPLOYMENT_RATE",
        "label": "취업률",
        "category": "취업",
        "kind": "percent",
        "description": "졸업생 취업 현황",
    },
    {
        "code": "AVG_TUITION",
        "label": "평균 등록금",
        "category": "비용",
        "kind": "money",
        "description": "연간 평균 등록금",
    },
    {
        "code": "SCHOLARSHIP_PER_STUDENT",
        "label": "학생 1인당 장학금",
        "category": "장학",
        "kind": "money",
        "description": "재학생 1인당 장학금",
    },
    {
        "code": "DORMITORY_CAPACITY_RATE",
        "label": "기숙사 수용률",
        "category": "생활",
        "kind": "percent",
        "description": "재학생 대비 기숙사 수용 가능 비율",
    },
    {
        "code": "EDUCATION_COST_PER_STUDENT",
        "label": "학생 1인당 교육비",
        "category": "교육",
        "kind": "money",
        "description": "학생 1인당 교육 투자 규모",
    },
    {
        "code": "STUDENTS_PER_FULLTIME_FACULTY",
        "label": "전임교원 1인당 학생 수",
        "category": "교육",
        "kind": "person",
        "description": "전임교원 1명이 담당하는 학생 수",
    },
    {
        "code": "FULLTIME_FACULTY_SECURING_RATE",
        "label": "전임교원 확보율",
        "category": "교육",
        "kind": "percent",
        "description": "법정 정원 대비 전임교원 확보 수준",
    },
]

CORE_INDICATOR_CODES = [item["code"] for item in CORE_UNIVERSITY_INDICATORS]
CORE_INDICATOR_MAP = {item["code"]: item for item in CORE_UNIVERSITY_INDICATORS}


def _format_decimal(value, digits=1):
    quantized = round(Decimal(value), digits)
    return f"{quantized:,.{digits}f}"


def _format_money(value):
    value = Decimal(value)
    if abs(value) >= Decimal("10000"):
        return f"{value / Decimal('10000'):,.0f}", "만원"
    return f"{value:,.0f}", "원"


def format_indicator_value(indicator, spec):
    kind = spec.get("kind")
    value = indicator.value

    if kind == "money":
        return _format_money(value)
    if kind == "percent":
        return _format_decimal(value, 1), "%"
    if kind == "person":
        return _format_decimal(value, 1), "명"

    return _format_decimal(value, 1), indicator.unit or ""


def build_core_indicator_cards(indicators):
    """각 핵심 지표의 가장 최신 공시값만 카드 데이터로 반환한다."""
    latest_by_code = {}
    for indicator in indicators:
        if indicator.indicator_code not in CORE_INDICATOR_MAP:
            continue
        current = latest_by_code.get(indicator.indicator_code)
        if current is None or indicator.year > current.year:
            latest_by_code[indicator.indicator_code] = indicator

    cards = []
    for spec in CORE_UNIVERSITY_INDICATORS:
        indicator = latest_by_code.get(spec["code"])
        if indicator is None:
            continue

        display_value, display_unit = format_indicator_value(indicator, spec)
        cards.append(
            {
                **spec,
                "indicator": indicator,
                "display_value": display_value,
                "display_unit": display_unit,
                "year": indicator.year,
            }
        )

    return cards
