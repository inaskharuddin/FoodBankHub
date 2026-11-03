from django.db import models
from accounts.models.provider import Provider
from .item import Item


class Inventory(models.Model):
    inventory_id = models.BigAutoField(primary_key=True)

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="inventory_items"
    )

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="inventory_records"
    )

    quantity = models.PositiveIntegerField(default=0)

    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    threshold_level = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.provider.food_bank_name} - {self.item.name}"