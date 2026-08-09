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


SEOUL_NAME = "상명대학교"
CHEONAN_NAME = "상명대학교 천안캠퍼스"

SEOUL_FALLBACK_ADDRESS = "서울특별시 종로구 홍지문2길 20 (홍지동, 상명대학교)"
CHEONAN_FALLBACK_ADDRESS = "충청남도 천안시 동남구 상명대길 31 (안서동, 상명대학교천안캠퍼스)"

ADIGA_SOURCE = "ADIGA"
SEOUL_ADIGA_CODE = "0000117"
CHEONAN_ADIGA_CODE = "0002959"


class Command(BaseCommand):
    help = (
        "상명대학교를 서울/천안 대학 단위로 안전하게 분리합니다. "
        "서울은 기존 '상명대학교' PK를 유지하고 천안은 "
        "'상명대학교 천안캠퍼스'로 분리합니다. "
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
            self.stdout.write(
                self.style.WARNING("미리보기 모드입니다. DB는 변경하지 않습니다.")
            )

        with transaction.atomic():
            result = self.split_sangmyung()
            self.print_result(result)

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "미리보기 완료: 모든 DB 변경을 롤백했습니다."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "상명대학교 서울/천안 분리를 DB에 반영했습니다."
                    )
                )

    def split_sangmyung(self):
        seoul = University.objects.filter(name=SEOUL_NAME).first()
        cheonan = University.objects.filter(name=CHEONAN_NAME).first()

        if seoul is None:
            seoul = self.find_existing_seoul_candidate()

        if seoul is None:
            raise CommandError(
                "기존 상명대학교(서울) 레코드를 찾지 못했습니다. "
                "먼저 대학/CareerNet 동기화 상태를 확인해주세요."
            )

        candidate_ids = list(
            University.objects.filter(name__startswith="상명대학교")
            .values_list("pk", flat=True)
        )
        if seoul.pk not in candidate_ids:
            candidate_ids.append(seoul.pk)
        if cheonan and cheonan.pk not in candidate_ids:
            candidate_ids.append(cheonan.pk)

        campuses = list(
            UniversityCampus.objects.filter(university_id__in=candidate_ids)
            .order_by("source", "campus_id")
        )

        seoul_campus = self.pick_campus(campuses, "SEOUL")
        cheonan_campus = self.pick_campus(campuses, "CHEONAN")

        # 기존 상명대학교 PK/투표/랭킹 관계는 서울이 그대로 유지한다.
        seoul.name = SEOUL_NAME
        seoul.address = (
            normalize_address(seoul_campus.address)
            if seoul_campus and seoul_campus.address
            else normalize_address(seoul.address or SEOUL_FALLBACK_ADDRESS)
        )
        seoul.region = normalize_region(
            seoul_campus.region if seoul_campus else seoul.region,
            seoul.address,
        )
        if seoul_campus and seoul_campus.homepage_url:
            seoul.homepage_url = seoul_campus.homepage_url
        seoul.is_active = True
        seoul.save()

        created_cheonan = False
        if cheonan is None:
            cheonan = University.objects.create(
                name=CHEONAN_NAME,
                short_name=None,
                address=(
                    normalize_address(cheonan_campus.address)
                    if cheonan_campus and cheonan_campus.address
                    else normalize_address(CHEONAN_FALLBACK_ADDRESS)
                ),
                region=normalize_region(
                    cheonan_campus.region if cheonan_campus else None,
                    (
                        cheonan_campus.address
                        if cheonan_campus and cheonan_campus.address
                        else CHEONAN_FALLBACK_ADDRESS
                    ),
                ),
                university_type=seoul.university_type,
                establishment_type=seoul.establishment_type,
                homepage_url=(
                    cheonan_campus.homepage_url
                    if cheonan_campus and cheonan_campus.homepage_url
                    else seoul.homepage_url
                ),
                college_info_url=seoul.college_info_url,
                logo_path=seoul.logo_path,
                is_active=True,
            )
            created_cheonan = True
        else:
            cheonan.address = (
                normalize_address(cheonan_campus.address)
                if cheonan_campus and cheonan_campus.address
                else normalize_address(
                    cheonan.address or CHEONAN_FALLBACK_ADDRESS
                )
            )
            cheonan.region = normalize_region(
                cheonan_campus.region if cheonan_campus else cheonan.region,
                cheonan.address,
            )
            if not cheonan.logo_path:
                cheonan.logo_path = seoul.logo_path
            if cheonan_campus and cheonan_campus.homepage_url:
                cheonan.homepage_url = cheonan_campus.homepage_url
            elif not cheonan.homepage_url:
                cheonan.homepage_url = seoul.homepage_url
            if not cheonan.university_type:
                cheonan.university_type = seoul.university_type
            if not cheonan.establishment_type:
                cheonan.establishment_type = seoul.establishment_type
            if not cheonan.college_info_url:
                cheonan.college_info_url = seoul.college_info_url
            cheonan.is_active = True
            cheonan.save()

        all_candidate_ids = set(candidate_ids) | {seoul.pk, cheonan.pk}

        # Campus를 서울/천안 University로 재연결.
        campuses = list(
            UniversityCampus.objects.filter(university_id__in=all_candidate_ids)
            .order_by("source", "campus_id")
        )

        moved_campuses = {"SEOUL": 0, "CHEONAN": 0, "UNRESOLVED": 0}
        for campus in campuses:
            side = self.classify_campus(campus)
            if side == "SEOUL":
                target = seoul
            elif side == "CHEONAN":
                target = cheonan
            else:
                moved_campuses["UNRESOLVED"] += 1
                continue

            if campus.university_id != target.pk or not campus.is_primary:
                campus.university = target
                # 분리 후 각각 독립 University이므로 각 캠퍼스를 대표 캠퍼스로 본다.
                campus.is_primary = True
                campus.save(
                    update_fields=["university", "is_primary", "updated_at"]
                )
            moved_campuses[side] += 1

        # ExternalMapping은 ADIGA exact code를 최우선으로 사용한다.
        moved_mappings = {"SEOUL": 0, "CHEONAN": 0, "UNRESOLVED": 0}
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
            elif side == "CHEONAN":
                target = cheonan
            else:
                moved_mappings["UNRESOLVED"] += 1
                continue

            if mapping.university_id != target.pk:
                mapping.university = target
                mapping.save(update_fields=["university", "updated_at"])
            moved_mappings[side] += 1

        admission_move = self.move_admissions_by_adiga_code(
            seoul=seoul,
            cheonan=cheonan,
        )
        aggregate_count = self.rebuild_target_aggregates(
            [seoul.pk, cheonan.pk]
        )

        return {
            "seoul": seoul,
            "cheonan": cheonan,
            "created_cheonan": created_cheonan,
            "campuses": moved_campuses,
            "mappings": moved_mappings,
            "admissions": admission_move,
            "aggregate_count": aggregate_count,
        }

    def find_existing_seoul_candidate(self):
        candidates = list(
            University.objects.filter(name__startswith="상명대학교")
        )
        for university in candidates:
            if (
                self.classify_values(university.address, university.name)
                == "SEOUL"
            ):
                return university
        return None

    def pick_campus(self, campuses, side):
        matches = [
            campus
            for campus in campuses
            if self.classify_campus(campus) == side
        ]
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
        if mapping.source == ADIGA_SOURCE:
            if mapping.external_code == SEOUL_ADIGA_CODE:
                return "SEOUL"
            if mapping.external_code == CHEONAN_ADIGA_CODE:
                return "CHEONAN"

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
        if address.startswith("충청남도 천안"):
            return "CHEONAN"

        compact = re.sub(r"\s+", "", label)

        if any(
            token in compact
            for token in (
                "천안캠퍼스",
                "상명대학교천안",
                "제2캠퍼스",
                "2캠퍼스",
            )
        ):
            return "CHEONAN"

        if any(
            token in compact
            for token in ("본교", "본캠퍼스", "서울캠퍼스")
        ):
            return "SEOUL"

        return None

    def extract_adiga_code(self, source_url):
        if not source_url:
            return None

        match = re.search(r"(?:[?&])unvCd=([^&#]+)", source_url)
        return match.group(1) if match else None

    def move_admissions_by_adiga_code(self, seoul, cheonan):
        moved_sources = 0
        moved_results = 0
        unresolved_sources = []

        sources = list(
            AdmissionSource.objects
            .filter(
                university__in=[seoul, cheonan],
                source_type=ADIGA_SOURCE,
            )
            .order_by("source_id")
        )

        mappings_by_code = {
            mapping.external_code: mapping
            for mapping in UniversityExternalMapping.objects
            .select_related("university", "campus")
            .filter(
                source=ADIGA_SOURCE,
                external_code__in=[
                    SEOUL_ADIGA_CODE,
                    CHEONAN_ADIGA_CODE,
                ],
            )
        }

        target_by_code = {
            SEOUL_ADIGA_CODE: seoul,
            CHEONAN_ADIGA_CODE: cheonan,
        }

        fallback_campus_by_code = {
            SEOUL_ADIGA_CODE: self.pick_campus(
                list(seoul.campuses.all()),
                "SEOUL",
            ),
            CHEONAN_ADIGA_CODE: self.pick_campus(
                list(cheonan.campuses.all()),
                "CHEONAN",
            ),
        }

        for source in sources:
            code = self.extract_adiga_code(source.source_url)
            target = target_by_code.get(code)

            if target is None:
                unresolved_sources.append(
                    (source.source_id, code or "코드 없음")
                )
                continue

            mapping = mappings_by_code.get(code)
            target_campus = (
                mapping.campus
                if mapping and mapping.campus_id
                else fallback_campus_by_code.get(code)
            )

            if source.university_id != target.pk:
                source.university = target
                source.save(update_fields=["university"])
                moved_sources += 1

            for result in source.results.select_related(
                "recruitment_unit"
            ).all():
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
                    result.save(
                        update_fields=["university", "recruitment_unit"]
                    )
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
            groups[key].append(
                (metric.value, result.recruitment_count)
            )

        AdmissionAggregate.objects.filter(
            university_id__in=university_ids
        ).delete()

        count = 0
        for key, values in groups.items():
            university_id, year, phase, category, metric_code = key

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
        cheonan = result["cheonan"]

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("[상명대학교 분리 결과]")
        )
        self.stdout.write(
            f"서울: id={seoul.pk} | {seoul.name} | "
            f"{seoul.region} | {seoul.address}"
        )
        self.stdout.write(
            f"천안: id={cheonan.pk} | {cheonan.name} | "
            f"{cheonan.region} | {cheonan.address}"
        )
        self.stdout.write(
            "천안 University: "
            + (
                "새로 생성"
                if result["created_cheonan"]
                else "기존 레코드 재사용"
            )
        )

        campuses = result["campuses"]
        self.stdout.write(
            "캠퍼스 분류: "
            f"서울 {campuses['SEOUL']} / "
            f"천안 {campuses['CHEONAN']} / "
            f"미확인 {campuses['UNRESOLVED']}"
        )

        mappings = result["mappings"]
        self.stdout.write(
            "외부 매핑 분류: "
            f"서울 {mappings['SEOUL']} / "
            f"천안 {mappings['CHEONAN']} / "
            f"미확인 {mappings['UNRESOLVED']}"
        )

        admissions = result["admissions"]
        self.stdout.write(
            "기존 ADIGA 데이터 이동: "
            f"source {admissions['sources']} / "
            f"result {admissions['results']}"
        )
        self.stdout.write(
            f"상명대 입시 Aggregate 재계산: "
            f"{result['aggregate_count']}건"
        )

        if admissions["unresolved"]:
            self.stdout.write(
                self.style.WARNING(
                    "ADIGA code를 안전하게 판별하지 못한 기존 source는 "
                    "이동하지 않았습니다: "
                    + ", ".join(
                        f"source#{source_id}({code})"
                        for source_id, code in admissions["unresolved"]
                    )
                )
            )
