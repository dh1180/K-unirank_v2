from django.contrib import admin

from .models import (
    ComparisonVote,
    PersonalResult,
    RankingBoard,
    RankingSnapshot,
    RankingSnapshotItem,
    UniversityRating,
    VoteSession,
)


@admin.register(RankingBoard)
class RankingBoardAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "display_order")
    list_editable = ("is_active", "display_order")


@admin.register(UniversityRating)
class UniversityRatingAdmin(admin.ModelAdmin):
    list_display = ("university", "board", "rating", "rating_deviation", "match_count", "win_count", "loss_count")
    list_filter = ("board",)
    search_fields = ("university__name",)
    ordering = ("board", "-rating")


@admin.register(ComparisonVote)
class ComparisonVoteAdmin(admin.ModelAdmin):
    list_display = ("vote_id", "board", "university_a", "university_b", "selected_university", "skipped", "created_at")
    list_filter = ("board", "skipped")
    search_fields = ("university_a__name", "university_b__name", "selected_university__name")
    readonly_fields = ("board", "session", "university_a", "university_b", "selected_university", "skipped", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(VoteSession)
admin.site.register(RankingSnapshot)
admin.site.register(RankingSnapshotItem)
admin.site.register(PersonalResult)
