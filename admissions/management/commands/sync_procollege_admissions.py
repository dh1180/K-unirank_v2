import hashlib
import json
import time
from collections import defaultdict
from datetime import date
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from admissions.models import (
    AdmissionMetric,
    AdmissionResult,
    AdmissionSource,
    RecruitmentUnit,
)
from admissions.services.procollege import (
    PROCOLLEGE_URL,
    build_search_payload,
    extract_last_page,
    extract_selected_year,
    parse_procollege_results,
    normalize_procollege_match_name,
)
from universities.models import University, UniversityExternalMapping
from universities.services.university_normalizer import normalize_university_name


PROCOLLEGE_SOURCE = "PROCOLLEGE"


class Command(BaseCommand):
    help = (
        "전문대학포털(Procollege)의 전년도 입시결과를 가져옵니다. "
        "기본은 미리보기이며 --apply를 붙여야 DB에 저장합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=date.today().year,
            help="모집학년도. 기본값은 현재 연도입니다.",
        )
        parser.add_argument(
            "--university",
            default="",
            help="특정 대학만 조회합니다. 예: 인하공업전문대학",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="전문대학포털의 해당 학년도 전체 결과를 수집합니다.",
        )
        parser.add_argument(
            "--page-unit",
            type=int,
            choices=[15, 30, 50, 100],
            default=100,
            help="Procollege 페이지당 결과 수. 기본 100.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=0,
            help="테스트용 최대 페이지 수. 0이면 전체 페이지.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.15,
            help="페이지 요청 사이 대기 시간(초). 기본 0.15.",
        )
        parser.add_argument(
            "--show-rows",
            action="store_true",
            help="파싱 결과 예시를 최대 20건 출력합니다.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제 DB에 저장합니다.",
        )

    def handle(self, *args, **options):
        year = options["year"]
        target_name = options["university"].strip()
        collect_all = options["all"]
        page_unit = options["page_unit"]
        max_pages = max(0, options["max_pages"])
        delay = max(0, options["delay"])
        show_rows = options["show_rows"]
        apply_changes = options["apply"]

        if not target_name and not collect_all:
            raise CommandError(
                "--university \"대학명\" 또는 --all 중 하나를 지정해주세요."
            )

        if target_name and collect_all:
            raise CommandError("--university와 --all은 동시에 사용할 수 없습니다.")

        session = self.build_session()
        self.establish_session(session)

        rows, html_by_page = self.fetch_rows(
            session=session,
            year=year,
            university_name=target_name,
            page_unit=page_unit,
            max_pages=max_pages,
            delay=delay,
        )

        if target_name:
            # 서버 검색이 무시되거나 엉뚱한 초기 목록을 반환하는 경우를
            # 데이터 오염 전에 즉시 차단한다.
            target_key = normalize_procollege_match_name(target_name)
            exact_rows = [
                row
                for row in rows
                if normalize_procollege_match_name(row.university_name) == target_key
            ]

            if rows and not exact_rows:
                found = sorted({row.university_name for row in rows})[:8]
                raise CommandError(
                    "Procollege 대학명 검색 결과가 요청 대학과 일치하지 않습니다. "
                    f"요청={target_name}, 응답 예시={', '.join(found)}"
                )

            rows = exact_rows

        if not rows:
            self.stdout.write(
                self.style.WARNING(
                    f"{year}학년도 조건에서 파싱된 전문대 입시결과가 없습니다."
                )
            )
            return

        parsed_years = {
            extract_selected_year(html)
            for html in html_by_page.values()
            if extract_selected_year(html)
        }
        if parsed_years and year not in parsed_years:
            raise CommandError(
                f"요청 학년도 {year}와 응답 화면 학년도 {sorted(parsed_years)}가 다릅니다."
            )

        grouped = defaultdict(list)
        for row in rows:
            grouped[(row.university_code, row.university_name)].append(row)

        self.stdout.write(
            self.style.SUCCESS(
                f"Procollege {year}학년도: "
                f"{len(grouped)}개 대학 / {len(rows)}개 모집단위 결과 파싱"
            )
        )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING("미리보기 모드입니다. DB는 변경하지 않습니다.")
            )

        if show_rows:
            self.print_samples(rows)

        active_universities = list(University.objects.filter(is_active=True))
        stats = defaultdict(int)

        for (external_code, external_name), university_rows in sorted(
            grouped.items(),
            key=lambda item: item[0][1],
        ):
            university = self.match_university(
                external_code=external_code,
                external_name=external_name,
                universities=active_universities,
            )

            if university is None:
                stats["unmatched"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"미매칭: {external_name} ({external_code or '코드 없음'}) "
                        f"/ {len(university_rows)}건"
                    )
                )
                continue

            stats["matched"] += 1
            self.stdout.write(
                f"{external_name} ({external_code or '-'}) "
                f"-> {university.name} | {len(university_rows)}건"
            )

            if not apply_changes:
                stats["parsed"] += len(university_rows)
                continue

            with transaction.atomic():
                if external_code:
                    UniversityExternalMapping.objects.update_or_create(
                        source=PROCOLLEGE_SOURCE,
                        external_code=external_code,
                        defaults={
                            "university": university,
                            "campus": None,
                            "external_name": external_name,
                        },
                    )

                saved = self.replace_results(
                    university=university,
                    admission_year=year,
                    external_name=external_name,
                    rows=university_rows,
                )
                stats["saved"] += saved

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "완료: "
                f"매칭 {stats['matched']}개 / "
                f"미매칭 {stats['unmatched']}개 / "
                f"{'저장' if apply_changes else '파싱'} "
                f"{stats['saved'] if apply_changes else stats['parsed']}건"
            )
        )

        if apply_changes and stats["saved"]:
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"{year}학년도 대학 단위 집계를 다시 계산합니다."
                )
            )
            call_command("recalculate_admission_aggregates", year=year)

    def build_session(self):
        session = requests.Session()

        retry = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset({"GET", "POST"}),
        )

        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            }
        )

        return session

    def establish_session(self, session):
        try:
            response = session.get(PROCOLLEGE_URL, timeout=25)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(
                f"전문대학포털 초기 접속 실패: {exc}"
            ) from exc

    def fetch_page(
        self,
        session,
        *,
        year,
        page,
        university_name,
        page_unit,
    ):
        payload = build_search_payload(
            year=year,
            page=page,
            page_unit=page_unit,
            university_name=university_name,
        )

        try:
            response = session.post(
                PROCOLLEGE_URL,
                data=payload,
                headers={"Referer": PROCOLLEGE_URL},
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(
                f"Procollege {page}페이지 요청 실패: {exc}"
            ) from exc

        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def fetch_rows(
        self,
        *,
        session,
        year,
        university_name,
        page_unit,
        max_pages,
        delay,
    ):
        first_html = self.fetch_page(
            session,
            year=year,
            page=1,
            university_name=university_name,
            page_unit=page_unit,
        )

        html_by_page = {1: first_html}
        rows = list(parse_procollege_results(first_html))

        last_page = extract_last_page(first_html)
        if max_pages:
            last_page = min(last_page, max_pages)

        self.stdout.write(
            f"검색: {university_name or '전체 전문대'} / "
            f"{year}학년도 / 총 {last_page}페이지"
        )

        for page in range(2, last_page + 1):
            if delay:
                time.sleep(delay)

            html = self.fetch_page(
                session,
                year=year,
                page=page,
                university_name=university_name,
                page_unit=page_unit,
            )
            html_by_page[page] = html
            page_rows = parse_procollege_results(html)
            rows.extend(page_rows)

            if page == 2 or page == last_page or page % 10 == 0:
                self.stdout.write(
                    f"  {page}/{last_page} 페이지 "
                    f"/ 누적 {len(rows)}건"
                )

        return rows, html_by_page

    def match_university(
        self,
        *,
        external_code,
        external_name,
        universities,
    ):
        if external_code:
            mapping = (
                UniversityExternalMapping.objects
                .select_related("university")
                .filter(
                    source=PROCOLLEGE_SOURCE,
                    external_code=external_code,
                    university__is_active=True,
                )
                .first()
            )
            if mapping:
                if (
                    normalize_procollege_match_name(external_name)
                    == normalize_procollege_match_name(mapping.university.name)
                ):
                    return mapping.university

                self.stdout.write(
                    self.style.WARNING(
                        "기존 PROCOLLEGE 매핑 이름 불일치: "
                        f"{external_name} ({external_code}) -> "
                        f"{mapping.university.name}; 매핑을 무시합니다."
                    )
                )

        target_key = normalize_procollege_match_name(external_name)

        exact = [
            university
            for university in universities
            if normalize_procollege_match_name(university.name) == target_key
        ]
        if len(exact) == 1:
            return exact[0]

        # 전문대 데이터는 학교명이 비슷한 대학이 많기 때문에
        # contains/fuzzy 매칭을 절대 사용하지 않는다.
        return None

    def replace_results(
        self,
        *,
        university,
        admission_year,
        external_name,
        rows,
    ):
        source_url = (
            f"{PROCOLLEGE_URL}?"
            + urlencode(
                {
                    "cate": "1",
                    "univName": external_name,
                    "sel_1": admission_year,
                }
            )
        )

        payload_for_checksum = [
            {
                "code": row.university_code,
                "name": row.university_name,
                "period": row.recruitment_period,
                "unit": row.recruitment_unit,
                "count": row.recruitment_count,
                "day_night": row.day_night,
                "category": row.selection_category,
                "selection": row.selection_name,
                "competition": (
                    str(row.competition_rate)
                    if row.competition_rate is not None
                    else None
                ),
                "metrics": {
                    code: [str(value), unit]
                    for code, (value, unit) in row.metrics.items()
                },
            }
            for row in rows
        ]
        checksum = hashlib.sha256(
            json.dumps(
                payload_for_checksum,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        existing_sources = AdmissionSource.objects.filter(
            university=university,
            admission_year=admission_year,
            source_type=PROCOLLEGE_SOURCE,
        )

        # 같은 대학/학년의 이전 Procollege 수집분만 교체한다.
        AdmissionResult.objects.filter(
            university=university,
            admission_year=admission_year,
            source__in=existing_sources,
        ).delete()
        existing_sources.delete()

        source = AdmissionSource.objects.create(
            university=university,
            admission_year=admission_year,
            source_type=PROCOLLEGE_SOURCE,
            source_url=source_url,
            document_title=f"전문대학포털 {admission_year}학년도 전년도 입시결과",
            checksum=checksum,
        )

        saved = 0

        for row in rows:
            recruitment_unit, _ = RecruitmentUnit.objects.get_or_create(
                university=university,
                campus=None,
                name=row.recruitment_unit,
                defaults={
                    "college_name": "",
                    "is_active": True,
                },
            )

            result = AdmissionResult.objects.create(
                source=source,
                university=university,
                recruitment_unit=recruitment_unit,
                admission_year=admission_year,
                admission_phase=row.admission_phase,
                selection_category=row.selection_category,
                selection_name=row.selection_name,
                recruitment_group=row.recruitment_group,
                recruitment_count=row.recruitment_count,
                applicant_count=None,
                registered_count=None,
                competition_rate=row.competition_rate,
            )

            AdmissionMetric.objects.bulk_create(
                [
                    AdmissionMetric(
                        result=result,
                        metric_code=metric_code,
                        unit=unit,
                        value=value,
                    )
                    for metric_code, (value, unit) in row.metrics.items()
                ]
            )

            saved += 1

        return saved

    def print_samples(self, rows):
        self.stdout.write("")
        self.stdout.write("=== 파싱 예시 ===")

        for row in rows[:20]:
            metrics = ", ".join(
                f"{code}={value}{(' ' + unit) if unit else ''}"
                for code, (value, unit) in row.metrics.items()
            ) or "공개 지표 없음"

            self.stdout.write(
                f"{row.university_name} | "
                f"{row.recruitment_period} / "
                f"{row.day_night or '-'} | "
                f"{row.selection_category}"
                f"{(' / ' + row.selection_name) if row.selection_name else ''} | "
                f"{row.recruitment_unit} | "
                f"정원={row.recruitment_count} | "
                f"경쟁률={row.competition_rate} | "
                f"{metrics}"
            )
