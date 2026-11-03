import hashlib
import hmac
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models.provider import Provider
from accounts.models.supplier import Supplier
from accounts.models.user import User
from distribution.models import ProviderSupplier
from donations.models import Cart, CartItem, Donation, Transaction
from inventory.models.item import Item
from inventory.models.supplier_product import SupplierProduct
from orders.models import POItem, PurchaseOrder
from urgent_needs.models.urgent_need import UrgentNeed


@override_settings(BILLPLZ_X_SIGNATURE_KEY="sandbox-test-signature")
class BillplzDonationFlowTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user(
            email="donor@example.test", name="Donor", password="test-pass", role="DONOR",
        )
        provider_user = User.objects.create_user(
            email="provider@example.test", name="Provider", password="test-pass", role="PROVIDER",
        )
        self.provider = Provider.objects.create(
            user=provider_user, food_bank_name="Food Bank", phone="0123456789",
            address="Kuala Lumpur", operating_hours="9-5",
        )
        self.item = Item.objects.create(name="Rice", category="Grain", unit="kg")
        supplier_user = User.objects.create_user(
            email="supplier@example.test", name="Supplier", password="test-pass", role="SUPPLIER",
        )
        self.supplier = Supplier.objects.create(
            user=supplier_user, business_name="ABC Supplier", ssm_registration_no="123",
            contact_person="Contact", phone="0120000000", bank_account="000", bank_name="Bank",
        )
        self.product = SupplierProduct.objects.create(
            supplier=self.supplier, item=self.item, price=Decimal("5.00"), stock=100,
        )
        ProviderSupplier.objects.create(provider=self.provider, supplier=self.supplier, status="ACTIVE")
        self.need = UrgentNeed.objects.create(
            provider=self.provider, item=self.item, required_quantity=5, remaining_quantity=5,
            target_amount=Decimal("25.00"),
        )
        self.cart = Cart.objects.create(donor=self.donor, total_amount=Decimal("10.00"))
        CartItem.objects.create(
            cart=self.cart, provider=self.provider, urgent_need=self.need, quantity=2,
            price=Decimal("5.00"), subtotal=Decimal("10.00"),
        )

    def test_donor_dashboard_links_to_open_needs_and_need_browse_is_role_scoped(self):
        self.client.force_login(self.donor)
        dashboard = self.client.get(reverse("donor_dashboard"))
        self.assertContains(dashboard, reverse("donor_needs"))
        response = self.client.get(reverse("donor_needs"))
        self.assertContains(response, "Rice")
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.get(reverse("donor_needs")).status_code, 302)

    def test_donor_can_add_need_to_cart_and_quantity_is_capped(self):
        self.client.force_login(self.donor)
        response = self.client.post(reverse("add_need_to_cart", args=[self.need.urgent_need_id]), {"quantity": "2"})
        self.assertRedirects(response, reverse("donor_needs"))
        cart_item = CartItem.objects.get(cart=self.cart, urgent_need=self.need)
        self.assertEqual(cart_item.quantity, 4)
        self.assertEqual(cart_item.subtotal, Decimal("20.00"))
        response = self.client.post(reverse("add_need_to_cart", args=[self.need.urgent_need_id]), {"quantity": "2"})
        self.assertEqual(response.status_code, 400)
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 4)

    def test_donor_registration_creates_and_signs_in_donor_account(self):
        response = self.client.post(reverse("donor_register"), {
            "name": "New Donor", "email": "newdonor@example.test", "password": "Strong-Test-Password-481!",
        })
        self.assertRedirects(response, reverse("donor_dashboard"))
        user = User.objects.get(email="newdonor@example.test")
        self.assertEqual(user.role, "DONOR")
        self.assertTrue(user.check_password("Strong-Test-Password-481!"))

    def test_donor_profile_updates_name_and_email(self):
        self.client.force_login(self.donor)
        response = self.client.get(reverse("donor_profile"))
        self.assertContains(response, "My donor profile")
        response = self.client.post(reverse("donor_profile"), {"name": "Updated Donor", "email": "updated@example.test"})
        self.assertRedirects(response, reverse("donor_profile"))
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.name, "Updated Donor")
        self.assertEqual(self.donor.email, "updated@example.test")

    def test_provider_directory_and_profile_are_donor_only(self):
        self.client.force_login(self.donor)
        self.assertContains(self.client.get(reverse("provider_directory")), "Food Bank")
        self.assertContains(self.client.get(reverse("provider_public_profile", args=[self.provider.provider_id])), "0123456789")
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.get(reverse("provider_directory")).status_code, 302)

    def test_one_cart_cannot_include_items_from_multiple_providers(self):
        provider_user = User.objects.create_user(email="provider2@example.test", name="Provider Two", password="test-pass", role="PROVIDER")
        provider_two = Provider.objects.create(user=provider_user, food_bank_name="Second Food Bank", phone="01112345678", address="Selangor", operating_hours="9-5")
        ProviderSupplier.objects.create(provider=provider_two, supplier=self.supplier, status="ACTIVE")
        need_two = UrgentNeed.objects.create(provider=provider_two, item=self.need.item, required_quantity=10, remaining_quantity=10, target_amount=Decimal("50.00"))
        self.client.force_login(self.donor)
        response = self.client.post(reverse("add_need_to_cart", args=[need_two.urgent_need_id]), {"quantity": "5"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(CartItem.objects.filter(cart=self.cart).values("provider_id").distinct().count(), 1)
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.total_amount, Decimal("10.00"))

    def test_delivered_provider_can_be_rated_for_a_paid_donation(self):
        order = PurchaseOrder.objects.create(provider=self.provider, supplier=self.supplier, status="DELIVERED", delivery_confirmed=True)
        POItem.objects.create(po=order, product=self.product, quantity=2, price=Decimal("5.00"), subtotal=Decimal("10.00"))
        donation = Donation.objects.create(donor=self.donor, cart=self.cart, total_amount=Decimal("10.00"), status="PAID")
        from donations.models import DonationItem, ProviderReview
        DonationItem.objects.create(donation=donation, provider=self.provider, urgent_need=self.need, item=self.need.item, quantity=2, price=Decimal("5.00"))
        from donations.models import DonationOrderAllocation
        DonationOrderAllocation.objects.create(donation_item=donation.items.get(), purchase_order_item=order.items.get(), quantity=2)
        self.client.force_login(self.donor)
        response = self.client.post(reverse("rate_provider", args=[donation.donation_id, self.provider.provider_id]), {"rating": "5", "comment": "Thanks"})
        self.assertRedirects(response, reverse("donation_history"))
        self.assertEqual(ProviderReview.objects.get(donation=donation, provider=self.provider).rating, 5)

    def test_cart_refreshes_supplier_price_before_display(self):
        self.product.price = Decimal("6.00")
        self.product.save(update_fields=["price", "updated_at"])
        self.client.force_login(self.donor)
        response = self.client.get(reverse("donor_cart"))
        self.assertContains(response, "12.00")
        cart_item = CartItem.objects.get(cart=self.cart)
        self.assertEqual(cart_item.price, Decimal("6.00"))
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.total_amount, Decimal("12.00"))
    def test_donor_can_adjust_and_remove_cart_item(self):
        self.client.force_login(self.donor)
        response = self.client.post(reverse("donor_cart"), {
            "item_id": CartItem.objects.get(cart=self.cart).cart_item_id,
            "action": "update", "quantity": "3",
        })
        self.assertRedirects(response, reverse("donor_cart"))
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.total_amount, Decimal("15.00"))
        response = self.client.post(reverse("donor_cart"), {
            "item_id": CartItem.objects.get(cart=self.cart).cart_item_id, "action": "remove",
        })
        self.assertRedirects(response, reverse("donor_cart"))
        self.assertFalse(CartItem.objects.filter(cart=self.cart).exists())

    def test_paid_donor_can_download_receipt_but_other_donor_cannot(self):
        donation = Donation.objects.create(donor=self.donor, cart=self.cart, total_amount=Decimal("10.00"), status="PAID")
        self.client.force_login(self.donor)
        response = self.client.get(reverse("donation_receipt", args=[donation.donation_id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))
        other = User.objects.create_user(email="receipt@example.test", name="Other", password="pass", role="DONOR")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("donation_receipt", args=[donation.donation_id])).status_code, 404)

    def test_donor_history_and_impact_certificate(self):
        donation = Donation.objects.create(donor=self.donor, cart=self.cart, total_amount=Decimal("10.00"), status="PAID")
        from donations.models import DonationItem
        DonationItem.objects.create(donation=donation, provider=self.provider, urgent_need=self.need, item=self.need.item, quantity=2, price=Decimal("5.00"))
        self.client.force_login(self.donor)
        history = self.client.get(reverse("donation_history"))
        self.assertContains(history, "Pending Collection")
        certificate = self.client.get(reverse("impact_certificate"))
        self.assertEqual(certificate.status_code, 200)
        self.assertEqual(certificate["Content-Type"], "application/pdf")

    def _signed_callback(self, values):
        parts = [f"{key}{value}" for key, value in values.items()]
        parts.sort(key=str.casefold)
        source = "|".join(parts).encode()
        values["x_signature"] = hmac.new(
            b"sandbox-test-signature", source, hashlib.sha256,
        ).hexdigest()
        return values

    @patch("donations.views._create_bill")
    def test_donor_checkout_creates_pending_donation_and_fpx_transaction(self, create_bill):
        def fake_bill(donation, payment, request):
            payment.gateway_reference = "bill-test-1"
            payment.save(update_fields=["gateway_reference"])
            return "https://www.billplz-sandbox.com/bills/bill-test-1"
        create_bill.side_effect = fake_bill
        self.client.force_login(self.donor)
        response = self.client.post(reverse("donation_checkout", args=[self.cart.cart_id]))
        self.assertEqual(response.status_code, 302)
        donation = Donation.objects.get(cart=self.cart)
        payment = Transaction.objects.get(donation=donation)
        self.assertEqual(donation.donor, self.donor)
        self.assertEqual(donation.total_amount, Decimal("10.00"))
        self.assertEqual(donation.status, "PENDING")
        self.assertEqual(payment.payment_method, "FPX")
        self.assertEqual(payment.gateway_reference, "bill-test-1")

    def test_checkout_is_scoped_to_cart_owner_and_donor_role(self):
        other = User.objects.create_user(
            email="other@example.test", name="Other", password="test-pass", role="DONOR",
        )
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("donation_checkout", args=[self.cart.cart_id])).status_code, 404)
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.post(reverse("donation_checkout", args=[self.cart.cart_id])).status_code, 302)
        self.assertFalse(Donation.objects.exists())

    def test_signed_success_callback_updates_payment_once_and_is_visible_to_admin(self):
        donation = Donation.objects.create(donor=self.donor, cart=self.cart, total_amount=Decimal("10.00"))
        payment = Transaction.objects.create(
            donation=donation, amount=Decimal("10.00"), payment_method="FPX",
            gateway_reference="bill-test-2",
        )
        from donations.models import DonationItem
        DonationItem.objects.create(
            donation=donation, provider=self.provider, urgent_need=self.need,
            item=self.need.item, quantity=2, price=Decimal("5.00"),
        )
        callback = self._signed_callback({
            "id": "bill-test-2", "paid": "true", "state": "paid", "amount": "1000",
            "transaction_id": "fpx-ref-2",
        })
        url = reverse("billplz_callback")
        self.assertEqual(self.client.post(url, callback).status_code, 200)
        self.assertEqual(self.client.post(url, callback).status_code, 200)
        payment.refresh_from_db()
        donation.refresh_from_db()
        self.cart.refresh_from_db()
        self.assertEqual(payment.status, "PAID")
        self.assertEqual(payment.fpx_reference, "fpx-ref-2")
        self.assertEqual(donation.status, "PAID")
        self.assertEqual(self.cart.status, "COMPLETED")
        self.need.refresh_from_db()
        self.assertEqual(self.need.funded_quantity, 2)
        self.assertEqual(self.need.remaining_quantity, 3)
        self.client.force_login(User.objects.create_user(
            email="admin@example.test", name="Admin", password="test-pass", role="ADMIN",
        ))
        self.assertContains(self.client.get(reverse("admin_donation_list")), "Donor")

    def test_invalid_signature_or_amount_does_not_mark_donation_paid(self):
        donation = Donation.objects.create(donor=self.donor, cart=self.cart, total_amount=Decimal("10.00"))
        Transaction.objects.create(
            donation=donation, amount=Decimal("10.00"), payment_method="FPX", gateway_reference="bill-test-3",
        )
        url = reverse("billplz_callback")
        bad_signature = self.client.post(url, {"id": "bill-test-3", "paid": "true", "x_signature": "bad"})
        self.assertEqual(bad_signature.status_code, 400)
        wrong_amount = self._signed_callback({"id": "bill-test-3", "paid": "true", "state": "paid", "amount": "999"})
        self.assertEqual(self.client.post(url, wrong_amount).status_code, 400)
        donation.refresh_from_db()
        self.assertEqual(donation.status, "PENDING")

    def test_paid_donation_is_allocated_to_matching_order_line_only(self):
        from donations.models import DonationItem, DonationOrderAllocation
        donation = Donation.objects.create(donor=self.donor, cart=self.cart, total_amount=Decimal("10.00"), status="PAID")
        donated = DonationItem.objects.create(donation=donation, provider=self.provider, urgent_need=self.need, item=self.item, quantity=2, price=Decimal("5.00"))
        order = PurchaseOrder.objects.create(provider=self.provider, supplier=self.supplier)
        line = POItem.objects.create(po=order, product=self.product, quantity=3, price=Decimal("5.00"), subtotal=Decimal("15.00"))
        from donations.services import allocate_paid_donations_to_order
        allocate_paid_donations_to_order(order)
        allocation = DonationOrderAllocation.objects.get(donation_item=donated, purchase_order_item=line)
        self.assertEqual(allocation.quantity, 2)
        self.assertEqual(DonationOrderAllocation.objects.filter(purchase_order_item=line).aggregate(total=__import__("django.db.models").db.models.Sum("quantity"))["total"], 2)

    def test_legacy_donation_history_is_labeled_estimated(self):
        from donations.models import DonationItem
        donation = Donation.objects.create(donor=self.donor, cart=self.cart, total_amount=Decimal("10.00"), status="PAID")
        donated = DonationItem.objects.create(donation=donation, provider=self.provider, urgent_need=self.need, item=self.item, quantity=2, price=Decimal("5.00"), link_tracking_enabled=False)
        self.need.funded_quantity = self.need.required_quantity
        self.need.save(update_fields=["funded_quantity"])
        from donations.views import _donation_item_progress
        self.assertIn("estimated", _donation_item_progress(donated).lower())

    def test_admin_donation_records_are_not_available_to_provider(self):
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.get(reverse("admin_donation_list")).status_code, 302)




