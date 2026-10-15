from django.db import models
from accounts.models.supplier import Supplier
from .purchase_order import PurchaseOrder


class Payout(models.Model):
    payout_id = models.BigAutoField(primary_key=True)

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="payouts"
    )

    po = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="payouts"
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        default="PENDING"
    )

    transfer_reference = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["po"], name="unique_payout_per_purchase_order"),
        ]

    def __str__(self):
        return f"Payout {self.payout_id}"
