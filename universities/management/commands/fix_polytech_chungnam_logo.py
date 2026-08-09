from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from universities.models import University


TARGET_NAME = "한국폴리텍 IV 대학 충남캠퍼스"

# 같은 IV 대학 캠퍼스의 기존 로고를 우선 사용한다.
PREFERRED_DONORS = (
    "한국폴리텍 IV 대학 대전캠퍼스",
    "한국폴리텍 IV 대학 아산캠퍼스",
    "한국폴리텍 IV 대학 청주캠퍼스",
    "한국폴리텍 IV 대학 홍성캠퍼스",
)


class Command(BaseCommand):
    help = (
        "한국폴리텍 IV 대학 충남캠퍼스에 같은 폴리텍 IV 대학의 기존 로고를 적용합니다. "
        "기본은 미리보기이며 --apply를 붙여야 실제 반영됩니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 logo_path를 반영합니다. 생략하면 롤백합니다.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        target = University.objects.filter(name=TARGET_NAME).first()
        if target is None:
            raise CommandError(
                f"대상 대학을 찾지 못했습니다: {TARGET_NAME}"
            )

        donor = self.find_donor(target)

        if donor is None:
            raise CommandError(
                "같은 한국폴리텍 계열에서 사용 가능한 logo_path를 찾지 못했습니다. "
                "기존 폴리텍 대학들의 logo_path를 먼저 확인해주세요."
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("[폴리텍 충남캠퍼스 로고 적용]"))
        self.stdout.write(
            f"대상: {target.name} (id={target.pk})"
        )
        self.stdout.write(
            f"기존 logo_path: {target.logo_path or '(없음)'}"
        )
        self.stdout.write(
            f"로고 제공 대학: {donor.name} (id={donor.pk})"
        )
        self.stdout.write(
            f"적용 logo_path: {donor.logo_path}"
        )

        if target.logo_path == donor.logo_path:
            self.stdout.write(
                self.style.SUCCESS(
                    "이미 동일한 폴리텍 로고가 적용되어 있습니다."
                )
            )
            return

        with transaction.atomic():
            target.logo_path = donor.logo_path
            target.save(update_fields=["logo_path", "updated_at"])

            if not apply_changes:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "미리보기 완료: 실제 DB 변경은 롤백했습니다."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "한국폴리텍 IV 대학 충남캠퍼스 로고 적용 완료."
                    )
                )

    def find_donor(self, target):
        # 1. 같은 IV 대학 캠퍼스를 우선.
        for name in PREFERRED_DONORS:
            donor = (
                University.objects.filter(
                    name=name,
                )
                .exclude(logo_path__isnull=True)
                .exclude(logo_path="")
                .first()
            )
            if donor:
                return donor

        # 2. 이름 표기 차이가 있더라도 같은 IV 대학 내 로고가 있으면 사용.
        donor = (
            University.objects.filter(
                name__icontains="한국폴리텍 IV 대학",
            )
            .exclude(pk=target.pk)
            .exclude(logo_path__isnull=True)
            .exclude(logo_path="")
            .order_by("name")
            .first()
        )
        if donor:
            return donor

        # 3. 마지막 fallback: 다른 한국폴리텍 대학에서 비어 있지 않은 공통 로고 사용.
        return (
            University.objects.filter(
                name__startswith="한국폴리텍",
            )
            .exclude(pk=target.pk)
            .exclude(logo_path__isnull=True)
            .exclude(logo_path="")
            .order_by("name")
            .first()
        )
