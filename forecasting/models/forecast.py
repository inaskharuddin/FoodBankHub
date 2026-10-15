from django.db import models
from accounts.models.provider import Provider
from inventory.models.item import Item


class Forecast(models.Model):
    forecast_id = models.BigAutoField(primary_key=True)

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="forecasts"
    )

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="forecasts"
    )

    forecast_date = models.DateField()

    predicted_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    actual_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    mape_score = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    forecast_type = models.CharField(
        max_length=50
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.item.name} - {self.forecast_date}"