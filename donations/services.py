from django.db import transaction
from django.db.models import Sum

from .models import DonationItem, DonationOrderAllocation
from orders.models import POItem


@transaction.atomic
def allocate_paid_donations_to_order(order):
    """Allocate paid donor quantities against matching PO lines without exceeding either side."""
    for line in POItem.objects.select_for_update().filter(po=order).select_related("product__item"):
        allocated = DonationOrderAllocation.objects.filter(purchase_order_item=line).aggregate(total=Sum("quantity"))["total"] or 0
        available = line.quantity - allocated
        candidates = DonationItem.objects.select_for_update().filter(
            donation__status="PAID", provider=order.provider, item=line.product.item,
        ).order_by("donation__created_at", "donation_item_id")
        for donor_item in candidates:
            used = DonationOrderAllocation.objects.filter(donation_item=donor_item).aggregate(total=Sum("quantity"))["total"] or 0
            quantity = min(available, donor_item.quantity - used)
            if quantity > 0:
                DonationOrderAllocation.objects.create(donation_item=donor_item, purchase_order_item=line, quantity=quantity)
                available -= quantity
            if available <= 0:
                break
