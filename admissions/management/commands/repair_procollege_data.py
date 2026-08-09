from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AdmissionMetric, AdmissionResult


PROCOLLEGE_SOURCE = "PROCOLLEGE"


def inferred_unit(metric):
    if metric.unit:
        return metric.unit

    value = metric.value
    if value is None or value <= 0:
        return ""

    if metric.metric_code.startswith("COLLEGE_CSAT_"):
        if value <= Decimal("9"):
            return "등급"
        if value <= Decimal("100"):
            return "백분위"
        return "점수"

    if metric.metric_code.startswith("COLLEGE_STUDENT_"):
        if value <= Decimal("9"):
            return "등급"
        return "점수"

    return ""


class Command(BaseCommand):
    help = (
        "기존 PROCOLLEGE 데이터의 0 결측치와 비어 있는 점수산출기준을 "
        "보정합니다. 기본은 미리보기입니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        year = options.get("year")
        apply_changes = options["apply"]

        results = AdmissionResult.objects.filter(
            source__source_type=PROCOLLEGE_SOURCE
        )
        metrics = AdmissionMetric.objects.filter(
            result__source__source_type=PROCOLLEGE_SOURCE
        )

        if year:
            results = results.filter(admission_year=year)
            metrics = metrics.filter(result__admission_year=year)

        zero_results = list(
            results.filter(competition_rate__lte=0)
            .values_list("result_id", flat=True)
        )
        zero_metrics = list(
            metrics.filter(value__lte=0)
            .values_list("metric_id", flat=True)
        )

        unit_updates = []
        for metric in metrics.filter(unit="").iterator():
            unit = inferred_unit(metric)
            if unit:
                unit_updates.append((metric.metric_id, unit))

        self.stdout.write("=== PROCOLLEGE 데이터 보정 ===")
        if year:
            self.stdout.write(f"학년도: {year}")
        self.stdout.write(f"0 이하 경쟁률 -> 결측 처리: {len(zero_results)}건")
        self.stdout.write(f"0 이하 성적지표 -> 삭제: {len(zero_metrics)}건")
        self.stdout.write(f"비어 있는 산출기준 -> 단위 보정: {len(unit_updates)}건")

        if unit_updates:
            self.stdout.write("")
            self.stdout.write("단위 보정 예시:")
            examples = (
                metrics.filter(metric_id__in=[pk for pk, _ in unit_updates[:10]])
                .select_related("result__university", "result__recruitment_unit")
            )
            unit_map = dict(unit_updates)
            for metric in examples:
                self.stdout.write(
                    f"  {metric.result.university.name} | "
                    f"{metric.result.recruitment_unit.name} | "
                    f"{metric.metric_code}={metric.value} "
                    f"-> {unit_map[metric.metric_id]}"
                )

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "미리보기입니다. 실제 보정하려면 --apply를 붙이세요."
                )
            )
            return

        with transaction.atomic():
            if zero_results:
                AdmissionResult.objects.filter(
                    result_id__in=zero_results
                ).update(competition_rate=None)

            if zero_metrics:
                AdmissionMetric.objects.filter(
                    metric_id__in=zero_metrics
                ).delete()

            for metric_id, unit in unit_updates:
                AdmissionMetric.objects.filter(
                    metric_id=metric_id,
                    unit="",
                ).update(unit=unit)

        if year:
            call_command("recalculate_admission_aggregates", year=year)
        else:
            call_command("recalculate_admission_aggregates")

        self.stdout.write(
            self.style.SUCCESS("PROCOLLEGE 데이터 보정 완료.")
        )
