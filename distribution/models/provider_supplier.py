from django.db import models
from accounts.models.provider import Provider
from accounts.models.supplier import Supplier


class ProviderSupplier(models.Model):
    provider_supplier_id = models.BigAutoField(primary_key=True)

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="supplier_relationships"
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="provider_relationships"
    )

    selected_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        default="ACTIVE"
    )

    def __str__(self):
        return f"{self.provider.food_bank_name} - {self.supplier.business_name}"