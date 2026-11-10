from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.views import role_required
from .models import UrgentNeed


@role_required("PROVIDER")
def provider_urgent_needs(request):
    from distribution.models import ProviderSupplier
    from donations.models import CartItem, DonationItem
    from orders.models import PurchaseOrder

    provider = request.user.provider_profile
    relationship = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").first()
    needs = UrgentNeed.objects.filter(provider=provider).select_related("item").order_by("status", "item__name")
    for need in needs:
        product = relationship.supplier.products.filter(item=need.item, status="ACTIVE").first() if relationship else None
        need.supplier_product_id = product.product_id if product else None
        need.suggested_order_quantity = min(need.required_quantity, product.stock) if product else 0
        need.progress_percent = int(need.funded_quantity * 100 / need.required_quantity) if need.required_quantity else 0
        need.can_edit = need.status in {"OPEN", "FUNDED", "UNAVAILABLE", "DISMISSED"}
        need.can_dismiss = (
            need.status not in {"ORDERED", "FULFILLED"}
            and need.funded_quantity == 0
            and not DonationItem.objects.filter(urgent_need=need, donation__status__in=["PAID", "PENDING"]).exists()
            and not CartItem.objects.filter(urgent_need=need, cart__status="ACTIVE").exists()
            and not PurchaseOrder.objects.filter(provider=provider, items__product__item=need.item, status__in=["PENDING", "ACCEPTED", "SHIPPED", "DELIVERED"]).exists()
        )
    return render(request, "urgent_needs/provider_needs.html", {"needs": needs})


@role_required("PROVIDER")
def provider_urgent_need_edit(request, need_id):
    from distribution.models import ProviderSupplier

    provider = request.user.provider_profile
    need = get_object_or_404(UrgentNeed.objects.select_related("item"), urgent_need_id=need_id, provider=provider)
    if need.status not in {"OPEN", "FUNDED", "UNAVAILABLE", "DISMISSED"}:
        messages.error(request, "This need can no longer be edited because it has already been ordered or fulfilled.")
        return redirect("provider_urgent_needs")
    relationship = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").first()
    product = relationship.supplier.products.filter(item=need.item, status="ACTIVE").first() if relationship else None
    if not product:
        messages.error(request, "Select an active supplier that offers this item before editing its need.")
        return redirect("provider_urgent_needs")

    error = ""
    if request.method == "POST":
        with transaction.atomic():
            need = get_object_or_404(UrgentNeed.objects.select_for_update().select_related("item"), urgent_need_id=need_id, provider=provider)
            raw_quantity = request.POST.get("required_quantity", "").strip()
            if not raw_quantity.isascii() or not raw_quantity.isdecimal() or int(raw_quantity) <= 0:
                error = "Enter a whole-number need quantity greater than zero."
            elif int(raw_quantity) < need.funded_quantity:
                error = f"The target cannot be lower than the {need.funded_quantity} unit(s) already funded."
            elif need.status not in {"OPEN", "FUNDED", "UNAVAILABLE", "DISMISSED"}:
                error = "This need can no longer be edited because it has already been ordered or fulfilled."
            else:
                required = int(raw_quantity)
                need.required_quantity = required
                need.remaining_quantity = max(required - need.funded_quantity, 0)
                need.target_amount = (product.price * required).quantize(Decimal("0.01"))
                need.status = "FUNDED" if need.remaining_quantity == 0 else "OPEN"
                need.provider_managed = True
                need.save(update_fields=["required_quantity", "remaining_quantity", "target_amount", "status", "provider_managed"])
                messages.success(request, f"Updated the {need.item.name} need.")
                return redirect("provider_urgent_needs")

    return render(request, "urgent_needs/provider_need_edit.html", {
        "need": need, "product": product, "error": error,
    })


@role_required("PROVIDER")
@require_POST
def provider_urgent_need_delete(request, need_id):
    from donations.models import CartItem, DonationItem
    from orders.models import PurchaseOrder

    provider = request.user.provider_profile
    with transaction.atomic():
        need = get_object_or_404(UrgentNeed.objects.select_for_update().select_related("item"), urgent_need_id=need_id, provider=provider)
        has_paid_or_pending_donations = DonationItem.objects.filter(
            urgent_need=need, donation__status__in=["PAID", "PENDING"],
        ).exists()
        has_active_cart = CartItem.objects.filter(urgent_need=need, cart__status="ACTIVE").exists()
        has_order = PurchaseOrder.objects.filter(
            provider=provider, items__product__item=need.item,
            status__in=["PENDING", "ACCEPTED", "SHIPPED", "DELIVERED"],
        ).exists()
        if need.status in {"ORDERED", "FULFILLED"} or need.funded_quantity or has_paid_or_pending_donations or has_active_cart or has_order:
            messages.error(request, "This need cannot be removed while it has donor funding, an active donor cart, or a supplier order. Keep it so those records remain connected.")
            return redirect("provider_urgent_needs")
        need.status = "DISMISSED"
        need.remaining_quantity = 0
        need.provider_managed = True
        need.save(update_fields=["status", "remaining_quantity", "provider_managed"])
    messages.success(request, f"Dismissed the {need.item.name} need. It will no longer appear on the donor page.")
    return redirect("provider_urgent_needs")
