from django.db import models
from accounts.models.user import User
from .cart import Cart


class Donation(models.Model):
    donation_id = models.BigAutoField(primary_key=True)

    donor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="donations"
    )

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="donations"
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        default="PENDING"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Donation {self.donation_id}"
        