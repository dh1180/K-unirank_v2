from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "사용 중단: K-unirank는 더 이상 운영자 초기 랭킹 시드를 사용하지 않습니다."

    def add_arguments(self, parser):
        # 과거 배포 스크립트가 옵션을 전달해도 에러 대신 안내만 하도록 호환 유지.
        parser.add_argument("--board", default="overall")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--include-all", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "초기 시드 기능은 비활성화되었습니다. "
                "모든 대학은 1500점에서 시작하며 실제 사용자 VS만 반영됩니다."
            )
        )
