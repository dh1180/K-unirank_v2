from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("admissions", "0002_alter_admissionsource_source_type"),
        ("universities", "0004_load_academyinfo_core_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmissionRequirement",
            fields=[
                ("requirement_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("admission_year", models.PositiveIntegerField()),
                (
                    "admission_phase",
                    models.CharField(
                        choices=[("SUSI", "수시"), ("JEONGSI", "정시")],
                        default="SUSI",
                        max_length=10,
                    ),
                ),
                (
                    "requirement_type",
                    models.CharField(
                        choices=[("CSAT_MINIMUM", "수능최저학력기준")],
                        default="CSAT_MINIMUM",
                        max_length=30,
                    ),
                ),
                ("selection_name", models.CharField(blank=True, max_length=200)),
                ("recruitment_unit_name", models.CharField(blank=True, max_length=300)),
                ("applied", models.BooleanField(blank=True, null=True)),
                ("requirement_text", models.TextField()),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("ADIGA", "대입정보포털 어디가"),
                            ("PROCOLLEGE", "전문대학포털"),
                            ("UNIVERSITY", "대학 입학처"),
                            ("OTHER", "기타"),
                        ],
                        default="ADIGA",
                        max_length=20,
                    ),
                ),
                ("source_code", models.CharField(blank=True, max_length=30)),
                ("source_url", models.URLField(max_length=1000)),
                ("collected_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "university",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="admission_requirements",
                        to="universities.university",
                    ),
                ),
            ],
            options={
                "db_table": "admission_requirements",
                "indexes": [
                    models.Index(
                        fields=["university", "admission_year", "admission_phase"],
                        name="admission_req_uni_year_idx",
                    ),
                    models.Index(
                        fields=["requirement_type", "source_type"],
                        name="admission_req_type_src_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "university",
                            "admission_year",
                            "admission_phase",
                            "requirement_type",
                            "source_type",
                            "source_code",
                            "selection_name",
                            "recruitment_unit_name",
                        ),
                        name="uq_admission_requirement_scope",
                    )
                ],
            },
        ),
    ]
