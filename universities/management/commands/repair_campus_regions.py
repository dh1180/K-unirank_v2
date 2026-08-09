from django.core.management.base import BaseCommand
from django.db import transaction

from universities.models import UniversityCampus
from universities.services.university_normalizer import (
    normalize_address,
    normalize_region,
)


class Command(BaseCommand):
    help = (
        "UniversityCampus.region을 저장된 region 값이 아니라 실제 address 기준으로 "
        "재계산합니다. 기본은 미리보기이며 --apply를 붙여야 반영됩니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 반영합니다. 생략하면 롤백합니다.",
        )
        parser.add_argument(
            "--source",
            type=str,
            help="특정 source만 처리합니다. 예: --source ADIGA",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        source = (options.get("source") or "").strip()

        queryset = UniversityCampus.objects.select_related(
            "university"
        ).order_by("campus_id")

        if source:
            queryset = queryset.filter(source=source)

        changes = []

        with transaction.atomic():
            for campus in queryset.iterator():
                address = normalize_address(campus.address)
                if not address:
                    continue

                derived_region = normalize_region(None, address)
                if not derived_region:
                    continue

                if campus.region == derived_region:
                    continue

                changes.append(
                    (
                        campus.campus_id,
                        campus.university.name,
                        campus.campus_name or "",
                        campus.region or "",
                        derived_region,
                        address,
                    )
                )

                campus.region = derived_region
                campus.save(
                    update_fields=["region", "updated_at"]
                )

            self.stdout.write(
                f"주소 기준 region 보정 대상: {len(changes)}개"
            )

            for row in changes[:100]:
                (
                    campus_id,
                    university_name,
                    campus_name,
                    before,
                    after,
                    address,
                ) = row
                self.stdout.write(
                    f"{campus_id} | {university_name} | "
                    f"{campus_name or '-'} | "
                    f"{before or '-'} -> {after} | {address}"
                )

            if len(changes) > 100:
                self.stdout.write(
                    f"... 외 {len(changes) - 100}개"
                )

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "미리보기 완료: 실제 DB 변경은 롤백했습니다."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"UniversityCampus.region {len(changes)}개를 보정했습니다."
                    )
                )
