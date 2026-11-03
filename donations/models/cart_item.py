from django.db import models
from .cart import Cart
from accounts.models.provider import Provider
from urgent_needs.models.urgent_need import UrgentNeed


class CartItem(models.Model):
    cart_item_id = models.BigAutoField(primary_key=True)

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items"
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="cart_items"
    )

    urgent_need = models.ForeignKey(
        UrgentNeed,
        on_delete=models.CASCADE,
        related_name="cart_items"
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
        return f"Cart {self.cart.cart_id} - {self.urgent_need.item.name}"