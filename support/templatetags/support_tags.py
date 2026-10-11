from django import template
from django.conf import settings

from support.services import monthly_support_leaders

register = template.Library()


@register.inclusion_tag("support/_home_banner.html")
def support_home_banner():
    enabled = bool(
        getattr(settings, "SUPPORT_ACCEPTING_TRANSFERS", False)
        and getattr(settings, "SUPPORT_BANK_OWNER", "").strip()
    )
    if not enabled:
        return {"enabled": False}
    _, leaders = monthly_support_leaders(limit=1)
    return {"enabled": True, "leader": leaders[0] if leaders else None}
