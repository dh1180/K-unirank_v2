from django.conf import settings
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .forms import SupportPledgeForm
from .models import SupportPledge
from .services import monthly_support_leaders


def transfers_enabled():
    return bool(
        getattr(settings, "SUPPORT_ACCEPTING_TRANSFERS", False)
        and getattr(settings, "SUPPORT_BANK_OWNER", "").strip()
    )


def bank_details():
    return {
        "bank_name": "우리은행",
        "bank_account": getattr(settings, "SUPPORT_BANK_ACCOUNT", ""),
        "bank_owner": getattr(settings, "SUPPORT_BANK_OWNER", ""),
        "bank_qr_url": getattr(settings, "SUPPORT_QR_IMAGE_URL", ""),
    }


@never_cache
@require_http_methods(["GET", "POST"])
def index(request):
    accepting = transfers_enabled()
    month_label, leaders = monthly_support_leaders()
    form = SupportPledgeForm(request.POST or None)

    if request.method == "POST":
        if not accepting:
            return HttpResponseForbidden("현재 후원 신청을 받고 있지 않습니다.")
        previous = request.session.get("support_last_submission", 0)
        if timezone.now().timestamp() - previous < 90:
            form.add_error(None, "신청은 90초에 한 번만 가능합니다.")
        elif form.is_valid():
            pledge = form.save(commit=False)
            pledge.status = SupportPledge.Status.PENDING
            pledge.save()
            request.session["support_last_submission"] = timezone.now().timestamp()
            return redirect("support:submitted", pledge_id=pledge.pk)

    context = {
        "form": form,
        "accepting": accepting,
        "month_label": month_label,
        "leaders": leaders,
        **(bank_details() if accepting else {}),
    }
    return render(request, "support/index.html", context)


@never_cache
@require_http_methods(["GET"])
def submitted(request, pledge_id):
    if not transfers_enabled():
        raise Http404()
    pledge = get_object_or_404(SupportPledge.objects.select_related("university"), pk=pledge_id)
    return render(request, "support/submitted.html", {
        "pledge": pledge,
        **bank_details(),
    })
