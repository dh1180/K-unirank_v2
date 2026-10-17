from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AdmissionResult
from admissions.services.grade_cut_quality import (
    double_one_cut_result_ids,
)


class Command(BaseCommand):
    help = (
        "의치한약수 제외, 같은 입시결과의 학생부 50%와 70% 컷이 "
        "모두 정확히 1.0인 결과만 확인/정리합니다. 기본은 미리보기."
    )

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, help="특정 입학년도만 처리")
        parser.add_argument("--apply", action="store_true", help="DB 실제 삭제 및 대학 집계 재산출")
        parser.add_argument("--show", type=int, default=40, help="미리보기 표시 개수")

    def handle(self, *args, **options):
        qs = AdmissionResult.objects.filter(
            pk__in=double_one_cut_result_ids()
        ).select_related("university", "recruitment_unit", "source")
        if options["year"]:
            qs = qs.filter(admission_year=options["year"])
        qs = qs.order_by("admission_year", "university__name", "recruitment_unit__name", "pk")
        total = qs.count()

        self.stdout.write(f"정확히 50% 컷=1.0, 70% 컷=1.0인 비의치한약수 입시결과: {total}건")
        for item in qs[:max(0, options["show"])]:
            self.stdout.write(
                f"  result={item.pk} | {item.admission_year} | {item.university.name} | "
                f"{item.recruitment_unit.name} | {item.selection_category} / "
                f"{item.selection_name} | {item.source.source_type}"
            )
        if not options["apply"]:
            self.stdout.write("미리보기 모드: DB는 변경하지 않았습니다. 실제 삭제는 --apply 옵션으로 실행합니다.")
            return

        if not total:
            self.stdout.write("삭제할 결과가 없어 DB를 변경하지 않았습니다.")
            return

        # Transaction includes rebuilding aggregates so no stale 1.0 values
        # survive in ranking, university summaries or VS hover widgets.
        with transaction.atomic():
            deleted, details = qs.delete()
            self.stdout.write(f"입시결과 관련 레코드 삭제 완료: {deleted}건 (모델별 {details})")
            call_command(
                "recalculate_admission_aggregates",
                **({"year": options["year"]} if options["year"] else {}),
                stdout=self.stdout,
            )
        self.stdout.write(self.style.SUCCESS("정리 및 집계 재계산 완료"))
