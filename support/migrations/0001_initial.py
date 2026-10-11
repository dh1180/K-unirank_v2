import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("universities", "0004_load_academyinfo_core_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportPledge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount", models.PositiveIntegerField(
                    verbose_name="후원 금액(원)",
                    validators=[
                        django.core.validators.MinValueValidator(1000),
                        django.core.validators.MaxValueValidator(1000000),
                    ],
                )),
                ("depositor_name", models.CharField(max_length=40, verbose_name="입금자명(비공개)")),
                ("status", models.CharField(
                    choices=[
                        ("PENDING", "입금 확인 대기"),
                        ("CONFIRMED", "입금 확인"),
                        ("REJECTED", "미확인/취소"),
                    ],
                    db_index=True, default="PENDING", max_length=12, verbose_name="처리 상태",
                )),
                ("admin_note", models.TextField(blank=True, verbose_name="운영자 메모(비공개)")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="신청 시각")),
                ("confirmed_at", models.DateTimeField(blank=True, null=True, verbose_name="확인 시각")),
                ("university", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="support_pledges", to="universities.university",
                )),
            ],
            options={
                "db_table": "support_pledges",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="supportpledge",
            index=models.Index(fields=["status", "confirmed_at"], name="support_status_month_idx"),
        ),
        migrations.AddIndex(
            model_name="supportpledge",
            index=models.Index(fields=["university", "status"], name="support_uni_status_idx"),
        ),
    ]
