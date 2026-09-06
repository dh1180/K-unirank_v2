from django.contrib import admin

from .models import (
    University,
    UniversityCampus,
    UniversityExternalMapping,
    UniversityIndicator,
)


class UniversityCampusInline(admin.TabularInline):
    model = UniversityCampus
    extra = 0


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = (
        "university_id",
        "name",
        "region",
        "university_type",
        "establishment_type",
        "is_active",
    )

    search_fields = (
        "name",
        "short_name",
        "address",
    )

    list_filter = (
        "region",
        "university_type",
        "establishment_type",
        "is_active",
    )

    ordering = ("name",)
    inlines = [UniversityCampusInline]


@admin.register(UniversityCampus)
class UniversityCampusAdmin(admin.ModelAdmin):
    list_display = (
        "campus_id",
        "university",
        "campus_name",
        "region",
        "source",
        "external_code",
        "is_primary",
    )

    search_fields = (
        "university__name",
        "campus_name",
        "address",
        "external_code",
    )

    list_filter = (
        "source",
        "region",
        "is_primary",
    )


@admin.register(UniversityExternalMapping)
class UniversityExternalMappingAdmin(admin.ModelAdmin):
    list_display = (
        "mapping_id",
        "university",
        "campus",
        "source",
        "external_code",
        "external_name",
    )

    search_fields = (
        "university__name",
        "external_name",
        "external_code",
    )

    list_filter = ("source",)


@admin.register(UniversityIndicator)
class UniversityIndicatorAdmin(admin.ModelAdmin):
    list_display = (
        "indicator_id",
        "university",
        "year",
        "indicator_code",
        "value",
        "unit",
        "source",
        "updated_at",
    )
    search_fields = (
        "university__name",
        "indicator_code",
        "source_label",
    )
    list_filter = (
        "year",
        "indicator_code",
        "source",
    )
    ordering = ("-year", "university__name", "indicator_code")
