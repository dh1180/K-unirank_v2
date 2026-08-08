from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand

from admissions.models import AdmissionMetric, AdmissionResult


class Command(BaseCommand):
    help = "ADIGA 수집 결과에서 잘못된 컬럼 매핑이나 비정상 값을 점검합니다."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        year = options.get("year")
        limit = max(1, options.get("limit") or 100)

        results = (
            AdmissionResult.objects.filter(source__source_type="ADIGA")
            .select_related("university", "recruitment_unit", "source")
            .prefetch_related("metrics")
        )
        if year:
            results = results.filter(admission_year=year)

        warnings = []
        coverage = defaultdict(lambda: {"rows": 0, "grade70": 0, "percentile70": 0})

        for result in results.iterator():
            key = (result.university.name, result.admission_year)
            coverage[key]["rows"] += 1
            metric_map = {metric.metric_code: metric.value for metric in result.metrics.all()}

            grade70 = metric_map.get("STUDENT_GRADE_70_CUT")
            if grade70 is not None:
                coverage[key]["grade70"] += 1
                if not (Decimal("1") <= grade70 <= Decimal("9")):
                    warnings.append(
                        f"등급 범위 오류 | {result.university.name} | {result.selection_name} | "
                        f"{result.recruitment_unit.name} | 70%={grade70}"
                    )

            percentile70 = metric_map.get("CSAT_PERCENTILE_MEAN_70_CUT")
            if percentile70 is not None:
                coverage[key]["percentile70"] += 1
                if not (Decimal("0") <= percentile70 <= Decimal("100")):
                    warnings.append(
                        f"백분위 범위 오류 | {result.university.name} | {result.selection_name} | "
                        f"{result.recruitment_unit.name} | 70%={percentile70}"
                    )

            if result.recruitment_count and result.applicant_count is not None and result.competition_rate is not None:
                calculated = Decimal(result.applicant_count) / Decimal(result.recruitment_count)
                tolerance = max(Decimal("0.15"), calculated * Decimal("0.03"))
                if abs(result.competition_rate - calculated) > tolerance:
                    warnings.append(
                        f"경쟁률 불일치 | {result.university.name} | {result.selection_name} | "
                        f"{result.recruitment_unit.name} | 모집={result.recruitment_count}, "
                        f"지원={result.applicant_count}, 저장경쟁률={result.competition_rate}, "
                        f"계산값={calculated:.2f}"
                    )

            selection_key = (result.selection_name or "").replace(" ", "")
            if result.selection_category == "학생부교과" and any(
                marker in selection_key for marker in ("계열적합", "네오르네상스")
            ):
                warnings.append(
                    f"전형 분류 의심 | {result.university.name} | "
                    f"{result.selection_category}/{result.selection_name} | {result.recruitment_unit.name}"
                )

        self.stdout.write("ADIGA 데이터 점검 결과")
        self.stdout.write(f"검사 모집단위: {sum(item['rows'] for item in coverage.values())}건")
        self.stdout.write(f"대학-연도 조합: {len(coverage)}개")

        missing_grade = [
            (name, admission_year, data)
            for (name, admission_year), data in coverage.items()
            if data["rows"] and data["grade70"] == 0
        ]
        if missing_grade:
            self.stdout.write(
                self.style.WARNING(
                    f"학생부 70% 컷이 한 건도 없는 대학-연도: {len(missing_grade)}개 "
                    "(원문 미제공·이미지 표일 수도 있으므로 오류로 단정하지 않음)"
                )
            )

        if warnings:
            self.stdout.write(self.style.WARNING(f"의심 항목: {len(warnings)}건"))
            for warning in warnings[:limit]:
                self.stdout.write(f"- {warning}")
            if len(warnings) > limit:
                self.stdout.write(f"... 나머지 {len(warnings) - limit}건 생략")
        else:
            self.stdout.write(self.style.SUCCESS("명백한 범위/컬럼 매핑 이상을 찾지 못했습니다."))
