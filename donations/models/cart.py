from django.db import models
from accounts.models.user import User


class Cart(models.Model):
    cart_id = models.BigAutoField(primary_key=True)

    donor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="carts"
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=20,
        default="ACTIVE"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart {self.cart_id}"