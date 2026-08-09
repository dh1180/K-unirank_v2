import csv
import re
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Count

from admissions.models import AdmissionResult, AdmissionSource
from universities.models import (
    University,
    UniversityCampus,
    UniversityExternalMapping,
)
from universities.services.university_normalizer import (
    COLLAPSED_CAMPUS_BASES,
    MERGED_UNIVERSITIES,
    normalize_address,
    normalize_region,
)


ADIGA_SOURCE = "ADIGA"


class Command(BaseCommand):
    help = (
        "현재 K-unirank에서는 하나의 University로 연결되어 있지만 "
        "ADIGA에는 여러 대학/캠퍼스 코드로 존재하는 케이스를 자동 점검합니다. "
        "DB는 수정하지 않는 읽기 전용 감사 명령입니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            help=(
                "입결 건수를 집계할 학년도. 생략하면 DB에 저장된 "
                "최신 ADIGA 학년도를 사용합니다."
            ),
        )
        parser.add_argument(
            "--name",
            type=str,
            help="특정 대학명만 검사합니다. 예: --name 중앙대학교",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help=(
                "분리 권고뿐 아니라 REVIEW/POLICY_REVIEW 후보까지 "
                "모두 출력합니다."
            ),
        )
        parser.add_argument(
            "--csv",
            type=str,
            dest="csv_path",
            help="감사 결과를 CSV 파일로도 저장합니다.",
        )

    def handle(self, *args, **options):
        selected_year = options.get("year") or self.latest_adiga_year()
        name_filter = (options.get("name") or "").strip()
        include_all = options.get("all", False)
        csv_path = options.get("csv_path")

        if selected_year:
            self.stdout.write(
                self.style.SUCCESS(
                    f"ADIGA 캠퍼스 통합 감사 시작 / 입결 기준 {selected_year}학년도"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "ADIGA AdmissionSource 학년도를 찾지 못했습니다. "
                    "매핑/캠퍼스 구조만 검사합니다."
                )
            )

        suspects = self.find_suspects(name_filter=name_filter)

        if not suspects:
            self.stdout.write(
                self.style.SUCCESS(
                    "동일 University에 ADIGA 코드가 2개 이상 연결된 대학이 없습니다."
                )
            )
            return

        reports = []
        for university, mappings in suspects:
            report = self.build_report(
                university=university,
                mappings=mappings,
                selected_year=selected_year,
            )
            if include_all or report["recommendation"] == "SPLIT_RECOMMENDED":
                reports.append(report)

        if not reports:
            self.stdout.write(
                self.style.SUCCESS(
                    "자동 분리 권고 대상은 없습니다. "
                    "보류 후보까지 보려면 --all을 붙이세요."
                )
            )
            return

        self.print_reports(reports, selected_year=selected_year)

        if csv_path:
            self.write_csv(reports, csv_path)

    def latest_adiga_year(self):
        return (
            AdmissionSource.objects.filter(source_type=ADIGA_SOURCE)
            .order_by("-admission_year")
            .values_list("admission_year", flat=True)
            .first()
        )

    def find_suspects(self, name_filter=""):
        """ADIGA external mapping이 2개 이상 같은 University에 붙은 대학."""
        university_ids = list(
            UniversityExternalMapping.objects.filter(source=ADIGA_SOURCE)
            .values("university_id")
            .annotate(code_count=Count("external_code", distinct=True))
            .filter(code_count__gte=2)
            .values_list("university_id", flat=True)
        )

        universities = University.objects.filter(
            university_id__in=university_ids
        ).order_by("name")

        if name_filter:
            universities = universities.filter(name__icontains=name_filter)

        result = []
        for university in universities:
            mappings = list(
                UniversityExternalMapping.objects.filter(
                    source=ADIGA_SOURCE,
                    university=university,
                )
                .select_related("campus")
                .order_by("external_code")
            )
            if len({mapping.external_code for mapping in mappings}) >= 2:
                result.append((university, mappings))

        return result

    def build_report(self, university, mappings, selected_year):
        mapping_rows = [
            self.build_mapping_row(
                university=university,
                mapping=mapping,
                selected_year=selected_year,
            )
            for mapping in mappings
        ]

        location_keys = {
            row["location_key"]
            for row in mapping_rows
            if row["location_key"]
        }
        meaningful_labels = {
            self.normalize_label(row["campus_label"])
            for row in mapping_rows
            if self.normalize_label(row["campus_label"])
        }

        policy_reason = None
        if university.name in MERGED_UNIVERSITIES:
            policy_reason = (
                "최근 대학 통합/교명 통합 정책 대상으로 normalizer에서 "
                "통합 유지 중"
            )
        elif university.name in COLLAPSED_CAMPUS_BASES:
            policy_reason = (
                "normalizer에서 의도적으로 캠퍼스를 하나의 University로 "
                "묶도록 설정된 대학"
            )

        distinct_location = len(location_keys) >= 2
        distinct_label = len(meaningful_labels) >= 2

        if policy_reason:
            recommendation = "POLICY_REVIEW"
            reason = policy_reason
        elif distinct_location:
            recommendation = "SPLIT_RECOMMENDED"
            reason = (
                f"ADIGA 코드 {len(mapping_rows)}개가 같은 University에 연결되어 있고 "
                f"서로 다른 위치 {len(location_keys)}곳이 확인됨"
            )
        elif distinct_label:
            recommendation = "SPLIT_RECOMMENDED"
            reason = (
                f"ADIGA 코드 {len(mapping_rows)}개가 같은 University에 연결되어 있고 "
                "캠퍼스 라벨이 서로 다름"
            )
        else:
            recommendation = "REVIEW"
            reason = (
                "ADIGA 코드는 여러 개지만 주소/캠퍼스명만으로 자동 분리 여부를 "
                "확정하기 어려움"
            )

        total_results = sum(row["result_count"] for row in mapping_rows)
        codes_with_results = sum(
            1 for row in mapping_rows if row["result_count"] > 0
        )

        return {
            "university": university,
            "mappings": mapping_rows,
            "recommendation": recommendation,
            "reason": reason,
            "location_count": len(location_keys),
            "label_count": len(meaningful_labels),
            "total_results": total_results,
            "codes_with_results": codes_with_results,
        }

    def build_mapping_row(self, university, mapping, selected_year):
        campus = mapping.campus

        # mapping.campus가 비어 있더라도 같은 ADIGA external_code의 campus를
        # 한 번 더 찾아본다.
        if campus is None:
            campus = UniversityCampus.objects.filter(
                source=ADIGA_SOURCE,
                external_code=mapping.external_code,
            ).first()

        campus_label = ""
        address = ""
        region = ""

        if campus:
            campus_label = (campus.campus_name or "").strip()
            address = normalize_address(campus.address) or ""
            region = (
                normalize_region(None, address)
                or normalize_region(campus.region, address)
                or ""
            )

        if not campus_label:
            campus_label = (mapping.external_name or "").strip()

        location_key = self.location_key(
            region=region,
            address=address,
            campus_label=campus_label,
        )

        source_count, result_count = self.count_admissions_by_code(
            university=university,
            external_code=mapping.external_code,
            selected_year=selected_year,
        )

        return {
            "external_code": mapping.external_code,
            "external_name": mapping.external_name or "",
            "campus_label": campus_label,
            "region": region,
            "address": address,
            "location_key": location_key,
            "source_count": source_count,
            "result_count": result_count,
        }

    def count_admissions_by_code(
        self,
        university,
        external_code,
        selected_year,
    ):
        """
        AdmissionSource에는 ADIGA code 전용 컬럼이 없으므로 source_url의
        unvCd를 안전하게 파싱해 코드별 source/result 건수를 계산한다.
        """
        sources = AdmissionSource.objects.filter(
            source_type=ADIGA_SOURCE,
            university=university,
        )

        if selected_year:
            sources = sources.filter(admission_year=selected_year)

        matched_source_ids = []
        for source_id, source_url in sources.values_list(
            "source_id",
            "source_url",
        ):
            if self.extract_adiga_code(source_url) == external_code:
                matched_source_ids.append(source_id)

        if not matched_source_ids:
            return 0, 0

        result_count = AdmissionResult.objects.filter(
            source_id__in=matched_source_ids
        ).count()

        return len(matched_source_ids), result_count

    def extract_adiga_code(self, source_url):
        if not source_url:
            return None

        match = re.search(r"(?:[?&])unvCd=([^&#]+)", source_url)
        return match.group(1) if match else None

    def normalize_label(self, label):
        value = re.sub(r"\s+", "", label or "")
        if not value:
            return ""

        # 모든 mapping에서 외부 이름이 단순히 대학명만 반복되는 경우는
        # 캠퍼스 구분 증거로 쓰지 않는다.
        value = re.sub(r"\[(?:본교|분교|제\d+캠퍼스)\]$", "", value)
        return value

    def location_key(self, region, address, campus_label):
        address = normalize_address(address) or ""
        region = normalize_region(region, address) or ""

        if address:
            parts = address.split()
            if not parts:
                return region

            first = parts[0]

            # 광역시 안에서도 서로 다른 구/군의 별도 campus code가 존재한다.
            # 예: 인천가톨릭대 송도(연수권) / 강화군.
            if len(parts) >= 2:
                second = parts[1]

                # "송도문화로..."처럼 구/군 없이 바로 도로명이 오는 예외는
                # 시 단위까지만 사용한다.
                if second.endswith(("구", "군", "시")):
                    return f"{first} {second}"

                if not first.endswith(
                    ("특별시", "광역시", "특별자치시")
                ):
                    return f"{first} {second}"

            return first

        if region:
            return region

        compact = re.sub(r"\s+", "", campus_label or "")
        for token in (
            "서울",
            "천안",
            "수원",
            "안성",
            "광주",
            "여수",
            "대전",
            "논산",
            "용인",
            "춘천",
            "삼척",
            "강릉",
            "원주",
            "의정부",
            "동두천",
            "부산",
            "양산",
            "인천",
        ):
            if token in compact:
                return token

        return ""

    def print_reports(self, reports, selected_year):
        split_count = sum(
            1
            for report in reports
            if report["recommendation"] == "SPLIT_RECOMMENDED"
        )
        policy_count = sum(
            1
            for report in reports
            if report["recommendation"] == "POLICY_REVIEW"
        )
        review_count = sum(
            1
            for report in reports
            if report["recommendation"] == "REVIEW"
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[감사 결과] 총 {len(reports)}개 대학 "
                f"/ 분리 권고 {split_count} "
                f"/ 정책 검토 {policy_count} "
                f"/ 수동 검토 {review_count}"
            )
        )

        for report in reports:
            university = report["university"]
            recommendation = report["recommendation"]

            self.stdout.write("")
            self.stdout.write("=" * 78)

            if recommendation == "SPLIT_RECOMMENDED":
                label = self.style.ERROR("SPLIT_RECOMMENDED")
            elif recommendation == "POLICY_REVIEW":
                label = self.style.WARNING("POLICY_REVIEW")
            else:
                label = self.style.WARNING("REVIEW")

            self.stdout.write(
                f"[{university.name}] "
                f"University id={university.university_id} / {label}"
            )
            self.stdout.write(f"사유: {report['reason']}")

            if selected_year:
                self.stdout.write(
                    f"{selected_year}학년도 ADIGA 입결: "
                    f"총 {report['total_results']}건 / "
                    f"입결이 있는 코드 "
                    f"{report['codes_with_results']}개"
                )

            for index, row in enumerate(report["mappings"], start=1):
                self.stdout.write(
                    f"  {index}. code={row['external_code']} "
                    f"| name={row['external_name'] or '-'}"
                )
                self.stdout.write(
                    f"     campus={row['campus_label'] or '-'} "
                    f"| location={row['location_key'] or '미상'}"
                )
                self.stdout.write(
                    f"     region={row['region'] or '-'} "
                    f"| address={row['address'] or '-'}"
                )

                if selected_year:
                    self.stdout.write(
                        f"     source={row['source_count']} "
                        f"| AdmissionResult={row['result_count']}건"
                    )

        self.stdout.write("")
        self.stdout.write("=" * 78)
        self.stdout.write(
            "판정 기준: 서로 다른 ADIGA 코드가 현재 동일 University에 연결되고, "
            "주소/지역 또는 캠퍼스 라벨이 명확히 다르면 SPLIT_RECOMMENDED."
        )
        self.stdout.write(
            "POLICY_REVIEW는 현재 normalizer에서 통합 유지하도록 명시된 대학이므로 "
            "자동 분리하지 말고 통합 이력/입시 구조를 먼저 확인해야 합니다."
        )

    def write_csv(self, reports, csv_path):
        path = Path(csv_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)

        with path.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "university_id",
                    "university_name",
                    "recommendation",
                    "reason",
                    "external_code",
                    "external_name",
                    "campus_label",
                    "location_key",
                    "region",
                    "address",
                    "source_count",
                    "result_count",
                ]
            )

            for report in reports:
                university = report["university"]
                for row in report["mappings"]:
                    writer.writerow(
                        [
                            university.university_id,
                            university.name,
                            report["recommendation"],
                            report["reason"],
                            row["external_code"],
                            row["external_name"],
                            row["campus_label"],
                            row["location_key"],
                            row["region"],
                            row["address"],
                            row["source_count"],
                            row["result_count"],
                        ]
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"CSV 저장 완료: {path.resolve()}"
            )
        )
