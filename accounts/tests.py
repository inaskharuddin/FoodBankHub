from django.test import TestCase, override_settings
from django.core import mail
from django.urls import reverse

from .models import Supplier, User
from .models import Needy, Provider
from distribution.models import ServiceArea, AllowanceUsage, Report
from inventory.models import Inventory, Item
from distribution.models import ProviderSupplier
from forecasting.models import Forecast

# Create your tests here.


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="foodbankhub@example.test",
)
class SupplierApprovalEmailTests(TestCase):
    def test_admin_approval_activates_supplier_and_emails_supplier(self):
        admin = User.objects.create_user(
            email="admin@example.test", name="Admin", password="test-pass", role="ADMIN",
        )
        supplier_user = User.objects.create_user(
            email="supplier@example.test", name="Supplier", password="test-pass",
            role="SUPPLIER", is_active=False, status="INACTIVE",
        )
        supplier = Supplier.objects.create(
            user=supplier_user, business_name="Fresh Food Co", ssm_registration_no="BR-1",
            contact_person="Sam Supplier", phone="0100", bank_account="123",
            bank_name="Example Bank", is_approved=False,
        )
        self.client.force_login(admin)

        approval_url = reverse("approve_supplier", args=[supplier.supplier_id])
        response = self.client.post(approval_url)
        self.assertRedirects(response, reverse("admin_user_detail", args=[supplier.user_id]))
        supplier.refresh_from_db()
        self.assertFalse(supplier.is_approved)
        self.assertEqual(len(mail.outbox), 0)

        response = self.client.post(approval_url, {"documents_reviewed": "on"})

        self.assertRedirects(response, reverse("admin_user_directory"))
        supplier.refresh_from_db()
        supplier_user.refresh_from_db()
        self.assertTrue(supplier.is_approved)
        self.assertIsNotNone(supplier.approved_at)
        self.assertIsNotNone(supplier.documents_reviewed_at)
        self.assertEqual(supplier.documents_reviewed_by, admin)
        self.assertTrue(supplier_user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [supplier_user.email])
        self.assertIn("has been approved", mail.outbox[0].body)


class NeedyPortalPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="needy-ui@example.test", name="Amina Needy", password="test-pass", role="NEEDY",
        )
        Needy.objects.create(
            user=self.user, phone="0100", address="12 Garden Road",
            postcode="43000", city="Shah Alam", state="Selangor",
        )
        provider_user = User.objects.create_user(
            email="provider-ui@example.test", name="Bank User", password="test-pass", role="PROVIDER",
        )
        provider = Provider.objects.create(
            user=provider_user, food_bank_name="Garden Food Bank", phone="0110",
            address="1 Market Street", operating_hours="Mon–Fri, 9am–5pm",
        )
        ServiceArea.objects.create(provider=provider, postcode="43000", zone_name="Shah Alam")
        item = Item.objects.create(name="Rice", category="Grain", unit="kg")
        Inventory.objects.create(provider=provider, item=item, quantity=12)
        self.client.force_login(self.user)

    def test_needy_dashboard_scan_history_and_provider_finder_render(self):
        cases = (
            ("needy_dashboard", "Your registered address"),
            ("needy_scan", "Scan the food bank QR"),
            ("needy_history", "Collection history"),
            ("needy_provider_finder", "Garden Food Bank"),
        )
        for route, expected in cases:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="foodbankhub@example.test",
)
class AdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="platform-admin@example.test", name="Platform Admin", password="test-pass", role="ADMIN")
        provider_user = User.objects.create_user(email="admin-provider@example.test", name="Provider user", password="test-pass", role="PROVIDER")
        self.provider = Provider.objects.create(user=provider_user, food_bank_name="Admin Test Bank", phone="0100", address="Street", operating_hours="Daily")
        supplier_user = User.objects.create_user(email="admin-supplier@example.test", name="Supplier user", password="test-pass", role="SUPPLIER", is_active=False, status="INACTIVE")
        self.supplier = Supplier.objects.create(user=supplier_user, business_name="Admin Test Supplier", ssm_registration_no="SSM-A", contact_person="Contact", phone="0101", bank_account="111", bank_name="Bank", is_approved=False)
        self.donor = User.objects.create_user(email="admin-donor@example.test", name="Admin Donor", password="test-pass", role="DONOR")

    def test_dashboard_is_admin_only_and_shows_platform_metrics(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Test Bank")
        self.assertNotContains(response, "Admin Test Supplier")
        self.assertNotContains(response, "Admin Donor")
        self.assertNotContains(response, "Supplier panels")
        self.assertContains(response, "Approval")
        self.assertNotContains(response, "Supplier applications")
        self.assertNotContains(response, "Provider applications")
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 302)
        self.assertEqual(self.client.get(reverse("admin_approvals")).status_code, 302)

    def test_approval_page_contains_supplier_and_provider_application_tables(self):
        self.provider.is_approved = False
        self.provider.save(update_fields=["is_approved"])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_approvals"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supplier applications")
        self.assertContains(response, "Admin Test Supplier")
        self.assertContains(response, "Provider applications")
        self.assertContains(response, "Admin Test Bank")

    def test_admin_analytics_calculates_donation_fee_revenue_and_period_chart(self):
        from decimal import Decimal
        from donations.models import Cart, Donation
        from django.utils import timezone
        from orders.models import Payout, PurchaseOrder
        cart = Cart.objects.create(donor=self.donor, total_amount=Decimal("100.00"), status="COMPLETED")
        Donation.objects.create(donor=self.donor, cart=cart, total_amount=Decimal("100.00"), status="PAID")
        self.provider.address = "Shah Alam, Selangor"
        self.provider.save(update_fields=["address"])
        order = PurchaseOrder.objects.create(provider=self.provider, supplier=self.supplier, total_amount=Decimal("50.00"), status="DELIVERED")
        Payout.objects.create(supplier=self.supplier, po=order, amount=Decimal("50.00"), status="PAID", transfer_reference="BANK-50")
        needy_user = User.objects.create_user(email="analytics-needy@example.test", name="Analytics Needy", password="test-pass", role="NEEDY")
        needy = Needy.objects.create(user=needy_user, phone="01999", address="Test address", postcode="43000", city="Shah Alam", state="Selangor")
        item = Item.objects.create(name="Analytics Rice", category="Grain", unit="kg")
        for quantity in (1, 2):
            Report.objects.create(needy=needy, provider=self.provider, item=item, quantity=quantity, report_method="SELF_REPORT", status="DISTRIBUTED")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_dashboard"), {"revenue_period": "7"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["platform_fee_revenue"], Decimal("2.20000"))
        self.assertEqual(response.context["revenue_period"], "7")
        self.assertEqual(sum(response.context["revenue_chart"]["values"]), 2.2)
        self.assertEqual(response.context["provider_state_chart"]["values"][response.context["provider_state_chart"]["labels"].index("Selangor")], 1)
        self.assertEqual(response.context["supplier_transfer_chart"]["labels"], [self.supplier.business_name])
        self.assertEqual(response.context["supplier_transfer_chart"]["values"], [50.0])
        today_weekday = timezone.localdate().weekday()
        self.assertEqual(response.context["needy_weekday_chart"]["values"][today_weekday], 2)
        self.assertContains(response, 'id="provider-state-chart"')
        self.assertContains(response, 'id="supplier-transfer-chart"')
        self.assertContains(response, 'id="needy-weekday-chart"')
        self.assertContains(response, "Subscription payments are not currently recorded")

    def test_provider_application_requires_admin_approval_before_provider_tools(self):
        self.provider.is_approved = False
        self.provider.save(update_fields=["is_approved"])
        self.provider.user.is_active = False
        self.provider.user.status = "INACTIVE"
        self.provider.user.save(update_fields=["is_active", "status"])
        self.client.force_login(self.admin)
        dashboard = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(dashboard.context["pending_provider_count"], 1)
        approval_page = self.client.get(reverse("admin_approvals"))
        self.assertContains(approval_page, "Admin Test Bank")
        approval_url = reverse("approve_provider", args=[self.provider.pk])
        response = self.client.post(approval_url)
        self.assertRedirects(response, reverse("admin_user_detail", args=[self.provider.user.pk]))
        self.provider.refresh_from_db()
        self.assertFalse(self.provider.is_approved)
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(approval_url, {"documents_reviewed": "on"})
        self.assertRedirects(response, reverse("admin_user_detail", args=[self.provider.user.pk]))
        self.provider.refresh_from_db()
        self.provider.user.refresh_from_db()
        self.assertTrue(self.provider.is_approved)
        self.assertIsNotNone(self.provider.documents_reviewed_at)
        self.assertEqual(self.provider.documents_reviewed_by, self.admin)
        self.assertTrue(self.provider.user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.provider.user.email])
        self.assertIn("has been approved", mail.outbox[0].body)
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.get(reverse("provider_dashboard")).status_code, 200)

    def test_provider_registration_creates_pending_account_and_blocks_sign_in(self):
        response = self.client.post(reverse("provider_register"), {
            "name": "Pending Provider", "email": "pending-provider@example.test",
            "password": "Strong-FoodBank-Password-928!", "food_bank_name": "Pending Bank",
            "phone": "011222333", "address": "Kuala Lumpur", "operating_hours": "Weekdays",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An administrator must approve")
        account = User.objects.get(email="pending-provider@example.test")
        self.assertFalse(account.is_active)
        self.assertFalse(account.provider_profile.is_approved)
        login_response = self.client.post(reverse("login"), {"email": account.email, "password": "Strong-FoodBank-Password-928!"})
        self.assertContains(login_response, "waiting for admin approval")

    def test_provider_forecast_detail_filters_by_selected_item_and_month(self):
        from datetime import date
        rice = Item.objects.create(name="Forecast Rice", category="Grain", unit="kg")
        beans = Item.objects.create(name="Forecast Beans", category="Legume", unit="kg")
        Forecast.objects.create(provider=self.provider, item=rice, forecast_date=date(2026, 10, 1), predicted_quantity=10, actual_quantity=8, mape_score=20, forecast_type="PROPHET")
        Forecast.objects.create(provider=self.provider, item=rice, forecast_date=date(2026, 11, 1), predicted_quantity=12, actual_quantity=12, mape_score=0, forecast_type="PROPHET")
        Forecast.objects.create(provider=self.provider, item=beans, forecast_date=date(2026, 11, 1), predicted_quantity=5, actual_quantity=4, mape_score=25, forecast_type="PROPHET")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_user_detail", args=[self.provider.user.pk]), {"forecast_item": str(rice.pk), "forecast_month": "2026-10"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["admin_forecasts"].values_list("item__name", "forecast_date")), [("Forecast Rice", date(2026, 10, 1))])
        self.assertEqual(float(response.context["admin_provider_mape"]), 20.0)

    def test_admin_user_directory_lists_all_roles_and_actions(self):
        needy_user = User.objects.create_user(email="directory-needy@example.test", name="Directory Needy", password="test-pass", role="NEEDY")
        Needy.objects.create(user=needy_user, phone="0102", address="Road", postcode="40000", city="Shah Alam", state="Selangor")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_user_directory"))
        self.assertEqual(response.status_code, 200)
        for expected in ("Provider user", "Supplier user", "Admin Donor", "Directory Needy", "Provider", "Supplier", "Email", "Role", "Status", "Actions"):
            with self.subTest(expected=expected):
                self.assertContains(response, expected)
        self.assertContains(response, "Inactive")
        self.assertContains(response, "View Details")
        self.assertNotContains(response, "Update")
        self.assertNotContains(response, "Delete")
        self.assertNotContains(response, "Account detail")
        self.assertNotContains(response, "Registered")

        filtered = self.client.get(reverse("admin_user_directory"), {"role": "DONOR", "q": "Admin Donor"})
        self.assertContains(filtered, "admin-donor@example.test")
        self.assertNotContains(filtered, "Admin Test Bank")

    def test_user_directory_is_restricted_to_admin_role(self):
        url = reverse("admin_user_directory")
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.donor)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_admin_can_update_user_name_email_and_status(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin_user_update", args=[self.provider.user.pk]), {
            "name": "Updated Provider Contact", "email": "updated-provider@example.test",
            "status": "INACTIVE", "role": "ADMIN",
            "food_bank_name": self.provider.food_bank_name, "phone": self.provider.phone,
            "address": self.provider.address, "operating_hours": self.provider.operating_hours,
            "service_areas": "43000 | Shah Alam",
        })
        self.assertEqual(response.status_code, 302)
        self.provider.user.refresh_from_db()
        self.assertEqual(self.provider.user.name, "Updated Provider Contact")
        self.assertEqual(self.provider.user.email, "updated-provider@example.test")
        self.assertEqual(self.provider.user.status, "INACTIVE")
        self.assertFalse(self.provider.user.is_active)
        self.assertEqual(self.provider.user.role, "PROVIDER")
        self.assertEqual(list(self.provider.service_areas.values_list("postcode", "zone_name")), [("43000", "Shah Alam")])

    def test_admin_can_delete_other_account_but_not_self_and_non_admin_cannot(self):
        delete_url = reverse("admin_user_delete", args=[self.donor.pk])
        self.client.force_login(self.provider.user)
        self.client.post(delete_url)
        self.assertTrue(User.objects.filter(pk=self.donor.pk).exists())
        self.client.force_login(self.admin)
        self.client.post(reverse("admin_user_delete", args=[self.admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
        self.client.post(delete_url)
        self.assertFalse(User.objects.filter(pk=self.donor.pk).exists())

    def test_retention_and_payment_pages_use_the_admin_layout(self):
        self.client.force_login(self.admin)
        for route, heading in (("data_retention_settings", "Self-report data retention"), ("admin_donation_list", "Donor payments")):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, heading)
                self.assertContains(response, "Admin workspace")
                self.assertContains(response, "All users")

    def test_user_details_render_role_specific_pages_and_are_admin_only(self):
        needy_user = User.objects.create_user(email="detail-needy@example.test", name="Detail Needy", password="test-pass", role="NEEDY")
        Needy.objects.create(user=needy_user, phone="012345", address="12 Main Street", postcode="40000", city="Shah Alam", state="Selangor")
        routes = (
            (self.provider.user, "Food bank details"),
            (needy_user, "House number and street"),
            (self.donor, "Donor details"),
            (self.supplier.user, "Supplier approval"),
        )
        self.client.force_login(self.admin)
        for account, expected in routes:
            with self.subTest(role=account.role):
                response = self.client.get(reverse("admin_user_detail", args=[account.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected)
                self.assertContains(response, "Save Changes")
                self.assertContains(response, "Delete User")
                self.assertContains(response, "Cancel")
                self.assertContains(response, "admin_user_detail.js")

        self.client.force_login(self.donor)
        self.assertEqual(self.client.get(reverse("admin_user_detail", args=[self.provider.user.pk])).status_code, 302)

    def test_admin_user_details_show_related_history_and_current_allowance_can_be_adjusted(self):
        from datetime import timedelta
        from django.utils import timezone
        needy_user = User.objects.create_user(email="history-needy@example.test", name="History Needy", password="test-pass", role="NEEDY")
        needy = Needy.objects.create(user=needy_user, phone="012345", address="12 Main Street", postcode="40000", city="Shah Alam", state="Selangor")
        item = Item.objects.create(name="Rice", category="Grains", unit="kg")
        week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        usage = AllowanceUsage.objects.create(needy=needy, provider=self.provider, item=item, week_start_date=week_start, allowed_quantity=5, used_quantity=2, remaining_quantity=3)
        Report.objects.create(needy=needy, provider=self.provider, item=item, quantity=2, report_method="SELF_REPORT", status="DISTRIBUTED")
        self.client.force_login(self.admin)
        detail = self.client.get(reverse("admin_user_detail", args=[needy_user.pk]))
        self.assertContains(detail, "Self-report history")
        self.assertContains(detail, "Weekly allowance")
        response = self.client.post(reverse("admin_needy_allowance_update", args=[needy_user.pk, usage.pk]), {"weekly_limit": "8"})
        self.assertRedirects(response, reverse("admin_user_detail", args=[needy_user.pk]))
        usage.refresh_from_db()
        self.assertEqual((usage.allowed_quantity, usage.remaining_quantity), (8, 6))
        self.client.force_login(self.donor)
        self.assertEqual(self.client.post(reverse("admin_needy_allowance_update", args=[needy_user.pk, usage.pk]), {"weekly_limit": "9"}).status_code, 302)
        usage.refresh_from_db()
        self.assertEqual(usage.allowed_quantity, 8)

    def test_supplier_can_be_rejected_from_detail_approval_action(self):
        ProviderSupplier.objects.create(provider=self.provider, supplier=self.supplier, status="ACTIVE")
        self.supplier.is_approved = True
        self.supplier.save(update_fields=["is_approved"])
        self.supplier.user.is_active = True
        self.supplier.user.status = "ACTIVE"
        self.supplier.user.save(update_fields=["is_active", "status"])
        self.client.force_login(self.admin)
        response = self.client.post(reverse("reject_supplier", args=[self.supplier.pk]))
        self.assertRedirects(response, reverse("admin_user_directory"))
        self.supplier.refresh_from_db()
        self.supplier.user.refresh_from_db()
        self.assertFalse(self.supplier.is_approved)
        self.assertFalse(self.supplier.user.is_active)
        self.assertEqual(self.supplier.user.status, "INACTIVE")
        self.assertFalse(ProviderSupplier.objects.filter(supplier=self.supplier, status="ACTIVE").exists())
