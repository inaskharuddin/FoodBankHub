from django.db import models
from accounts.models.provider import Provider
from accounts.models.supplier import Supplier


class PurchaseOrder(models.Model):
    po_id = models.BigAutoField(primary_key=True)

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="purchase_orders"
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="purchase_orders"
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=20,
        default="PENDING"
    )

    delivery_confirmed = models.BooleanField(default=False)

    delivery_deadline = models.DateField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PO {self.po_id}"
