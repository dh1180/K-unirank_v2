from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from admissions.models import (
    AdmissionAggregate,
    AdmissionResult,
    AdmissionSource,
    RecruitmentUnit,
)
from rankings.baseline import baseline_defaults
from rankings.models import (
    ComparisonVote,
    PersonalResult,
    RankingSnapshot,
    UniversityRating,
    VoteSession,
)
from rankings.services import _apply_result
from universities.models import University


KEEP_NAMES = {"태재대학교", "서울사이버대학교"}


class Command(BaseCommand):
    help = (
        "university_type에 '사이버대학'이 포함된 대학 중 "
        "태재대학교와 서울사이버대학교만 남기고 나머지를 제거합니다. "
        "기본은 미리보기이며 --apply에서만 실제 반영됩니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 반영합니다. 생략하면 전체 작업 후 롤백합니다.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        targets = list(
            University.objects.filter(university_type__icontains="사이버대학")
            .exclude(name__in=KEEP_NAMES)
            .order_by("name")
        )

        kept = list(
            University.objects.filter(
                university_type__icontains="사이버대학",
                name__in=KEEP_NAMES,
            )
            .order_by("name")
        )

        self.stdout.write("")
        self.stdout.write("=" * 78)
        self.stdout.write(self.style.SUCCESS("[사이버대학 정리 미리보기]"))
        self.stdout.write("유지:")
        for university in kept:
            self.stdout.write(
                f"  KEEP   id={university.pk} | {university.name} "
                f"| {university.university_type or '-'}"
            )

        self.stdout.write("")
        self.stdout.write(f"삭제 대상: {len(targets)}개")
        for university in targets:
            self.stdout.write(
                f"  DELETE id={university.pk} | {university.name} "
                f"| {university.university_type or '-'}"
            )
        self.stdout.write("=" * 78)

        if not targets:
            self.stdout.write(
                self.style.SUCCESS("삭제할 나머지 사이버대학이 없습니다.")
            )
            return

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "미리보기 모드입니다. 실제 DB 변경은 마지막에 롤백됩니다."
                )
            )

        with transaction.atomic():
            target_ids = [u.pk for u in targets]

            votes = ComparisonVote.objects.filter(
                Q(university_a_id__in=target_ids)
                | Q(university_b_id__in=target_ids)
                | Q(selected_university_id__in=target_ids)
            )
            deleted_votes = votes.count()
            votes.delete()

            UniversityRating.objects.filter(
                university_id__in=target_ids
            ).delete()

            aggregates_deleted, _ = AdmissionAggregate.objects.filter(
                university_id__in=target_ids
            ).delete()

            results = AdmissionResult.objects.filter(
                Q(university_id__in=target_ids)
                | Q(source__university_id__in=target_ids)
                | Q(recruitment_unit__university_id__in=target_ids)
            ).distinct()
            deleted_results = results.count()
            results.delete()

            sources = AdmissionSource.objects.filter(
                university_id__in=target_ids
            )
            deleted_sources = sources.count()
            sources.delete()

            units = RecruitmentUnit.objects.filter(
                university_id__in=target_ids
            )
            deleted_units = units.count()
            units.delete()

            deleted_universities = 0
            for university in targets:
                university.delete()
                deleted_universities += 1

            # 삭제된 대학명이 JSON/과거 snapshot에 남지 않도록 캐시성 데이터 제거.
            snapshot_rows, _ = RankingSnapshot.objects.all().delete()
            personal_rows, _ = PersonalResult.objects.all().delete()

            # 남은 실제 투표 이력을 기준으로 rating을 다시 계산한다.
            replayed_votes = self.rebuild_all_ratings()
            recounted_sessions = self.recount_vote_sessions()

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("[처리 요약]"))
            self.stdout.write(f"  University 삭제: {deleted_universities}개")
            self.stdout.write(f"  ComparisonVote 삭제: {deleted_votes}건")
            self.stdout.write(f"  AdmissionResult 삭제: {deleted_results}건")
            self.stdout.write(f"  AdmissionSource 삭제: {deleted_sources}건")
            self.stdout.write(f"  RecruitmentUnit 삭제: {deleted_units}건")
            self.stdout.write(f"  AdmissionAggregate 삭제 row: {aggregates_deleted}")
            self.stdout.write(f"  Rating 재생 유효투표: {replayed_votes}건")
            self.stdout.write(f"  VoteSession 재계산: {recounted_sessions}개")
            self.stdout.write(f"  RankingSnapshot 삭제 row: {snapshot_rows}")
            self.stdout.write(f"  PersonalResult 삭제 row: {personal_rows}")

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "미리보기 완료: 위 변경을 모두 롤백했습니다."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "실제 반영 완료: 태재대학교/서울사이버대학교만 유지했습니다."
                    )
                )

    def rebuild_all_ratings(self):
        UniversityRating.objects.all().delete()

        pair_counts = defaultdict(int)
        processed = 0

        votes = (
            ComparisonVote.objects.filter(skipped=False)
            .select_related(
                "board",
                "university_a",
                "university_b",
                "selected_university",
            )
            .order_by("created_at", "vote_id")
        )

        for vote in votes.iterator():
            pair_key = (
                vote.session_id,
                vote.board_id,
                min(vote.university_a_id, vote.university_b_id),
                max(vote.university_a_id, vote.university_b_id),
            )
            previous = pair_counts[pair_key]
            if previous == 0:
                impact_weight = 1.0
            elif previous == 1:
                impact_weight = 0.35
            else:
                impact_weight = 0.0

            rating_a, _ = UniversityRating.objects.get_or_create(
                board=vote.board,
                university=vote.university_a,
                defaults=baseline_defaults(vote.board, vote.university_a),
            )
            rating_b, _ = UniversityRating.objects.get_or_create(
                board=vote.board,
                university=vote.university_b,
                defaults=baseline_defaults(vote.board, vote.university_b),
            )

            _apply_result(
                rating_a,
                rating_b,
                vote.selected_university_id,
                impact_weight=impact_weight,
            )

            pair_counts[pair_key] += 1
            processed += 1

        return processed

    def recount_vote_sessions(self):
        VoteSession.objects.all().update(vote_count=0)

        rows = (
            ComparisonVote.objects.values("session_id")
            .annotate(total=Count("vote_id"))
        )

        count = 0
        for row in rows.iterator():
            VoteSession.objects.filter(
                pk=row["session_id"]
            ).update(vote_count=row["total"])
            count += 1

        return count
