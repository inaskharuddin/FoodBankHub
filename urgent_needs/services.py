from datetime import timedelta
from math import ceil

from django.db.models import Sum
from django.utils import timezone

from distribution.models import ProviderSupplier
from inventory.models import Inventory, SupplierProduct
from forecasting.models import current_forecasts
from .models import UrgentNeed


def sync_provider_urgent_needs(provider, days=7):
    """Refresh donor-facing needs from near-term forecast shortage and current stock."""
    relationship = ProviderSupplier.objects.filter(
        provider=provider, status="ACTIVE"
    ).select_related("supplier").first()
    if not relationship:
        return
    today = timezone.localdate()
    forecast_rows = list(current_forecasts(provider).filter(
        forecast_date__gt=today,
        forecast_date__lte=today + timedelta(days=days),
    ).values("item_id").annotate(demand=Sum("predicted_quantity")))
    stock_by_item = {row["item_id"]: row["total"] for row in Inventory.objects.filter(provider=provider).values("item_id").annotate(total=Sum("quantity"))}
    products = {
        product.item_id: product
        for product in SupplierProduct.objects.filter(
            supplier=relationship.supplier, status="ACTIVE",
        ).select_related("item")
    }
    active_needs = {
        need.item_id: need for need in UrgentNeed.objects.filter(
            provider=provider, status__in=["OPEN", "FUNDED", "UNAVAILABLE", "ORDERED"],
        )
    }
    dismissed_items = set(UrgentNeed.objects.filter(
        provider=provider, status="DISMISSED",
    ).values_list("item_id", flat=True))
    for need in active_needs.values():
        if need.status == "ORDERED":
            continue
        if need.item_id not in stock_by_item or need.item_id not in products:
            need.status = "UNAVAILABLE"
            need.remaining_quantity = 0
            need.save(update_fields=["status", "remaining_quantity"])
    for row in forecast_rows:
        if row["item_id"] in dismissed_items:
            continue
        product = products.get(row["item_id"])
        if not product:
            continue
        buffered_demand = ceil(max(float(row["demand"] or 0), 0) * 1.1)
        stock = int(stock_by_item.get(row["item_id"], 0) or 0)
        shortage = max(buffered_demand - stock, 0)
        need = active_needs.get(row["item_id"])
        if need and need.status == "ORDERED":
            continue
        if need and need.provider_managed:
            if stock >= need.required_quantity and need.status == "OPEN" and need.funded_quantity == 0:
                need.status = "FULFILLED"
                need.remaining_quantity = 0
                need.save(update_fields=["status", "remaining_quantity"])
            continue
        if shortage <= 0:
            if need and need.status == "OPEN" and need.funded_quantity == 0:
                need.status = "FULFILLED"
                need.remaining_quantity = 0
                need.save(update_fields=["status", "remaining_quantity"])
            continue
        if not need:
            UrgentNeed.objects.create(
                provider=provider, item_id=row["item_id"],
                required_quantity=shortage, funded_quantity=0,
                remaining_quantity=shortage,
                target_amount=(product.price * shortage).quantize(product.price),
                funded_amount=0, status="OPEN",
            )
            continue
        required = max(shortage, need.funded_quantity)
        need.required_quantity = required
        need.remaining_quantity = max(required - need.funded_quantity, 0)
        need.target_amount = (product.price * required).quantize(product.price)
        need.status = "FUNDED" if need.remaining_quantity == 0 else "OPEN"
        need.save(update_fields=["required_quantity", "remaining_quantity", "target_amount", "status"])


