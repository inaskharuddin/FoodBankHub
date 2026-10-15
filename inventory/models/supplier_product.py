from django.db import models
from accounts.models.supplier import Supplier
from .item import Item


class SupplierProduct(models.Model):
    product_id = models.BigAutoField(primary_key=True)

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="products"
    )

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="supplier_products"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    stock = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        default="ACTIVE"
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.supplier.business_name} - {self.item.name}"