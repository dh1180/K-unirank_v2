from django.core.management.base import BaseCommand
from django.db import transaction

from universities.models import University, UniversityCampus
from universities.services.university_normalizer import (
    PRIMARY_CAMPUS_LABELS,
    clean_text,
    normalize_address,
    normalize_campus_label,
    normalize_region,
)


CAREER_SOURCE = "CAREER_NET"


class Command(BaseCommand):
    help = (
        "대표 지역이 '지역 미상'인 대학을 CareerNet 제1캠퍼스/본교 기준 "
        "주소·지역으로 보정합니다. 기본은 미리보기이며 --apply 시 반영합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 반영합니다.",
        )
        parser.add_argument(
            "--university",
            help="특정 대학명만 확인/보정합니다. 예: 가천대학교",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        university_name = (options.get("university") or "").strip()

        qs = University.objects.filter(is_active=True).order_by("name")
        if university_name:
            qs = qs.filter(name=university_name)

        targets = []
        skipped_no_primary = []

        for university in qs:
            current_region = normalize_region(university.region, university.address)

            # 이미 대표 지역이 정상인 대학은 건드리지 않는다.
            if current_region:
                continue

            campuses = list(
                UniversityCampus.objects.filter(
                    university=university,
                    source=CAREER_SOURCE,
                ).order_by("-is_primary", "campus_id")
            )

            primary = self.pick_primary_campus(campuses)
            if primary is None:
                skipped_no_primary.append(university)
                continue

            new_address = normalize_address(primary.address)
            new_region = normalize_region(primary.region, primary.address)

            # 제1캠퍼스 자체에도 주소/지역을 판정할 정보가 없다면 보정하지 않는다.
            if not new_address or not new_region:
                skipped_no_primary.append(university)
                continue

            targets.append(
                {
                    "university": university,
                    "campus": primary,
                    "old_address": university.address,
                    "old_region": university.region,
                    "new_address": new_address,
                    "new_region": new_region,
                }
            )

        self.stdout.write("")
        self.stdout.write("=== 제1캠퍼스 기준 대표 주소/지역 보정 ===")
        self.stdout.write(f"보정 대상: {len(targets)}개")
        self.stdout.write(f"제1캠퍼스 확인 불가: {len(skipped_no_primary)}개")
        self.stdout.write("")

        for item in targets:
            university = item["university"]
            campus = item["campus"]

            self.stdout.write(
                f"[{university.name}] "
                f"{campus.campus_name or '본교'}"
            )
            self.stdout.write(
                f"  기존: 지역={item['old_region'] or '없음'} | "
                f"주소={item['old_address'] or '없음'}"
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"  변경: 지역={item['new_region']} | "
                    f"주소={item['new_address']}"
                )
            )

        if skipped_no_primary:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("제1캠퍼스 확인 불가 대학:"))
            for university in skipped_no_primary:
                self.stdout.write(f"  - {university.name}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "미리보기입니다. 실제 반영하려면 --apply를 붙이세요."
                )
            )
            return

        updated = 0
        with transaction.atomic():
            for item in targets:
                university = item["university"]
                university.address = item["new_address"]
                university.region = item["new_region"]
                university.save(
                    update_fields=[
                        "address",
                        "region",
                        "updated_at",
                    ]
                )
                updated += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"완료: {updated}개 대학의 대표 주소/지역을 제1캠퍼스 기준으로 보정했습니다."
            )
        )

    def pick_primary_campus(self, campuses):
        # 1) sync 과정에서 이미 primary로 표시된 캠퍼스를 최우선
        for campus in campuses:
            if campus.is_primary and campus.address:
                return campus

        # 2) 이름이 본교/본캠퍼스/제1캠퍼스/1캠퍼스인 캠퍼스
        for campus in campuses:
            label = normalize_campus_label(campus.campus_name)
            if label in PRIMARY_CAMPUS_LABELS and campus.address:
                return campus

        # 임의의 제2캠퍼스를 대표 주소로 선택하지 않는다.
        return None
