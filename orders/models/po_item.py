from django.db import models
from .purchase_order import PurchaseOrder
from inventory.models.supplier_product import SupplierProduct


class POItem(models.Model):
    po_item_id = models.BigAutoField(primary_key=True)

    po = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        SupplierProduct,
        on_delete=models.CASCADE,
        related_name="po_items"
    )

    quantity = models.PositiveIntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"PO {self.po.po_id} - {self.product.item.name}"