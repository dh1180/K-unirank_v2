from django.conf import settings


def analytics(request):
    """Expose GA4 config only on approved production hosts."""
    measurement_id = getattr(settings, "GA_MEASUREMENT_ID", "")
    allowed_hosts = set(getattr(settings, "GA_ALLOWED_HOSTS", []))

    try:
        host = request.get_host().split(":", 1)[0].lower()
    except Exception:
        host = ""

    enabled = bool(
        getattr(settings, "GA_ENABLED", False)
        and measurement_id
        and (not allowed_hosts or host in allowed_hosts)
    )

    return {
        "ga_enabled": enabled,
        "ga_measurement_id": measurement_id,
    }
