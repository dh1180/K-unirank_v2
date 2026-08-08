from django.core.management.base import BaseCommand
from django.db import transaction

from rankings.baseline import baseline_defaults
from rankings.models import ComparisonVote, RankingBoard, UniversityRating
from rankings.services import _apply_result, ensure_default_boards


class Command(BaseCommand):
    help = "원본 ComparisonVote를 순서대로 재생해 파생 rating을 다시 계산합니다."

    def add_arguments(self, parser):
        parser.add_argument("--board", help="특정 board slug만 재계산")

    def handle(self, *args, **options):
        ensure_default_boards()
        boards = RankingBoard.objects.all()
        if options.get("board"):
            boards = boards.filter(slug=options["board"])

        for board in boards:
            with transaction.atomic():
                UniversityRating.objects.filter(board=board).delete()
                votes = (
                    ComparisonVote.objects.filter(board=board, skipped=False)
                    .select_related("university_a", "university_b")
                    .order_by("created_at", "vote_id")
                )

                count = 0
                for vote in votes.iterator():
                    rating_a, _ = UniversityRating.objects.get_or_create(
                        board=board,
                        university=vote.university_a,
                        defaults=baseline_defaults(board, vote.university_a),
                    )
                    rating_b, _ = UniversityRating.objects.get_or_create(
                        board=board,
                        university=vote.university_b,
                        defaults=baseline_defaults(board, vote.university_b),
                    )
                    _apply_result(rating_a, rating_b, vote.selected_university_id)
                    count += 1

            self.stdout.write(self.style.SUCCESS(f"{board.name}: {count}개 투표로 재계산 완료"))
