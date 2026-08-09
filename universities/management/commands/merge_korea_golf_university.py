from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from admissions.models import (
    AdmissionAggregate,
    AdmissionMetric,
    AdmissionResult,
    AdmissionSource,
    RecruitmentUnit,
)
from rankings.models import (
    ComparisonVote,
    RankingSnapshotItem,
    UniversityRating,
)
from universities.models import (
    University,
    UniversityCampus,
    UniversityExternalMapping,
)


SOURCE_NAME = "한국골프대학교"
TARGET_NAME = "한국골프과학기술대학교"


class Command(BaseCommand):
    help = (
        "'한국골프대학교' 중복 레코드를 '한국골프과학기술대학교'로 안전하게 병합합니다. "
        "캠퍼스/외부매핑/입결/랭킹 참조를 이전한 뒤 중복 University를 삭제합니다. "
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

        target = University.objects.filter(name=TARGET_NAME).first()
        source = University.objects.filter(name=SOURCE_NAME).first()

        if source is None:
            if target is not None:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"이미 병합된 상태입니다: '{TARGET_NAME}'만 존재합니다."
                    )
                )
                return
            raise CommandError(
                f"'{SOURCE_NAME}'와 '{TARGET_NAME}' 모두 찾지 못했습니다."
            )

        if target is None:
            self.stdout.write(
                self.style.WARNING(
                    f"'{TARGET_NAME}'가 없어 기존 '{SOURCE_NAME}' 레코드를 "
                    f"'{TARGET_NAME}'로 이름만 변경합니다."
                )
            )
            with transaction.atomic():
                source.name = TARGET_NAME
                source.save(update_fields=["name", "updated_at"])

                if not apply_changes:
                    transaction.set_rollback(True)
                    self.stdout.write(
                        self.style.WARNING(
                            "미리보기 완료: 이름 변경을 롤백했습니다."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"'{SOURCE_NAME}' -> '{TARGET_NAME}' 변경 완료."
                        )
                    )
            return

        self.preflight(target, source)

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "미리보기 모드입니다. 모든 변경은 마지막에 롤백됩니다."
                )
            )

        with transaction.atomic():
            summary = self.merge(target, source)
            self.print_summary(summary)

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "미리보기 완료: 병합/삭제 작업을 모두 롤백했습니다."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"'{SOURCE_NAME}'를 '{TARGET_NAME}'로 병합하고 "
                        "중복 University를 삭제했습니다."
                    )
                )

    def preflight(self, target, source):
        # 1) 두 중복 대학끼리 직접 비교된 투표는 병합 후 self-vote가 되므로 중단.
        direct_votes = ComparisonVote.objects.filter(
            Q(university_a=source, university_b=target)
            | Q(university_a=target, university_b=source)
        ).count()
        if direct_votes:
            raise CommandError(
                f"두 중복 대학끼리 직접 비교된 투표가 {direct_votes}건 있어 "
                "자동 병합하면 자기 자신과의 비교가 됩니다. "
                "해당 투표를 먼저 별도 검토해주세요."
            )

        # 2) 같은 board에서 양쪽 모두 실제 투표 이력이 있는 rating은
        # Glicko 상태를 수학적으로 정확히 합칠 수 없으므로 임의 병합하지 않는다.
        target_ratings = {
            rating.board_id: rating
            for rating in UniversityRating.objects.filter(university=target)
        }
        conflicts = []
        for source_rating in UniversityRating.objects.filter(
            university=source
        ).select_related("board"):
            target_rating = target_ratings.get(source_rating.board_id)
            if (
                target_rating is not None
                and source_rating.match_count > 0
                and target_rating.match_count > 0
            ):
                conflicts.append(
                    (
                        source_rating.board.slug,
                        target_rating.match_count,
                        source_rating.match_count,
                    )
                )

        if conflicts:
            detail = ", ".join(
                f"{slug}: target {target_count}전/source {source_count}전"
                for slug, target_count, source_count in conflicts
            )
            raise CommandError(
                "양쪽 University에 모두 실제 rating 이력이 있어 자동 병합을 "
                f"중단합니다. {detail}"
            )

        # 3) 같은 snapshot에 두 대학이 모두 존재하면 historical rank 중 하나를
        # 임의로 삭제해야 하므로 자동 병합하지 않는다.
        source_snapshot_ids = set(
            RankingSnapshotItem.objects.filter(university=source)
            .values_list("snapshot_id", flat=True)
        )
        target_snapshot_ids = set(
            RankingSnapshotItem.objects.filter(university=target)
            .values_list("snapshot_id", flat=True)
        )
        snapshot_conflicts = source_snapshot_ids & target_snapshot_ids
        if snapshot_conflicts:
            raise CommandError(
                "같은 RankingSnapshot에 두 중복 대학이 동시에 존재하는 기록이 "
                f"{len(snapshot_conflicts)}개 있어 자동 병합을 중단합니다."
            )

    def merge(self, target, source):
        summary = {
            "target_id": target.pk,
            "source_id": source.pk,
            "metadata": [],
            "campuses": 0,
            "mappings": 0,
            "recruitment_units_moved": 0,
            "recruitment_units_merged": 0,
            "sources": 0,
            "results": 0,
            "votes_a": 0,
            "votes_b": 0,
            "selected_votes": 0,
            "ratings_moved": 0,
            "ratings_merged": 0,
            "snapshot_items": 0,
            "aggregates": 0,
        }

        # ----------------------------------------------------
        # Metadata: desired University name/PK wins, but fill blanks
        # from the duplicate. This preserves the visible golf logo
        # when the target currently has no logo.
        # ----------------------------------------------------
        metadata_fields = (
            "short_name",
            "address",
            "region",
            "university_type",
            "establishment_type",
            "homepage_url",
            "college_info_url",
            "logo_path",
        )
        changed_fields = []
        for field in metadata_fields:
            target_value = getattr(target, field)
            source_value = getattr(source, field)
            if not target_value and source_value:
                setattr(target, field, source_value)
                changed_fields.append(field)
                summary["metadata"].append(field)

        if not target.is_active and source.is_active:
            target.is_active = True
            changed_fields.append("is_active")
            summary["metadata"].append("is_active")

        if changed_fields:
            target.save(
                update_fields=list(dict.fromkeys(changed_fields + ["updated_at"]))
            )

        # ----------------------------------------------------
        # Campus + external mapping
        # ----------------------------------------------------
        summary["campuses"] = UniversityCampus.objects.filter(
            university=source
        ).update(university=target)

        summary["mappings"] = UniversityExternalMapping.objects.filter(
            university=source
        ).update(university=target)

        # ----------------------------------------------------
        # RecruitmentUnit.
        # If the target already has the same (campus, name) unit,
        # point results to the existing unit and remove the duplicate.
        # ----------------------------------------------------
        for old_unit in list(
            RecruitmentUnit.objects.filter(university=source)
            .select_related("campus")
            .order_by("recruitment_unit_id")
        ):
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

                changed = []
                if old_unit.college_name and not existing.college_name:
                    existing.college_name = old_unit.college_name
                    changed.append("college_name")
                if old_unit.is_active and not existing.is_active:
                    existing.is_active = True
                    changed.append("is_active")
                if changed:
                    existing.save(update_fields=changed)

                old_unit.delete()
                summary["recruitment_units_merged"] += 1
            else:
                old_unit.university = target
                old_unit.save(update_fields=["university"])
                summary["recruitment_units_moved"] += 1

        # ----------------------------------------------------
        # Admissions
        # ----------------------------------------------------
        summary["sources"] = AdmissionSource.objects.filter(
            university=source
        ).update(university=target)

        summary["results"] = AdmissionResult.objects.filter(
            university=source
        ).update(university=target)

        # Old aggregates are no longer trustworthy after merge.
        AdmissionAggregate.objects.filter(
            university__in=[target, source]
        ).delete()
        summary["aggregates"] = self.rebuild_aggregates(target)

        # ----------------------------------------------------
        # Ranking votes
        # direct target-vs-source pairs were rejected in preflight.
        # ----------------------------------------------------
        summary["votes_a"] = ComparisonVote.objects.filter(
            university_a=source
        ).update(university_a=target)

        summary["votes_b"] = ComparisonVote.objects.filter(
            university_b=source
        ).update(university_b=target)

        summary["selected_votes"] = ComparisonVote.objects.filter(
            selected_university=source
        ).update(selected_university=target)

        # ----------------------------------------------------
        # Ratings
        # - no target rating: move source rating
        # - source has no matches: target wins; delete empty source state
        # - target has no matches: copy source state into target then delete source
        # - both have matches: already blocked by preflight
        # ----------------------------------------------------
        for source_rating in list(
            UniversityRating.objects.filter(
                university=source
            ).select_related("board")
        ):
            target_rating = UniversityRating.objects.filter(
                university=target,
                board=source_rating.board,
            ).first()

            if target_rating is None:
                source_rating.university = target
                source_rating.save(update_fields=["university", "updated_at"])
                summary["ratings_moved"] += 1
                continue

            if source_rating.match_count == 0:
                source_rating.delete()
                summary["ratings_merged"] += 1
                continue

            if target_rating.match_count == 0:
                target_rating.rating = source_rating.rating
                target_rating.rating_deviation = source_rating.rating_deviation
                target_rating.volatility = source_rating.volatility
                target_rating.match_count = source_rating.match_count
                target_rating.win_count = source_rating.win_count
                target_rating.loss_count = source_rating.loss_count
                target_rating.save(
                    update_fields=[
                        "rating",
                        "rating_deviation",
                        "volatility",
                        "match_count",
                        "win_count",
                        "loss_count",
                        "updated_at",
                    ]
                )
                source_rating.delete()
                summary["ratings_merged"] += 1
                continue

            raise CommandError(
                "preflight를 통과하지 못했어야 하는 rating 충돌이 발견되었습니다."
            )

        # ----------------------------------------------------
        # Historical ranking snapshot items.
        # Same-snapshot conflict was rejected in preflight.
        # ----------------------------------------------------
        summary["snapshot_items"] = RankingSnapshotItem.objects.filter(
            university=source
        ).update(university=target)

        # ----------------------------------------------------
        # Safety check: before deleting source, make sure no unknown
        # reverse relation containing rows would be cascaded/lost.
        # ----------------------------------------------------
        self.assert_no_unhandled_relations(source)

        source.delete()
        return summary

    def assert_no_unhandled_relations(self, source):
        handled_model_labels = {
            "universities.UniversityCampus",
            "universities.UniversityExternalMapping",
            "admissions.RecruitmentUnit",
            "admissions.AdmissionSource",
            "admissions.AdmissionResult",
            "admissions.AdmissionAggregate",
            "rankings.ComparisonVote",
            "rankings.UniversityRating",
            "rankings.RankingSnapshotItem",
        }

        leftovers = []

        for relation in source._meta.related_objects:
            model = relation.related_model
            model_label = model._meta.label

            if model_label in handled_model_labels:
                continue

            field_name = relation.field.name
            count = model._default_manager.filter(
                **{field_name: source}
            ).count()

            if count:
                leftovers.append(
                    f"{model_label}.{field_name}={count}"
                )

        if leftovers:
            raise CommandError(
                "아직 처리하지 않은 University 참조 데이터가 있어 중복 대학 삭제를 "
                "중단합니다: "
                + ", ".join(leftovers)
            )

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

    def print_summary(self, summary):
        self.stdout.write("")
        self.stdout.write("=" * 72)
        self.stdout.write(
            self.style.SUCCESS("[한국골프대학교 중복 병합 결과]")
        )
        self.stdout.write(
            f"유지 University: {TARGET_NAME} (id={summary['target_id']})"
        )
        self.stdout.write(
            f"삭제 대상 University: {SOURCE_NAME} (id={summary['source_id']})"
        )

        if summary["metadata"]:
            self.stdout.write(
                "메타데이터 보완: "
                + ", ".join(summary["metadata"])
            )
        else:
            self.stdout.write("메타데이터 보완: 없음")

        self.stdout.write(
            f"Campus 이동: {summary['campuses']}"
        )
        self.stdout.write(
            f"ExternalMapping 이동: {summary['mappings']}"
        )
        self.stdout.write(
            "RecruitmentUnit: "
            f"이동 {summary['recruitment_units_moved']} / "
            f"중복 병합 {summary['recruitment_units_merged']}"
        )
        self.stdout.write(
            f"AdmissionSource 이동: {summary['sources']}"
        )
        self.stdout.write(
            f"AdmissionResult 이동: {summary['results']}"
        )
        self.stdout.write(
            f"AdmissionAggregate 재계산: {summary['aggregates']}"
        )
        self.stdout.write(
            "ComparisonVote 이동: "
            f"A {summary['votes_a']} / "
            f"B {summary['votes_b']} / "
            f"선택 {summary['selected_votes']}"
        )
        self.stdout.write(
            "UniversityRating: "
            f"이동 {summary['ratings_moved']} / "
            f"중복 상태 병합 {summary['ratings_merged']}"
        )
        self.stdout.write(
            f"RankingSnapshotItem 이동: {summary['snapshot_items']}"
        )
        self.stdout.write(
            f"최종 표시명: {TARGET_NAME}"
        )
