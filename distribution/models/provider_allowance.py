from django.db import models
from accounts.models.provider import Provider
from inventory.models.item import Item

class ProviderAllowance(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="allowance_limits")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="provider_allowance_limits")
    weekly_limit = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider", "item"), name="unique_provider_item_allowance")]
    def __str__(self): return f"{self.provider} · {self.item}: {self.weekly_limit}"
