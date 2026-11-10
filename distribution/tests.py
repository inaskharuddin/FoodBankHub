from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core import signing

from accounts.models import Needy, Provider, Supplier, User
from distribution.models import AllowanceUsage, ProviderAllowance, ProviderSupplier, Report, ServiceArea
from forecasting.models import Forecast, HistoricalData
from inventory.models import Inventory, Item, SupplierProduct


class ProviderSelfReportTests(TestCase):
    def setUp(self):
        self.provider_user = User.objects.create_user(
            email="bank@example.test", name="Bank", password="test-pass", role="PROVIDER",
        )
        self.provider = Provider.objects.create(
            user=self.provider_user, food_bank_name="Test Bank", phone="0100",
            address="Test Street", operating_hours="24/7",
        )
        self.needy_user = User.objects.create_user(
            email="needy@example.test", name="Needy", password="test-pass", role="NEEDY",
        )
        self.needy = Needy.objects.create(
            user=self.needy_user, phone="0101", address="Test address",
            postcode="43000", city="Shah Alam", state="Selangor",
        )
        self.item = Item.objects.create(name="Rice", category="Grain", unit="kg")
        self.inventory = Inventory.objects.create(
            provider=self.provider, item=self.item, quantity=10, threshold_level=2,
        )
        ServiceArea.objects.create(provider=self.provider, postcode="43000", zone_name="Central")
        ProviderAllowance.objects.create(provider=self.provider, item=self.item, weekly_limit=10)

    def report_url(self, provider=None):
        provider = provider or self.provider
        token = signing.dumps(provider.provider_id, salt="distribution.provider-self-report", compress=True)
        return reverse("needy_self_report", args=[token])

    def test_in_area_self_report_reduces_stock_and_creates_actual_history(self):
        self.client.force_login(self.needy_user)
        response = self.client.post(
            self.report_url(),
            {"item_id": self.item.item_id, "quantity": "3"},
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 7)
        self.assertTrue(Report.objects.filter(provider=self.provider, status="DISTRIBUTED", quantity=3).exists())
        report = Report.objects.get(provider=self.provider, status="DISTRIBUTED", quantity=3)
        from distribution.models import ReportLotAllocation
        allocation = ReportLotAllocation.objects.get(report=report)
        self.assertTrue(allocation.estimated)
        self.assertIsNone(allocation.inventory_lot)

    def test_admin_allowance_override_is_not_replaced_by_provider_default(self):
        from datetime import timedelta
        week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        usage = AllowanceUsage.objects.create(
            needy=self.needy, provider=self.provider, item=self.item,
            week_start_date=week_start, allowed_quantity=4, used_quantity=1,
            remaining_quantity=3, admin_override=True,
        )
        self.client.force_login(self.needy_user)
        response = self.client.post(self.report_url(), {"item_id": self.item.item_id, "quantity": "3"})
        self.assertEqual(response.status_code, 302)
        usage.refresh_from_db()
        self.assertEqual(usage.allowed_quantity, 4)
        self.assertEqual(usage.used_quantity, 4)
        self.assertEqual(usage.remaining_quantity, 0)

    def test_distribution_consumes_exact_donor_order_allocation(self):
        from decimal import Decimal
        from donations.models import Cart, Donation, DonationItem, DonationOrderAllocation
        from orders.models import InventoryLot, POItem, PurchaseOrder
        from urgent_needs.models import UrgentNeed
        donor = User.objects.create_user(email="trace-donor@example.test", name="Trace donor", password="test-pass", role="DONOR")
        cart = Cart.objects.create(donor=donor, total_amount=Decimal("20.00"), status="COMPLETED")
        donation = Donation.objects.create(donor=donor, cart=cart, total_amount=Decimal("20.00"), status="PAID")
        need = UrgentNeed.objects.create(provider=self.provider, item=self.item, required_quantity=4, remaining_quantity=0, funded_quantity=4, target_amount=Decimal("20.00"), funded_amount=Decimal("20.00"), status="ORDERED")
        supplier = Supplier.objects.create(user=User.objects.create_user(email="trace-supplier@example.test", name="Supplier", password="test-pass", role="SUPPLIER"), business_name="Trace supplier", ssm_registration_no="TRACE-1", contact_person="Contact", phone="0103", bank_account="001", bank_name="Bank")
        product = SupplierProduct.objects.create(supplier=supplier, item=self.item, price=Decimal("5.00"), stock=20)
        order = PurchaseOrder.objects.create(provider=self.provider, supplier=supplier, status="DELIVERED", delivery_confirmed=True, total_amount=Decimal("50.00"))
        line = POItem.objects.create(po=order, product=product, quantity=10, price=Decimal("5.00"), subtotal=Decimal("50.00"))
        donated_item = DonationItem.objects.create(donation=donation, provider=self.provider, urgent_need=need, item=self.item, quantity=4, price=Decimal("5.00"))
        link = DonationOrderAllocation.objects.create(donation_item=donated_item, purchase_order_item=line, quantity=4)
        InventoryLot.objects.create(inventory=self.inventory, purchase_order_item=line, received_quantity=10, remaining_quantity=10)
        self.client.force_login(self.needy_user)
        response = self.client.post(self.report_url(), {"item_id": self.item.item_id, "quantity": "3"})
        self.assertEqual(response.status_code, 302)
        from distribution.models import ReportLotAllocation
        report = Report.objects.get(provider=self.provider, status="DISTRIBUTED", quantity=3)
        allocation = ReportLotAllocation.objects.get(report=report)
        self.assertEqual(allocation.donation_order_allocation, link)
        self.assertFalse(allocation.estimated)
        self.assertTrue(HistoricalData.objects.filter(provider=self.provider, item=self.item, source="ACTUAL", quantity=3).exists())

    def test_out_of_area_attempt_is_visible_and_does_not_reduce_stock(self):
        self.needy.postcode = "99999"
        self.needy.save(update_fields=["postcode"])
        self.client.force_login(self.needy_user)
        response = self.client.post(
            self.report_url(),
            {"item_id": self.item.item_id, "quantity": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertTrue(Report.objects.filter(provider=self.provider, status="BLOCKED_ADDRESS").exists())

    def test_signed_report_link_cannot_be_changed_to_another_provider(self):
        another_user = User.objects.create_user(
            email="another-bank@example.test", name="Other Bank", password="test-pass", role="PROVIDER",
        )
        another_provider = Provider.objects.create(
            user=another_user, food_bank_name="Other Bank", phone="0111",
            address="Other Street", operating_hours="9-5",
        )
        token = signing.dumps(self.provider.provider_id, salt="distribution.provider-self-report", compress=True)
        changed_token = signing.dumps(another_provider.provider_id, salt="distribution.provider-self-report", compress=True)
        self.client.force_login(self.needy_user)
        response = self.client.post(
            reverse("needy_self_report", args=[token[:-1] + ("A" if token[-1] != "A" else "B")]),
            {"item_id": self.item.item_id, "quantity": "1"},
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("needy_self_report", args=[changed_token]),
            {"item_id": self.item.item_id, "quantity": "1"},
        )
        self.assertEqual(response.status_code, 404)

    def test_provider_can_download_unique_qr_image(self):
        self.client.force_login(self.provider_user)
        response = self.client.get(reverse("provider_self_report_qr"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_provider_views_render(self):
        self.client.force_login(self.provider_user)
        for route in ("provider_dashboard", "provider_settings", "service_area_manage", "provider_reports", "provider_donation_monitoring", "provider_daily_summary", "needy_usage_report", "provider_urgent_needs", "view_forecast"):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200, route)

    def test_low_stock_page_generates_donor_need_from_forecast(self):
        supplier_user = User.objects.create_user(
            email="supplier@example.test", name="Supplier", password="test-pass", role="SUPPLIER",
        )
        supplier = Supplier.objects.create(
            user=supplier_user, business_name="Supplier", ssm_registration_no="SSM",
            contact_person="Contact", phone="0102", bank_account="000", bank_name="Bank",
        )
        ProviderSupplier.objects.create(provider=self.provider, supplier=supplier, status="ACTIVE")
        SupplierProduct.objects.create(supplier=supplier, item=self.item, price=3, stock=100)
        Forecast.objects.create(
            provider=self.provider, item=self.item,
            forecast_date=timezone.localdate() + timezone.timedelta(days=1),
            predicted_quantity=10, forecast_type="PROPHET",
        )
        self.client.force_login(self.provider_user)
        response = self.client.get(reverse("low_stock_alerts"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suggested order")
        from urgent_needs.models import UrgentNeed
        need = UrgentNeed.objects.get(provider=self.provider, item=self.item, status="OPEN")
        self.assertEqual(need.required_quantity, 2)
