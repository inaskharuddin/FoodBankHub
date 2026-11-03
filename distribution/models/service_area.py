from django.db import models
from accounts.models.provider import Provider


class ServiceArea(models.Model):
    service_area_id = models.BigAutoField(primary_key=True)

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="service_areas"
    )

    postcode = models.CharField(max_length=10)
    zone_name = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider.food_bank_name} - {self.zone_name}"