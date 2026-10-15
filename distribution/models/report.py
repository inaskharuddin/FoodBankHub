from django.db import models
from accounts.models.needy import Needy
from accounts.models.provider import Provider
from inventory.models.item import Item


class Report(models.Model):
    report_id = models.BigAutoField(primary_key=True)

    needy = models.ForeignKey(
        Needy,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="distribution_reports"
    )

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="distribution_reports"
    )

    quantity = models.PositiveIntegerField()

    report_method = models.CharField(
        max_length=50
    )

    status = models.CharField(
        max_length=20,
        default="PENDING"
    )

    reported_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report {self.report_id}"