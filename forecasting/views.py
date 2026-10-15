import csv
import io
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.views import role_required
from distribution.models.provider_supplier import ProviderSupplier
from inventory.models.supplier_product import SupplierProduct
from .models.historical_data import HistoricalData

import logging
from datetime import timedelta

import pandas as pd
from prophet import Prophet

from django.db.models import Sum
from django.utils import timezone

from .models.forecast import Forecast
from inventory.models.inventory import Inventory

MAX_CSV_BYTES = 2 * 1024 * 1024


def _selected_products(provider):
    relationship = (
        ProviderSupplier.objects.filter(provider=provider, status="ACTIVE")
        .select_related("supplier")
        .first()
    )
    if relationship is None:
        return None, SupplierProduct.objects.none()
    products = SupplierProduct.objects.filter(
        supplier=relationship.supplier, status="ACTIVE"
    ).select_related("item").order_by("item__name", "product_id")
    return relationship, products


def _month_start(offset=0):
    today = timezone.localdate()
    month_index = today.year * 12 + today.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _render_page(request, supplier_relationship, products, history):
    return render(request, "forecasting/historical_data.html", {
        "supplier_relationship": supplier_relationship,
        "products": products,
        "history": history,
        "months": ((_month_start(-2), "Month 1"), (_month_start(-1), "Month 2"), (_month_start(0), "Month 3")),
    })


def _error(request, message, supplier, products, history):
    messages.error(request, message)
    return _render_page(request, supplier, products, history)


@role_required("PROVIDER")
def historical_data(request):
    provider = request.user.provider_profile
    supplier_relationship, products = _selected_products(provider)
    if supplier_relationship is None:
        messages.info(request, "Select an active supplier before adding historical data.")
        return redirect("supplier_list")
    history = HistoricalData.objects.filter(provider=provider).filter(
        Q(supplier=supplier_relationship.supplier)
        | Q(
            supplier__isnull=True,
            item__supplier_products__supplier=supplier_relationship.supplier,
            item__supplier_products__status="ACTIVE",
        )
    ).select_related("item", "supplier").distinct()
    if not products.exists():
        return _error(request, "Your selected supplier has no active products yet.", supplier_relationship, products, history)

    if request.method == "POST" and request.POST.get("action") == "upload_actual":
        upload = request.FILES.get("csv_file")
        if not upload:
            return _error(request, "Choose a CSV file to upload.", supplier_relationship, products, history)
        if not upload.name.lower().endswith(".csv") or upload.size > MAX_CSV_BYTES:
            return _error(request, "Upload a CSV file no larger than 2 MB.", supplier_relationship, products, history)
        try:
            text = upload.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            expected = ["product_id", "date", "quantity"]
            if reader.fieldnames != expected:
                raise ValueError("CSV headers must be product_id,date,quantity.")
            product_by_id = {str(product.product_id): product for product in products}
            rows = []
            seen = set()
            for line_number, row in enumerate(reader, start=2):
                try:
                    product = product_by_id[row["product_id"].strip()]
                    record_date = date.fromisoformat(row["date"].strip())
                    quantity = int(row["quantity"].strip())
                    if quantity < 0:
                        raise ValueError
                except (KeyError, AttributeError, TypeError, ValueError):
                    raise ValueError(f"Invalid product_id, date, or quantity on row {line_number}.")
                key = (product.item_id, record_date)
                if key in seen:
                    raise ValueError(f"Duplicate product and date on row {line_number}.")
                seen.add(key)
                rows.append((product, record_date, quantity))
            if not rows:
                raise ValueError("The CSV contains no demand rows.")
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            return _error(request, str(exc), supplier_relationship, products, history)

        with transaction.atomic():
            months = {(product.item_id, record_date.year, record_date.month) for product, record_date, _ in rows}
            for item_id, year, month in months:
                HistoricalData.objects.filter(
                    provider=provider, item_id=item_id, date__year=year, date__month=month,
                    source=HistoricalData.Source.ESTIMATED,
                ).delete()
            for product, record_date, quantity in rows:
                HistoricalData.objects.update_or_create(
                    provider=provider, item=product.item, date=record_date,
                    defaults={
                        "quantity": quantity,
                        "source": HistoricalData.Source.ACTUAL,
                        "supplier": supplier_relationship.supplier,
                    },
                )
        messages.success(request, f"Imported {len(rows)} actual demand rows.")
        return redirect("historical_data")

    if request.method == "POST" and request.POST.get("action") == "save_estimates":
        entries = []
        try:
            for product in products:
                for month_number, offset in enumerate((-2, -1, 0), start=1):
                    raw = request.POST.get(f"month_{month_number}_{product.product_id}", "").strip()
                    quantity = int(raw)
                    if quantity < 0:
                        raise ValueError
                    entries.append((product, _month_start(offset), quantity))
        except (TypeError, ValueError):
            return _error(request, "Enter a whole number of zero or more for each product and month.", supplier_relationship, products, history)

        with transaction.atomic():
            for product, period, quantity in entries:
                key = dict(provider=provider, item=product.item, date=period)
                existing = HistoricalData.objects.filter(**key).first()
                if existing and existing.source == HistoricalData.Source.ACTUAL:
                    continue
                HistoricalData.objects.update_or_create(
                    **key,
                    defaults={
                        "quantity": quantity,
                        "source": HistoricalData.Source.ESTIMATED,
                        "supplier": supplier_relationship.supplier,
                    },
                )
        messages.success(request, "Your three-month estimated baseline has been saved.")
        return redirect("historical_data")

    return _render_page(request, supplier_relationship, products, history)

@role_required("PROVIDER")
def view_forecast(request):
    provider = request.user.provider_profile

    if request.method == "POST":
        forecast_days = int(request.POST.get("forecast_days", 7))

        if forecast_days not in (7, 30):
            messages.error(request, "Choose 7 or 30 forecast days.")
            return redirect("view_forecast")

        today = timezone.localdate()
        inventory = Inventory.objects.filter(
            provider=provider
        ).select_related("item")

        generated = 0

        for inventory_item in inventory:
            records = HistoricalData.objects.filter(
                provider=provider,
                item=inventory_item.item,
                date__lt=today,
            ).order_by("date")

            # Prefer actual records when present.
            actual_dates = set(
                records.filter(
                    source=HistoricalData.Source.ACTUAL
                ).values_list("date", flat=True)
            )

            records = [
                record for record in records
                if record.source == HistoricalData.Source.ACTUAL
                or record.date not in actual_dates
            ]

            if len(records) < 2:
                continue

            df = pd.DataFrame([
                {"ds": record.date, "y": record.quantity}
                for record in records
            ])

            # Combine any records on the same date.
            df = df.groupby("ds", as_index=False)["y"].sum()

            if len(df) < 2:
                continue

            try:
                model = Prophet()
                model.fit(df)

                future_dates = pd.DataFrame({
                    "ds": pd.date_range(
                        start=today + timedelta(days=1),
                        periods=forecast_days,
                        freq="D",
                    )
                })
                predictions = model.predict(future_dates)

                with transaction.atomic():
                    Forecast.objects.filter(
                        provider=provider,
                        item=inventory_item.item,
                        forecast_date__gte=today,
                    ).delete()

                    for _, prediction in predictions.iterrows():
                        predicted_quantity = max(
                            0, round(float(prediction["yhat"]), 2)
                        )

                        Forecast.objects.update_or_create(
                            provider=provider,
                            item=inventory_item.item,
                            forecast_date=prediction["ds"].date(),
                            defaults={
                                "predicted_quantity": predicted_quantity,
                                "forecast_type": "PROPHET",
                            },
                        )

                generated += 1

            except Exception:
                logging.exception(
                    "Forecast generation failed for item %s",
                    inventory_item.item_id,
                )
                messages.warning(
                    request,
                    f"Forecast generation failed for {inventory_item.item.name}.",
                )

        if generated:
            messages.success(
                request,
                f"Forecasts generated for {generated} inventory item(s).",
            )
        else:
            messages.warning(
                request,
                "No forecasts generated. Each item needs at least two usable historical records.",
            )

        return redirect("view_forecast")

    forecasts = Forecast.objects.filter(
        provider=provider,
        forecast_date__gte=timezone.localdate(),
    ).select_related("item").order_by("forecast_date", "item__name")

    return render(
        request,
        "forecasting/view_forecast.html",
        {"forecasts": forecasts},
    )
