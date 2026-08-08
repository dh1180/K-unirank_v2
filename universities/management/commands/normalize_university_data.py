from collections import defaultdict

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import (
    AdmissionAggregate,
    AdmissionResult,
    AdmissionSource,
    RecruitmentUnit,
)
from rankings.models import (
    ComparisonVote,
    PersonalResult,
    RankingSnapshot,
    UniversityRating,
)
from universities.models import University
from universities.services.university_normalizer import (
    canonical_university_name,
    normalize_address,
    normalize_region,
)


class Command(BaseCommand):
    help = "실제 통합 대학만 합치고 대학명, 지역, 주소 표기를 정리합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 반영합니다. 생략하면 변경 예정 내용만 보여줍니다.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        universities = list(University.objects.all().order_by("university_id"))

        groups = defaultdict(list)
        for university in universities:
            groups[canonical_university_name(university.name)].append(university)

        merge_groups = {
            name: items
            for name, items in groups.items()
            if name and (len(items) > 1 or items[0].name != name)
        }

        self.stdout.write(f"대학 {len(universities)}개 확인")
        self.stdout.write(f"통합 또는 이름 정리 대상 {len(merge_groups)}그룹")

        for canonical_name, items in sorted(merge_groups.items()):
            names = ", ".join(item.name for item in items)
            self.stdout.write(f"- {names} -> {canonical_name}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "미리보기만 했습니다. 실제 반영은 "
                    "python manage.py normalize_university_data --apply"
                )
            )
            return

        merged_count = 0
        renamed_count = 0
        location_count = 0

        with transaction.atomic():
            for canonical_name, items in sorted(merge_groups.items()):
                target = self.choose_target(canonical_name, items)
                duplicates = [item for item in items if item.pk != target.pk]
                if canonical_name == "국립경국대학교":
                    duplicates.sort(
                        key=lambda item: (
                            item.name not in {"안동대학교", "국립안동대학교"},
                            item.pk,
                        )
                    )

                for duplicate in duplicates:
                    self.merge_university(target, duplicate)
                    merged_count += 1

                if target.name != canonical_name:
                    target.name = canonical_name
                    renamed_count += 1

                self.fill_location_from_primary_campus(target)
                target.address = normalize_address(target.address)
                target.region = normalize_region(target.region, target.address)
                target.save()

            for university in University.objects.all():
                old_address = university.address
                old_region = university.region
                self.fill_location_from_primary_campus(university)
                university.address = normalize_address(university.address)
                university.region = normalize_region(university.region, university.address)

                if university.address != old_address or university.region != old_region:
                    university.save(update_fields=["address", "region", "updated_at"])
                    location_count += 1

            if merged_count:
                UniversityRating.objects.all().delete()
                RankingSnapshot.objects.all().delete()
                PersonalResult.objects.all().delete()
                AdmissionAggregate.objects.all().delete()

        if merged_count:
            call_command("rebuild_ratings")
            call_command("recalculate_admission_aggregates")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"완료: 통합 {merged_count}개, 이름 정리 {renamed_count}개, "
                f"주소/지역 정리 {location_count}개"
            )
        )

    def choose_target(self, canonical_name, items):
        exact = [item for item in items if item.name == canonical_name]
        if exact:
            return min(exact, key=lambda item: item.pk)

        with_logo = [item for item in items if item.logo_path]
        if with_logo:
            return min(with_logo, key=lambda item: item.pk)

        return min(items, key=lambda item: item.pk)

    def fill_location_from_primary_campus(self, university):
        primary = (
            university.campuses.filter(is_primary=True)
            .order_by("campus_id")
            .first()
        )

        if primary is None:
            primary = university.campuses.order_by("campus_id").first()

        if primary:
            if not university.address and primary.address:
                university.address = primary.address
            if not university.region and primary.region:
                university.region = primary.region

    def merge_university(self, target, duplicate):
        if not target.logo_path and duplicate.logo_path:
            target.logo_path = duplicate.logo_path

        if not target.address and duplicate.address:
            target.address = duplicate.address

        if not target.region and duplicate.region:
            target.region = duplicate.region

        if not target.homepage_url and duplicate.homepage_url:
            target.homepage_url = duplicate.homepage_url

        duplicate.campuses.update(university=target)
        duplicate.external_mappings.update(university=target)

        self.merge_recruitment_units(target, duplicate)
        AdmissionSource.objects.filter(university=duplicate).update(university=target)
        AdmissionResult.objects.filter(university=duplicate).update(university=target)

        ComparisonVote.objects.filter(university_a=duplicate).update(university_a=target)
        ComparisonVote.objects.filter(university_b=duplicate).update(university_b=target)
        ComparisonVote.objects.filter(selected_university=duplicate).update(selected_university=target)
        ComparisonVote.objects.filter(university_a=target, university_b=target).delete()

        duplicate.delete()
        target.save()

    def merge_recruitment_units(self, target, duplicate):
        for unit in list(RecruitmentUnit.objects.filter(university=duplicate)):
            existing = RecruitmentUnit.objects.filter(
                university=target,
                campus=unit.campus,
                name=unit.name,
            ).first()

            if existing:
                AdmissionResult.objects.filter(recruitment_unit=unit).update(
                    recruitment_unit=existing
                )
                unit.delete()
            else:
                unit.university = target
                unit.save(update_fields=["university"])
