from django.db import models
from inventory.models.inventory import Inventory
from .po_item import POItem


class InventoryLot(models.Model):
    """Traceable received stock; null PO line means legacy/manual stock."""
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="lots")
    purchase_order_item = models.ForeignKey(POItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="inventory_lots")
    received_quantity = models.PositiveIntegerField()
    remaining_quantity = models.PositiveIntegerField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["purchase_order_item"], name="unique_inventory_lot_per_po_item")]

