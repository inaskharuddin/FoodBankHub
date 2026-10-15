from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models.provider import Provider
from accounts.models.supplier import Supplier
from accounts.models.user import User
from inventory.models.inventory import Inventory
from inventory.models.item import Item
from inventory.models.supplier_product import SupplierProduct
from .models.payout import Payout
from .models.po_item import POItem
from .models.purchase_order import PurchaseOrder


class SupplierDeliveryWorkflowTests(TestCase):
    def setUp(self):
        self.provider_user = User.objects.create_user(
            email="provider@example.test", name="Provider", password="test-pass",
            role="PROVIDER",
        )
        self.provider = Provider.objects.create(
            user=self.provider_user, food_bank_name="Community Food Bank",
            phone="0123456789", address="Kuala Lumpur", operating_hours="9-5",
        )
        self.supplier_user = User.objects.create_user(
            email="supplier@example.test", name="Supplier", password="test-pass",
            role="SUPPLIER",
        )
        self.supplier = Supplier.objects.create(
            user=self.supplier_user, business_name="Fresh Supplier",
            ssm_registration_no="SSM-1", contact_person="Contact",
            phone="0123456789", bank_account="123", bank_name="Bank",
        )
        self.other_provider_user = User.objects.create_user(
            email="other-provider@example.test", name="Other Provider", password="test-pass",
            role="PROVIDER",
        )
        self.other_provider = Provider.objects.create(
            user=self.other_provider_user, food_bank_name="Other Food Bank",
            phone="0123456789", address="Kuala Lumpur", operating_hours="9-5",
        )
        self.other_supplier_user = User.objects.create_user(
            email="other@example.test", name="Other Supplier", password="test-pass",
            role="SUPPLIER",
        )
        self.other_supplier = Supplier.objects.create(
            user=self.other_supplier_user, business_name="Other Supplier",
            ssm_registration_no="SSM-2", contact_person="Contact",
            phone="0123456789", bank_account="456", bank_name="Bank",
        )
        self.item = Item.objects.create(name="Rice", category="Grain", unit="kg")
        self.product = SupplierProduct.objects.create(
            supplier=self.supplier, item=self.item, price=Decimal("2.50"), stock=100,
        )
        self.order = PurchaseOrder.objects.create(
            provider=self.provider, supplier=self.supplier,
            total_amount=Decimal("10.00"),
        )
        POItem.objects.create(
            po=self.order, product=self.product, quantity=4,
            price=Decimal("2.50"), subtotal=Decimal("10.00"),
        )

    def test_lifecycle_updates_inventory_only_once_after_provider_confirmation(self):
        self.client.force_login(self.supplier_user)
        list_response = self.client.get(reverse("supplier_order_list"))
        self.assertContains(list_response, "Community Food Bank")
        self.assertContains(list_response, "Rice")
        self.assertContains(list_response, "10.00")

        status_url = reverse("supplier_update_order_status", args=[self.order.po_id])
        for action, expected in (("accept", "ACCEPTED"), ("ship", "SHIPPED"), ("mark-delivered", "DELIVERED")):
            response = self.client.post(status_url, {"action": action})
            self.assertEqual(response.status_code, 302)
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, expected)
            self.assertFalse(Inventory.objects.filter(provider=self.provider, item=self.item).exists())

        self.client.force_login(self.provider_user)
        detail_url = reverse("purchase_order_detail", args=[self.order.po_id])
        self.assertContains(self.client.get(detail_url), "Confirm delivery")
        confirm_url = reverse("confirm_purchase_order_delivery", args=[self.order.po_id])
        self.assertEqual(self.client.post(confirm_url).status_code, 302)
        inventory = Inventory.objects.get(provider=self.provider, item=self.item)
        self.assertEqual(inventory.quantity, 4)

        self.client.post(confirm_url)
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity, 4)
        self.order.refresh_from_db()
        self.assertTrue(self.order.delivery_confirmed)

    def test_supplier_and_provider_views_are_scoped_to_owners(self):
        self.client.force_login(self.other_supplier_user)
        response = self.client.get(reverse("supplier_order_list"))
        self.assertNotContains(response, "Community Food Bank")
        foreign_status_url = reverse("supplier_update_order_status", args=[self.order.po_id])
        self.assertEqual(self.client.post(foreign_status_url, {"action": "accept"}).status_code, 404)

        self.client.force_login(self.supplier_user)
        self.assertContains(self.client.get(reverse("supplier_order_list")), "PO " + str(self.order.po_id))

        self.client.force_login(self.other_provider_user)
        self.assertEqual(
            self.client.get(reverse("purchase_order_detail", args=[self.order.po_id])).status_code,
            404,
        )




    def test_only_admin_records_payment_after_confirmed_delivery(self):
        payment_url = reverse("record_purchase_order_payment", args=[self.order.po_id])
        self.client.force_login(self.provider_user)

        self.assertEqual(self.client.post(payment_url, {"transfer_reference": "TX-123"}).status_code, 302)
        self.assertFalse(Payout.objects.filter(po=self.order).exists())

        self.order.status = "DELIVERED"
        self.order.delivery_confirmed = True
        self.order.save(update_fields=["status", "delivery_confirmed"])
        self.client.force_login(self.provider_user)
        self.assertNotContains(self.client.get(reverse("purchase_order_detail", args=[self.order.po_id])), "Record supplier payment")
        self.client.post(payment_url, {"transfer_reference": "TX-123"})
        self.assertFalse(Payout.objects.filter(po=self.order).exists())

        self.client.force_login(User.objects.create_user(
            email="admin@example.test", name="Admin", password="test-pass", role="ADMIN",
        ))
        self.client.post(payment_url, {"transfer_reference": "TX-123"})
        self.client.post(payment_url, {"transfer_reference": "TX-456"})

        payout = Payout.objects.get(po=self.order)
        self.assertEqual(Payout.objects.filter(po=self.order).count(), 1)
        self.assertEqual(payout.supplier, self.supplier)
        self.assertEqual(payout.amount, Decimal("10.00"))
        self.assertEqual(payout.status, "PAID")
        self.assertEqual(payout.transfer_reference, "TX-123")

        self.client.force_login(self.supplier_user)
        self.assertContains(self.client.get(reverse("supplier_payout_list")), "TX-123")
        self.client.force_login(self.other_supplier_user)
        self.assertNotContains(self.client.get(reverse("supplier_payout_list")), "TX-123")
