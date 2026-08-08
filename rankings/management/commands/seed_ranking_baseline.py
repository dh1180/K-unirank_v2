from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from rankings.baseline import (
    DEFAULT_BASE_RATING,
    OVERALL_BASELINE,
    SEEDED_RD,
    baseline_rating_for_name,
    normalize_name,
    ranking_university_queryset,
)
from rankings.models import RankingBoard, UniversityRating
from rankings.services import ensure_default_boards
from universities.models import University


class Command(BaseCommand):
    help = (
        "종합 랭킹에 운영자 정의 초기 시드값을 넣습니다. "
        "이원화/분교 캠퍼스도 별도 점수로 포함하며 ComparisonVote는 생성하지 않습니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--board", default="overall", help="대상 board slug (기본 overall)")
        parser.add_argument("--apply", action="store_true", help="실제 DB에 반영")
        parser.add_argument(
            "--force",
            action="store_true",
            help="이미 사용자 비교가 있는 rating도 시작점으로 덮어쓰기 (주의)",
        )
        parser.add_argument(
            "--include-all",
            action="store_true",
            help=f"시드 목록 밖 활성 대학도 {DEFAULT_BASE_RATING:.0f}점 rating row 생성",
        )

    def handle(self, *args, **options):
        ensure_default_boards()
        try:
            board = RankingBoard.objects.get(slug=options["board"])
        except RankingBoard.DoesNotExist as exc:
            raise CommandError(f"board를 찾을 수 없습니다: {options['board']}") from exc

        if board.slug != "overall":
            self.stdout.write(
                self.style.WARNING(
                    "현재 시드 목록은 overall 기준으로 설계되었습니다. 다른 board에는 1500 기본값이 사용됩니다."
                )
            )

        universities = list(ranking_university_queryset().order_by("name"))
        by_key = {normalize_name(u.name): u for u in universities}

        resolved = []
        missing = []
        used_ids = set()

        for seed_name, seed_rating in OVERALL_BASELINE:
            key = normalize_name(seed_name)
            university = by_key.get(key)

            if university is None:
                candidates = [
                    u for u in universities
                    if normalize_name(u.name).startswith(key)
                    or key.startswith(normalize_name(u.name))
                ]
                # Only accept an unambiguous fallback. This prevents e.g.
                # 연세대학교 seed from silently applying to 미래캠퍼스.
                if len(candidates) == 1:
                    university = candidates[0]

            if university is None:
                missing.append(seed_name)
                continue

            if university.pk in used_ids:
                continue
            used_ids.add(university.pk)
            resolved.append((university, seed_rating))

        self.stdout.write(f"대상 보드: {board.name} ({board.slug})")
        self.stdout.write(f"시드 매칭: {len(resolved)}개 / 미매칭: {len(missing)}개")
        for rank, (university, rating) in enumerate(resolved, start=1):
            self.stdout.write(f"  {rank:>2}. {university.name:<24} {rating:.0f}")

        if missing:
            self.stdout.write(self.style.WARNING("미매칭: " + ", ".join(missing)))

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("미리보기입니다. 실제 반영은 --apply를 붙이세요."))
            return

        created = updated = skipped_live = 0
        with transaction.atomic():
            for university, seed_rating in resolved:
                rating, was_created = UniversityRating.objects.get_or_create(
                    board=board,
                    university=university,
                    defaults={
                        "rating": seed_rating,
                        "rating_deviation": SEEDED_RD,
                        "volatility": 0.06,
                        "match_count": 0,
                        "win_count": 0,
                        "loss_count": 0,
                    },
                )
                if was_created:
                    created += 1
                    continue

                if rating.match_count > 0 and not options["force"]:
                    skipped_live += 1
                    continue

                rating.rating = seed_rating
                rating.rating_deviation = SEEDED_RD
                rating.volatility = 0.06
                rating.save(update_fields=["rating", "rating_deviation", "volatility", "updated_at"])
                updated += 1

            if options["include_all"]:
                for university in universities:
                    if university.pk in used_ids:
                        continue
                    rating, was_created = UniversityRating.objects.get_or_create(
                        board=board,
                        university=university,
                        defaults={
                            "rating": baseline_rating_for_name(university.name, board.slug),
                            "rating_deviation": 350.0,
                            "volatility": 0.06,
                            "match_count": 0,
                            "win_count": 0,
                            "loss_count": 0,
                        },
                    )
                    if was_created:
                        created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"완료: 생성 {created} / 갱신 {updated} / 기존 사용자 비교 보존으로 건너뜀 {skipped_live}"
            )
        )
        if skipped_live:
            self.stdout.write(
                self.style.WARNING(
                    "기존 비교가 있는 학교까지 시드를 강제로 덮어쓰려면 --force를 추가하세요."
                )
            )
