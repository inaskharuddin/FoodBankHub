import logging
from datetime import timedelta

import pandas as pd
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from prophet import Prophet

from inventory.models.inventory import Inventory
from .models.forecast import Forecast
from .models.forecast_run import ForecastRun
from .models.historical_data import HistoricalData


logger = logging.getLogger(__name__)


def generate_provider_forecasts(provider, forecast_days=7):
    today = timezone.localdate()
    generated = 0
    failures = []
    run = ForecastRun.objects.create(provider=provider, forecast_days=forecast_days)
    inventory = Inventory.objects.filter(provider=provider).select_related("item")
    for record in inventory:
        history = list(HistoricalData.objects.filter(
            provider=provider, item=record.item, date__lt=today,
        ).order_by("date"))
        actual_dates = {row.date for row in history if row.source == HistoricalData.Source.ACTUAL}
        training = [row for row in history if row.source == HistoricalData.Source.ACTUAL or row.date not in actual_dates]
        grouped = {}
        for row in training:
            grouped[row.date] = grouped.get(row.date, 0) + row.quantity
        if len(grouped) < 2:
            continue
        frame = pd.DataFrame([{"ds": day, "y": qty} for day, qty in sorted(grouped.items())])
        try:
            model = Prophet()
            model.fit(frame)
            future = pd.DataFrame({"ds": pd.date_range(
                start=today + timedelta(days=1), periods=forecast_days, freq="D",
            )})
            predictions = model.predict(future)
            with transaction.atomic():
                Forecast.objects.bulk_create([
                    Forecast(
                        provider=provider, item=record.item,
                        forecast_date=row["ds"].date(),
                        predicted_quantity=max(0, round(float(row["yhat"]), 2)),
                        forecast_type="PROPHET",
                        run=run,
                    ) for _, row in predictions.iterrows()
                ])
            generated += 1
        except Exception as exc:
            logger.exception("Forecast generation failed for provider %s, item %s", provider.pk, record.item_id)
            failures.append(record.item.name)
    return generated, failures


def refresh_forecast_accuracy(provider):
    today = timezone.localdate()
    rows = Forecast.objects.filter(provider=provider, forecast_date__lt=today).select_related("item")
    scored = []
    for forecast in rows:
        actual = HistoricalData.objects.filter(
            provider=provider, item=forecast.item, date=forecast.forecast_date,
            source=HistoricalData.Source.ACTUAL,
        ).aggregate(total=Sum("quantity"))["total"]
        if actual is None:
            continue
        forecast.actual_quantity = actual
        if actual > 0:
            forecast.mape_score = abs(float(actual) - float(forecast.predicted_quantity)) / float(actual) * 100
            scored.append(float(forecast.mape_score))
        else:
            forecast.mape_score = None
        forecast.save(update_fields=["actual_quantity", "mape_score"])
    return scored
