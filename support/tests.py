from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from universities.models import University

from .models import SupportPledge
from .services import monthly_support_leaders


class SupportTests(TestCase):
    def setUp(self):
        self.first = University.objects.create(name="한빛대학교")
        self.second = University.objects.create(name="바다대학교")
        cache.clear()

    @override_settings(SUPPORT_ACCEPTING_TRANSFERS=False)
    def test_disabled_page_does_not_publish_account_or_accept_application(self):
        response = self.client.get(reverse("support:index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "1002863490240")
        response = self.client.post(reverse("support:index"), {
            "university": self.first.pk, "amount": 5000, "depositor_name": "테스트",
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SupportPledge.objects.count(), 0)

    @override_settings(
        SUPPORT_ACCEPTING_TRANSFERS=True, SUPPORT_BANK_OWNER="테스트예금주",
        SUPPORT_BANK_ACCOUNT="1002863490240",
    )
    def test_application_requires_manual_confirmation(self):
        response = self.client.post(reverse("support:index"), {
            "university": self.first.pk, "amount": 5000, "depositor_name": "입금자",
        })
        self.assertEqual(response.status_code, 302)
        pledge = SupportPledge.objects.get()
        self.assertEqual(pledge.status, SupportPledge.Status.PENDING)
        _, leaders = monthly_support_leaders()
        self.assertEqual(leaders, [])
        receipt = self.client.get(response["Location"])
        self.assertContains(receipt, "1002863490240")
        self.assertNotContains(receipt, "입금자")

    @override_settings(
        SUPPORT_ACCEPTING_TRANSFERS=True, SUPPORT_BANK_OWNER="테스트예금주",
    )
    def test_invalid_amount_and_honeypot_rejected(self):
        data = {"university": self.first.pk, "depositor_name": "입금자", "amount": 0}
        response = self.client.post(reverse("support:index"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SupportPledge.objects.count(), 0)
        data["amount"] = 5000
        data["website"] = "bot.example"
        response = self.client.post(reverse("support:index"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SupportPledge.objects.count(), 0)

    def test_only_confirmed_pledges_are_ranked(self):
        SupportPledge.objects.create(
            university=self.first, amount=100000, depositor_name="미입금",
        )
        SupportPledge.objects.create(
            university=self.first, amount=5000, depositor_name="실입금",
            status=SupportPledge.Status.CONFIRMED, confirmed_at=timezone.now(),
        )
        SupportPledge.objects.create(
            university=self.second, amount=3000, depositor_name="실입금",
            status=SupportPledge.Status.CONFIRMED, confirmed_at=timezone.now(),
        )
        _, leaders = monthly_support_leaders()
        self.assertEqual([p["university__name"] for p in leaders], ["한빛대학교", "바다대학교"])
        self.assertEqual(leaders[0]["total"], 5000)
        self.assertEqual(leaders[0]["confirmation_count"], 1)

    def test_previous_month_pledge_is_excluded(self):
        SupportPledge.objects.create(
            university=self.first, amount=12000, depositor_name="실입금",
            status=SupportPledge.Status.CONFIRMED,
            confirmed_at=timezone.now() - timedelta(days=40),
        )
        _, leaders = monthly_support_leaders()
        self.assertEqual(leaders, [])

    def test_admin_confirmation_sets_timestamp(self):
        admin = get_user_model().objects.create_superuser(
            username="support_admin", email="admin@example.com", password="secret-pass-123"
        )
        pledge = SupportPledge.objects.create(
            university=self.first, amount=5000, depositor_name="후원자",
        )
        self.client.force_login(admin)
        url = reverse("admin:support_supportpledge_changelist")
        response = self.client.post(url, {
            "action": "mark_confirmed", "_selected_action": [str(pledge.pk)],
        })
        self.assertEqual(response.status_code, 302)
        pledge.refresh_from_db()
        self.assertEqual(pledge.status, SupportPledge.Status.CONFIRMED)
        self.assertIsNotNone(pledge.confirmed_at)

    @override_settings(
        SUPPORT_ACCEPTING_TRANSFERS=True, SUPPORT_BANK_OWNER="테스트예금주",
        SUPPORT_QR_IMAGE_URL="/static/support/payment-qr.png",
    )
    def test_bank_qr_is_optional_and_home_banner_uses_confirmed_rank(self):
        pledge = SupportPledge.objects.create(
            university=self.first, amount=8000, depositor_name="후원자",
            status=SupportPledge.Status.CONFIRMED, confirmed_at=timezone.now(),
        )
        response = self.client.get(reverse("support:index"))
        self.assertContains(response, "/static/support/payment-qr.png")
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "이번 달 대학 응원 1위")
        self.assertContains(home, self.first.name)

    @override_settings(
        SUPPORT_ACCEPTING_TRANSFERS=True,
        SUPPORT_BANK_OWNER="테스트예금주",
        SUPPORT_QR_IMAGE_URL="",
        SUPPORT_BANK_ACCOUNT="1002863490240",
    )
    def test_uploaded_toss_qr_is_default_for_support_and_receipt(self):
        get_response = self.client.get(reverse("support:index"))
        self.assertContains(get_response, "support/payment-qr.png")
        self.assertContains(get_response, "토스 송금 QR")
        post_response = self.client.post(reverse("support:index"), {
            "university": self.first.pk, "amount": 5000, "depositor_name": "입금자",
        })
        self.assertEqual(post_response.status_code, 302)
        receipt = self.client.get(post_response["Location"])
        self.assertContains(receipt, "support/payment-qr.png")
        self.assertContains(receipt, "1002863490240")

    def test_header_support_link_is_visible_to_unauthenticated_users(self):
        response = self.client.get(reverse("support:index"))
        self.assertContains(response, 'href="/support/"')
        self.assertContains(response, 'nav-support-link')
