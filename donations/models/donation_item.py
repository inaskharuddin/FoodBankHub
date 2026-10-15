from django.db import models
from .donation import Donation
from accounts.models.provider import Provider
from urgent_needs.models.urgent_need import UrgentNeed
from inventory.models.item import Item


class DonationItem(models.Model):
    donation_item_id = models.BigAutoField(primary_key=True)

    donation = models.ForeignKey(
        Donation,
        on_delete=models.CASCADE,
        related_name="items"
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="donation_items"
    )

    urgent_need = models.ForeignKey(
        UrgentNeed,
        on_delete=models.CASCADE,
        related_name="donation_items"
    )

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="donation_items"
    )

    quantity = models.PositiveIntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"Donation {self.donation.donation_id} - {self.item.name}"