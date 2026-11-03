from django.db import models

from accounts.models.provider import Provider
from inventory.models.item import Item


class LowStockAlert(models.Model):
    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="low_stock_alerts",
    )
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name="low_stock_alerts",
    )
    forecast_days = models.PositiveSmallIntegerField(choices=((7, "7 days"), (30, "30 days")))
    is_active = models.BooleanField(default=False)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=10, default="NORMAL")
    is_read = models.BooleanField(default=False)
    message = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "item", "forecast_days"),
                name="unique_provider_item_low_stock_window",
            ),
        ]

    def __str__(self):
        return f"{self.provider} - {self.item} ({self.forecast_days} days)"
