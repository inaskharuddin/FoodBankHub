from django.db import models

from .donation_item import DonationItem
from orders.models.po_item import POItem


class DonationOrderAllocation(models.Model):
    """Quantity of one donor contribution fulfilled by one supplier order line."""
    donation_item = models.ForeignKey(DonationItem, on_delete=models.CASCADE, related_name="order_allocations")
    purchase_order_item = models.ForeignKey(POItem, on_delete=models.CASCADE, related_name="donation_allocations")
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [models.CheckConstraint(check=models.Q(quantity__gt=0), name="donation_order_allocation_positive")]

