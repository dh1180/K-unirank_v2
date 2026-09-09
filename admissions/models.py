from django.db import models
from django.utils import timezone

from universities.models import University, UniversityCampus


class RecruitmentUnit(models.Model):
    recruitment_unit_id = models.BigAutoField(primary_key=True)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="recruitment_units")
    campus = models.ForeignKey(UniversityCampus, on_delete=models.SET_NULL, null=True, blank=True, related_name="recruitment_units")
    name = models.CharField(max_length=200)
    college_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "recruitment_units"
        constraints = [
            models.UniqueConstraint(
                fields=["university", "campus", "name"],
                name="uq_recruitment_unit",
            )
        ]

    def __str__(self):
        return f"{self.university} - {self.name}"


class AdmissionSource(models.Model):
    SOURCE_CHOICES = [
        ("ADIGA", "대입정보포털 어디가"),
        ("PROCOLLEGE", "전문대학포털"),
        ("UNIVERSITY", "대학 입학처"),
        ("OTHER", "기타"),
    ]

    source_id = models.BigAutoField(primary_key=True)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="admission_sources")
    admission_year = models.PositiveIntegerField()
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    source_url = models.URLField(max_length=1000)
    document_title = models.CharField(max_length=300, blank=True)
    collected_at = models.DateTimeField(default=timezone.now)
    checksum = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "admission_sources"
        indexes = [models.Index(fields=["university", "admission_year"])]

    def __str__(self):
        return f"{self.university} {self.admission_year} {self.source_type}"


class AdmissionResult(models.Model):
    PHASE_CHOICES = [("SUSI", "수시"), ("JEONGSI", "정시")]

    result_id = models.BigAutoField(primary_key=True)
    source = models.ForeignKey(AdmissionSource, on_delete=models.PROTECT, related_name="results")
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="admission_results")
    recruitment_unit = models.ForeignKey(RecruitmentUnit, on_delete=models.PROTECT, related_name="admission_results")
    admission_year = models.PositiveIntegerField()
    admission_phase = models.CharField(max_length=10, choices=PHASE_CHOICES)
    selection_category = models.CharField(max_length=100, blank=True)
    selection_name = models.CharField(max_length=200, blank=True)
    recruitment_group = models.CharField(max_length=30, blank=True)
    recruitment_count = models.PositiveIntegerField(null=True, blank=True)
    applicant_count = models.PositiveIntegerField(null=True, blank=True)
    registered_count = models.PositiveIntegerField(null=True, blank=True)
    competition_rate = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    class Meta:
        db_table = "admission_results"
        indexes = [
            models.Index(fields=["university", "admission_year", "admission_phase"]),
            models.Index(fields=["selection_category"]),
        ]


class AdmissionRequirement(models.Model):
    """입시 결과와 분리해 보존하는 연도별 공식 지원 요건.

    수능최저는 전년도 결과표(Q2)가 아니라 해당 학년도 전형별 주요사항(Q1)에
    속하는 정보라 AdmissionResult와 별도 엔터티로 관리한다.
    """

    REQUIREMENT_CHOICES = [
        ("CSAT_MINIMUM", "수능최저학력기준"),
    ]

    requirement_id = models.BigAutoField(primary_key=True)
    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        related_name="admission_requirements",
    )
    admission_year = models.PositiveIntegerField()
    admission_phase = models.CharField(
        max_length=10,
        choices=AdmissionResult.PHASE_CHOICES,
        default="SUSI",
    )
    requirement_type = models.CharField(
        max_length=30,
        choices=REQUIREMENT_CHOICES,
        default="CSAT_MINIMUM",
    )
    selection_name = models.CharField(max_length=200, blank=True)
    recruitment_unit_name = models.CharField(max_length=300, blank=True)
    applied = models.BooleanField(null=True, blank=True)
    requirement_text = models.TextField()
    source_type = models.CharField(
        max_length=20,
        choices=AdmissionSource.SOURCE_CHOICES,
        default="ADIGA",
    )
    source_code = models.CharField(max_length=30, blank=True)
    source_url = models.URLField(max_length=1000)
    collected_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admission_requirements"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "university",
                    "admission_year",
                    "admission_phase",
                    "requirement_type",
                    "source_type",
                    "source_code",
                    "selection_name",
                    "recruitment_unit_name",
                ],
                name="uq_admission_requirement_scope",
            )
        ]
        indexes = [
            models.Index(
                fields=["university", "admission_year", "admission_phase"],
                name="admission_req_uni_year_idx",
            ),
            models.Index(
                fields=["requirement_type", "source_type"],
                name="admission_req_type_src_idx",
            ),
        ]

    def __str__(self):
        target = self.selection_name or self.recruitment_unit_name or "공통"
        return f"{self.university} {self.admission_year} {target} {self.get_requirement_type_display()}"


class AdmissionMetric(models.Model):
    metric_id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(AdmissionResult, on_delete=models.CASCADE, related_name="metrics")
    metric_code = models.CharField(max_length=100)
    unit = models.CharField(max_length=50, blank=True)
    value = models.DecimalField(max_digits=14, decimal_places=5)

    class Meta:
        db_table = "admission_metrics"
        constraints = [
            models.UniqueConstraint(
                fields=["result", "metric_code"],
                name="uq_result_metric_code",
            )
        ]
        indexes = [models.Index(fields=["metric_code"])]


class AdmissionAggregate(models.Model):
    METHOD_CHOICES = [
        ("SIMPLE_AVERAGE", "단순 평균"),
        ("WEIGHTED_BY_RECRUITMENT", "모집인원 가중평균"),
    ]

    aggregate_id = models.BigAutoField(primary_key=True)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="admission_aggregates")
    admission_year = models.PositiveIntegerField()
    admission_phase = models.CharField(max_length=10, choices=AdmissionResult.PHASE_CHOICES)
    selection_category = models.CharField(max_length=100, blank=True)
    metric_code = models.CharField(max_length=100)
    aggregation_method = models.CharField(max_length=30, choices=METHOD_CHOICES)
    value = models.DecimalField(max_digits=14, decimal_places=5)
    sample_count = models.PositiveIntegerField(default=0)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admission_aggregates"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "university",
                    "admission_year",
                    "admission_phase",
                    "selection_category",
                    "metric_code",
                    "aggregation_method",
                ],
                name="uq_admission_aggregate",
            )
        ]
