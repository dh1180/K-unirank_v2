from django.core.management.base import BaseCommand

from rankings.services import ensure_default_boards


class Command(BaseCommand):
    help = "기본 랭킹 보드를 생성합니다."

    def handle(self, *args, **options):
        boards = ensure_default_boards()
        self.stdout.write(self.style.SUCCESS(f"기본 랭킹 보드 {len(boards)}개를 확인했습니다."))
