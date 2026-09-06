# Generated manually for university official disclosure indicators.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("universities", "0002_remove_university_campus_name_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="UniversityIndicator",
            fields=[
                (
                    "indicator_id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("year", models.PositiveIntegerField()),
                ("indicator_code", models.CharField(max_length=80)),
                (
                    "value",
                    models.DecimalField(decimal_places=4, max_digits=18),
                ),
                ("unit", models.CharField(blank=True, max_length=30)),
                (
                    "source",
                    models.CharField(default="ACADEMYINFO", max_length=50),
                ),
                ("source_url", models.URLField(blank=True, max_length=1000)),
                ("source_label", models.CharField(blank=True, max_length=200)),
                ("collected_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "university",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="official_indicators",
                        to="universities.university",
                    ),
                ),
            ],
            options={
                "db_table": "university_indicators",
                "indexes": [
                    models.Index(
                        fields=["university", "year"],
                        name="uni_indicator_year_idx",
                    ),
                    models.Index(
                        fields=["indicator_code", "year"],
                        name="indicator_code_year_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "university",
                            "year",
                            "indicator_code",
                            "source",
                        ),
                        name="uq_uni_indicator_year_source",
                    )
                ],
            },
        )
    ]
