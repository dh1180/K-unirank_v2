import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from universities.models import University


class SupportPledge(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "입금 확인 대기"
        CONFIRMED = "CONFIRMED", "입금 확인"
        REJECTED = "REJECTED", "미확인/취소"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    university = models.ForeignKey(
        University, on_delete=models.PROTECT, related_name="support_pledges"
    )
    amount = models.PositiveIntegerField(
        "후원 금액(원)",
        validators=[MinValueValidator(1000), MaxValueValidator(1000000)],
    )
    depositor_name = models.CharField("입금자명(비공개)", max_length=40)
    status = models.CharField(
        "처리 상태", max_length=12, choices=Status.choices, default=Status.PENDING,
        db_index=True,
    )
    admin_note = models.TextField("운영자 메모(비공개)", blank=True)
    created_at = models.DateTimeField("신청 시각", auto_now_add=True)
    confirmed_at = models.DateTimeField("확인 시각", null=True, blank=True)

    class Meta:
        db_table = "support_pledges"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "confirmed_at"], name="support_status_month_idx"),
            models.Index(fields=["university", "status"], name="support_uni_status_idx"),
        ]

    def __str__(self):
        return f"{self.university.name} {self.amount:,}원 ({self.get_status_display()})"
