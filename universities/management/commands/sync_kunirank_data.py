from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "CareerNet 대학정보 정리 후 ADIGA 입시결과와 수능최저까지 순서대로 동기화합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--adiga-limit",
            type=int,
            default=0,
            help="ADIGA 대학 코드 처리 개수를 제한합니다. 0이면 전체입니다.",
        )
        parser.add_argument(
            "--university",
            default="",
            help="특정 대학만 ADIGA 동기화를 시험할 때 사용합니다.",
        )
        parser.add_argument(
            "--search-year",
            type=int,
            default=date.today().year + 1,
            help="ADIGA 조회 화면의 모집학년도입니다.",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="CareerNet 현재 목록에 없는 대학을 비활성화합니다.",
        )

    def handle(self, *args, **options):
        self.stdout.write("1/4 CareerNet 대학정보 갱신")
        call_command(
            "sync_career_universities",
            apply=True,
            create_new=True,
            deactivate_missing=options["deactivate_missing"],
            per_page=100,
        )

        self.stdout.write("")
        self.stdout.write("2/4 대학명, 캠퍼스, 주소 표기 정리")
        call_command("normalize_university_data", apply=True)

        self.stdout.write("")
        self.stdout.write("3/4 ADIGA 전년도 입시결과 동기화")
        call_command(
            "sync_adiga_admissions",
            apply=True,
            limit=max(0, options["adiga_limit"]),
            university=options["university"],
            search_year=options["search_year"],
            delay=0.2,
            map_only=False,
        )

        self.stdout.write("")
        self.stdout.write("4/4 현재 모집학년도 수능최저 동기화")
        # 같은 searchSyr 화면에서 Q2는 전년도 입시결과, Q1은 현재 모집학년도
        # 전형별 주요사항을 제공한다. 예: searchSyr=2027 -> 2026 결과 + 2027 최저.
        call_command(
            "sync_adiga_csat_minimum",
            apply=True,
            year=max(0, options["search_year"]),
            university=options["university"],
            limit=max(0, options["adiga_limit"]),
            delay=0.2,
        )

        self.stdout.write(
            self.style.SUCCESS("대학정보, 입시결과, 수능최저 동기화를 완료했습니다.")
        )
