from django.db import models
from orders.models.inventory_lot import InventoryLot
from donations.models.order_allocation import DonationOrderAllocation
from .report import Report


class ReportLotAllocation(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="stock_allocations")
    inventory_lot = models.ForeignKey(InventoryLot, null=True, blank=True, on_delete=models.SET_NULL, related_name="distribution_allocations")
    donation_order_allocation = models.ForeignKey(DonationOrderAllocation, null=True, blank=True, on_delete=models.SET_NULL, related_name="distribution_allocations")
    quantity = models.PositiveIntegerField()
    estimated = models.BooleanField(default=False)

