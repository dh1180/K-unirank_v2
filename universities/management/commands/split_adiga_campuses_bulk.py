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
from universities.models import (
    University,
    UniversityCampus,
    UniversityExternalMapping,
)
from universities.services.university_normalizer import (
    normalize_address,
    normalize_region,
)


ADIGA_SOURCE = "ADIGA"

# base_code의 target_name은 반드시 기존 University.name과 같게 둔다.
# 기존 투표/랭킹/URL의 University PK는 base_code 캠퍼스가 그대로 재사용한다.
SPLIT_SPECS = {
    "건양대학교": {
        "base_code": "0000054",
        "campuses": {
            "0000054": {
                "target_name": "건양대학교",
                "campus_label": "글로컬캠퍼스",
                "address_prefixes": ("충청남도 논산",),
            },
            "0000055": {
                "target_name": "건양대학교 메디컬캠퍼스",
                "campus_label": "메디컬캠퍼스",
                "address_prefixes": ("대전광역시",),
            },
        },
    },
    "경기대학교": {
        "base_code": "0000056",
        "campuses": {
            "0000056": {
                "target_name": "경기대학교",
                "campus_label": "수원캠퍼스",
                "address_prefixes": ("경기도 수원",),
            },
            "0000058": {
                "target_name": "경기대학교 서울캠퍼스",
                "campus_label": "서울캠퍼스",
                "address_prefixes": ("서울특별시",),
            },
        },
    },
    "경동대학교": {
        "base_code": "0000060",
        "campuses": {
            "0000060": {
                "target_name": "경동대학교",
                "campus_label": "글로벌캠퍼스",
                "address_prefixes": ("강원특별자치도 고성",),
            },
            "0002574": {
                "target_name": "경동대학교 메디컬캠퍼스",
                "campus_label": "메디컬캠퍼스",
                "address_prefixes": ("강원특별자치도 원주",),
            },
            "0002744": {
                "target_name": "경동대학교 메트로폴캠퍼스",
                "campus_label": "메트로폴캠퍼스",
                "address_prefixes": ("경기도 양주",),
            },
        },
    },
    "신한대학교": {
        "base_code": "0002800",
        "campuses": {
            "0002800": {
                "target_name": "신한대학교",
                "campus_label": "의정부캠퍼스",
                "address_prefixes": ("경기도 의정부",),
            },
            "0002712": {
                "target_name": "신한대학교 동두천캠퍼스",
                "campus_label": "동두천캠퍼스",
                "address_prefixes": ("경기도 동두천",),
            },
        },
    },
    "안양대학교": {
        "base_code": "0000147",
        "campuses": {
            "0000147": {
                "target_name": "안양대학교",
                "campus_label": "안양캠퍼스",
                "address_prefixes": ("경기도 안양",),
            },
            "0000148": {
                "target_name": "안양대학교 강화캠퍼스",
                "campus_label": "강화캠퍼스",
                "address_prefixes": ("인천광역시 강화",),
            },
        },
    },
    "영산대학교": {
        "base_code": "0003193",
        "campuses": {
            "0003193": {
                "target_name": "영산대학교",
                "campus_label": "해운대캠퍼스",
                "address_prefixes": ("부산광역시",),
            },
            "0003194": {
                "target_name": "영산대학교 양산캠퍼스",
                "campus_label": "양산캠퍼스",
                "address_prefixes": ("경상남도 양산",),
            },
        },
    },
    "을지대학교": {
        "base_code": "0000162",
        "campuses": {
            "0000162": {
                "target_name": "을지대학교",
                "campus_label": "성남캠퍼스",
                "address_prefixes": ("경기도 성남",),
            },
            "0000161": {
                "target_name": "을지대학교 대전캠퍼스",
                "campus_label": "대전캠퍼스",
                "address_prefixes": ("대전광역시",),
            },
            "0002911": {
                "target_name": "을지대학교 의정부캠퍼스",
                "campus_label": "의정부캠퍼스",
                "address_prefixes": ("경기도 의정부",),
            },
        },
    },
    "전남대학교": {
        "base_code": "0000023",
        "campuses": {
            "0000023": {
                "target_name": "전남대학교",
                "campus_label": "광주캠퍼스",
                "address_prefixes": ("광주광역시",),
            },
            "0000024": {
                "target_name": "전남대학교 여수캠퍼스",
                "campus_label": "여수캠퍼스",
                "address_prefixes": ("전라남도 여수",),
            },
        },
    },
    "중앙대학교": {
        "base_code": "0000175",
        "campuses": {
            "0000175": {
                "target_name": "중앙대학교",
                "campus_label": "서울캠퍼스",
                "address_prefixes": ("서울특별시",),
            },
            "0000174": {
                "target_name": "중앙대학교 다빈치캠퍼스",
                "campus_label": "다빈치캠퍼스",
                "address_prefixes": ("경기도 안성",),
            },
        },
    },
    "예원예술대학교": {
        # 현재 K-unirank 대표 주소/지역이 경기권으로 잡혀 있었으므로
        # 기존 University PK는 경기드림캠퍼스가 유지한다.
        "base_code": "0000219",
        "campuses": {
            "0000219": {
                "target_name": "예원예술대학교",
                "campus_label": "경기드림캠퍼스",
                "address_prefixes": ("경기도 양주",),
            },
            "0000218": {
                "target_name": "예원예술대학교 전북희망캠퍼스",
                "campus_label": "전북희망캠퍼스",
                "address_prefixes": ("전북특별자치도 임실",),
            },
        },
    },
    "인천가톨릭대학교": {
        # 2026 ADIGA 결과 대부분이 송도 code에 연결되어 있고,
        # 기존 서비스 대표 대학명은 송도 쪽에 유지한다.
        "base_code": "0000167",
        "campuses": {
            "0000167": {
                "target_name": "인천가톨릭대학교",
                "campus_label": "송도국제캠퍼스",
                "address_prefixes": (
                    "인천광역시 연수",
                    "인천광역시 송도",
                ),
            },
            "0000168": {
                "target_name": "인천가톨릭대학교 강화캠퍼스",
                "campus_label": "강화캠퍼스",
                "address_prefixes": ("인천광역시 강화",),
            },
        },
    },
}


class Command(BaseCommand):
    help = (
        "ADIGA에서 캠퍼스별 unvCd를 별도로 제공하지만 현재 하나의 University에 "
        "합쳐진 대학들을 안전하게 일괄 분리합니다. 기본은 미리보기이며 "
        "--apply를 붙여야 실제 반영됩니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 반영합니다. 생략하면 전체 작업 후 롤백합니다.",
        )
        parser.add_argument(
            "--university",
            action="append",
            dest="universities",
            help=(
                "특정 대학만 처리합니다. 여러 번 지정 가능. "
                "예: --university 중앙대학교 --university 전남대학교"
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        requested = options.get("universities") or []

        specs = self.select_specs(requested)

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "미리보기 모드입니다. 실제 DB 변경은 마지막에 모두 롤백됩니다."
                )
            )

        self.stdout.write(
            f"처리 대상: {len(specs)}개 대학 / "
            + ", ".join(specs.keys())
        )

        with transaction.atomic():
            summaries = []
            for base_name, spec in specs.items():
                summaries.append(
                    self.split_one_university(base_name, spec)
                )

            self.print_global_summary(summaries)

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "미리보기 완료: 생성/이동/region 보정을 모두 롤백했습니다."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "ADIGA 캠퍼스 일괄 분리를 실제 DB에 반영했습니다."
                    )
                )

    def select_specs(self, requested):
        if not requested:
            return SPLIT_SPECS

        unknown = [
            name
            for name in requested
            if name not in SPLIT_SPECS
        ]
        if unknown:
            raise CommandError(
                "지원하지 않는 대학: "
                + ", ".join(unknown)
                + "\n지원 대학: "
                + ", ".join(SPLIT_SPECS.keys())
            )

        return {
            name: SPLIT_SPECS[name]
            for name in requested
        }

    def split_one_university(self, base_name, spec):
        base = University.objects.filter(name=base_name).first()
        if base is None:
            raise CommandError(
                f"기존 대표 University '{base_name}'를 찾지 못했습니다."
            )

        base_code = spec["base_code"]
        campus_specs = spec["campuses"]

        if base_code not in campus_specs:
            raise CommandError(
                f"{base_name}: base_code={base_code}가 campuses에 없습니다."
            )
        if campus_specs[base_code]["target_name"] != base_name:
            raise CommandError(
                f"{base_name}: base_code target_name은 기존 대학명과 같아야 합니다."
            )

        self.stdout.write("")
        self.stdout.write("=" * 78)
        self.stdout.write(
            self.style.SUCCESS(f"[{base_name}] 분리 미리보기/처리")
        )

        # target University 준비. base_code만 기존 PK를 강제 재사용한다.
        targets = {base_code: base}
        created_names = []

        for code, campus_spec in campus_specs.items():
            if code == base_code:
                continue

            target_name = campus_spec["target_name"]
            target = University.objects.filter(name=target_name).first()

            if target is None:
                target = University.objects.create(
                    name=target_name,
                    short_name=None,
                    address=None,
                    region=None,
                    university_type=base.university_type,
                    establishment_type=base.establishment_type,
                    homepage_url=base.homepage_url,
                    college_info_url=base.college_info_url,
                    logo_path=base.logo_path,
                    is_active=True,
                )
                created_names.append(target_name)
            else:
                self.fill_target_metadata(target, base)

            targets[code] = target

        family_ids = set(
            University.objects.filter(
                name__startswith=base_name
            ).values_list("university_id", flat=True)
        )
        family_ids.update(
            target.university_id
            for target in targets.values()
        )

        # 1) Campus를 exact ADIGA code / 주소 기준으로 분리한다.
        campus_moves = 0
        campus_regions_fixed = 0
        campus_labels_fixed = 0
        unresolved_campuses = []

        campuses = list(
            UniversityCampus.objects.filter(
                university_id__in=family_ids
            ).order_by("source", "campus_id")
        )

        for campus in campuses:
            code = self.classify_campus_code(
                campus,
                campus_specs,
            )

            # region은 저장값보다 address를 우선한다.
            derived_region = self.region_from_address(campus.address)
            if derived_region and campus.region != derived_region:
                campus.region = derived_region
                campus_regions_fixed += 1

            if code is None:
                unresolved_campuses.append(
                    (
                        campus.campus_id,
                        campus.source,
                        campus.external_code,
                        campus.campus_name or "",
                        campus.address or "",
                    )
                )
                if derived_region:
                    campus.save(
                        update_fields=["region", "updated_at"]
                    )
                continue

            target = targets[code]
            desired_label = campus_specs[code]["campus_label"]

            update_fields = []

            if campus.university_id != target.university_id:
                campus.university = target
                update_fields.append("university")
                campus_moves += 1

            if campus.campus_name != desired_label:
                campus.campus_name = desired_label
                update_fields.append("campus_name")
                campus_labels_fixed += 1

            if derived_region and "region" not in update_fields:
                # region이 실제로 바뀐 경우에만 저장.
                # 위에서 campus.region 값을 바꿨으므로 원본 비교를 위해
                # campus_regions_fixed 증가 여부로 별도 판별할 수 없어서,
                # 주소 기반 값과 DB 업데이트 대상 여부를 다시 확인한다.
                update_fields.append("region")

            if not campus.is_primary:
                campus.is_primary = True
                update_fields.append("is_primary")

            if update_fields:
                update_fields.append("updated_at")
                # 중복 필드 제거
                campus.save(
                    update_fields=list(dict.fromkeys(update_fields))
                )

        # 2) ADIGA code는 이름이 아닌 external_code로 mapping을 재배치.
        mapping_moves = 0
        mapping_campus_links = 0

        mappings = list(
            UniversityExternalMapping.objects.filter(
                university_id__in=family_ids
            )
            .select_related("campus")
            .order_by("source", "mapping_id")
        )

        # exact code campus lookup after campus moves.
        campus_by_adiga_code = {
            campus.external_code: campus
            for campus in UniversityCampus.objects.filter(
                source=ADIGA_SOURCE,
                external_code__in=list(campus_specs.keys()),
            )
        }

        for mapping in mappings:
            code = None

            if (
                mapping.source == ADIGA_SOURCE
                and mapping.external_code in campus_specs
            ):
                code = mapping.external_code
            elif (
                mapping.campus_id
                and mapping.campus.university_id
                in {t.university_id for t in targets.values()}
            ):
                # CareerNet 등 다른 source는 이미 분류된 campus를 따라간다.
                target_id = mapping.campus.university_id
                for candidate_code, target in targets.items():
                    if target.university_id == target_id:
                        code = candidate_code
                        break

            if code is None:
                continue

            target = targets[code]
            update_fields = []

            if mapping.university_id != target.university_id:
                mapping.university = target
                update_fields.append("university")
                mapping_moves += 1

            if mapping.source == ADIGA_SOURCE:
                exact_campus = campus_by_adiga_code.get(code)
                if (
                    exact_campus is not None
                    and mapping.campus_id != exact_campus.campus_id
                ):
                    mapping.campus = exact_campus
                    update_fields.append("campus")
                    mapping_campus_links += 1

            if update_fields:
                update_fields.append("updated_at")
                mapping.save(
                    update_fields=list(dict.fromkeys(update_fields))
                )

        # mappings가 family 밖에 잘못 붙어 있던 부분 상태도 exact code로 보정.
        for code, target in targets.items():
            exact_mapping = UniversityExternalMapping.objects.filter(
                source=ADIGA_SOURCE,
                external_code=code,
            ).first()
            if exact_mapping is None:
                continue

            update_fields = []
            if exact_mapping.university_id != target.university_id:
                exact_mapping.university = target
                update_fields.append("university")
                mapping_moves += 1

            exact_campus = campus_by_adiga_code.get(code)
            if (
                exact_campus is not None
                and exact_mapping.campus_id != exact_campus.campus_id
            ):
                exact_mapping.campus = exact_campus
                update_fields.append("campus")
                mapping_campus_links += 1

            if update_fields:
                update_fields.append("updated_at")
                exact_mapping.save(
                    update_fields=list(dict.fromkeys(update_fields))
                )

        # 3) 기존 ADIGA AdmissionSource/Result를 source_url의 unvCd로 이동.
        admission_sources_moved = 0
        admission_results_moved = 0
        admissions_by_code = defaultdict(int)

        all_sources = AdmissionSource.objects.filter(
            source_type=ADIGA_SOURCE
        ).order_by("source_id")

        for source in all_sources.iterator():
            code = self.extract_adiga_code(source.source_url)
            if code not in campus_specs:
                continue

            target = targets[code]
            target_campus = campus_by_adiga_code.get(code)

            if source.university_id != target.university_id:
                source.university = target
                source.save(update_fields=["university"])
                admission_sources_moved += 1

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

                # 기존 unit에 더 좋은 metadata가 있고 새 unit이 빈 경우 보정.
                unit_fields = []
                if (
                    old_unit.college_name
                    and not new_unit.college_name
                ):
                    new_unit.college_name = old_unit.college_name
                    unit_fields.append("college_name")
                if old_unit.is_active and not new_unit.is_active:
                    new_unit.is_active = True
                    unit_fields.append("is_active")
                if unit_fields:
                    new_unit.save(update_fields=unit_fields)

                result_fields = []
                if result.university_id != target.university_id:
                    result.university = target
                    result_fields.append("university")
                if result.recruitment_unit_id != new_unit.recruitment_unit_id:
                    result.recruitment_unit = new_unit
                    result_fields.append("recruitment_unit")

                if result_fields:
                    result.save(update_fields=result_fields)
                    admission_results_moved += 1

                admissions_by_code[code] += 1

        # 4) 각 University의 대표 주소/region/homepage를 자기 캠퍼스 기준으로 보정.
        for code, target in targets.items():
            preferred_campus = self.pick_preferred_campus(
                target=target,
                code=code,
                campus_spec=campus_specs[code],
            )
            self.update_target_from_campus(
                target=target,
                base=base,
                campus=preferred_campus,
            )

        # 5) 이번 family의 aggregate를 전체 학년도 기준 재계산.
        target_ids = [
            target.university_id
            for target in targets.values()
        ]
        aggregate_count = self.rebuild_target_aggregates(target_ids)

        # 6) 출력
        for code, target in targets.items():
            campus_spec = campus_specs[code]
            self.stdout.write(
                f"  {code} -> {target.name} "
                f"| {campus_spec['campus_label']} "
                f"| {target.region or '-'} "
                f"| 입결 {admissions_by_code.get(code, 0)}건"
            )

        if created_names:
            self.stdout.write(
                "  새 University 생성: "
                + ", ".join(created_names)
            )

        self.stdout.write(
            "  Campus 이동 "
            f"{campus_moves} / region 보정 {campus_regions_fixed} / "
            f"라벨 보정 {campus_labels_fixed}"
        )
        self.stdout.write(
            "  Mapping 이동 "
            f"{mapping_moves} / ADIGA campus 연결 보정 {mapping_campus_links}"
        )
        self.stdout.write(
            "  Admission 이동 "
            f"source {admission_sources_moved} / result {admission_results_moved}"
        )
        self.stdout.write(
            f"  Aggregate 재계산 {aggregate_count}건"
        )

        if unresolved_campuses:
            self.stdout.write(
                self.style.WARNING(
                    "  주소/code로 분류 못한 Campus는 억지로 이동하지 않았습니다:"
                )
            )
            for row in unresolved_campuses:
                self.stdout.write(
                    "    "
                    + " | ".join(str(value) for value in row)
                )

        return {
            "base_name": base_name,
            "targets": targets,
            "created_names": created_names,
            "campus_moves": campus_moves,
            "campus_regions_fixed": campus_regions_fixed,
            "mapping_moves": mapping_moves,
            "source_moves": admission_sources_moved,
            "result_moves": admission_results_moved,
            "aggregate_count": aggregate_count,
            "unresolved_count": len(unresolved_campuses),
        }

    def fill_target_metadata(self, target, base):
        fields = []
        for field in (
            "university_type",
            "establishment_type",
            "homepage_url",
            "college_info_url",
            "logo_path",
        ):
            if not getattr(target, field) and getattr(base, field):
                setattr(target, field, getattr(base, field))
                fields.append(field)

        if not target.is_active:
            target.is_active = True
            fields.append("is_active")

        if fields:
            target.save(update_fields=fields + ["updated_at"])

    def classify_campus_code(self, campus, campus_specs):
        if (
            campus.source == ADIGA_SOURCE
            and campus.external_code in campus_specs
        ):
            return campus.external_code

        address = normalize_address(campus.address) or ""

        for code, spec in campus_specs.items():
            if any(
                address.startswith(prefix)
                for prefix in spec["address_prefixes"]
            ):
                return code

        label = re.sub(r"\s+", "", campus.campus_name or "")
        for code, spec in campus_specs.items():
            desired = re.sub(
                r"\s+",
                "",
                spec["campus_label"],
            )
            if desired and desired in label:
                return code

        return None

    def region_from_address(self, address):
        address = normalize_address(address)
        if not address:
            return None
        # normalize_region은 value가 있으면 value를 우선하므로
        # 저장된 잘못된 region을 넘기지 않고 주소만 사용한다.
        return normalize_region(None, address)

    def pick_preferred_campus(self, target, code, campus_spec):
        exact = UniversityCampus.objects.filter(
            university=target,
            source=ADIGA_SOURCE,
            external_code=code,
        ).first()
        if exact:
            return exact

        campuses = list(
            UniversityCampus.objects.filter(
                university=target
            ).order_by("source", "campus_id")
        )

        for campus in campuses:
            address = normalize_address(campus.address) or ""
            if any(
                address.startswith(prefix)
                for prefix in campus_spec["address_prefixes"]
            ):
                return campus

        return campuses[0] if campuses else None

    def update_target_from_campus(self, target, base, campus):
        fields = []

        if campus and campus.address:
            address = normalize_address(campus.address)
            region = self.region_from_address(address)

            if address and target.address != address:
                target.address = address
                fields.append("address")

            if region and target.region != region:
                target.region = region
                fields.append("region")

            if (
                campus.homepage_url
                and target.homepage_url != campus.homepage_url
            ):
                target.homepage_url = campus.homepage_url
                fields.append("homepage_url")

        # 새 target은 base metadata를 계속 상속한다.
        for field in (
            "university_type",
            "establishment_type",
            "college_info_url",
            "logo_path",
        ):
            if not getattr(target, field) and getattr(base, field):
                setattr(target, field, getattr(base, field))
                fields.append(field)

        if not target.is_active:
            target.is_active = True
            fields.append("is_active")

        if fields:
            target.save(
                update_fields=list(dict.fromkeys(fields + ["updated_at"]))
            )

    def extract_adiga_code(self, source_url):
        if not source_url:
            return None
        match = re.search(
            r"(?:[?&])unvCd=([^&#]+)",
            source_url,
        )
        return match.group(1) if match else None

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
            (
                university_id,
                year,
                phase,
                category,
                metric_code,
            ) = key

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

    def print_global_summary(self, summaries):
        self.stdout.write("")
        self.stdout.write("=" * 78)
        self.stdout.write(self.style.SUCCESS("[전체 요약]"))
        self.stdout.write(
            f"대학 {len(summaries)}개 / "
            f"새 University {sum(len(s['created_names']) for s in summaries)}개"
        )
        self.stdout.write(
            f"Campus 이동 {sum(s['campus_moves'] for s in summaries)} / "
            f"region 보정 {sum(s['campus_regions_fixed'] for s in summaries)}"
        )
        self.stdout.write(
            f"Mapping 이동 {sum(s['mapping_moves'] for s in summaries)}"
        )
        self.stdout.write(
            f"AdmissionSource 이동 {sum(s['source_moves'] for s in summaries)} / "
            f"AdmissionResult 이동 {sum(s['result_moves'] for s in summaries)}"
        )
        self.stdout.write(
            f"Aggregate 재계산 {sum(s['aggregate_count'] for s in summaries)}"
        )

        unresolved_total = sum(
            s["unresolved_count"]
            for s in summaries
        )
        if unresolved_total:
            self.stdout.write(
                self.style.WARNING(
                    f"분류 보류 Campus {unresolved_total}개가 있습니다. "
                    "미리보기 로그를 확인한 뒤 --apply 하세요."
                )
            )

        self.stdout.write(
            "기존 base University의 투표/랭킹 PK는 유지되며, "
            "새 캠퍼스에 과거 투표/rating을 복제하지 않습니다."
        )
