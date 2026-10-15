from django.db import models
from accounts.models.provider import Provider
from inventory.models.item import Item


class UrgentNeed(models.Model):
    urgent_need_id = models.BigAutoField(primary_key=True)

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="urgent_needs"
    )

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="urgent_needs"
    )

    required_quantity = models.PositiveIntegerField()
    funded_quantity = models.PositiveIntegerField(default=0)
    remaining_quantity = models.PositiveIntegerField(default=0)

    target_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    funded_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=20,
        default="OPEN"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider.food_bank_name} - {self.item.name}"