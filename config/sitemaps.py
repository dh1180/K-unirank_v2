from django.contrib.sitemaps import Sitemap
from django.db.models import Max
from django.urls import reverse

from admissions.models import RecruitmentUnit
from universities.models import University, UniversityIndicator
from universities.services.indicators import CORE_UNIVERSITY_INDICATORS


class StaticViewSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return [
            ("home", "daily", 1.0),
            ("universities:list", "weekly", 0.9),
            ("rankings:ranking_hub", "daily", 0.95),
            ("rankings:ranking_default", "daily", 0.9),
            ("admissions:compare", "daily", 0.95),
            ("admissions:ranking", "daily", 0.9),
        ]

    def location(self, item):
        return reverse(item[0])

    def changefreq(self, item):
        return item[1]

    def priority(self, item):
        return item[2]


class UniversitySitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return University.objects.filter(is_active=True).order_by("university_id")

    def location(self, obj):
        return reverse("universities:detail", args=[obj.pk])

    def lastmod(self, obj):
        return obj.updated_at


class UniversityAdmissionsSitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.95

    def items(self):
        return (
            University.objects.filter(
                is_active=True,
                admission_results__isnull=False,
            )
            .annotate(
                admission_lastmod=Max("admission_results__source__collected_at"),
            )
            .distinct()
            .order_by("university_id")
        )

    def location(self, obj):
        return reverse("admissions:university", args=[obj.pk])

    def lastmod(self, obj):
        return obj.admission_lastmod or obj.updated_at


class RecruitmentUnitSitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.85

    def items(self):
        return (
            RecruitmentUnit.objects.filter(
                is_active=True,
                university__is_active=True,
                admission_results__isnull=False,
            )
            .select_related("university")
            .annotate(
                admission_lastmod=Max("admission_results__source__collected_at"),
            )
            .distinct()
            .order_by("recruitment_unit_id")
        )

    def location(self, obj):
        return reverse("admissions:unit", args=[obj.pk])

    def lastmod(self, obj):
        return obj.admission_lastmod


class IndicatorRankingSitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.85

    def items(self):
        available_codes = set(
            UniversityIndicator.objects.filter(
                source="ACADEMYINFO",
                university__is_active=True,
                value__gt=0,
            ).values_list("indicator_code", flat=True)
        )
        return [
            spec
            for spec in CORE_UNIVERSITY_INDICATORS
            if spec["code"] in available_codes
        ]

    def location(self, item):
        return reverse("universities:indicator_ranking", args=[item["slug"]])


sitemaps = {
    "static": StaticViewSitemap,
    "universities": UniversitySitemap,
    "university_admissions": UniversityAdmissionsSitemap,
    "recruitment_units": RecruitmentUnitSitemap,
    "indicator_rankings": IndicatorRankingSitemap,
}
