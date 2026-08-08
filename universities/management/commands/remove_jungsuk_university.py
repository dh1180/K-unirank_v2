from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from admissions.models import AdmissionAggregate, AdmissionResult, AdmissionSource, RecruitmentUnit
from rankings.models import ComparisonVote, RankingSnapshotItem, UniversityRating
from universities.models import University


TARGET_NAMES = ("정석대학", "정석대학교")


class Command(BaseCommand):
    help = "정석대학/정석대학교 레코드와 연결된 입시·랭킹 데이터를 안전하게 삭제합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 삭제합니다. 생략하면 삭제 대상만 미리보기합니다.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        universities = list(
            University.objects.filter(name__in=TARGET_NAMES).order_by("name")
        )

        if not universities:
            # 혹시 교명에 공백/캠퍼스 표기가 섞여 들어간 경우도 눈에 보이게 안내한다.
            similar = list(
                University.objects.filter(name__icontains="정석").values_list("name", flat=True)
            )
            if similar:
                raise CommandError(
                    "정확한 정석대학 레코드는 찾지 못했습니다. 유사 이름: "
                    + ", ".join(similar)
                )
            self.stdout.write(self.style.SUCCESS("정석대학 레코드가 이미 없습니다."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("정석대학 삭제 대상"))
        for university in universities:
            vote_count = ComparisonVote.objects.filter(
                Q(university_a=university)
                | Q(university_b=university)
                | Q(selected_university=university)
            ).count()
            self.stdout.write(
                f"- {university.name} (id={university.pk}) | "
                f"입시결과={AdmissionResult.objects.filter(university=university).count()}건 | "
                f"VS투표={vote_count}건 | "
                f"rating={UniversityRating.objects.filter(university=university).count()}건"
            )

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write("실제 삭제하려면 --apply 를 붙여 다시 실행하세요.")
            return

        with transaction.atomic():
            for university in universities:
                # PROTECT 관계를 먼저 제거한 뒤 University를 삭제한다.
                ComparisonVote.objects.filter(
                    Q(university_a=university)
                    | Q(university_b=university)
                    | Q(selected_university=university)
                ).delete()

                AdmissionResult.objects.filter(university=university).delete()
                AdmissionSource.objects.filter(university=university).delete()
                RecruitmentUnit.objects.filter(university=university).delete()
                AdmissionAggregate.objects.filter(university=university).delete()

                UniversityRating.objects.filter(university=university).delete()
                RankingSnapshotItem.objects.filter(university=university).delete()

                # campus / external mapping 등은 University CASCADE로 함께 정리된다.
                name = university.name
                university.delete()
                self.stdout.write(self.style.SUCCESS(f"삭제 완료: {name}"))

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "정석대학 삭제 완료. CareerNet 재동기화 시에도 제외되도록 normalizer에 등록했습니다."
            )
        )
