from django.db import models
from .user import User


class Provider(models.Model):
    provider_id = models.BigAutoField(primary_key=True)

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="provider_profile"
    )

    food_bank_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    operating_hours = models.CharField(max_length=255)

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    service_document = models.FileField(
        upload_to="provider_documents/",
        null=True,
        blank=True
    )

    photo = models.ImageField(
        upload_to="provider_photos/",
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.food_bank_name