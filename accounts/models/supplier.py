from django.db import models
from .user import User


class Supplier(models.Model):
    supplier_id = models.BigAutoField(primary_key=True)

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="supplier_profile"
    )

    business_name = models.CharField(max_length=200)
    ssm_registration_no = models.CharField(max_length=50)
    business_license = models.FileField(
        upload_to="supplier_licenses/",
        null=True,
        blank=True
    )
    contact_person = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    bank_account = models.CharField(max_length=50)
    bank_name = models.CharField(max_length=100)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name