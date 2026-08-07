from django.db import models


class University(models.Model):
    university_id = models.BigAutoField(primary_key=True)

    name = models.CharField(max_length=150, unique=True)
    short_name = models.CharField(max_length=100, null=True, blank=True)

    address = models.CharField(max_length=255, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    university_type = models.CharField(max_length=100, null=True, blank=True)
    establishment_type = models.CharField(max_length=50, null=True, blank=True)

    homepage_url = models.URLField(max_length=500, null=True, blank=True)
    college_info_url = models.URLField(max_length=1000, null=True, blank=True)

    # 직접 정리한 기존 로고는 CareerNet 동기화에서도 유지한다.
    logo_path = models.CharField(max_length=255, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "universities"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["region"]),
        ]

    def __str__(self):
        return self.name


class UniversityCampus(models.Model):
    campus_id = models.BigAutoField(primary_key=True)

    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        related_name="campuses",
    )

    source = models.CharField(max_length=50)
    external_code = models.CharField(max_length=100)

    campus_name = models.CharField(max_length=150, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    homepage_url = models.URLField(max_length=500, null=True, blank=True)

    is_primary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "university_campuses"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_code"],
                name="uq_campus_source_code",
            )
        ]
        indexes = [
            models.Index(fields=["university"]),
        ]

    def __str__(self):
        return f"{self.university.name} - {self.campus_name or '본교'}"


class UniversityExternalMapping(models.Model):
    mapping_id = models.BigAutoField(primary_key=True)

    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        related_name="external_mappings",
    )

    campus = models.ForeignKey(
        UniversityCampus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_mappings",
    )

    source = models.CharField(max_length=50)
    external_code = models.CharField(max_length=100)
    external_name = models.CharField(max_length=200, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "university_external_mappings"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_code"],
                name="uq_external_source_code",
            )
        ]
        indexes = [
            models.Index(fields=["source", "external_code"]),
        ]

    def __str__(self):
        return f"{self.source}: {self.external_name or self.external_code}"
