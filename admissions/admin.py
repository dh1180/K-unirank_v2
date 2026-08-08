from django.contrib import admin

from .models import AdmissionAggregate, AdmissionMetric, AdmissionResult, AdmissionSource, RecruitmentUnit


class AdmissionMetricInline(admin.TabularInline):
    model = AdmissionMetric
    extra = 0


@admin.register(AdmissionResult)
class AdmissionResultAdmin(admin.ModelAdmin):
    list_display = ("university", "admission_year", "admission_phase", "selection_category", "recruitment_unit", "competition_rate")
    list_filter = ("admission_year", "admission_phase", "selection_category")
    search_fields = ("university__name", "recruitment_unit__name", "selection_name")
    inlines = [AdmissionMetricInline]


admin.site.register(RecruitmentUnit)
admin.site.register(AdmissionSource)
admin.site.register(AdmissionAggregate)
