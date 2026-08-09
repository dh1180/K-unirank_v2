import re
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from admissions.models import (
    AdmissionAggregate,
    AdmissionMetric,
    AdmissionResult,
    AdmissionSource,
    RecruitmentUnit,
)
from universities.models import University, UniversityCampus, UniversityExternalMapping
from universities.services.university_normalizer import normalize_address, normalize_region


LEGACY_NAME = "홍익대학교"
SEOUL_NAME = "홍익대학교"
SEJONG_NAME = "홍익대학교 세종캠퍼스"

SEOUL_FALLBACK_ADDRESS = "서울특별시 마포구 와우산로 94 (상수동, 홍익대학교)"
SEJONG_FALLBACK_ADDRESS = "세종특별자치시 조치원읍 세종로 2639 (신안리, 홍익대학교세종캠퍼스)"

ADIGA_SOURCE = "ADIGA"


class Command(BaseCommand):
    help = (
        "기존 홍익대학교 1개 레코드를 서울캠퍼스/세종캠퍼스 2개 대학으로 안전하게 분리합니다. "
        "기본은 미리보기이며 --apply를 붙여야 실제 반영됩니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 반영합니다. 생략하면 전체 작업 후 롤백하는 미리보기입니다.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        if not apply_changes:
            self.stdout.write(self.style.WARNING("미리보기 모드입니다. DB는 변경하지 않습니다."))

        with transaction.atomic():
            result = self.split_hongik()

            self.print_result(result)

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("미리보기 완료: 모든 DB 변경을 롤백했습니다."))
            else:
                self.stdout.write(self.style.SUCCESS("홍익대학교 서울/세종 캠퍼스 분리를 DB에 반영했습니다."))

    def split_hongik(self):
        legacy = University.objects.filter(name=LEGACY_NAME).first()
        seoul = University.objects.filter(name=SEOUL_NAME).first()
        sejong = University.objects.filter(name=SEJONG_NAME).first()

        if legacy and seoul and legacy.pk != seoul.pk:
            raise CommandError(
                "'홍익대학교'와 '홍익대학교 서울캠퍼스'가 동시에 별도 레코드로 존재합니다. "
                "기존 투표/랭킹 관계를 임의 병합하지 않기 위해 중단합니다."
            )

        # 현재 서비스에서 사용하던 홍익대학교 PK를 서울캠퍼스가 그대로 재사용한다.
        if seoul is None:
            if legacy is not None:
                seoul = legacy
            else:
                seoul = self.find_existing_seoul_candidate()

        if seoul is None:
            raise CommandError(
                "기존 홍익대학교(서울) 레코드를 찾지 못했습니다. "
                "먼저 CareerNet 대학 동기화 상태를 확인해주세요."
            )

        candidate_ids = list(
            University.objects.filter(name__startswith="홍익대학교")
            .values_list("pk", flat=True)
        )
        if seoul.pk not in candidate_ids:
            candidate_ids.append(seoul.pk)
        if sejong and sejong.pk not in candidate_ids:
            candidate_ids.append(sejong.pk)

        campuses = list(
            UniversityCampus.objects.filter(university_id__in=candidate_ids)
            .order_by("source", "campus_id")
        )

        seoul_campus = self.pick_campus(campuses, "SEOUL")
        sejong_campus = self.pick_campus(campuses, "SEJONG")

        # 기존 PK/투표/랭킹/상세 URL 관계를 보존한 채 이름과 대표 주소만 서울 기준으로 바꾼다.
        seoul.name = SEOUL_NAME
        seoul.address = (
            normalize_address(seoul_campus.address)
            if seoul_campus and seoul_campus.address
            else normalize_address(SEOUL_FALLBACK_ADDRESS)
        )
        seoul.region = normalize_region(
            seoul_campus.region if seoul_campus else None,
            seoul.address,
        )
        if seoul_campus and seoul_campus.homepage_url:
            seoul.homepage_url = seoul_campus.homepage_url
        seoul.is_active = True
        seoul.save()

        created_sejong = False
        if sejong is None:
            sejong = University.objects.create(
                name=SEJONG_NAME,
                short_name=None,
                address=(
                    normalize_address(sejong_campus.address)
                    if sejong_campus and sejong_campus.address
                    else normalize_address(SEJONG_FALLBACK_ADDRESS)
                ),
                region=normalize_region(
                    sejong_campus.region if sejong_campus else None,
                    sejong_campus.address if sejong_campus and sejong_campus.address else SEJONG_FALLBACK_ADDRESS,
                ),
                university_type=seoul.university_type,
                establishment_type=seoul.establishment_type,
                homepage_url=(
                    sejong_campus.homepage_url
                    if sejong_campus and sejong_campus.homepage_url
                    else seoul.homepage_url
                ),
                college_info_url=seoul.college_info_url,
                logo_path=seoul.logo_path,
                is_active=True,
            )
            created_sejong = True
        else:
            sejong.address = (
                normalize_address(sejong_campus.address)
                if sejong_campus and sejong_campus.address
                else normalize_address(sejong.address or SEJONG_FALLBACK_ADDRESS)
            )
            sejong.region = normalize_region(
                sejong_campus.region if sejong_campus else sejong.region,
                sejong.address,
            )
            if not sejong.logo_path:
                sejong.logo_path = seoul.logo_path
            if sejong_campus and sejong_campus.homepage_url:
                sejong.homepage_url = sejong_campus.homepage_url
            elif not sejong.homepage_url:
                sejong.homepage_url = seoul.homepage_url
            if not sejong.university_type:
                sejong.university_type = seoul.university_type
            if not sejong.establishment_type:
                sejong.establishment_type = seoul.establishment_type
            if not sejong.college_info_url:
                sejong.college_info_url = seoul.college_info_url
            sejong.is_active = True
            sejong.save()

        # 새 세종 레코드까지 후보에 포함해 캠퍼스/외부 매핑을 다시 분류한다.
        all_candidate_ids = set(candidate_ids) | {seoul.pk, sejong.pk}
        campuses = list(
            UniversityCampus.objects.filter(university_id__in=all_candidate_ids)
            .order_by("source", "campus_id")
        )

        moved_campuses = {"SEOUL": 0, "SEJONG": 0, "UNRESOLVED": 0}
        for campus in campuses:
            side = self.classify_campus(campus)
            if side == "SEOUL":
                target = seoul
            elif side == "SEJONG":
                target = sejong
            else:
                moved_campuses["UNRESOLVED"] += 1
                continue

            if campus.university_id != target.pk or not campus.is_primary:
                campus.university = target
                # 두 campus가 이제 각각 하나의 독립 University이므로 각자의 대표 캠퍼스로 본다.
                campus.is_primary = True
                campus.save(update_fields=["university", "is_primary", "updated_at"])
            moved_campuses[side] += 1

        moved_mappings = {"SEOUL": 0, "SEJONG": 0, "UNRESOLVED": 0}
        mappings = list(
            UniversityExternalMapping.objects
            .select_related("campus")
            .filter(university_id__in=all_candidate_ids)
            .order_by("source", "mapping_id")
        )

        for mapping in mappings:
            side = self.classify_mapping(mapping)
            if side == "SEOUL":
                target = seoul
            elif side == "SEJONG":
                target = sejong
            else:
                moved_mappings["UNRESOLVED"] += 1
                continue

            changed = mapping.university_id != target.pk
            mapping.university = target
            if changed:
                mapping.save(update_fields=["university", "updated_at"])
            moved_mappings[side] += 1

        # ADIGA mapping의 code가 명확하게 서울/세종으로 분리된 경우에는 기존 저장된
        # AdmissionSource/Result도 같은 code를 기준으로 이동한다. 이름/숫자를 추측해서 옮기지 않는다.
        admission_move = self.move_admissions_by_adiga_code(seoul, sejong)
        aggregate_count = self.rebuild_target_aggregates([seoul.pk, sejong.pk])

        return {
            "seoul": seoul,
            "sejong": sejong,
            "created_sejong": created_sejong,
            "campuses": moved_campuses,
            "mappings": moved_mappings,
            "admissions": admission_move,
            "aggregate_count": aggregate_count,
        }

    def find_existing_seoul_candidate(self):
        candidates = list(University.objects.filter(name__startswith="홍익대학교"))
        for university in candidates:
            if self.classify_values(university.address, university.name) == "SEOUL":
                return university
        return None

    def pick_campus(self, campuses, side):
        matches = [campus for campus in campuses if self.classify_campus(campus) == side]
        if not matches:
            return None

        source_priority = {"CAREER_NET": 0, "ADIGA": 1}
        matches.sort(
            key=lambda campus: (
                source_priority.get(campus.source, 9),
                0 if campus.address else 1,
                campus.campus_id,
            )
        )
        return matches[0]

    def classify_campus(self, campus):
        return self.classify_values(campus.address, campus.campus_name)

    def classify_mapping(self, mapping):
        if mapping.campus_id:
            side = self.classify_campus(mapping.campus)
            if side:
                return side
        return self.classify_values(None, mapping.external_name)

    def classify_values(self, address, label):
        address = normalize_address(address) or ""
        label = (label or "").strip()

        if address.startswith("서울특별시"):
            return "SEOUL"
        if address.startswith("세종특별자치시") or "조치원" in address:
            return "SEJONG"

        compact = re.sub(r"\s+", "", label)
        if any(token in compact for token in ("제2캠퍼스", "2캠퍼스", "세종캠퍼스", "홍익대학교세종", "조치원")):
            return "SEJONG"
        if any(token in compact for token in ("본교", "본캠퍼스", "서울캠퍼스")):
            return "SEOUL"

        return None

    def extract_adiga_code(self, source_url):
        if not source_url:
            return None
        match = re.search(r"(?:[?&])unvCd=([^&#]+)", source_url)
        return match.group(1) if match else None

    def move_admissions_by_adiga_code(self, seoul, sejong):
        moved_sources = 0
        moved_results = 0
        unresolved_sources = []

        sources = list(
            AdmissionSource.objects
            .filter(university__in=[seoul, sejong], source_type=ADIGA_SOURCE)
            .order_by("source_id")
        )

        mapping_by_code = {
            mapping.external_code: mapping
            for mapping in UniversityExternalMapping.objects
            .select_related("university", "campus")
            .filter(source=ADIGA_SOURCE, university__in=[seoul, sejong])
        }

        for source in sources:
            code = self.extract_adiga_code(source.source_url)
            mapping = mapping_by_code.get(code)
            if not mapping or mapping.university_id not in {seoul.pk, sejong.pk}:
                unresolved_sources.append((source.source_id, code or "코드 없음"))
                continue

            target = mapping.university
            target_campus = mapping.campus

            if source.university_id != target.pk:
                source.university = target
                source.save(update_fields=["university"])
                moved_sources += 1

            for result in source.results.select_related("recruitment_unit").all():
                old_unit = result.recruitment_unit
                new_unit, _ = RecruitmentUnit.objects.get_or_create(
                    university=target,
                    campus=target_campus,
                    name=old_unit.name,
                    defaults={
                        "college_name": old_unit.college_name,
                        "is_active": old_unit.is_active,
                    },
                )

                changed = False
                if result.university_id != target.pk:
                    result.university = target
                    changed = True
                if result.recruitment_unit_id != new_unit.pk:
                    result.recruitment_unit = new_unit
                    changed = True

                if changed:
                    result.save(update_fields=["university", "recruitment_unit"])
                    moved_results += 1

        return {
            "sources": moved_sources,
            "results": moved_results,
            "unresolved": unresolved_sources,
        }

    def rebuild_target_aggregates(self, university_ids):
        metrics = (
            AdmissionMetric.objects
            .select_related("result")
            .filter(result__university_id__in=university_ids)
        )

        groups = defaultdict(list)
        for metric in metrics.iterator():
            result = metric.result
            key = (
                result.university_id,
                result.admission_year,
                result.admission_phase,
                result.selection_category,
                metric.metric_code,
            )
            groups[key].append((metric.value, result.recruitment_count))

        AdmissionAggregate.objects.filter(university_id__in=university_ids).delete()

        count = 0
        for key, values in groups.items():
            university_id, year, phase, category, metric_code = key
            weighted_values = [
                (value, weight)
                for value, weight in values
                if weight and weight > 0
            ]

            if weighted_values:
                total_weight = sum(Decimal(weight) for _, weight in weighted_values)
                aggregate_value = (
                    sum(value * Decimal(weight) for value, weight in weighted_values)
                    / total_weight
                )
                method = "WEIGHTED_BY_RECRUITMENT"
            else:
                aggregate_value = sum(value for value, _ in values) / Decimal(len(values))
                method = "SIMPLE_AVERAGE"

            AdmissionAggregate.objects.create(
                university_id=university_id,
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

    def print_result(self, result):
        seoul = result["seoul"]
        sejong = result["sejong"]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("[홍익대학교 분리 결과]"))
        self.stdout.write(
            f"서울: id={seoul.pk} | {seoul.name} | {seoul.region} | {seoul.address}"
        )
        self.stdout.write(
            f"세종: id={sejong.pk} | {sejong.name} | {sejong.region} | {sejong.address}"
        )
        self.stdout.write(
            "세종 University: " + ("새로 생성" if result["created_sejong"] else "기존 레코드 재사용")
        )

        campuses = result["campuses"]
        self.stdout.write(
            "캠퍼스 분류: "
            f"서울 {campuses['SEOUL']} / 세종 {campuses['SEJONG']} / 미확인 {campuses['UNRESOLVED']}"
        )

        mappings = result["mappings"]
        self.stdout.write(
            "외부 매핑 분류: "
            f"서울 {mappings['SEOUL']} / 세종 {mappings['SEJONG']} / 미확인 {mappings['UNRESOLVED']}"
        )

        admissions = result["admissions"]
        self.stdout.write(
            "기존 ADIGA 데이터 이동: "
            f"source {admissions['sources']} / result {admissions['results']}"
        )
        self.stdout.write(f"홍익대 입시 Aggregate 재계산: {result['aggregate_count']}건")

        if admissions["unresolved"]:
            self.stdout.write(
                self.style.WARNING(
                    "ADIGA code를 안전하게 판별하지 못한 기존 source는 이동하지 않았습니다: "
                    + ", ".join(
                        f"source#{source_id}({code})"
                        for source_id, code in admissions["unresolved"]
                    )
                )
            )
