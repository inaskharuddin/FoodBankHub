from django.db import models


class DataRetentionPolicy(models.Model):
    retention_months = models.PositiveSmallIntegerField(default=12)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        policy, _ = cls.objects.get_or_create(pk=1)
        return policy
