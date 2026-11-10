import base64
import hashlib
import hmac
import json
import textwrap
from django.db.models import Avg, Sum
from django.urls import reverse
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.mail import EmailMessage
from django.utils import timezone
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.views import role_required
from urgent_needs.models import UrgentNeed
from .models import Cart, CartItem, Donation, DonationItem, ProviderReview, Transaction
from accounts.models import Provider, User
from distribution.models import ProviderSupplier, Report
from orders.models import PurchaseOrder


SANDBOX_API = "https://www.billplz-sandbox.com/api/v3/bills"


@role_required("DONOR")
def donor_profile(request):
    saved = False
    error = ""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        if not name or len(name) > 100:
            error = "Enter your name using 100 characters or fewer."
        else:
            try:
                validate_email(email)
            except ValidationError:
                error = "Enter a valid email address."
        if not error and User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
            error = "That email address is already in use."
        if not error:
            request.user.name = name
            request.user.email = email
            request.user.save(update_fields=["name", "email"])
            messages.success(request, "Your donor profile has been updated.")
            return redirect("donor_profile")
    return render(request, "donations/donor_profile.html", {"saved": saved, "error": error})


@role_required("DONOR")
def donor_needs(request):
    providers = Provider.objects.filter(
        is_approved=True, user__is_active=True,
    ).select_related("user").order_by("food_bank_name")
    return render(request, "donations/donor_needs.html", {"providers": providers})


@role_required("DONOR")
@require_POST
def add_need_to_cart(request, need_id):
    quantity_text = request.POST.get("quantity", "1").strip()
    if not quantity_text.isascii() or not quantity_text.isdecimal() or int(quantity_text) < 1:
        return render(request, "donations/checkout_error.html", {
            "error": "Choose a whole-number quantity greater than zero.",
        }, status=400)
    quantity = int(quantity_text)

    with transaction.atomic():
        need = get_object_or_404(
            UrgentNeed.objects.select_for_update().select_related("item", "provider"),
            urgent_need_id=need_id, status="OPEN", remaining_quantity__gt=0,
            required_quantity__gt=0,
        )
        relationship = ProviderSupplier.objects.filter(provider=need.provider, status="ACTIVE").select_related("supplier").first()
        product = relationship.supplier.products.filter(item=need.item, status="ACTIVE").first() if relationship else None
        if not product:
            return render(request, "donations/checkout_error.html", {"error": "This food item is not available from the active supplier."}, status=409)
        current_price = product.price
        cart = Cart.objects.filter(donor=request.user, status="ACTIVE").order_by("-created_at").first()
        if cart is None:
            cart = Cart.objects.create(donor=request.user, status="ACTIVE")
        if cart.donations.filter(status="PENDING").exists():
            return render(request, "donations/checkout_error.html", {
                "error": "This cart already has a pending payment. Please finish or contact the platform administrator before changing it.",
            }, status=409)
        existing_provider_ids = set(cart.items.values_list("provider_id", flat=True).distinct())
        if existing_provider_ids and existing_provider_ids != {need.provider_id}:
            return render(request, "donations/checkout_error.html", {
                "error": "Each FPX payment can support one food bank only. Finish or clear the current food bank's cart before adding another.",
            }, status=409)
        item, created = CartItem.objects.select_for_update().get_or_create(
            cart=cart, urgent_need=need,
            defaults={
                "provider": need.provider, "quantity": quantity,
                "price": current_price,
                "subtotal": Decimal("0.00"),
            },
        )
        total_quantity = quantity if created else item.quantity + quantity
        if total_quantity > need.remaining_quantity:
            return render(request, "donations/checkout_error.html", {
                "error": f"Only {need.remaining_quantity} unit(s) remain for this need.",
            }, status=400)
        if not created:
            item.quantity = total_quantity
        item.subtotal = (item.price * item.quantity).quantize(Decimal("0.01"))
        item.save()
        cart.total_amount = sum(cart.items.values_list("subtotal", flat=True), Decimal("0.00"))
        cart.save(update_fields=["total_amount"])
    return redirect("provider_public_profile", provider_id=need.provider_id)


@role_required("DONOR")
def provider_directory(request):
    providers = Provider.objects.filter(is_approved=True, user__is_active=True).select_related("user").order_by("food_bank_name")
    provider_data = []
    for provider in providers:
        provider_data.append({
            "provider": provider,
            "lat": float(provider.latitude) if provider.latitude is not None else None,
            "lng": float(provider.longitude) if provider.longitude is not None else None,
        })
    return render(request, "donations/provider_directory.html", {
        "provider_data": provider_data,
        "map_providers": [{
            "name": d["provider"].food_bank_name,
            "address": d["provider"].address,
            "lat": d["lat"], "lng": d["lng"],
            "url": reverse("provider_public_profile", args=[d["provider"].provider_id]),
        } for d in provider_data if d["lat"] is not None and d["lng"] is not None],
    })

@role_required("DONOR")
def provider_public_profile(request, provider_id):
    provider = get_object_or_404(Provider.objects.select_related("user"), provider_id=provider_id)
    relationship = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").first()
    product_by_item = {
        product.item_id: product
        for product in relationship.supplier.products.filter(status="ACTIVE", image__gt="").select_related("item")
    } if relationship else {}
    needs = [need for need in provider.urgent_needs.filter(
        status="OPEN", remaining_quantity__gt=0,
    ).select_related("item").order_by("created_at") if need.item_id in product_by_item]
    for need in needs:
        need.progress_percent = int(need.funded_quantity * 100 / need.required_quantity) if need.required_quantity else 0
        need.product = product_by_item[need.item_id]
        need.supplier_name = relationship.supplier.business_name
    relationships = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").prefetch_related("supplier__products__item")
    suppliers = [{
        "supplier": rel.supplier,
        "products": rel.supplier.products.filter(status="ACTIVE", image__gt="").select_related("item"),
    } for rel in relationships]
    return render(request, "donations/provider_profile.html", {
        "provider": provider, "needs": needs, "suppliers": suppliers,
        "average_rating": provider.donor_reviews.aggregate(avg=Avg("rating"))["avg"],
        "review_count": provider.donor_reviews.count(),
    })


@role_required("DONOR")
def donor_cart(request):
    cart = Cart.objects.filter(donor=request.user, status="ACTIVE").order_by("-created_at").first()
    if cart and not cart.donations.filter(status="PENDING").exists():
        _refresh_cart_prices(cart)
    if request.method == "POST":
        if cart is None:
            return redirect("donor_cart")
        item = get_object_or_404(CartItem.objects.select_related("cart", "urgent_need"), cart=cart, cart_item_id=request.POST.get("item_id"))
        if cart.donations.filter(status="PENDING").exists():
            return render(request, "donations/checkout_error.html", {"error": "This cart has a pending payment and cannot be changed."}, status=409)
        action = request.POST.get("action")
        if action == "remove":
            item.delete()
        elif action == "update":
            raw = request.POST.get("quantity", "")
            if not raw.isascii() or not raw.isdecimal() or int(raw) < 1 or int(raw) > item.urgent_need.remaining_quantity:
                return render(request, "donations/checkout_error.html", {"error": "Choose a quantity between 1 and the remaining need."}, status=400)
            item.quantity = int(raw)
            item.subtotal = (item.price * item.quantity).quantize(Decimal("0.01"))
            item.save(update_fields=["quantity", "subtotal"])
        cart.total_amount = sum(cart.items.values_list("subtotal", flat=True), Decimal("0.00"))
        cart.save(update_fields=["total_amount"])
        return redirect("donor_cart")
    items = cart.items.select_related("provider", "urgent_need__item") if cart else []
    for item in items:
        relation = ProviderSupplier.objects.filter(provider=item.provider, status="ACTIVE").select_related("supplier").first()
        product = relation.supplier.products.filter(item=item.urgent_need.item, status="ACTIVE").first() if relation else None
        item.product_image = product.image if product and product.image else None
        item.supplier_name = relation.supplier.business_name if relation else ""
    return render(request, "donations/donor_cart.html", {"cart": cart, "items": items})


def _refresh_cart_prices(cart):
    """Keep an unpaid cart aligned with each provider's current supplier catalog."""
    with transaction.atomic():
        for item in cart.items.select_related("provider", "urgent_need__item"):
            relation = ProviderSupplier.objects.filter(
                provider=item.provider, status="ACTIVE",
            ).select_related("supplier").first()
            product = relation.supplier.products.filter(
                item=item.urgent_need.item, status="ACTIVE",
            ).first() if relation else None
            if product is None:
                item.delete()
                continue
            item.price = product.price
            item.subtotal = (product.price * item.quantity).quantize(Decimal("0.01"))
            item.save(update_fields=["price", "subtotal"])
        cart.total_amount = sum(cart.items.values_list("subtotal", flat=True), Decimal("0.00"))
        cart.save(update_fields=["total_amount"])


def _donation_item_progress(donation_item):
    donation_item.can_rate = False
    donation_item.status_is_estimated = False
    need = donation_item.urgent_need
    if donation_item.donation.status != "PAID":
        return "Payment pending"
    if need.funded_quantity < need.required_quantity:
        return "Pending Collection"
    allocations = list(donation_item.order_allocations.select_related("purchase_order_item__po__supplier", "purchase_order_item__po").order_by("purchase_order_item__po__created_at"))
    orders = list({allocation.purchase_order_item.po for allocation in allocations})
    if not orders:
        donation_item.supplier_name = ""
        if not donation_item.link_tracking_enabled and need.funded_quantity >= need.required_quantity:
            donation_item.status_is_estimated = True
            legacy_order = PurchaseOrder.objects.filter(
                provider=donation_item.provider, items__product__item=donation_item.item,
            ).select_related("supplier").order_by("-created_at").first()
            if legacy_order:
                donation_item.supplier_name = legacy_order.supplier.business_name
                if legacy_order.status in {"PENDING", "ACCEPTED"}:
                    return "Ordered from Supplier (estimated)"
                if legacy_order.status == "SHIPPED":
                    return "Shipped (estimated)"
                if legacy_order.status == "DELIVERED" and not legacy_order.delivery_confirmed:
                    donation_item.can_rate = True
                    return "Delivered to Provider (estimated)"
                if legacy_order.delivery_confirmed:
                    donation_item.can_rate = True
                    legacy_reports = Report.objects.filter(provider=donation_item.provider, item=donation_item.item, status__in=["DISTRIBUTED", "COMPLETED"])
                    donation_item.families_helped = legacy_reports.values("needy_id").distinct().count()
                    if donation_item.families_helped:
                        return "Distributed to Needy (estimated)"
                    return "Delivered to Provider (estimated)"
            return "Fully Funded (estimated; legacy order link unavailable)"
        return "Fully Funded"
    donation_item.supplier_name = ", ".join(sorted({order.supplier.business_name for order in orders}))
    if any(order.status in {"PENDING", "ACCEPTED"} for order in orders):
        return "Ordered from Supplier"
    if any(order.status == "SHIPPED" for order in orders):
        return "Shipped"
    if any(order.status == "DELIVERED" and not order.delivery_confirmed for order in orders):
        donation_item.can_rate = True
        return "Delivered to Provider"
    reports = Report.objects.filter(
        status__in=["DISTRIBUTED", "COMPLETED"],
        stock_allocations__donation_order_allocation__donation_item=donation_item,
    )
    donation_item.families_helped = reports.values("needy_id").distinct().count()
    if donation_item.families_helped:
        donation_item.can_rate = True
        return "Distributed to Needy"
    if all(order.delivery_confirmed for order in orders):
        donation_item.can_rate = True
        return "Delivered to Provider"
    return "Fully Funded"


@role_required("DONOR")
def donation_history(request):
    donations = Donation.objects.filter(donor=request.user).prefetch_related(
        "transactions", "items__item", "items__provider", "items__urgent_need",
    ).order_by("-created_at")
    entries = []
    for donation in donations:
        items = list(donation.items.all())
        for item in items:
            item.display_status = _donation_item_progress(item)
        entries.append({"donation": donation, "items": items})
    return render(request, "donations/donor_history.html", {"entries": entries})


@role_required("DONOR")
@require_POST
def rate_provider(request, donation_id, provider_id):
    donation = get_object_or_404(Donation, donation_id=donation_id, donor=request.user, status="PAID")
    provider = get_object_or_404(Provider, provider_id=provider_id)
    from .models import DonationOrderAllocation
    linked = DonationOrderAllocation.objects.filter(
        donation_item__donation=donation, donation_item__provider=provider,
        purchase_order_item__po__delivery_confirmed=True,
    ).exists()
    legacy = not donation.items.filter(link_tracking_enabled=True, provider=provider).exists()
    estimated_match = legacy and PurchaseOrder.objects.filter(
        provider=provider, delivery_confirmed=True,
        items__product__item__in=donation.items.filter(provider=provider).values("item_id"),
    ).exists()
    has_delivered_order = linked or estimated_match
    if not has_delivered_order:
        return render(request, "donations/checkout_error.html", {"error": "You can review a provider after an associated order is delivered and confirmed."}, status=400)
    raw_rating = request.POST.get("rating", "")
    if raw_rating not in {"1", "2", "3", "4", "5"}:
        return render(request, "donations/checkout_error.html", {"error": "Choose a rating from 1 to 5."}, status=400)
    ProviderReview.objects.update_or_create(
        donation=donation, provider=provider,
        defaults={"donor": request.user, "rating": int(raw_rating), "comment": request.POST.get("comment", "").strip()[:500]},
    )
    return redirect("donation_history")


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
    missing_settings = [
        name for name, value in (
            ("BILLPLZ_SANDBOX_API_KEY", api_key),
            ("BILLPLZ_SANDBOX_COLLECTION_ID", collection_id),
            ("BILLPLZ_X_SIGNATURE_KEY", settings.BILLPLZ_X_SIGNATURE_KEY),
        )
        if not value
    ]
    if missing_settings:
        raise RuntimeError(
            "Billplz sandbox is not configured. Django did not receive: "
            + ", ".join(missing_settings)
            + "."
        )

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
    if not cart.donations.filter(status="PENDING").exists():
        _refresh_cart_prices(cart)
    items = list(cart.items.select_related("urgent_need__item", "provider"))
    if not items:
        return render(request, "donations/checkout_error.html", {"error": "This cart has no items."}, status=400)
    if len({item.provider_id for item in items}) != 1:
        return render(request, "donations/checkout_error.html", {
            "error": "Each FPX transaction must contain items for one food bank only. Remove items from other food banks before checkout.",
        }, status=409)

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
            if not data.get("amount"):
                return HttpResponseBadRequest("Missing bill amount.")
            if int(data["amount"]) != expected_amount:
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
                    for donated_item in payment.donation.items.select_related("urgent_need"):
                        need = UrgentNeed.objects.select_for_update().get(pk=donated_item.urgent_need_id)
                        funded = min(need.required_quantity, need.funded_quantity + donated_item.quantity)
                        unit_amount = (need.target_amount / need.required_quantity) if need.required_quantity else Decimal("0.00")
                        funded_amount = min(need.target_amount, need.funded_amount + unit_amount * donated_item.quantity)
                        need.funded_quantity = funded
                        need.remaining_quantity = max(need.required_quantity - funded, 0)
                        need.funded_amount = funded_amount.quantize(Decimal("0.01"))
                        if need.remaining_quantity == 0:
                            need.status = "FUNDED"
                        need.save(update_fields=["funded_quantity", "remaining_quantity", "funded_amount", "status"])
                    from .services import allocate_paid_donations_to_order
                    providers = payment.donation.items.values_list("provider_id", flat=True).distinct()
                    items = payment.donation.items.values_list("item_id", flat=True).distinct()
                    for order in PurchaseOrder.objects.filter(provider_id__in=providers, items__product__item_id__in=items).distinct():
                        allocate_paid_donations_to_order(order)
                    donation = payment.donation
                    donation.receipt_pdf = _build_donation_receipt(donation)
                    donation.receipt_generated_at = timezone.now()
                    donation.save(update_fields=["receipt_pdf", "receipt_generated_at"])
                    _email_donation_receipt(donation)
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
    donations = Donation.objects.filter(donor=request.user).order_by("-created_at")[:10]
    return render(request, "donations/checkout_complete.html", {"donations": donations})


def _make_pdf(lines):
    def pdf_text(value):
        safe = str(value).encode("latin-1", "replace").decode("latin-1")
        return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(str(line), width=78) or [""])
    pages = [wrapped[i:i + 36] for i in range(0, len(wrapped), 36)] or [[]]
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_index, page_lines in enumerate(pages):
        page_id = 4 + 2 * page_index
        content_id = page_id + 1
        commands = ["BT", "/F1 12 Tf", "50 790 Td"]
        for index, line in enumerate(page_lines):
            if index:
                commands.append("0 -20 Td")
            commands.append(f"({pdf_text(line)}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        objects[page_id] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        objects[content_id] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (len(objects) + 1)
    for index, obj in objects.items():
        offsets[index] = len(pdf)
        pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode())
    return bytes(pdf)


def _build_donation_receipt(donation):
    lines = ["FoodBankHub Donation Receipt", f"Receipt for donation #{donation.donation_id}", f"Donor: {donation.donor.name} ({donation.donor.email})", f"Date: {donation.created_at:%Y-%m-%d}", f"Amount: RM {donation.total_amount:.2f}", "Items:"]
    lines.extend(f"{item.quantity} {item.item.unit} {item.item.name} — {item.provider.food_bank_name}" for item in donation.items.select_related("item", "provider"))
    lines.extend(["", "Tax note: This receipt confirms payment only. Tax deduction eligibility depends on the recipient's current LHDN approval.", "This document does not by itself certify tax deductibility."])
    return _make_pdf(lines)


def _email_donation_receipt(donation):
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD or donation.receipt_email_sent_at:
        return
    message = EmailMessage(
        subject=f"FoodBankHub donation receipt #{donation.donation_id}",
        body="Thank you for your donation. Your payment receipt is attached.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[donation.donor.email],
    )
    message.attach(f"foodbankhub-donation-{donation.donation_id}.pdf", bytes(donation.receipt_pdf), "application/pdf")
    if message.send(fail_silently=True):
        donation.receipt_email_sent_at = timezone.now()
        donation.save(update_fields=["receipt_email_sent_at"])


@role_required("DONOR")
def donation_receipt(request, donation_id):
    donation = get_object_or_404(Donation.objects.prefetch_related("items__item", "items__provider"), donation_id=donation_id, donor=request.user, status="PAID")
    lines = ["FoodBankHub Donation Receipt", f"Receipt for donation #{donation.donation_id}", f"Donor: {request.user.name} ({request.user.email})", f"Date: {donation.created_at:%Y-%m-%d}", f"Amount: RM {donation.total_amount:.2f}", "Items:"]
    lines.extend(f"{item.quantity} {item.item.unit} {item.item.name} — {item.provider.food_bank_name}" for item in donation.items.all())
    lines.extend(["", "Tax note: This receipt confirms payment only. Tax deduction eligibility depends on the recipient's current LHDN approval.", "This document does not by itself certify tax deductibility."])
    response = HttpResponse(bytes(donation.receipt_pdf) if donation.receipt_pdf else _make_pdf(lines), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="foodbankhub-donation-{donation.donation_id}.pdf"'
    return response


@role_required("DONOR")
def impact_certificate(request):
    from donations.models import DonationItem
    paid = Donation.objects.filter(donor=request.user, status="PAID")
    total = paid.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    kilos = sum(row["quantity"] for row in DonationItem.objects.filter(donation__in=paid, item__unit__iexact="kg").values("quantity"))
    people = int(kilos / 2)
    lines = ["FoodBankHub Certificate of Impact", f"Presented to {request.user.name}", f"Lifetime donations: RM {total:.2f}", f"Food funded: {kilos} kg", f"Estimated people helped: {people}", "Estimate: 2 kg of food per person served."]
    response = HttpResponse(_make_pdf(lines), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="foodbankhub-impact-certificate.pdf"'
    return response


@role_required("ADMIN")
def admin_donation_list(request):
    donations = Donation.objects.select_related("donor").prefetch_related("transactions").order_by("-created_at")
    return render(request, "donations/admin_donation_list.html", {"donations": donations})


@role_required("ADMIN")
@require_POST
def admin_verify_failed_payment(request, transaction_id):
    reference = request.POST.get("bank_reference", "").strip()[:100]
    note = request.POST.get("verification_note", "").strip()[:500]
    if not reference or not note:
        return render(request, "donations/checkout_error.html", {"error": "Enter the verified bank reference and a short verification note."}, status=400)
    with transaction.atomic():
        try:
            payment = Transaction.objects.select_for_update().select_related("donation__cart", "donation__donor").get(
                transaction_id=transaction_id, status="FAILED", donation__status="FAILED",
            )
        except Transaction.DoesNotExist:
            return HttpResponseBadRequest("Only failed payments can be manually verified.")
        payment.status = "PAID"
        payment.fpx_reference = reference
        payment.verification_note = note
        payment.save(update_fields=["status", "fpx_reference", "verification_note"])
        donation = payment.donation
        donation.status = "PAID"
        donation.cart.status = "COMPLETED"
        donation.cart.save(update_fields=["status"])
        donation.save(update_fields=["status"])
        for donated_item in donation.items.select_related("urgent_need"):
            need = UrgentNeed.objects.select_for_update().get(pk=donated_item.urgent_need_id)
            funded = min(need.required_quantity, need.funded_quantity + donated_item.quantity)
            unit_amount = need.target_amount / need.required_quantity if need.required_quantity else Decimal("0.00")
            need.funded_quantity = funded
            need.remaining_quantity = max(need.required_quantity - funded, 0)
            need.funded_amount = min(need.target_amount, need.funded_amount + unit_amount * donated_item.quantity).quantize(Decimal("0.01"))
            if need.remaining_quantity == 0:
                need.status = "FUNDED"
            need.save(update_fields=["funded_quantity", "remaining_quantity", "funded_amount", "status"])
        providers = donation.items.values_list("provider_id", flat=True).distinct()
        items = donation.items.values_list("item_id", flat=True).distinct()
        from .services import allocate_paid_donations_to_order
        for order in PurchaseOrder.objects.filter(provider_id__in=providers, items__product__item_id__in=items).distinct():
            allocate_paid_donations_to_order(order)
        donation.receipt_pdf = _build_donation_receipt(donation)
        donation.receipt_generated_at = timezone.now()
        donation.save(update_fields=["receipt_pdf", "receipt_generated_at"])
        _email_donation_receipt(donation)
    from django.contrib import messages
    messages.success(request, f"Payment {transaction_id} was verified as received.")
    return redirect("admin_donation_list")



