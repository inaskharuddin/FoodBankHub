from django.db import models

from accounts.models.provider import Provider
from accounts.models.supplier import Supplier
from inventory.models.item import Item


class HistoricalData(models.Model):
    class Source(models.TextChoices):
        ACTUAL = "ACTUAL", "Actual"
        ESTIMATED = "ESTIMATED", "Estimated"

    history_id = models.BigAutoField(primary_key=True)
    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="historical_data"
    )
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name="historical_data"
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        related_name="historical_data",
        null=True,
        blank=True,
    )
    date = models.DateField()
    quantity = models.PositiveIntegerField(default=0)
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.ACTUAL
    )

    class Meta:
        indexes = [models.Index(
            fields=("provider", "date"), name="forecast_h_provider_4aa923_idx"
        )]

    def __str__(self):
        return f"{self.provider.food_bank_name} - {self.item.name} - {self.date} ({self.source})"
