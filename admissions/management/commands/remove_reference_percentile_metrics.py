from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AdmissionAggregate, AdmissionMetric


REFERENCE_CODES = {
    "CSAT_PERCENTILE_REFERENCE_MEAN_50_CUT",
    "CSAT_PERCENTILE_REFERENCE_MEAN_70_CUT",
}


class Command(BaseCommand):
    help = "기존 DB의 K-unirank 참고 평균 백분위 50/70% 지표를 제거합니다."

    def handle(self, *args, **options):
        with transaction.atomic():
            metric_deleted, _ = AdmissionMetric.objects.filter(
                metric_code__in=REFERENCE_CODES
            ).delete()
            aggregate_deleted, _ = AdmissionAggregate.objects.filter(
                metric_code__in=REFERENCE_CODES
            ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"참고 평균 백분위 제거 완료: metric {metric_deleted}건 / "
                f"aggregate {aggregate_deleted}건"
            )
        )
