from django.conf import settings
from django.db import models

from admissions.models import RecruitmentUnit
from universities.models import University


class FavoriteUniversity(models.Model):
    favorite_university_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_universities",
    )
    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        related_name="favorited_by_users",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorite_universities"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "university"],
                name="uq_user_favorite_university",
            )
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["university"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.university}"


class FavoriteRecruitmentUnit(models.Model):
    """사용자가 관심 등록한 입시 모집단위.

    현재 입시 원본의 기준 엔터티인 RecruitmentUnit을 직접 참조한다.
    향후 별도 학과 마스터가 도입되더라도 이 모델을 마이그레이션할 수 있도록
    관심 데이터 자체는 users 앱에서 관리한다.
    """

    favorite_recruitment_unit_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_recruitment_units",
    )
    recruitment_unit = models.ForeignKey(
        RecruitmentUnit,
        on_delete=models.CASCADE,
        related_name="favorited_by_users",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorite_recruitment_units"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "recruitment_unit"],
                name="uq_user_favorite_recruitment_unit",
            )
        ]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["recruitment_unit"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.recruitment_unit}"
