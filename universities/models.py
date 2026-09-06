from django.db import models

from .services.university_normalizer import normalize_address, normalize_region


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

    @property
    def location_label(self):
        return normalize_region(self.region, self.address) or "지역 미상"

    @property
    def display_address(self):
        return normalize_address(self.address) or "주소 정보 없음"

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

    @property
    def location_label(self):
        return normalize_region(self.region, self.address) or self.university.location_label

    @property
    def display_address(self):
        return normalize_address(self.address) or self.university.display_address

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


class UniversityIndicator(models.Model):
    """대학알리미 등 공식 공시 출처의 대학 단위 연도별 지표."""

    indicator_id = models.BigAutoField(primary_key=True)

    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        related_name="official_indicators",
    )

    year = models.PositiveIntegerField()
    indicator_code = models.CharField(max_length=80)
    value = models.DecimalField(max_digits=18, decimal_places=4)
    unit = models.CharField(max_length=30, blank=True)

    source = models.CharField(max_length=50, default="ACADEMYINFO")
    source_url = models.URLField(max_length=1000, blank=True)
    source_label = models.CharField(max_length=200, blank=True)

    collected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "university_indicators"
        constraints = [
            models.UniqueConstraint(
                fields=["university", "year", "indicator_code", "source"],
                name="uq_uni_indicator_year_source",
            )
        ]
        indexes = [
            models.Index(
                fields=["university", "year"],
                name="uni_indicator_year_idx",
            ),
            models.Index(
                fields=["indicator_code", "year"],
                name="indicator_code_year_idx",
            ),
        ]

    def __str__(self):
        return f"{self.university.name} {self.year} {self.indicator_code}: {self.value}"
