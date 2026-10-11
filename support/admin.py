from django.contrib import admin, messages
from django.utils import timezone

from .models import SupportPledge


@admin.register(SupportPledge)
class SupportPledgeAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "university", "amount", "depositor_name",
        "status", "confirmed_at",
    )
    list_filter = ("status", "created_at", "university")
    search_fields = ("university__name", "depositor_name", "admin_note")
    readonly_fields = ("id", "created_at", "confirmed_at")
    ordering = ("-created_at",)
    actions = ["mark_confirmed", "mark_rejected"]

    @admin.action(description="실제 은행 입금 확인 후 승인 (선택 항목)")
    def mark_confirmed(self, request, queryset):
        updated = queryset.exclude(status=SupportPledge.Status.CONFIRMED).update(
            status=SupportPledge.Status.CONFIRMED,
            confirmed_at=timezone.now(),
        )
        self.message_user(request, f"{updated}건을 입금 확인 처리했습니다.", messages.SUCCESS)

    @admin.action(description="미확인·취소 처리 (선택 항목)")
    def mark_rejected(self, request, queryset):
        updated = queryset.update(
            status=SupportPledge.Status.REJECTED, confirmed_at=None,
        )
        self.message_user(request, f"{updated}건을 미확인 처리했습니다.", messages.WARNING)

    def save_model(self, request, obj, form, change):
        if obj.status == SupportPledge.Status.CONFIRMED:
            if not obj.confirmed_at:
                obj.confirmed_at = timezone.now()
        else:
            obj.confirmed_at = None
        super().save_model(request, obj, form, change)
