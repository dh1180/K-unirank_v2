from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AdmissionResult, AdmissionSource
from universities.models import UniversityExternalMapping


PROCOLLEGE_SOURCE = "PROCOLLEGE"


class Command(BaseCommand):
    help = (
        "전문대학포털(PROCOLLEGE)에서 수집한 입시 데이터와 외부 매핑만 "
        "초기화합니다. ADIGA/대학/랭킹 데이터는 보존합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        year = options.get("year")
        apply_changes = options["apply"]

        sources = AdmissionSource.objects.filter(source_type=PROCOLLEGE_SOURCE)
        results = AdmissionResult.objects.filter(source__source_type=PROCOLLEGE_SOURCE)

        if year:
            sources = sources.filter(admission_year=year)
            results = results.filter(admission_year=year)

        mapping_count = UniversityExternalMapping.objects.filter(
            source=PROCOLLEGE_SOURCE
        ).count()

        self.stdout.write("=== PROCOLLEGE 초기화 대상 ===")
        if year:
            self.stdout.write(f"학년도: {year}")
        self.stdout.write(f"입시 결과: {results.count()}건")
        self.stdout.write(f"출처: {sources.count()}건")
        self.stdout.write(
            f"외부 매핑: {mapping_count}건"
            + (" (매핑은 학년도 개념이 없어 전체 삭제)" if year else "")
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "보존: ADIGA 입시 / University / Campus / 랭킹 / 투표 / 사용자"
            )
        )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "미리보기입니다. 실제 삭제하려면 --apply를 붙이세요."
                )
            )
            return

        with transaction.atomic():
            results.delete()
            sources.delete()
            UniversityExternalMapping.objects.filter(
                source=PROCOLLEGE_SOURCE
            ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "PROCOLLEGE 데이터/매핑 초기화 완료."
            )
        )
