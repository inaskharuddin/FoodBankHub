from django.db import models
from .donation import Donation


class Transaction(models.Model):
    transaction_id = models.BigAutoField(primary_key=True)

    donation = models.ForeignKey(
        Donation,
        on_delete=models.CASCADE,
        related_name="transactions"
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    payment_method = models.CharField(
        max_length=50
    )

    fpx_reference = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    gateway_reference = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
    )

    status = models.CharField(
        max_length=20,
        default="PENDING"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction {self.transaction_id}"
        
