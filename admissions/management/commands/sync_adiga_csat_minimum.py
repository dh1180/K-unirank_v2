import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from admissions.models import AdmissionRequirement, AdmissionResult
from admissions.services.csat_minimum import (
    extract_adiga_code,
    format_csat_minimum_display,
    match_csat_minimum_rule,
    parse_csat_minimum_rules,
)
from admissions.services.csat_minimum_quality import normalize_safe_csat_minimum_rule
from universities.models import University, UniversityExternalMapping


ADIGA_RESULT_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"


class Command(BaseCommand):
    help = (
        "대입정보포털 어디가 Q1(전형별 주요사항)에서 수시 수능최저학력기준을 "
        "전형/모집단위 단위로 수집합니다. 기본은 미리보기입니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=0,
            help=(
                "모집학년도. 연도를 지정하면 해당 학년도 입시결과가 아직 없어도 "
                "ADIGA 대학 매핑 전체에서 Q1을 확인합니다. 0이면 현재 DB의 "
                "ADIGA 수시 결과 학년만 확인합니다."
            ),
        )
        parser.add_argument(
            "--university",
            default="",
            help="특정 대학명만 처리합니다.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="처리할 ADIGA 대학 코드 수를 제한합니다. 0이면 전체입니다.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.2,
            help="대학별 요청 사이 대기 시간(초)입니다.",
        )
        parser.add_argument(
            "--show-rules",
            action="store_true",
            help="파싱된 수능최저 규칙 예시를 출력합니다.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 반영합니다. 생략하면 미리보기만 합니다.",
        )

    def handle(self, *args, **options):
        year = max(0, options["year"])
        target_name = options["university"].strip()
        limit = max(0, options["limit"])
        delay = max(0.0, options["delay"])
        show_rules = options["show_rules"]
        apply_changes = options["apply"]

        scopes = self.build_scopes(year=year, target_name=target_name)
        if limit:
            scopes = scopes[:limit]

        if not scopes:
            self.stdout.write(self.style.WARNING("처리할 ADIGA 대학/학년도 범위가 없습니다."))
            return

        university_map = {
            university.pk: university
            for university in University.objects.filter(
                pk__in={scope["university_id"] for scope in scopes}
            )
        }
        session = self.build_session()

        if not apply_changes:
            self.stdout.write(self.style.WARNING("미리보기 모드입니다. DB는 변경하지 않습니다."))

        stats = {
            "scopes": 0,
            "rules": 0,
            "matched_results": 0,
            "saved": 0,
            "empty": 0,
            "failed": 0,
            "future_without_results": 0,
        }

        for scope in scopes:
            university = university_map.get(scope["university_id"])
            if university is None:
                continue

            admission_year = scope["admission_year"]
            code = scope["code"]
            if not code:
                stats["failed"] += 1
                self.stderr.write(
                    f"{university.name} {admission_year}: ADIGA 대학 코드를 찾지 못했습니다."
                )
                continue

            source_url = self.source_url(code, admission_year)
            if delay:
                time.sleep(delay)

            try:
                html = self.fetch(session, code, admission_year)
            except CommandError as exc:
                stats["failed"] += 1
                self.stderr.write(
                    f"[{code}] {university.name} {admission_year}: {exc}"
                )
                continue

            parsed_rules = []
            for rule in parse_csat_minimum_rules(html, admission_year):
                safe_rule = normalize_safe_csat_minimum_rule(rule)
                if safe_rule is not None:
                    parsed_rules.append(safe_rule)

            stats["scopes"] += 1

            if not parsed_rules:
                stats["empty"] += 1
                self.stdout.write(
                    f"[{code}] {university.name} {admission_year}: 수능최저 규칙 미확인"
                )
                continue

            requirement_objects = [
                AdmissionRequirement(
                    university=university,
                    admission_year=admission_year,
                    admission_phase="SUSI",
                    requirement_type="CSAT_MINIMUM",
                    selection_name=rule.selection_name,
                    recruitment_unit_name=rule.recruitment_unit_name,
                    applied=rule.applied,
                    requirement_text=rule.requirement_text,
                    source_type="ADIGA",
                    source_code=code,
                    source_url=source_url,
                    collected_at=timezone.now(),
                )
                for rule in parsed_rules
            ]

            scope_results = self.results_for_code(
                university=university,
                admission_year=admission_year,
                code=code,
            )
            matched_count = sum(
                1
                for result in scope_results
                if match_csat_minimum_rule(result, requirement_objects) is not None
            )

            stats["rules"] += len(requirement_objects)
            stats["matched_results"] += matched_count

            if scope_results:
                match_note = f"현재 수시결과 매칭 {matched_count}/{len(scope_results)}건"
            else:
                match_note = "동학년도 수시결과 없음"
                stats["future_without_results"] += 1

            self.stdout.write(
                f"[{code}] {university.name} {admission_year}: "
                f"규칙 {len(requirement_objects)}건 / {match_note}"
            )

            if show_rules:
                for requirement in requirement_objects[:12]:
                    target = requirement.selection_name or requirement.recruitment_unit_name
                    if requirement.recruitment_unit_name and requirement.selection_name:
                        target += f" / {requirement.recruitment_unit_name}"
                    self.stdout.write(
                        f"    {target or '-'} | {format_csat_minimum_display(requirement)}"
                    )

            if apply_changes:
                with transaction.atomic():
                    AdmissionRequirement.objects.filter(
                        university=university,
                        admission_year=admission_year,
                        admission_phase="SUSI",
                        requirement_type="CSAT_MINIMUM",
                        source_type="ADIGA",
                        source_code=code,
                    ).delete()
                    AdmissionRequirement.objects.bulk_create(requirement_objects)
                stats["saved"] += len(requirement_objects)

        self.stdout.write("")
        self.stdout.write(f"확인한 대학/코드: {stats['scopes']}개")
        self.stdout.write(f"파싱한 수능최저 규칙: {stats['rules']}건")
        self.stdout.write(f"현재 수시 결과와 안전 매칭: {stats['matched_results']}건")
        if stats["future_without_results"]:
            self.stdout.write(
                f"입시결과보다 먼저 공개된 학년도 범위: {stats['future_without_results']}개"
            )
        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f"DB 저장: {stats['saved']}건"))
        if stats["empty"]:
            self.stdout.write(f"수능최저 규칙 미확인: {stats['empty']}개")
        if stats["failed"]:
            self.stdout.write(self.style.WARNING(f"요청/코드 실패: {stats['failed']}개"))

    def build_scopes(self, year, target_name):
        """수능최저 수집 범위를 만든다.

        명시적인 학년이 있으면 AdmissionResult 존재 여부와 무관하게 ADIGA
        외부 매핑을 사용한다. 따라서 2027 수시 결과가 아직 없어도 이미 공개된
        2027 전형별 주요사항(Q1)을 수집할 수 있다.
        """
        if year:
            mappings = (
                UniversityExternalMapping.objects.filter(
                    source="ADIGA",
                    university__is_active=True,
                )
                .select_related("university")
                .order_by("university_id", "external_code")
            )
            if target_name:
                mappings = mappings.filter(university__name__icontains=target_name)

            return [
                {
                    "university_id": mapping.university_id,
                    "admission_year": year,
                    "code": str(mapping.external_code or "").strip(),
                }
                for mapping in mappings
                if str(mapping.external_code or "").strip()
            ]

        results = AdmissionResult.objects.filter(
            source__source_type="ADIGA",
            admission_phase="SUSI",
            university__is_active=True,
        )
        if target_name:
            results = results.filter(university__name__icontains=target_name)

        raw_scopes = list(
            results.values(
                "university_id",
                "admission_year",
                "source__source_url",
            )
            .distinct()
            .order_by("-admission_year", "university_id", "source__source_url")
        )

        scopes = []
        seen = set()
        for scope in raw_scopes:
            code = extract_adiga_code(scope["source__source_url"])
            key = (scope["university_id"], scope["admission_year"], code)
            if not code or key in seen:
                continue
            seen.add(key)
            scopes.append(
                {
                    "university_id": scope["university_id"],
                    "admission_year": scope["admission_year"],
                    "code": code,
                }
            )
        return scopes

    def results_for_code(self, university, admission_year, code):
        candidates = list(
            AdmissionResult.objects.filter(
                university=university,
                admission_year=admission_year,
                admission_phase="SUSI",
                source__source_type="ADIGA",
            ).select_related("source", "recruitment_unit")
        )
        return [
            result
            for result in candidates
            if extract_adiga_code(result.source.source_url) == code
        ]

    def source_url(self, code, admission_year):
        return (
            f"{ADIGA_RESULT_URL}?menuId=PCUVTINF2000"
            f"&searchSyr={admission_year}&unvCd={code}"
        )

    def build_session(self):
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/150 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.6",
            }
        )
        return session

    def fetch(self, session, code, admission_year):
        try:
            response = session.get(
                ADIGA_RESULT_URL,
                params={
                    "menuId": "PCUVTINF2000",
                    "searchSyr": admission_year,
                    "unvCd": code,
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"ADIGA 요청 실패: {exc}") from exc

        response.encoding = response.apparent_encoding or "utf-8"
        return response.text
