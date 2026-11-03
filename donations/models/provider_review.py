from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from accounts.models import Provider, User
from .donation import Donation


class ProviderReview(models.Model):
    review_id = models.BigAutoField(primary_key=True)
    donation = models.ForeignKey(Donation, on_delete=models.CASCADE, related_name="provider_reviews")
    donor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="provider_reviews")
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="donor_reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["donation", "provider"], name="unique_donation_provider_review")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} — {self.rating}/5"
