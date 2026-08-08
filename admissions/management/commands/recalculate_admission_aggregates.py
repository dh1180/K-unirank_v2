from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AdmissionAggregate, AdmissionMetric


class Command(BaseCommand):
    help = "모집단위 입시 지표를 대학 단위 가중평균으로 계산합니다."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)

    def handle(self, *args, **options):
        metrics = AdmissionMetric.objects.select_related("result", "result__university")
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
            groups[key].append((metric.value, result.recruitment_count))

        count = 0
        with transaction.atomic():
            stale = AdmissionAggregate.objects.all()
            if options.get("year"):
                stale = stale.filter(admission_year=options["year"])
            stale.delete()

            for key, values in groups.items():
                university_id, year, phase, category, metric_code = key
                weighted_values = [(value, weight) for value, weight in values if weight and weight > 0]

                if weighted_values:
                    total_weight = sum(Decimal(weight) for _, weight in weighted_values)
                    aggregate_value = sum(value * Decimal(weight) for value, weight in weighted_values) / total_weight
                    method = "WEIGHTED_BY_RECRUITMENT"
                else:
                    aggregate_value = sum(value for value, _ in values) / Decimal(len(values))
                    method = "SIMPLE_AVERAGE"

                AdmissionAggregate.objects.update_or_create(
                    university_id=university_id,
                    admission_year=year,
                    admission_phase=phase,
                    selection_category=category,
                    metric_code=metric_code,
                    aggregation_method=method,
                    defaults={"value": aggregate_value, "sample_count": len(values)},
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f"입시 집계 {count}건을 계산했습니다."))
