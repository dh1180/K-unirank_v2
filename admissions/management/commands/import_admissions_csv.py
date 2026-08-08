import csv
import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from admissions.models import AdmissionMetric, AdmissionResult, AdmissionSource, RecruitmentUnit
from universities.models import University


BASE_COLUMNS = {
    "university_name",
    "admission_year",
    "admission_phase",
    "recruitment_unit",
    "selection_category",
    "selection_name",
    "recruitment_group",
    "recruitment_count",
    "applicant_count",
    "registered_count",
    "competition_rate",
}


class Command(BaseCommand):
    help = "출처가 확인된 입시결과 CSV를 가져옵니다. metric_ 접두사 컬럼은 AdmissionMetric으로 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--source-url", required=True)
        parser.add_argument("--source-type", choices=["ADIGA", "UNIVERSITY", "OTHER"], default="ADIGA")
        parser.add_argument("--document-title", default="")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"파일을 찾을 수 없습니다: {path}")

        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        created = 0

        with path.open("r", encoding="utf-8-sig", newline="") as f, transaction.atomic():
            reader = csv.DictReader(f)
            if not reader.fieldnames or not BASE_COLUMNS.issubset(set(reader.fieldnames)):
                missing = BASE_COLUMNS - set(reader.fieldnames or [])
                raise CommandError(f"필수 컬럼이 없습니다: {sorted(missing)}")

            metric_columns = [name for name in reader.fieldnames if name.startswith("metric_")]

            source_cache = {}
            for row in reader:
                university = University.objects.filter(name=row["university_name"].strip()).first()
                if not university:
                    raise CommandError(f"대학을 찾을 수 없습니다: {row['university_name']}")

                year = int(row["admission_year"])
                source_key = (university.pk, year)
                source = source_cache.get(source_key)
                if source is None:
                    source, _ = AdmissionSource.objects.get_or_create(
                        university=university,
                        admission_year=year,
                        source_type=options["source_type"],
                        source_url=options["source_url"],
                        checksum=checksum,
                        defaults={"document_title": options["document_title"]},
                    )
                    source_cache[source_key] = source

                unit, _ = RecruitmentUnit.objects.get_or_create(
                    university=university,
                    campus=None,
                    name=row["recruitment_unit"].strip(),
                )

                result = AdmissionResult.objects.create(
                    source=source,
                    university=university,
                    recruitment_unit=unit,
                    admission_year=year,
                    admission_phase=row["admission_phase"].strip().upper(),
                    selection_category=row["selection_category"].strip(),
                    selection_name=row["selection_name"].strip(),
                    recruitment_group=row["recruitment_group"].strip(),
                    recruitment_count=self.to_int(row["recruitment_count"]),
                    applicant_count=self.to_int(row["applicant_count"]),
                    registered_count=self.to_int(row["registered_count"]),
                    competition_rate=self.to_decimal(row["competition_rate"]),
                )

                for column in metric_columns:
                    value = self.to_decimal(row.get(column))
                    if value is None:
                        continue
                    AdmissionMetric.objects.create(
                        result=result,
                        metric_code=column.removeprefix("metric_").upper(),
                        value=value,
                    )

                created += 1

        self.stdout.write(self.style.SUCCESS(f"입시결과 {created}건을 가져왔습니다."))

    def to_int(self, value):
        value = (value or "").strip()
        return int(value) if value else None

    def to_decimal(self, value):
        value = (value or "").strip()
        if not value:
            return None
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise CommandError(f"숫자 형식이 아닙니다: {value}") from exc
