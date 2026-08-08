import re

from django.core.management.base import BaseCommand
from django.db import transaction

from admissions.models import AdmissionResult
from universities.models import University


# 독립적인 입시 단위로 유지해야 하는 이원화/분교 캠퍼스.
# 입시 결과가 아직 없더라도 자동 정리 대상에서 제외한다.
STANDALONE_CAMPUSES = {
    "건국대학교 글로컬캠퍼스",
    "고려대학교 세종캠퍼스",
    "동국대학교 WISE캠퍼스",
    "연세대학교 미래캠퍼스",
    "한양대학교 ERICA캠퍼스",
}

SANGMYUNG_ADDRESS = "서울특별시 종로구 홍지문 2길 20"
SANGMYUNG_REGION = "서울특별시"

CAMPUS_SUFFIX_RE = re.compile(
    r"^(?P<base>.+?)\s+(?P<campus>(?:제?\d+|[^\s]+)캠퍼스)$"
)


class Command(BaseCommand):
    help = (
        "입시 결과가 없는 중복 캠퍼스 University를 본교에 통합/비활성화하고 "
        "상명대학교 대표 주소를 서울캠퍼스로 정리합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 DB를 변경합니다. 생략하면 미리보기만 합니다.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        if not apply_changes:
            self.stdout.write(self.style.WARNING("미리보기 모드입니다. DB는 변경하지 않습니다."))

        candidates = self.find_duplicate_campuses()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("중복 캠퍼스 정리 대상"))

        if not candidates:
            self.stdout.write("정리할 캠퍼스가 없습니다.")
        else:
            for duplicate, base in candidates:
                self.stdout.write(
                    f"- {duplicate.name} -> {base.name} "
                    f"(입시결과 {duplicate.admission_results.count()}건)"
                )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("상명대학교 대표 주소"))
        sangmyung = University.objects.filter(name="상명대학교").first()
        if sangmyung:
            self.stdout.write(
                f"- 현재: {sangmyung.region or '-'} | {sangmyung.address or '-'}"
            )
            self.stdout.write(
                f"- 변경: {SANGMYUNG_REGION} | {SANGMYUNG_ADDRESS}"
            )
        else:
            self.stdout.write(self.style.WARNING("- 상명대학교 본교 레코드를 찾지 못했습니다."))

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write("적용하려면 --apply 를 붙여 다시 실행하세요.")
            return

        with transaction.atomic():
            for duplicate, base in candidates:
                self.merge_campus_metadata(duplicate, base)
                duplicate.is_active = False
                duplicate.save(update_fields=["is_active", "updated_at"])

            if sangmyung:
                sangmyung.region = SANGMYUNG_REGION
                sangmyung.address = SANGMYUNG_ADDRESS
                sangmyung.save(update_fields=["region", "address", "updated_at"])

                # 서울 캠퍼스를 대표 캠퍼스로 표시한다.
                for campus in sangmyung.campuses.all():
                    address = (campus.address or "").strip()
                    should_be_primary = address.startswith("서울")
                    if campus.is_primary != should_be_primary:
                        campus.is_primary = should_be_primary
                        campus.save(update_fields=["is_primary", "updated_at"])

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"완료: 중복 캠퍼스 {len(candidates)}개 비활성화, "
                "상명대학교 대표 주소를 서울캠퍼스로 정리했습니다."
            )
        )

    def find_duplicate_campuses(self):
        candidates = []

        for university in University.objects.filter(is_active=True).order_by("name"):
            if university.name in STANDALONE_CAMPUSES:
                continue
            if university.name.startswith("한국폴리텍"):
                continue
            if AdmissionResult.objects.filter(university=university).exists():
                continue

            match = CAMPUS_SUFFIX_RE.match(university.name)
            if not match:
                continue

            base_name = match.group("base").strip()
            base = (
                University.objects.filter(name=base_name, is_active=True)
                .exclude(pk=university.pk)
                .first()
            )
            if not base:
                continue

            candidates.append((university, base))

        return candidates

    def merge_campus_metadata(self, duplicate, base):
        # 캠퍼스 원본 정보와 외부 매핑은 본교 쪽으로 옮겨 재동기화 시에도 추적 가능하게 한다.
        duplicate.campuses.update(university=base)
        duplicate.external_mappings.update(university=base)
