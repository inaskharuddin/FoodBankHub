from django.db import models

from accounts.models.provider import Provider


class ForecastRun(models.Model):
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="forecast_runs",
    )
    forecast_days = models.PositiveSmallIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.provider} forecast ({self.created_at:%Y-%m-%d %H:%M})"

    @classmethod
    def latest_for_provider(cls, provider):
        return cls.objects.filter(
            provider=provider,
            forecasts__isnull=False,
        ).order_by("-created_at", "-pk").first()


def current_forecasts(provider):
    """Return one current forecast set, with legacy rows as a migration fallback."""
    from .forecast import Forecast

    latest_run = ForecastRun.latest_for_provider(provider)
    if latest_run:
        return Forecast.objects.filter(provider=provider, run=latest_run)
    return Forecast.objects.filter(provider=provider, run__isnull=True)
