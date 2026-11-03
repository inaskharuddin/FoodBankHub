from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Provider, Supplier, User
from forecasting.models import Forecast
from distribution.models import ProviderSupplier
from inventory.models import Inventory, Item, LowStockAlert, SupplierProduct


class ProviderSupplierPanelTests(TestCase):
    def setUp(self):
        self.provider_user = User.objects.create_user(
            email="provider@example.test", name="Provider", password="test-pass", role="PROVIDER",
        )
        self.provider = Provider.objects.create(
            user=self.provider_user, food_bank_name="Bank", phone="0100",
            address="Address", operating_hours="24/7",
        )
        self.supplier_users = [
            User.objects.create_user(email=f"supplier{n}@example.test", name=f"Supplier {n}", password="test-pass", role="SUPPLIER")
            for n in (1, 2)
        ]
        self.suppliers = [
            Supplier.objects.create(
                user=user, business_name=f"Supplier {index}", ssm_registration_no=f"SSM{index}",
                contact_person="Contact", phone="0101", bank_account="000", bank_name="Bank",
            ) for index, user in enumerate(self.supplier_users, start=1)
        ]
        self.item = Item.objects.create(name="Rice", category="Grain", unit="kg")
        SupplierProduct.objects.create(supplier=self.suppliers[0], item=self.item, price=Decimal("3.00"), stock=50)
        SupplierProduct.objects.create(supplier=self.suppliers[1], item=self.item, price=Decimal("3.50"), stock=40)
        self.relationship = ProviderSupplier.objects.create(provider=self.provider, supplier=self.suppliers[0], status="ACTIVE")
        self.inventory = Inventory.objects.create(provider=self.provider, item=self.item, quantity=20, price_per_unit=Decimal("3.00"))

    def test_provider_can_switch_supplier_and_prices_follow_selected_panel(self):
        self.client.force_login(self.provider_user)
        response = self.client.post(reverse("supplier_select", args=[self.suppliers[1].supplier_id]))
        self.assertEqual(response.status_code, 302)
        self.relationship.refresh_from_db()
        self.assertEqual(self.relationship.status, "INACTIVE")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.price_per_unit, Decimal("3.50"))
        self.assertTrue(ProviderSupplier.objects.filter(provider=self.provider, supplier=self.suppliers[1], status="ACTIVE").exists())

    def test_provider_cannot_select_supplier_pending_admin_approval(self):
        pending_user = User.objects.create_user(
            email="pending-supplier@example.test", name="Pending Supplier", password="test-pass", role="SUPPLIER",
        )
        pending = Supplier.objects.create(
            user=pending_user, business_name="Pending Supplier", ssm_registration_no="PENDING",
            contact_person="Contact", phone="0101", bank_account="000", bank_name="Bank", is_approved=False,
        )
        self.client.force_login(self.provider_user)
        response = self.client.post(reverse("supplier_select", args=[pending.supplier_id]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProviderSupplier.objects.filter(provider=self.provider, supplier=pending, status="ACTIVE").exists())


class LowStockEmailTests(TestCase):
    def setUp(self):
        self.provider_user = User.objects.create_user(
            email="provider-alerts@example.test", name="Alert Provider", password="test-pass", role="PROVIDER",
        )
        self.provider = Provider.objects.create(
            user=self.provider_user, food_bank_name="Alert Food Bank", phone="0100",
            address="Address", operating_hours="24/7",
        )
        self.item = Item.objects.create(name="Rice", category="Grain", unit="kg")
        self.inventory = Inventory.objects.create(
            provider=self.provider, item=self.item, quantity=2, threshold_level=3,
        )
        from django.utils import timezone
        Forecast.objects.create(
            provider=self.provider, item=self.item,
            forecast_date=timezone.localdate() + timezone.timedelta(days=1),
            predicted_quantity=Decimal("5"), forecast_type="PROPHET",
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST_USER="foodbankhub@example.test",
        EMAIL_HOST_PASSWORD="gmail-app-password",
        DEFAULT_FROM_EMAIL="foodbankhub@example.test",
    )
    def test_low_stock_email_sent_once_until_alert_clears_and_returns(self):
        self.client.force_login(self.provider_user)
        url = reverse("low_stock_alerts")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.provider_user.email])
        self.assertIn("Rice", mail.outbox[0].body)
        alert = LowStockAlert.objects.get(provider=self.provider, item=self.item, forecast_days=7)
        self.assertTrue(alert.is_active)

        self.client.get(url)
        self.assertEqual(len(mail.outbox), 1)

        self.inventory.quantity = 50
        self.inventory.save(update_fields=["quantity"])
        self.client.get(url)
        alert.refresh_from_db()
        self.assertFalse(alert.is_active)

        self.inventory.quantity = 2
        self.inventory.save(update_fields=["quantity"])
        self.client.get(url)
        self.assertEqual(len(mail.outbox), 2)
