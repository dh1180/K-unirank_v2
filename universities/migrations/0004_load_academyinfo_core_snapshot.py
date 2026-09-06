import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import migrations


SOURCE_URL = "https://www.academyinfo.go.kr/index.do"
DATA_FILES = [
    "academyinfo_core_2026.csv",
    "academyinfo_core_2026_part02.csv",
    "academyinfo_core_2026_part03.csv",
    "academyinfo_core_2026_part04.csv",
    "academyinfo_core_2026_part05.csv",
]

INDICATORS = [
    ("EMPLOYMENT_RATE", "employment_rate", 2025, "%", Decimal("1")),
    (
        "STUDENTS_PER_FULLTIME_FACULTY",
        "students_per_faculty",
        2026,
        "PERSON",
        Decimal("1"),
    ),
    (
        "FULLTIME_FACULTY_SECURING_RATE",
        "faculty_securing_rate",
        2026,
        "%",
        Decimal("1"),
    ),
    (
        "SCHOLARSHIP_PER_STUDENT",
        "scholarship_per_student",
        2026,
        "KRW",
        Decimal("1"),
    ),
    (
        "AVG_TUITION",
        "avg_tuition_thousand_krw",
        2026,
        "KRW",
        Decimal("1000"),
    ),
    (
        "EDUCATION_COST_PER_STUDENT",
        "education_cost_thousand_krw",
        2026,
        "KRW",
        Decimal("1000"),
    ),
    (
        "DORMITORY_CAPACITY_RATE",
        "dormitory_capacity_rate",
        2025,
        "%",
        Decimal("1"),
    ),
]

CAMPUS_TARGETS = {
    ("건양대학교", "제2캠퍼스"): "건양대학교 메디컬캠퍼스",
    ("경기대학교", "제2캠퍼스"): "경기대학교 서울캠퍼스",
    ("경동대학교", "제3캠퍼스"): "경동대학교 메디컬캠퍼스",
    ("경동대학교", "제4캠퍼스"): "경동대학교 메트로폴캠퍼스",
    ("단국대학교", "본교"): "단국대학교 죽전캠퍼스",
    ("단국대학교", "제2캠퍼스"): "단국대학교 천안캠퍼스",
    ("명지대학교", "본교"): "명지대학교 자연캠퍼스",
    ("명지대학교", "제2캠퍼스"): "명지대학교 인문캠퍼스",
    ("상명대학교", "제2캠퍼스"): "상명대학교 천안캠퍼스",
    ("신한대학교", "제2캠퍼스"): "신한대학교 동두천캠퍼스",
    ("안양대학교", "제2캠퍼스"): "안양대학교 강화캠퍼스",
    ("예원예술대학교", "본교"): "예원예술대학교 전북희망캠퍼스",
    ("예원예술대학교", "제2캠퍼스"): "예원예술대학교",
    ("을지대학교", "본교"): "을지대학교 대전캠퍼스",
    ("을지대학교", "제2캠퍼스"): "을지대학교",
    ("을지대학교", "제3캠퍼스"): "을지대학교 의정부캠퍼스",
    ("인천가톨릭대학교", "본교"): "인천가톨릭대학교 강화캠퍼스",
    ("인천가톨릭대학교", "제2캠퍼스"): "인천가톨릭대학교",
    ("전남대학교", "제2캠퍼스"): "전남대학교 여수캠퍼스",
    ("중앙대학교", "제2캠퍼스"): "중앙대학교 다빈치캠퍼스",
    ("홍익대학교", "제2캠퍼스"): "홍익대학교 세종캠퍼스",
}

SOURCE_NAME_TARGETS = {
    "가야대학교(김해)": "가야대학교",
    "건국대학교(글로컬)": "건국대학교 글로컬캠퍼스",
    "고려대학교(세종)": "고려대학교 세종캠퍼스",
    "동국대학교(WISE)": "동국대학교 WISE캠퍼스",
    "연세대학교(미래)": "연세대학교 미래캠퍼스",
    "영산대학교(양산)": "영산대학교 양산캠퍼스",
    "영산대학교(해운대)": "영산대학교",
    "한양대학교(ERICA)": "한양대학교 ERICA캠퍼스",
}

NAME_ALIASES = {
    "서울사이버대학": "서울사이버대학교",
    "한국복지사이버대학": "한국복지사이버대학교",
    "한국골프대학교": "한국골프과학기술대학교",
    "강릉원주대학교": "강원대학교",
    "국립강릉원주대학교": "강원대학교",
    "안동대학교": "국립경국대학교",
    "국립안동대학교": "국립경국대학교",
    "경북도립대학교": "국립경국대학교",
    "경남도립거창대학": "국립창원대학교",
    "경남도립거창대학교": "국립창원대학교",
    "경남도립남해대학": "국립창원대학교",
    "경남도립남해대학교": "국립창원대학교",
}

SKIP_SOURCE_NAMES = {
    "가야대학교(고령)",
    "경남도립거창대학",
    "경남도립남해대학",
    "경북도립대학교",
    "국립강릉원주대학교",
    "국립목포대학교(담양캠퍼스)",
    "국립창원대학교(거창캠퍼스)",
    "국립창원대학교(남해캠퍼스)",
}


def parse_decimal(value):
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def normalize_name(name):
    name = str(name or "").strip()
    if not name:
        return ""
    name = NAME_ALIASES.get(name, name)
    name = re.sub(r"^국립(?=[가-힣A-Za-z])", "", name)
    name = name.replace("대학교", "대")
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"[()\[\]{}·ㆍ,._-]", "", name)
    return name.lower()


def canonical_name(name):
    name = str(name or "").strip()
    if not name:
        return ""
    return NAME_ALIASES.get(name, name)


def resolve_target_name(raw_name, campus_name):
    raw_name = str(raw_name or "").strip()
    campus_name = str(campus_name or "").strip()

    if not raw_name or raw_name in SKIP_SOURCE_NAMES:
        return None, 0
    if "(산업대)" in raw_name:
        return None, 0
    if raw_name.startswith("한국폴리텍"):
        return None, 0

    if raw_name in SOURCE_NAME_TARGETS:
        return SOURCE_NAME_TARGETS[raw_name], 100

    if (raw_name, campus_name) in CAMPUS_TARGETS:
        return CAMPUS_TARGETS[(raw_name, campus_name)], 100

    if raw_name == "가톨릭대학교" and campus_name not in {"", "본교"}:
        return None, 0
    if raw_name == "강원대학교" and campus_name not in {"", "본교"}:
        return None, 0

    return canonical_name(raw_name), 50 if campus_name in {"", "본교"} else 20


def should_skip_zero(code, value, graduate_count, student_count, admission_quota):
    if value != 0:
        return False
    if code == "EMPLOYMENT_RATE":
        return not graduate_count
    if code in {
        "STUDENTS_PER_FULLTIME_FACULTY",
        "FULLTIME_FACULTY_SECURING_RATE",
        "SCHOLARSHIP_PER_STUDENT",
        "EDUCATION_COST_PER_STUDENT",
        "DORMITORY_CAPACITY_RATE",
    }:
        return not student_count
    if code == "AVG_TUITION":
        return not student_count and not admission_quota
    return False


def load_academyinfo_snapshot(apps, schema_editor):
    University = apps.get_model("universities", "University")
    UniversityIndicator = apps.get_model("universities", "UniversityIndicator")

    university_map = {
        normalize_name(university.name): university
        for university in University.objects.filter(is_active=True)
    }

    data_dir = Path(__file__).resolve().parent.parent / "data"
    prepared = {}

    for filename in DATA_FILES:
        path = data_dir / filename
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_name = row.get("school_name", "")
                campus_name = row.get("campus_name", "")
                target_name, priority = resolve_target_name(raw_name, campus_name)
                if not target_name:
                    continue

                university = university_map.get(normalize_name(target_name))
                if university is None:
                    continue

                graduate_count = parse_decimal(row.get("graduate_count")) or Decimal("0")
                student_count = parse_decimal(row.get("student_count")) or Decimal("0")
                admission_quota = parse_decimal(row.get("admission_quota")) or Decimal("0")

                for code, field, year, unit, multiplier in INDICATORS:
                    value = parse_decimal(row.get(field))
                    if value is None:
                        continue
                    if should_skip_zero(
                        code,
                        value,
                        graduate_count,
                        student_count,
                        admission_quota,
                    ):
                        continue

                    value *= multiplier
                    key = (university.pk, year, code)
                    candidate = {
                        "university": university,
                        "year": year,
                        "indicator_code": code,
                        "value": value,
                        "unit": unit,
                        "priority": priority,
                        "source_label": f"대학알리미 대학주요정보 · {campus_name or '본교'}",
                    }
                    previous = prepared.get(key)
                    if previous is None or priority > previous["priority"]:
                        prepared[key] = candidate

    for item in prepared.values():
        UniversityIndicator.objects.update_or_create(
            university=item["university"],
            year=item["year"],
            indicator_code=item["indicator_code"],
            source="ACADEMYINFO",
            defaults={
                "value": item["value"],
                "unit": item["unit"],
                "source_url": SOURCE_URL,
                "source_label": item["source_label"],
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("universities", "0003_universityindicator"),
    ]

    operations = [
        migrations.RunPython(load_academyinfo_snapshot, migrations.RunPython.noop),
    ]
