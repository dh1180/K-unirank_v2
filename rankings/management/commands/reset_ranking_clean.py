from django.core.management.base import BaseCommand
from django.db import transaction

from rankings.models import (
    ComparisonVote,
    PersonalResult,
    RankingSnapshot,
    UniversityRating,
    VoteSession,
)
from rankings.services import ensure_default_boards


class Command(BaseCommand):
    help = (
        "대학/입시 데이터는 유지하고 랭킹·VS 데이터만 완전히 초기화합니다. "
        "기본은 미리보기이며 --apply를 붙여야 실제 삭제됩니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 랭킹 초기화를 반영합니다.",
        )

    def handle(self, *args, **options):
        counts = {
            "comparison_votes": ComparisonVote.objects.count(),
            "vote_sessions": VoteSession.objects.count(),
            "personal_results": PersonalResult.objects.count(),
            "ranking_snapshots": RankingSnapshot.objects.count(),
            "ratings": UniversityRating.objects.count(),
        }

        self.stdout.write("=== K-unirank 랭킹 초기화 대상 ===")
        self.stdout.write(f"실제/테스트 VS 투표: {counts['comparison_votes']}건")
        self.stdout.write(f"투표 세션: {counts['vote_sessions']}건")
        self.stdout.write(f"개인 결과: {counts['personal_results']}건")
        self.stdout.write(f"랭킹 스냅샷: {counts['ranking_snapshots']}건")
        self.stdout.write(f"대학 Rating: {counts['ratings']}건")
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "보존: University / Campus / CareerNet·ADIGA 매핑 / 입시 결과 / 사용자 계정"
            )
        )

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    "미리보기입니다. 실제 초기화하려면 --apply를 붙이세요."
                )
            )
            return

        with transaction.atomic():
            # PROTECT 관계 때문에 vote를 session보다 먼저 삭제한다.
            ComparisonVote.objects.all().delete()
            PersonalResult.objects.all().delete()
            RankingSnapshot.objects.all().delete()  # items cascade
            UniversityRating.objects.all().delete()
            VoteSession.objects.all().delete()

            # overall 보드 자체는 유지/복구한다.
            ensure_default_boards()

        self.stdout.write(
            self.style.SUCCESS(
                "랭킹 초기화 완료: 이제 모든 대학은 첫 실제 VS에서 1500점/0전으로 시작합니다."
            )
        )
