import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from universities.models import (
    University,
    UniversityCampus,
    UniversityExternalMapping,
)
from universities.services.university_normalizer import (
    campus_label_from_name,
    canonical_university_name,
    ranking_university_name,
    is_excluded_university,
    normalize_address,
    normalize_region,
)


LEGACY_SOURCE = "LEGACY_SQLITE"


class Command(BaseCommand):
    help = "기존 SQLite의 대학 데이터를 현재 랭킹 단위 기준으로 이전합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--legacy-db",
            required=True,
            help="기존 SQLite DB 파일 경로",
        )

        parser.add_argument(
            "--legacy-media",
            required=False,
            help="기존 media 디렉터리 경로",
        )

    def handle(self, *args, **options):
        legacy_db = Path(options["legacy_db"]).resolve()
        legacy_media = (
            Path(options["legacy_media"]).resolve()
            if options.get("legacy_media")
            else None
        )

        if not legacy_db.exists():
            raise CommandError(f"SQLite DB를 찾을 수 없습니다: {legacy_db}")

        if legacy_media and not legacy_media.exists():
            raise CommandError(f"media 폴더를 찾을 수 없습니다: {legacy_media}")

        rows = self.read_legacy_rows(legacy_db)
        groups = defaultdict(list)
        skipped = 0

        for row in rows:
            raw_name = (row["school_name"] or "").strip()

            if not raw_name or is_excluded_university(raw_name):
                skipped += 1
                continue

            canonical_name = ranking_university_name(
                raw_name,
                address=row["school_address"],
            )
            groups[canonical_name].append(row)

        logo_destination = (
            settings.BASE_DIR / "static" / "university" / "logos"
        )
        logo_destination.mkdir(parents=True, exist_ok=True)

        created_count = 0
        updated_count = 0
        campus_count = 0
        copied_count = 0
        missing_count = 0

        with transaction.atomic():
            for canonical_name, group_rows in sorted(groups.items()):
                representative = self.pick_representative(
                    canonical_name,
                    group_rows,
                )

                logo_path = self.build_logo_path(
                    representative["school_image"]
                )

                representative_address = normalize_address(
                    representative["school_address"]
                )

                university, created = University.objects.update_or_create(
                    name=canonical_name,
                    defaults={
                        "address": representative_address,
                        "region": normalize_region(address=representative_address),
                        "logo_path": logo_path,
                        "is_active": True,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                for row in group_rows:
                    raw_name = (row["school_name"] or "").strip()
                    legacy_id = str(row["id"])

                    campus_name = campus_label_from_name(
                        raw_name,
                        canonical_name,
                    )

                    campus, _ = UniversityCampus.objects.update_or_create(
                        source=LEGACY_SOURCE,
                        external_code=legacy_id,
                        defaults={
                            "university": university,
                            "campus_name": campus_name,
                            "address": normalize_address(row["school_address"]),
                            "region": normalize_region(address=row["school_address"]),
                            "is_primary": raw_name == canonical_name,
                        },
                    )

                    UniversityExternalMapping.objects.update_or_create(
                        source=LEGACY_SOURCE,
                        external_code=legacy_id,
                        defaults={
                            "university": university,
                            "campus": campus,
                            "external_name": raw_name,
                        },
                    )

                    campus_count += 1

                    if legacy_media and row["school_image"]:
                        source_file = legacy_media / row["school_image"]
                        destination_file = (
                            logo_destination
                            / Path(row["school_image"]).name
                        )

                        if source_file.exists():
                            shutil.copy2(source_file, destination_file)
                            copied_count += 1
                        else:
                            missing_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"완료: 대학 {len(groups)}개, 신규 {created_count}, "
                f"갱신 {updated_count}, 캠퍼스 기록 {campus_count}, "
                f"제외 {skipped}, 로고 복사 {copied_count}, "
                f"로고 누락 {missing_count}"
            )
        )

    def read_legacy_rows(self, legacy_db):
        connection = sqlite3.connect(legacy_db)
        connection.row_factory = sqlite3.Row

        try:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'vote_school'
                """
            )

            if cursor.fetchone() is None:
                raise CommandError(
                    "기존 DB에서 vote_school 테이블을 찾지 못했습니다."
                )

            cursor.execute(
                """
                SELECT
                    id,
                    school_name,
                    school_image,
                    school_address
                FROM vote_school
                ORDER BY id
                """
            )

            return cursor.fetchall()
        finally:
            connection.close()

    def pick_representative(self, canonical_name, rows):
        exact_rows = [
            row
            for row in rows
            if (row["school_name"] or "").strip() == canonical_name
        ]

        if exact_rows:
            return exact_rows[0]

        return min(
            rows,
            key=lambda row: len((row["school_name"] or "").strip()),
        )

    def build_logo_path(self, school_image):
        if not school_image:
            return None

        return f"university/logos/{Path(school_image).name}"
