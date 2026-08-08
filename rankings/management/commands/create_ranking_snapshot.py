from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from rankings.models import ComparisonVote, RankingBoard, RankingSnapshot, RankingSnapshotItem, UniversityRating
from rankings.services import ensure_default_boards


class Command(BaseCommand):
    help = "현재 랭킹을 일자별 스냅샷으로 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--board", help="특정 board slug만 저장")

    def handle(self, *args, **options):
        ensure_default_boards()
        boards = RankingBoard.objects.filter(is_active=True)
        if options.get("board"):
            boards = boards.filter(slug=options["board"])

        today = timezone.localdate()

        for board in boards:
            with transaction.atomic():
                snapshot, _ = RankingSnapshot.objects.update_or_create(
                    board=board,
                    snapshot_date=today,
                    defaults={"total_votes": ComparisonVote.objects.filter(board=board, skipped=False).count()},
                )
                snapshot.items.all().delete()

                ratings = UniversityRating.objects.filter(
                    board=board,
                    university__is_active=True,
                    match_count__gt=0,
                ).order_by("-rating", "university__name")

                RankingSnapshotItem.objects.bulk_create(
                    [
                        RankingSnapshotItem(
                            snapshot=snapshot,
                            university=rating.university,
                            rank=rank,
                            rating=rating.rating,
                            match_count=rating.match_count,
                        )
                        for rank, rating in enumerate(ratings, start=1)
                    ]
                )

            self.stdout.write(self.style.SUCCESS(f"{board.name}: {today} 스냅샷 저장 완료"))
