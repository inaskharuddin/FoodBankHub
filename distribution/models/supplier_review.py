from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from accounts.models.provider import Provider
from accounts.models.supplier import Supplier
from orders.models.purchase_order import PurchaseOrder


class SupplierReview(models.Model):
    supplier_review_id = models.BigAutoField(primary_key=True)
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="supplier_reviews")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="provider_reviews")
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="supplier_reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["po"], name="unique_po_supplier_review")]

    def __str__(self):
        return f"{self.supplier} — {self.rating}/5"
