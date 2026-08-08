import uuid

from django.conf import settings
from django.db import models

from universities.models import University


class RankingBoard(models.Model):
    board_id = models.BigAutoField(primary_key=True)
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ranking_boards"
        ordering = ["display_order", "board_id"]

    def __str__(self):
        return self.name


class VoteSession(models.Model):
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kunirank_vote_sessions",
    )
    session_key = models.CharField(max_length=64, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    vote_count = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vote_sessions"
        indexes = [models.Index(fields=["session_key", "last_seen_at"])]

    def __str__(self):
        return str(self.session_id)


class ComparisonVote(models.Model):
    vote_id = models.BigAutoField(primary_key=True)
    board = models.ForeignKey(RankingBoard, on_delete=models.PROTECT, related_name="votes")
    session = models.ForeignKey(VoteSession, on_delete=models.PROTECT, related_name="votes")
    university_a = models.ForeignKey(
        University,
        on_delete=models.PROTECT,
        related_name="votes_as_a",
    )
    university_b = models.ForeignKey(
        University,
        on_delete=models.PROTECT,
        related_name="votes_as_b",
    )
    selected_university = models.ForeignKey(
        University,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="selected_votes",
    )
    skipped = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comparison_votes"
        ordering = ["vote_id"]
        indexes = [
            models.Index(fields=["board", "created_at"]),
            models.Index(fields=["session", "created_at"]),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.university_a_id == self.university_b_id:
            raise ValidationError("같은 대학끼리는 비교할 수 없습니다.")

        pair = {self.university_a_id, self.university_b_id}

        if self.skipped and self.selected_university_id is not None:
            raise ValidationError("건너뛰기 투표에는 선택 대학이 없어야 합니다.")

        if not self.skipped and self.selected_university_id not in pair:
            raise ValidationError("선택 대학은 비교 대상 중 하나여야 합니다.")

    def __str__(self):
        return f"{self.university_a} vs {self.university_b}"


class UniversityRating(models.Model):
    rating_id = models.BigAutoField(primary_key=True)
    board = models.ForeignKey(RankingBoard, on_delete=models.CASCADE, related_name="ratings")
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="ratings")
    rating = models.FloatField(default=1500.0)
    rating_deviation = models.FloatField(default=350.0)
    volatility = models.FloatField(default=0.06)
    match_count = models.PositiveBigIntegerField(default=0)
    win_count = models.PositiveBigIntegerField(default=0)
    loss_count = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "university_ratings"
        constraints = [
            models.UniqueConstraint(
                fields=["board", "university"],
                name="uq_rating_board_university",
            )
        ]
        indexes = [
            models.Index(fields=["board", "rating"]),
            models.Index(fields=["board", "match_count"]),
        ]

    def __str__(self):
        return f"{self.board}: {self.university} {self.rating:.1f}"


class RankingSnapshot(models.Model):
    snapshot_id = models.BigAutoField(primary_key=True)
    board = models.ForeignKey(RankingBoard, on_delete=models.CASCADE, related_name="snapshots")
    snapshot_date = models.DateField()
    total_votes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ranking_snapshots"
        constraints = [
            models.UniqueConstraint(
                fields=["board", "snapshot_date"],
                name="uq_snapshot_board_date",
            )
        ]
        ordering = ["-snapshot_date"]


class RankingSnapshotItem(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    snapshot = models.ForeignKey(RankingSnapshot, on_delete=models.CASCADE, related_name="items")
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="ranking_snapshot_items")
    rank = models.PositiveIntegerField()
    rating = models.FloatField()
    match_count = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = "ranking_snapshot_items"
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "university"],
                name="uq_snapshot_university",
            ),
            models.UniqueConstraint(
                fields=["snapshot", "rank"],
                name="uq_snapshot_rank",
            ),
        ]
        ordering = ["rank"]


class PersonalResult(models.Model):
    result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(VoteSession, on_delete=models.CASCADE, related_name="personal_results")
    board = models.ForeignKey(RankingBoard, on_delete=models.CASCADE, related_name="personal_results")
    vote_count = models.PositiveIntegerField(default=0)
    result_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "personal_results"
        ordering = ["-created_at"]
