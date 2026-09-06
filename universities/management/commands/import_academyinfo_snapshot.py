import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from universities.models import University, UniversityIndicator


SOURCE_URL = "https://www.academyinfo.go.kr/main/main2130/doInit.do"

INDICATOR_COLUMNS = [
    (
        "EMPLOYMENT_RATE",
        ["취업률"],
        "%",
    ),
    (
        "AVG_TUITION",
        ["평균등록금", "연평균등록금"],
        "KRW",
    ),
    (
        "SCHOLARSHIP_PER_STUDENT",
        ["학생1인당연간장학금", "학생1인당장학금"],
        "KRW",
    ),
    (
        "DORMITORY_CAPACITY_RATE",
        ["기숙사수용률", "기숙사수용율"],
        "%",
    ),
    (
        "EDUCATION_COST_PER_STUDENT",
        ["학생1인당교육비", "학생1인당교육부"],
        "KRW",
    ),
    (
        "STUDENTS_PER_FULLTIME_FACULTY",
        ["전임교원1인당학생수"],
        "PERSON",
    ),
    (
        "FULLTIME_FACULTY_SECURING_RATE",
        ["전임교원확보율학생정원기준", "학생정원기준전임교원확보율"],
        "%",
    ),
]


def normalize_header(value):
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[()\[\]{}·,:/_-]", "", text)
    return text


def normalize_university_name(value):
    return re.sub(r"\s+", "", str(value or "").strip())


def parse_decimal(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    text = text.replace(",", "").replace("%", "").replace("원", "").strip()
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_year(value):
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def year_from_header(header):
    match = re.search(r"20\d{2}", str(header or ""))
    return int(match.group(0)) if match else None


class Command(BaseCommand):
    help = (
        "대학알리미 '대학주요정보 한눈에 보기' XLSX에서 K-unirank 핵심 공식 지표를 "
        "자동 탐지해 일괄 적재합니다. 기본은 미리보기이며 --apply 시 반영합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="대학알리미에서 내려받은 XLSX 파일")
        parser.add_argument(
            "--sheet",
            help="시트명. 생략하면 첫 시트를 사용합니다.",
        )
        parser.add_argument(
            "--header-row",
            type=int,
            default=1,
            help="헤더 행 번호 (1부터 시작, 기본 1)",
        )
        parser.add_argument(
            "--year",
            type=int,
            help="공시연도를 파일 값 대신 강제로 지정합니다.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 반영합니다.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"파일을 찾을 수 없습니다: {path}")
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise CommandError("이 명령은 대학알리미 XLSX/XLSM 파일을 대상으로 합니다.")

        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise CommandError("openpyxl 설치가 필요합니다.") from exc

        workbook = load_workbook(path, read_only=True, data_only=True)
        if options.get("sheet"):
            sheet_name = options["sheet"]
            if sheet_name not in workbook.sheetnames:
                raise CommandError(
                    f"시트를 찾을 수 없습니다: {sheet_name} / "
                    f"가능한 시트: {', '.join(workbook.sheetnames)}"
                )
            worksheet = workbook[sheet_name]
        else:
            worksheet = workbook[workbook.sheetnames[0]]

        header_row = max(options["header_row"], 1)
        raw_headers = [cell.value for cell in worksheet[header_row]]
        normalized_headers = [normalize_header(value) for value in raw_headers]

        university_col = self.find_column(normalized_headers, ["학교명", "대학명"])
        if university_col is None:
            raise CommandError("학교명/대학명 열을 찾지 못했습니다.")

        year_col = self.find_column(normalized_headers, ["공시년도", "기준연도"])

        detected = {}
        for code, aliases, unit in INDICATOR_COLUMNS:
            column_index = self.find_column(normalized_headers, aliases)
            if column_index is not None:
                detected[code] = {
                    "column": column_index,
                    "unit": unit,
                    "header": raw_headers[column_index],
                    "header_year": year_from_header(raw_headers[column_index]),
                }

        if not detected:
            raise CommandError(
                "핵심 지표 열을 하나도 찾지 못했습니다. --header-row 값을 확인하세요."
            )

        self.stdout.write("[자동 탐지된 지표]")
        for code, info in detected.items():
            self.stdout.write(f"- {code}: {info['header']}")

        universities = list(University.objects.filter(is_active=True))
        university_map = {
            normalize_university_name(university.name): university
            for university in universities
        }

        prepared = []
        unmatched = set()
        rows_seen = 0

        for row in worksheet.iter_rows(min_row=header_row + 1, values_only=True):
            rows_seen += 1
            raw_name = row[university_col] if university_col < len(row) else None
            university = university_map.get(normalize_university_name(raw_name))
            if university is None:
                if str(raw_name or "").strip():
                    unmatched.add(str(raw_name).strip())
                continue

            row_year = options.get("year")
            if row_year is None and year_col is not None and year_col < len(row):
                row_year = parse_year(row[year_col])

            for code, info in detected.items():
                column_index = info["column"]
                if column_index >= len(row):
                    continue
                value = parse_decimal(row[column_index])
                if value is None:
                    continue

                indicator_year = row_year or info["header_year"]
                if indicator_year is None:
                    continue

                prepared.append(
                    {
                        "university": university,
                        "year": indicator_year,
                        "indicator_code": code,
                        "value": value,
                        "unit": info["unit"],
                        "source_label": str(info["header"] or code),
                    }
                )

        self.stdout.write(
            f"읽음 {rows_seen}행 / 적재 후보 {len(prepared)}건 / 미매칭 대학 {len(unmatched)}개"
        )
        if unmatched:
            self.stdout.write(self.style.WARNING("[미매칭 대학 예시]"))
            for name in sorted(unmatched)[:30]:
                self.stdout.write(f"- {name}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("미리보기 완료. 실제 반영은 --apply를 추가하세요.")
            )
            return

        created = 0
        updated = 0
        with transaction.atomic():
            for item in prepared:
                _, was_created = UniversityIndicator.objects.update_or_create(
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
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"반영 완료: 신규 {created}건 / 갱신 {updated}건")
        )

    @staticmethod
    def find_column(headers, aliases):
        normalized_aliases = [normalize_header(alias) for alias in aliases]
        for index, header in enumerate(headers):
            for alias in normalized_aliases:
                if alias and alias in header:
                    return index
        return None
