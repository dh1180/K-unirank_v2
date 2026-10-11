from datetime import datetime

from django.db.models import Count, Sum
from django.utils import timezone

from .models import SupportPledge


def current_support_month():
    """집계 기준: 실제 계좌이체일이 아닌 운영자의 확인 시각(KST)."""
    local_now = timezone.localtime(timezone.now())
    month_start = timezone.make_aware(
        datetime(local_now.year, local_now.month, 1),
        timezone.get_current_timezone(),
    )
    if local_now.month == 12:
        next_month = timezone.make_aware(
            datetime(local_now.year + 1, 1, 1),
            timezone.get_current_timezone(),
        )
    else:
        next_month = timezone.make_aware(
            datetime(local_now.year, local_now.month + 1, 1),
            timezone.get_current_timezone(),
        )
    return local_now.strftime("%Y년 %m월"), month_start, next_month


def monthly_support_leaders(limit=10):
    label, begin, end = current_support_month()
    leaders = list(
        SupportPledge.objects.filter(
            status=SupportPledge.Status.CONFIRMED,
            confirmed_at__gte=begin,
            confirmed_at__lt=end,
            university__is_active=True,
        )
        .values("university_id", "university__name")
        .annotate(total=Sum("amount"), confirmation_count=Count("id"))
        .order_by("-total", "-confirmation_count", "university__name")[:limit]
    )
    return label, leaders
