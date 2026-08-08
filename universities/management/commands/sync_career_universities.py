import math
import os
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from universities.models import (
    University,
    UniversityCampus,
    UniversityExternalMapping,
)
from universities.services.university_normalizer import (
    canonical_university_name,
    fallback_split_name,
    ranking_university_name,
    clean_text,
    is_excluded_university,
    normalize_university_name,
    normalize_address,
    normalize_region,
)


CAREER_API_URL = "https://www.career.go.kr/cnet/openapi/getOpenApi"
CAREER_SOURCE = "CAREER_NET"


class Command(BaseCommand):
    help = "CareerNet 대학 목록을 캠퍼스 통합 방식으로 확인하고 갱신합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB에 반영합니다. 생략하면 미리보기만 합니다.",
        )

        parser.add_argument(
            "--create-new",
            action="store_true",
            help="기존 DB에 없는 대학을 새로 생성합니다.",
        )

        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="CareerNet 현재 목록에 없는 기존 대학을 비활성화합니다.",
        )

        parser.add_argument(
            "--per-page",
            type=int,
            default=100,
            help="CareerNet API 한 페이지당 조회 건수",
        )

    def handle(self, *args, **options):
        api_key = os.getenv("CAREER_API_KEY")

        if not api_key:
            raise CommandError(
                ".env의 CAREER_API_KEY에 커리어넷 API 키를 입력해주세요."
            )

        apply_changes = options["apply"]
        create_new = options["create_new"]
        deactivate_missing = options["deactivate_missing"]
        per_page = options["per_page"]

        if per_page < 1:
            raise CommandError("--per-page는 1 이상이어야 합니다.")

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "미리보기 모드입니다. DB는 변경하지 않습니다."
                )
            )

        schools = self.fetch_all(
            api_key=api_key,
            per_page=per_page,
        )

        grouped, excluded = self.group_schools(schools)

        self.stdout.write(
            self.style.SUCCESS(
                f"CareerNet 원본 {len(schools)}건, "
                f"랭킹 단위 정리 후 {len(grouped)}개 대학, "
                f"제외 {len(excluded)}건"
            )
        )

        stats = {
            "mapped": 0,
            "matched": 0,
            "created": 0,
            "unmatched": 0,
            "deactivated": 0,
        }

        unmatched = []
        active_names = set()

        with transaction.atomic():
            for canonical_name, rows in sorted(grouped.items(), key=self.group_order_key):
                active_names.add(canonical_name)

                result = self.sync_university_group(
                    canonical_name=canonical_name,
                    rows=rows,
                    apply_changes=apply_changes,
                    create_new=create_new,
                )

                stats[result] += 1

                if result == "unmatched":
                    unmatched.append(
                        {
                            "name": canonical_name,
                            "rows": rows,
                        }
                    )

            if apply_changes:
                stats["deactivated"] += self.disable_excluded_existing()

                if deactivate_missing:
                    stats["deactivated"] += self.deactivate_missing(
                        active_names
                    )
            else:
                transaction.set_rollback(True)

        self.print_result(
            stats=stats,
            excluded=excluded,
            unmatched=unmatched,
            apply_changes=apply_changes,
        )

    def build_session(self):
        session = requests.Session()

        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        session.mount(
            "https://",
            HTTPAdapter(max_retries=retry),
        )

        return session

    def fetch_all(self, api_key, per_page):
        session = self.build_session()

        first_data = self.fetch_page(
            session=session,
            api_key=api_key,
            page=1,
            per_page=per_page,
        )

        first_search = first_data.get("dataSearch", {})
        first_contents = first_search.get("content", [])

        if isinstance(first_contents, dict):
            first_contents = [first_contents]

        if not first_contents:
            return []

        raw_total = first_search.get("totalCount")

        if raw_total is None:
            raw_total = first_contents[0].get("totalCount")

        try:
            total_count = int(raw_total)
        except (TypeError, ValueError):
            total_count = len(first_contents)

        total_pages = max(1, math.ceil(total_count / per_page))
        results = list(first_contents)

        for page in range(2, total_pages + 1):
            data = self.fetch_page(
                session=session,
                api_key=api_key,
                page=page,
                per_page=per_page,
            )

            contents = data.get("dataSearch", {}).get("content", [])

            if isinstance(contents, dict):
                contents = [contents]

            results.extend(contents)

        return results

    def fetch_page(self, session, api_key, page, per_page):
        params = {
            "apiKey": api_key,
            "svcType": "api",
            "svcCode": "SCHOOL",
            "contentType": "json",
            "gubun": "univ_list",
            "thisPage": page,
            "perPage": per_page,
        }

        try:
            response = session.get(
                CAREER_API_URL,
                params=params,
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(
                f"CareerNet API 요청에 실패했습니다: {exc}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise CommandError(
                "CareerNet 응답을 JSON으로 읽지 못했습니다."
            ) from exc

    def group_schools(self, schools):
        base_groups = defaultdict(list)
        excluded = []

        for school in schools:
            name = clean_text(school.get("schoolName"))
            school_type = clean_text(school.get("schoolType"))

            if not name:
                continue

            if is_excluded_university(
                name=name,
                school_type=school_type,
            ):
                excluded.append(school)
                continue

            base_name = canonical_university_name(name)
            base_groups[base_name].append(school)

        grouped = defaultdict(list)

        for base_name, rows in base_groups.items():
            if len(rows) == 1:
                row = rows[0]
                rank_name = ranking_university_name(
                    row.get("schoolName"),
                    row.get("campusName"),
                    row.get("adres"),
                )
                grouped[rank_name].append(row)
                continue

            for row in rows:
                rank_name = fallback_split_name(
                    row.get("schoolName"),
                    row.get("campusName"),
                    row.get("adres"),
                )
                grouped[rank_name].append(row)

        return dict(grouped), excluded

    def sync_university_group(
        self,
        canonical_name,
        rows,
        apply_changes,
        create_new,
    ):
        university = self.find_by_mapping(rows, canonical_name)

        if university:
            if apply_changes:
                self.update_university_and_campuses(
                    university,
                    canonical_name,
                    rows,
                )

            return "mapped"

        university = self.find_existing_university(canonical_name)

        if university:
            if apply_changes:
                self.update_university_and_campuses(
                    university,
                    canonical_name,
                    rows,
                )

            return "matched"

        if create_new:
            if apply_changes:
                representative = self.pick_representative(rows)

                university = University.objects.create(
                    name=canonical_name,
                    address=normalize_address(representative.get("adres")),
                    region=normalize_region(representative.get("region"), representative.get("adres")),
                    university_type=clean_text(
                        representative.get("schoolType")
                        or representative.get("schoolGubun")
                    ),
                    establishment_type=clean_text(
                        representative.get("estType")
                    ),
                    homepage_url=clean_text(representative.get("link")),
                    college_info_url=clean_text(
                        representative.get("collegeinfourl")
                    ),
                    logo_path=self.find_logo_from_mapping(rows),
                    is_active=True,
                )

                self.update_university_and_campuses(
                    university,
                    canonical_name,
                    rows,
                )

            return "created"

        return "unmatched"

    def find_by_mapping(self, rows, canonical_name):
        seqs = [
            clean_text(row.get("seq"))
            for row in rows
            if clean_text(row.get("seq"))
        ]

        mappings = list(
            UniversityExternalMapping.objects
            .select_related("university")
            .filter(
                source=CAREER_SOURCE,
                external_code__in=seqs,
            )
        )

        target_key = normalize_university_name(canonical_name)

        for mapping in mappings:
            university = mapping.university
            if normalize_university_name(university.name) == target_key:
                return university

        # 이전 버전에서 캠퍼스가 하나로 합쳐져 있던 경우,
        # 첫 번째(주 캠퍼스) 그룹은 기존 대학 레코드를 재사용한다.
        for mapping in mappings:
            university = mapping.university
            old_name = canonical_university_name(university.name)

            target_exists = (
                University.objects
                .filter(name=canonical_name)
                .exclude(pk=university.pk)
                .exists()
            )

            if target_exists:
                continue

            if canonical_name.startswith(f"{old_name} ") and "캠퍼스" not in university.name:
                return university

        return None

    def find_logo_from_mapping(self, rows):
        seqs = [
            clean_text(row.get("seq"))
            for row in rows
            if clean_text(row.get("seq"))
        ]

        mapping = (
            UniversityExternalMapping.objects
            .select_related("university")
            .filter(
                source=CAREER_SOURCE,
                external_code__in=seqs,
            )
            .exclude(university__logo_path__isnull=True)
            .first()
        )

        if mapping and mapping.university.logo_path:
            return mapping.university.logo_path

        return None

    def group_order_key(self, item):
        _, rows = item
        primary = any(
            clean_text(row.get("campusName")) in {None, "", "본교", "본캠퍼스", "제1캠퍼스", "1캠퍼스"}
            for row in rows
        )
        return (0 if primary else 1, item[0])

    def find_existing_university(self, canonical_name):
        target = normalize_university_name(canonical_name)

        for university in University.objects.filter(is_active=True):
            if normalize_university_name(university.name) == target:
                return university

        return None

    def update_university_and_campuses(
        self,
        university,
        canonical_name,
        rows,
    ):
        representative = self.pick_representative(rows)

        university.name = canonical_name
        university.address = normalize_address(representative.get("adres"))
        university.region = normalize_region(representative.get("region"), representative.get("adres"))

        university.university_type = clean_text(
            representative.get("schoolType")
            or representative.get("schoolGubun")
        )

        university.establishment_type = clean_text(
            representative.get("estType")
        )

        university.homepage_url = clean_text(
            representative.get("link")
        )

        university.college_info_url = clean_text(
            representative.get("collegeinfourl")
        )

        university.is_active = True

        # logo_path는 기존 값을 그대로 둔다.
        university.save()

        for row in rows:
            seq = clean_text(row.get("seq"))

            if not seq:
                continue

            campus_name = clean_text(row.get("campusName"))
            is_primary = campus_name in {
                None,
                "본교",
                "본캠퍼스",
                "제1캠퍼스",
            }

            campus, _ = UniversityCampus.objects.update_or_create(
                source=CAREER_SOURCE,
                external_code=seq,
                defaults={
                    "university": university,
                    "campus_name": campus_name,
                    "address": normalize_address(row.get("adres")),
                    "region": normalize_region(row.get("region"), row.get("adres")),
                    "homepage_url": clean_text(row.get("link")),
                    "is_primary": is_primary,
                },
            )

            UniversityExternalMapping.objects.update_or_create(
                source=CAREER_SOURCE,
                external_code=seq,
                defaults={
                    "university": university,
                    "campus": campus,
                    "external_name": clean_text(row.get("schoolName")),
                },
            )

    def pick_representative(self, rows):
        def score(row):
            school_name = clean_text(row.get("schoolName")) or ""
            campus_name = clean_text(row.get("campusName"))

            primary_score = 0 if campus_name in {
                None,
                "본교",
                "본캠퍼스",
                "제1캠퍼스",
            } else 1

            campus_word_score = 1 if "캠퍼스" in school_name else 0

            return (
                primary_score,
                campus_word_score,
                len(school_name),
            )

        return min(rows, key=score)

    def disable_excluded_existing(self):
        count = 0

        for university in University.objects.filter(is_active=True):
            if is_excluded_university(university.name):
                university.is_active = False
                university.save(update_fields=["is_active", "updated_at"])
                count += 1

        return count

    def deactivate_missing(self, active_names):
        active_keys = {
            normalize_university_name(name)
            for name in active_names
        }

        count = 0

        for university in University.objects.filter(is_active=True):
            if normalize_university_name(university.name) not in active_keys:
                university.is_active = False
                university.save(update_fields=["is_active", "updated_at"])
                count += 1

        return count

    def print_result(
        self,
        stats,
        excluded,
        unmatched,
        apply_changes,
    ):
        self.stdout.write("")
        self.stdout.write(
            f"기존 CareerNet 매핑: {stats['mapped']}"
        )
        self.stdout.write(
            f"기존 대학 자동 매칭: {stats['matched']}"
        )
        self.stdout.write(
            f"신규 생성 대상: {stats['created']}"
        )
        self.stdout.write(
            f"미매칭: {stats['unmatched']}"
        )
        self.stdout.write(
            f"비활성화: {stats['deactivated']}"
        )

        if excluded:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("제외된 대학")
            )

            for school in excluded:
                self.stdout.write(
                    f"{school.get('schoolName')} | "
                    f"{school.get('schoolType')}"
                )

        if unmatched:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("미매칭 대학")
            )

            for item in unmatched:
                regions = sorted(
                    {
                        clean_text(row.get("region")) or ""
                        for row in item["rows"]
                    }
                )

                self.stdout.write(
                    f"{item['name']} | {', '.join(regions)}"
                )

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "실제 반영하려면 "
                    "python manage.py sync_career_universities "
                    "--apply --create-new "
                    "명령을 사용하세요."
                )
            )
