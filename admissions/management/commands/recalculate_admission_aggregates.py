from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AdmissionAggregate, AdmissionMetric


class Command(BaseCommand):
    help = (
        "모집단위 입시 지표를 대학 단위 가중평균으로 계산합니다. "
        "전문대학포털 지표도 동일 산출단위끼리만 안전하게 집계합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)

    def handle(self, *args, **options):
        metrics = AdmissionMetric.objects.select_related(
            "result",
            "result__university",
            "result__source",
        )

        if options.get("year"):
            metrics = metrics.filter(result__admission_year=options["year"])

        groups = defaultdict(list)

        for metric in metrics.iterator():
            result = metric.result
            key = (
                result.university_id,
                result.admission_year,
                result.admission_phase,
                result.selection_category,
                metric.metric_code,
            )

            groups[key].append(
                (
                    metric.value,
                    result.recruitment_count,
                    (metric.unit or "").strip(),
                    result.source.source_type,
                )
            )

        count = 0
        skipped_mixed_units = 0

        with transaction.atomic():
            stale = AdmissionAggregate.objects.all()
            if options.get("year"):
                stale = stale.filter(admission_year=options["year"])
            stale.delete()

            for key, values in groups.items():
                (
                    university_id,
                    year,
                    phase,
                    category,
                    metric_code,
                ) = key

                # Procollege는 학교/전형에 따라 점수산출기준이
                # 등급, 백분위, 점수 등으로 달라질 수 있다.
                #
                # 서로 다른 단위를 하나의 숫자로 평균내는 것은 의미가 없으므로,
                # 같은 aggregate 그룹 안에 실제 단위가 2개 이상 있으면
                # 해당 카드만 생성하지 않는다.
                units = {
                    unit
                    for _, _, unit, _ in values
                    if unit
                }

                if len(units) > 1:
                    skipped_mixed_units += 1
                    continue

                weighted_values = [
                    (value, weight)
                    for value, weight, _, _ in values
                    if weight and weight > 0
                ]

                if weighted_values:
                    total_weight = sum(
                        Decimal(weight)
                        for _, weight in weighted_values
                    )
                    aggregate_value = (
                        sum(
                            value * Decimal(weight)
                            for value, weight in weighted_values
                        )
                        / total_weight
                    )
                    method = "WEIGHTED_BY_RECRUITMENT"
                else:
                    aggregate_value = (
                        sum(value for value, _, _, _ in values)
                        / Decimal(len(values))
                    )
                    method = "SIMPLE_AVERAGE"

                AdmissionAggregate.objects.update_or_create(
                    university_id=university_id,
                    admission_year=year,
                    admission_phase=phase,
                    selection_category=category,
                    metric_code=metric_code,
                    aggregation_method=method,
                    defaults={
                        "value": aggregate_value,
                        "sample_count": len(values),
                    },
                )
                count += 1

        message = f"입시 집계 {count}건을 계산했습니다."
        if skipped_mixed_units:
            message += (
                f" 서로 다른 산출단위가 섞인 {skipped_mixed_units}개 그룹은 "
                "안전하게 제외했습니다."
            )

        self.stdout.write(self.style.SUCCESS(message))
