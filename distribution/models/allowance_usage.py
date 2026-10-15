from django.db import models
from accounts.models.needy import Needy
from accounts.models.provider import Provider
from inventory.models.item import Item


class AllowanceUsage(models.Model):
    allowance_id = models.BigAutoField(primary_key=True)

    needy = models.ForeignKey(
        Needy,
        on_delete=models.CASCADE,
        related_name="allowance_usage"
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="allowance_usage"
    )

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="allowance_usage"
    )

    week_start_date = models.DateField()

    allowed_quantity = models.PositiveIntegerField(default=0)
    used_quantity = models.PositiveIntegerField(default=0)
    remaining_quantity = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.needy.user.name} - {self.item.name}"
        