from datetime import timedelta
from decimal import Decimal
from math import ceil

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Provider
from forecasting.models import current_forecasts
from forecasting.services import generate_provider_forecasts, refresh_forecast_accuracy
from inventory.models import Inventory
from inventory.notifications import email_new_low_stock_alerts
from urgent_needs.services import sync_provider_urgent_needs


def refresh_alerts(provider, days):
    today = timezone.localdate()
    rows = Inventory.objects.filter(provider=provider).values(
        "item_id", "item__name", "item__category", "item__unit",
    ).annotate(current_stock=Sum("quantity"), threshold_level=Sum("threshold_level"))
    forecasts = current_forecasts(provider).filter(
        forecast_date__gt=today, forecast_date__lte=today + timedelta(days=days),
    ).values("item_id").annotate(forecast_demand=Sum("predicted_quantity"))
    by_item = {row["item_id"]: row["forecast_demand"] for row in forecasts}
    alerts = []
    for row in rows:
        demand = Decimal(by_item.get(row["item_id"], 0) or 0)
        stock = Decimal(row["current_stock"] or 0)
        threshold = Decimal(row["threshold_level"] or 0)
        required = demand * Decimal("1.1")
        shortage = max(Decimal("0"), required - stock)
        if shortage <= 0 and stock > threshold:
            continue
        coverage = (stock / (demand / Decimal(days)) * Decimal(24)) if demand else None
        alerts.append({
            "item_id": row["item_id"], "name": row["item__name"],
            "category": row["item__category"], "unit": row["item__unit"],
            "forecast_demand": demand, "required_stock": required,
            "current_stock": stock, "threshold_level": threshold,
            "shortage": shortage,
            "suggested_order": ceil(max(shortage, threshold - stock, Decimal("0"))),
            "priority": "HIGH" if coverage is not None and coverage < 48 else "NORMAL",
            "reason": "Less than 48 hours of projected stock remains." if coverage is not None and coverage < 48 else "Forecast demand exceeds stock with 10% safety buffer or reached the stock threshold.",
        })
    email_new_low_stock_alerts(provider, alerts, days)


class Command(BaseCommand):
    help = "Generate saved forecasts, accuracy scores, urgent needs and provider stock alerts."

    def handle(self, *args, **options):
        for provider in Provider.objects.select_related("user").iterator():
            for days in (7, 30):
                generated, failures = generate_provider_forecasts(provider, forecast_days=days)
                self.stdout.write(f"Provider {provider.pk}: saved {days}-day forecast ({generated} rows, {len(failures)} item failures).")
            refresh_forecast_accuracy(provider)
            sync_provider_urgent_needs(provider)
            refresh_alerts(provider, 7)
            refresh_alerts(provider, 30)
        from django.core.management import call_command
        call_command("purge_expired_self_reports")
        self.stdout.write(self.style.SUCCESS("Daily provider automation completed."))
