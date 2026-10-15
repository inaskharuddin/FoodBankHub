import base64
import hashlib
import hmac
import json
import os
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.views import role_required
from .models import Cart, Donation, DonationItem, Transaction


SANDBOX_API = "https://www.billplz-sandbox.com/api/v3/bills"


def _billplz_signature(data):
    signature = data.get("x_signature", "")
    if not signature or not settings.BILLPLZ_X_SIGNATURE_KEY:
        return False
    parts = [f"{key}{value}" for key, value in data.items() if key != "x_signature"]
    parts.sort(key=str.casefold)
    source = "|".join(parts).encode("utf-8")
    expected = hmac.new(settings.BILLPLZ_X_SIGNATURE_KEY.encode("utf-8"), source, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _create_bill(donation, transaction_record, request):
    api_key = settings.BILLPLZ_SANDBOX_API_KEY
    collection_id = settings.BILLPLZ_SANDBOX_COLLECTION_ID
    if not api_key or not collection_id or not settings.BILLPLZ_X_SIGNATURE_KEY:
        raise RuntimeError("Billplz sandbox is not configured. Set the sandbox API key, collection ID, and X Signature key.")

    public_base = settings.BILLPLZ_PUBLIC_BASE_URL or request.build_absolute_uri("/").rstrip("/")
    callback_url = f"{public_base}/donations/billplz/callback/"
    redirect_url = f"{public_base}/donations/complete/"
    params = urlencode({
        "collection_id": collection_id,
        "email": donation.donor.email,
        "name": donation.donor.name,
        "amount": int(donation.total_amount * 100),
        "description": f"FoodBankHub donation {donation.donation_id}",
        "callback_url": callback_url,
        "redirect_url": redirect_url,
        "reference_1": str(donation.donation_id),
        "reference_1_label": "Donation ID",
    }).encode("utf-8")
    auth = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    api_request = Request(SANDBOX_API, data=params, headers={"Authorization": f"Basic {auth}"})
    with urlopen(api_request, timeout=20) as response:
        bill = json.loads(response.read().decode("utf-8"))
    if not bill.get("id") or not bill.get("url"):
        raise RuntimeError("Billplz sandbox returned an incomplete bill response.")
    transaction_record.gateway_reference = bill["id"]
    transaction_record.save(update_fields=["gateway_reference"])
    return bill["url"]


@role_required("DONOR")
@require_POST
def donation_checkout(request, cart_id):
    cart = get_object_or_404(Cart, cart_id=cart_id, donor=request.user, status="ACTIVE")
    items = list(cart.items.select_related("urgent_need__item", "provider"))
    if not items:
        return render(request, "donations/checkout_error.html", {"error": "This cart has no items."}, status=400)

    amount = sum((item.subtotal for item in items), Decimal("0.00")).quantize(Decimal("0.01"))
    if amount <= 0:
        return render(request, "donations/checkout_error.html", {"error": "The donation amount must be greater than zero."}, status=400)

    with transaction.atomic():
        donation = cart.donations.filter(status="PENDING").first()
        if donation is None:
            donation = Donation.objects.create(donor=request.user, cart=cart, total_amount=amount)
            DonationItem.objects.bulk_create([
                DonationItem(
                    donation=donation, provider=item.provider, urgent_need=item.urgent_need,
                    item=item.urgent_need.item, quantity=item.quantity, price=item.price,
                ) for item in items
            ])
        elif donation.total_amount != amount:
            return render(request, "donations/checkout_error.html", {"error": "This cart changed after checkout began. Please contact the platform administrator."}, status=409)
        payment = donation.transactions.order_by("-transaction_id").first()
        if payment is None:
            payment = Transaction.objects.create(
                donation=donation, amount=donation.total_amount, payment_method="FPX",
            )
        if payment.gateway_reference:
            return redirect(f"https://www.billplz-sandbox.com/bills/{payment.gateway_reference}")

    try:
        return redirect(_create_bill(donation, payment, request))
    except (RuntimeError, HTTPError, URLError, TimeoutError, ValueError) as exc:
        return render(request, "donations/checkout_error.html", {"error": str(exc)}, status=503)


@csrf_exempt
@require_POST
def billplz_callback(request):
    data = request.POST.dict()
    if not _billplz_signature(data):
        return HttpResponseBadRequest("Invalid Billplz signature.")

    bill_id = data.get("id")
    if not bill_id:
        return HttpResponseBadRequest("Missing bill ID.")
    try:
        with transaction.atomic():
            payment = Transaction.objects.select_for_update().select_related("donation").get(gateway_reference=bill_id)
            expected_amount = int(payment.amount * 100)
            if data.get("amount") and int(data["amount"]) != expected_amount:
                return HttpResponseBadRequest("Bill amount does not match donation.")
            if data.get("paid", "").casefold() == "true" or data.get("state", "").casefold() == "paid":
                if payment.status != "PAID":
                    payment.status = "PAID"
                    payment.fpx_reference = data.get("transaction_id", "")[:100]
                    payment.save(update_fields=["status", "fpx_reference"])
                    payment.donation.status = "PAID"
                    payment.donation.save(update_fields=["status"])
                    payment.donation.cart.status = "COMPLETED"
                    payment.donation.cart.save(update_fields=["status"])
            elif payment.status == "PENDING":
                payment.status = "FAILED"
                payment.save(update_fields=["status"])
                payment.donation.status = "FAILED"
                payment.donation.save(update_fields=["status"])
    except Transaction.DoesNotExist:
        return HttpResponseBadRequest("Unknown bill ID.")
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid bill amount.")
    return HttpResponse("OK")


@role_required("DONOR")
def donation_complete(request):
    return render(request, "donations/checkout_complete.html")


@role_required("ADMIN")
def admin_donation_list(request):
    donations = Donation.objects.select_related("donor").prefetch_related("transactions").order_by("-created_at")
    return render(request, "donations/admin_donation_list.html", {"donations": donations})
