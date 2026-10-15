import hashlib
import hmac
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models.provider import Provider
from accounts.models.user import User
from donations.models import Cart, CartItem, Donation, Transaction
from inventory.models.item import Item
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
        item = Item.objects.create(name="Rice", category="Grain", unit="kg")
        need = UrgentNeed.objects.create(
            provider=self.provider, item=item, required_quantity=5, remaining_quantity=5,
            target_amount=Decimal("25.00"),
        )
        self.cart = Cart.objects.create(donor=self.donor, total_amount=Decimal("10.00"))
        CartItem.objects.create(
            cart=self.cart, provider=self.provider, urgent_need=need, quantity=2,
            price=Decimal("5.00"), subtotal=Decimal("10.00"),
        )

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

    def test_admin_donation_records_are_not_available_to_provider(self):
        self.client.force_login(self.provider.user)
        self.assertEqual(self.client.get(reverse("admin_donation_list")).status_code, 302)
