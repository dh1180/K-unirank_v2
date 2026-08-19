from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Q

from admissions.models import (
    AdmissionAggregate,
    AdmissionMetric,
    AdmissionResult,
    AdmissionSource,
    RecruitmentUnit,
)
from rankings.baseline import baseline_defaults
from rankings.models import (
    ComparisonVote,
    PersonalResult,
    RankingBoard,
    RankingSnapshot,
    UniversityRating,
    VoteSession,
)
from rankings.services import _apply_result
from universities.models import (
    University,
    UniversityCampus,
    UniversityExternalMapping,
)


POLYTECH_TARGET = "한국폴리텍대학"
CYBER_TARGET = "서울사이버대학교"
CYBER_TARGET_ALIAS = "서울사이버대학"


class Command(BaseCommand):
    help = (
        "모든 한국폴리텍 University를 '한국폴리텍대학' 하나로 병합하고, "
        "'사이버'가 이름에 포함된 대학은 '서울사이버대학교'만 남기고 제거합니다. "
        "기본은 미리보기이며 --apply를 붙여야 실제 반영됩니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 반영합니다. 생략하면 전체 작업 후 롤백합니다.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        cyber_target = self.get_cyber_target()
        polytech_members = list(
            University.objects.filter(name__startswith="한국폴리텍")
            .order_by("name")
        )
        cyber_remove = list(
            University.objects.filter(name__icontains="사이버")
            .exclude(pk=cyber_target.pk)
            .order_by("name")
        )

        self.print_preflight(polytech_members, cyber_target, cyber_remove)

        if not polytech_members:
            self.stdout.write(
                self.style.WARNING("현재 한국폴리텍 University가 없습니다.")
            )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "미리보기 모드입니다. 아래 작업은 마지막에 모두 롤백됩니다."
                )
            )

        with transaction.atomic():
            summary = {
                "polytech": self.collapse_polytech(polytech_members),
                "cyber": self.purge_cyber(cyber_remove),
            }

            # 구조 변경 후 남은 투표를 기준으로 현재 랭킹 상태를 처음부터 재계산한다.
            # 기존 snapshots/personal result JSON에는 삭제된 대학명이 남을 수 있으므로 제거.
            snapshot_count, _ = RankingSnapshot.objects.all().delete()
            personal_count, _ = PersonalResult.objects.all().delete()

            rating_count = self.rebuild_all_ratings()
            session_count = self.recount_vote_sessions()

            summary["snapshots_deleted"] = snapshot_count
            summary["personal_deleted"] = personal_count
            summary["ratings_rebuilt"] = rating_count
            summary["sessions_recounted"] = session_count

            self.print_summary(summary)

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "미리보기 완료: 병합/삭제/랭킹 재계산을 전부 롤백했습니다."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "한국폴리텍 통합 + 사이버대학 정리를 실제 DB에 반영했습니다."
                    )
                )

    def get_cyber_target(self):
        target = University.objects.filter(name=CYBER_TARGET).first()
        if target is not None:
            return target

        alias = University.objects.filter(name=CYBER_TARGET_ALIAS).first()
        if alias is None:
            raise CommandError(
                f"유지 대상 '{CYBER_TARGET}'를 찾지 못했습니다. "
                "잘못된 대학을 남기지 않기 위해 작업을 중단합니다."
            )

        alias.name = CYBER_TARGET
        alias.save(update_fields=["name", "updated_at"])
        return alias

    def print_preflight(self, polytech_members, cyber_target, cyber_remove):
        self.stdout.write("")
        self.stdout.write("=" * 82)
        self.stdout.write(self.style.SUCCESS("[작업 대상 미리보기]"))

        self.stdout.write("")
        self.stdout.write(
            f"폴리텍: {len(polytech_members)}개 University -> '{POLYTECH_TARGET}' 1개"
        )
        for university in polytech_members:
            self.stdout.write(
                f"  - id={university.pk} | {university.name} "
                f"| {university.region or '-'}"
            )

        self.stdout.write("")
        self.stdout.write(
            f"사이버 유지: id={cyber_target.pk} | {cyber_target.name}"
        )
        self.stdout.write(
            f"사이버 삭제: {len(cyber_remove)}개 "
            "(이름에 '사이버'가 포함된 대학만 대상)"
        )
        for university in cyber_remove:
            self.stdout.write(
                f"  - id={university.pk} | {university.name} "
                f"| {university.region or '-'}"
            )

        self.stdout.write("=" * 82)

    # ------------------------------------------------------------
    # Polytech
    # ------------------------------------------------------------
    def collapse_polytech(self, members):
        if not members:
            return {
                "target_id": None,
                "created": False,
                "sources_removed": 0,
                "internal_votes_deleted": 0,
                "votes_repointed": 0,
                "campuses": 0,
                "mappings": 0,
                "results": 0,
                "sources": 0,
                "units": 0,
                "aggregates": 0,
            }

        target = next(
            (u for u in members if u.name == POLYTECH_TARGET),
            None,
        )
        created = False

        if target is None:
            donor = self.pick_polytech_donor(members)
            target = University.objects.create(
                name=POLYTECH_TARGET,
                short_name="한국폴리텍대학",
                address=None,
                region="전국",
                university_type=donor.university_type,
                establishment_type=donor.establishment_type,
                homepage_url=donor.homepage_url,
                college_info_url=donor.college_info_url,
                logo_path=donor.logo_path,
                is_active=True,
            )
            created = True
            members = [target] + members
        else:
            changed = []
            if target.region != "전국":
                target.region = "전국"
                changed.append("region")
            if target.address:
                target.address = None
                changed.append("address")
            if not target.logo_path:
                donor = self.pick_polytech_donor(members)
                if donor.logo_path:
                    target.logo_path = donor.logo_path
                    changed.append("logo_path")
            if not target.is_active:
                target.is_active = True
                changed.append("is_active")
            if changed:
                target.save(
                    update_fields=list(dict.fromkeys(changed + ["updated_at"]))
                )

        family_ids = {u.pk for u in members}
        family_ids.add(target.pk)
        source_ids = sorted(family_ids - {target.pk})

        # 폴리텍끼리의 기존 투표는 병합 후 self-vote가 되므로 삭제한다.
        internal_votes = ComparisonVote.objects.filter(
            university_a_id__in=family_ids,
            university_b_id__in=family_ids,
        )
        affected_sessions = set(
            internal_votes.values_list("session_id", flat=True)
        )
        internal_vote_count = internal_votes.count()
        internal_votes.delete()

        # 외부 대학과의 폴리텍 투표는 새 대표 University로 이동.
        votes_a = ComparisonVote.objects.filter(
            university_a_id__in=source_ids
        ).update(university_a=target)
        votes_b = ComparisonVote.objects.filter(
            university_b_id__in=source_ids
        ).update(university_b=target)
        votes_selected = ComparisonVote.objects.filter(
            selected_university_id__in=source_ids
        ).update(selected_university=target)

        # Campus / mapping을 먼저 대표 University로 이동한다.
        campus_count = UniversityCampus.objects.filter(
            university_id__in=source_ids
        ).update(university=target)
        mapping_count = UniversityExternalMapping.objects.filter(
            university_id__in=source_ids
        ).update(university=target)

        # 모집단위는 (target, campus, name) unique를 지키며 병합한다.
        unit_moved = 0
        source_units = list(
            RecruitmentUnit.objects.filter(
                university_id__in=source_ids
            )
            .select_related("campus")
            .order_by("recruitment_unit_id")
        )

        for old_unit in source_units:
            existing = (
                RecruitmentUnit.objects.filter(
                    university=target,
                    campus_id=old_unit.campus_id,
                    name=old_unit.name,
                )
                .exclude(pk=old_unit.pk)
                .first()
            )
            if existing is not None:
                AdmissionResult.objects.filter(
                    recruitment_unit=old_unit
                ).update(recruitment_unit=existing)
                old_unit.delete()
            else:
                old_unit.university = target
                old_unit.save(update_fields=["university"])
            unit_moved += 1

        source_count = AdmissionSource.objects.filter(
            university_id__in=source_ids
        ).update(university=target)

        result_count = AdmissionResult.objects.filter(
            university_id__in=source_ids
        ).update(university=target)

        # 기존 family aggregate는 모두 버리고 통합 대학 기준으로 재계산.
        AdmissionAggregate.objects.filter(
            university_id__in=family_ids
        ).delete()
        aggregate_count = self.rebuild_aggregates(target)

        # 현재 Rating은 전체 투표 재생 단계에서 다시 만들 것이므로 우선 family 것을 제거.
        UniversityRating.objects.filter(
            university_id__in=family_ids
        ).delete()

        # 스냅샷은 전체 삭제 단계에서 정리되므로 FK 충돌 걱정 없이 source 삭제.
        deleted_sources = 0
        for source_id in source_ids:
            source = University.objects.get(pk=source_id)
            source.delete()
            deleted_sources += 1

        return {
            "target_id": target.pk,
            "created": created,
            "sources_removed": deleted_sources,
            "internal_votes_deleted": internal_vote_count,
            "affected_sessions": len(affected_sessions),
            "votes_repointed": votes_a + votes_b + votes_selected,
            "campuses": campus_count,
            "mappings": mapping_count,
            "results": result_count,
            "sources": source_count,
            "units": unit_moved,
            "aggregates": aggregate_count,
        }

    def pick_polytech_donor(self, members):
        # 로고가 있는 IV 캠퍼스를 우선, 없으면 아무 로고가 있는 폴리텍,
        # 그것도 없으면 첫 University의 metadata를 사용한다.
        preferred = [
            u for u in members
            if "IV" in u.name and u.logo_path
        ]
        if preferred:
            return sorted(preferred, key=lambda u: u.name)[0]

        with_logo = [u for u in members if u.logo_path]
        if with_logo:
            return sorted(with_logo, key=lambda u: u.name)[0]

        return sorted(members, key=lambda u: u.name)[0]

    # ------------------------------------------------------------
    # Cyber universities
    # ------------------------------------------------------------
    def purge_cyber(self, universities):
        if not universities:
            return {
                "universities_deleted": 0,
                "votes_deleted": 0,
                "results_deleted": 0,
                "sources_deleted": 0,
                "units_deleted": 0,
                "aggregates_deleted": 0,
            }

        ids = [u.pk for u in universities]

        # 다른 대학과의 VS까지 포함해 삭제 대상 사이버대가 등장하는 투표는 제거.
        cyber_votes = ComparisonVote.objects.filter(
            Q(university_a_id__in=ids)
            | Q(university_b_id__in=ids)
            | Q(selected_university_id__in=ids)
        )
        vote_count = cyber_votes.count()
        cyber_votes.delete()

        UniversityRating.objects.filter(
            university_id__in=ids
        ).delete()

        aggregates_deleted, _ = AdmissionAggregate.objects.filter(
            university_id__in=ids
        ).delete()

        # source/result/unit 사이 PROTECT 관계를 고려해 result부터 제거한다.
        results = AdmissionResult.objects.filter(
            Q(university_id__in=ids)
            | Q(source__university_id__in=ids)
            | Q(recruitment_unit__university_id__in=ids)
        ).distinct()
        result_count = results.count()
        results.delete()

        sources = AdmissionSource.objects.filter(
            university_id__in=ids
        )
        source_count = sources.count()
        sources.delete()

        units = RecruitmentUnit.objects.filter(
            university_id__in=ids
        )
        unit_count = units.count()
        units.delete()

        # 캠퍼스/외부매핑/스냅샷은 University CASCADE로 함께 제거된다.
        deleted_universities = 0
        for university in universities:
            university.delete()
            deleted_universities += 1

        return {
            "universities_deleted": deleted_universities,
            "votes_deleted": vote_count,
            "results_deleted": result_count,
            "sources_deleted": source_count,
            "units_deleted": unit_count,
            "aggregates_deleted": aggregates_deleted,
        }

    # ------------------------------------------------------------
    # Admissions aggregate rebuild
    # ------------------------------------------------------------
    def rebuild_aggregates(self, target):
        metrics = (
            AdmissionMetric.objects
            .select_related("result")
            .filter(result__university=target)
        )

        groups = defaultdict(list)
        for metric in metrics.iterator():
            result = metric.result
            key = (
                result.admission_year,
                result.admission_phase,
                result.selection_category,
                metric.metric_code,
            )
            groups[key].append(
                (metric.value, result.recruitment_count)
            )

        count = 0
        for key, values in groups.items():
            year, phase, category, metric_code = key

            weighted_values = [
                (value, weight)
                for value, weight in values
                if weight and weight > 0
            ]

            if weighted_values:
                total_weight = sum(
                    Decimal(weight)
                    for _, weight in weighted_values
                )
                aggregate_value = (
                    sum(
                        value * Decimal(weight)
                        for value, weight in weighted_values
                    )
                    / total_weight
                )
                method = "WEIGHTED_BY_RECRUITMENT"
            else:
                aggregate_value = (
                    sum(value for value, _ in values)
                    / Decimal(len(values))
                )
                method = "SIMPLE_AVERAGE"

            AdmissionAggregate.objects.create(
                university=target,
                admission_year=year,
                admission_phase=phase,
                selection_category=category,
                metric_code=metric_code,
                aggregation_method=method,
                value=aggregate_value,
                sample_count=len(values),
            )
            count += 1

        return count

    # ------------------------------------------------------------
    # Rebuild ranking state from the remaining canonical vote history
    # ------------------------------------------------------------
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
                defaults=baseline_defaults(
                    vote.board,
                    vote.university_a,
                ),
            )
            rating_b, _ = UniversityRating.objects.get_or_create(
                board=vote.board,
                university=vote.university_b,
                defaults=baseline_defaults(
                    vote.board,
                    vote.university_b,
                ),
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

    def print_summary(self, summary):
        poly = summary["polytech"]
        cyber = summary["cyber"]

        self.stdout.write("")
        self.stdout.write("=" * 82)
        self.stdout.write(self.style.SUCCESS("[최종 작업 요약]"))

        self.stdout.write("")
        self.stdout.write("[한국폴리텍]")
        self.stdout.write(
            f"  최종 University id={poly['target_id']} | {POLYTECH_TARGET}"
        )
        self.stdout.write(
            f"  중복 University 삭제 {poly['sources_removed']}개"
        )
        self.stdout.write(
            f"  폴리텍 내부 self-vote 예정 투표 삭제 "
            f"{poly['internal_votes_deleted']}건"
        )
        self.stdout.write(
            f"  외부 VS 참조 이동 {poly['votes_repointed']}건"
        )
        self.stdout.write(
            f"  Campus {poly['campuses']} / Mapping {poly['mappings']} 이동"
        )
        self.stdout.write(
            f"  AdmissionResult {poly['results']} / "
            f"AdmissionSource {poly['sources']} 이동"
        )
        self.stdout.write(
            f"  RecruitmentUnit {poly['units']} 처리 / "
            f"Aggregate {poly['aggregates']} 재계산"
        )

        self.stdout.write("")
        self.stdout.write("[사이버대학]")
        self.stdout.write(
            f"  유지: {CYBER_TARGET}"
        )
        self.stdout.write(
            f"  삭제 University {cyber['universities_deleted']}개"
        )
        self.stdout.write(
            f"  삭제 투표 {cyber['votes_deleted']}건"
        )
        self.stdout.write(
            f"  삭제 입결 Result {cyber['results_deleted']}건 / "
            f"Source {cyber['sources_deleted']}건 / "
            f"Unit {cyber['units_deleted']}건"
        )

        self.stdout.write("")
        self.stdout.write("[랭킹 일관성]")
        self.stdout.write(
            f"  남은 유효 투표를 재생해 Rating {summary['ratings_rebuilt']}건 처리"
        )
        self.stdout.write(
            f"  VoteSession vote_count {summary['sessions_recounted']}개 세션 재계산"
        )
        self.stdout.write(
            f"  기존 RankingSnapshot 삭제 {summary['snapshots_deleted']}개 row"
        )
        self.stdout.write(
            f"  기존 PersonalResult 캐시 삭제 {summary['personal_deleted']}개 row"
        )

        self.stdout.write("=" * 82)
