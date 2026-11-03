from django.test import TestCase, override_settings
from django.core import mail
from django.urls import reverse

from .models import Supplier, User
from .models import Needy, Provider
from distribution.models import ServiceArea
from inventory.models import Inventory, Item

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

        response = self.client.post(reverse("approve_supplier", args=[supplier.supplier_id]))

        self.assertRedirects(response, reverse("admin_dashboard"))
        supplier.refresh_from_db()
        supplier_user.refresh_from_db()
        self.assertTrue(supplier.is_approved)
        self.assertIsNotNone(supplier.approved_at)
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
