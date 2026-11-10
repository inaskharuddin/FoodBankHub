import csv
import io
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

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
from .models.forecast_run import ForecastRun, current_forecasts
from inventory.models.inventory import Inventory
from .services import generate_provider_forecasts, refresh_forecast_accuracy
from urgent_needs.services import sync_provider_urgent_needs

MAX_CSV_BYTES = 2 * 1024 * 1024


@role_required("PROVIDER")
@require_POST
def delete_forecast_run(request):
    provider = request.user.provider_profile
    run_id = request.POST.get("run_id")
    run = get_object_or_404(ForecastRun, pk=run_id, provider=provider)
    was_current = ForecastRun.latest_for_provider(provider) == run
    run_label = run.created_at.strftime("%b %d, %Y %H:%M")
    run.delete()
    if was_current:
        sync_provider_urgent_needs(provider)
    messages.success(request, f"Forecast snapshot from {run_label} was deleted.")
    return redirect("view_forecast")


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
    item_options = list(history.values("item_id", "item__name", "item__unit").distinct().order_by("item__name"))
    month_options = [{
        "value": month.strftime("%Y-%m"),
        "label": month.strftime("%B %Y"),
    } for month in history.dates("date", "month", order="DESC")]
    selected_item = request.GET.get("item", "").strip()
    selected_month = request.GET.get("month", "").strip()
    filtered_history = []
    selected_item_name = ""
    try:
        month_date = date.fromisoformat(f"{selected_month}-01")
        valid_month = month_date.strftime("%Y-%m") == selected_month
    except ValueError:
        month_date = None
        valid_month = False
    item_by_id = {str(row["item_id"]): row for row in item_options}
    if selected_item in item_by_id and valid_month:
        selected_item_name = item_by_id[selected_item]["item__name"]
        filtered_history = history.filter(
            item_id=int(selected_item), date__year=month_date.year, date__month=month_date.month,
        ).order_by("date", "history_id")
    else:
        selected_item = ""
        selected_month = ""
    return render(request, "forecasting/historical_data.html", {
        "supplier_relationship": supplier_relationship,
        "products": products,
        "history": filtered_history,
        "has_history": bool(item_options),
        "item_options": item_options,
        "month_options": month_options,
        "selected_item": selected_item,
        "selected_item_name": selected_item_name,
        "selected_month": selected_month,
        "selected_month_label": month_date.strftime("%B %Y") if selected_month else "",
        "months": (_month_start(-3), _month_start(-2), _month_start(-1)),
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
                for month_number, offset in enumerate((-3, -2, -1), start=1):
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
        try:
            forecast_days = int(request.POST.get("forecast_days", 7))
        except (TypeError, ValueError):
            forecast_days = 0
        if forecast_days not in (7, 30):
            messages.error(request, "Choose a 7-day or 30-day forecast.")
            return redirect("view_forecast")
        generated, failures = generate_provider_forecasts(provider, forecast_days)
        sync_provider_urgent_needs(provider)
        if generated:
            messages.success(request, f"Prophet forecasts generated for {generated} item(s).")
        else:
            messages.warning(request, "No forecasts generated. Each item needs at least two usable historical dates.")
        if failures:
            messages.warning(request, "Forecast generation failed for: " + ", ".join(failures))
        return redirect(f"{reverse('view_forecast')}?days={forecast_days}")

    raw_days = request.GET.get("days", "7")
    days = int(raw_days) if raw_days in {"7", "30"} else 7
    today = timezone.localdate()
    future = list(current_forecasts(provider).filter(
        forecast_date__gt=today,
        forecast_date__lte=today + timedelta(days=days),
    ).select_related("item").order_by("item__category", "item__name", "forecast_date"))
    snapshot_runs = list(ForecastRun.objects.filter(
        provider=provider, forecasts__isnull=False,
    ).distinct().order_by("-created_at", "-pk"))
    latest_run = snapshot_runs[0] if snapshot_runs else None
    previous_runs = snapshot_runs[1:]
    comparison_run = None
    snapshot_menu_runs = []
    if previous_runs:
        requested_run_id = request.GET.get("compare_run")
        comparison_run = next(
            (run for run in previous_runs if str(run.pk) == requested_run_id),
            previous_runs[0],
        )
        snapshot_menu_runs = [comparison_run] + [run for run in previous_runs if run.pk != comparison_run.pk]
        previous_forecasts = Forecast.objects.filter(
            provider=provider, run=comparison_run,
        ).values("item_id", "forecast_date", "predicted_quantity")
        previous_by_key = {
            (row["item_id"], row["forecast_date"]): row["predicted_quantity"]
            for row in previous_forecasts
        }
        for forecast in future:
            previous_quantity = previous_by_key.get((forecast.item_id, forecast.forecast_date))
            forecast.comparison_quantity = previous_quantity
            forecast.comparison_delta = (
                forecast.predicted_quantity - previous_quantity
                if previous_quantity is not None else None
            )
    scores = refresh_forecast_accuracy(provider)
    history = list(Forecast.objects.filter(
        provider=provider, forecast_date__lt=today,
        forecast_date__gte=today - timedelta(days=30), actual_quantity__isnull=False,
    ).select_related("item").order_by("forecast_date", "item__name"))
    category_totals = {}
    for forecast in future:
        category = forecast.item.category
        category_totals[category] = category_totals.get(category, 0) + float(forecast.predicted_quantity)
    largest = max(category_totals.values(), default=1)
    category_data = [{
        "name": name, "total": round(total, 2),
        "bar_width": max(2, int(total * 100 / largest)),
    } for name, total in sorted(category_totals.items())]
    actual_max = max((max(float(row.actual_quantity or 0), float(row.predicted_quantity or 0)) for row in history), default=1) or 1
    for row in history:
        row.predicted_width = max(2, int(float(row.predicted_quantity or 0) * 100 / actual_max))
        row.actual_width = max(2, int(float(row.actual_quantity or 0) * 100 / actual_max))

    grouped_forecasts = {}
    for forecast in future:
        grouped_forecasts.setdefault(forecast.item_id, {"item": forecast.item, "rows": []})["rows"].append(forecast)
    item_charts = []
    chart_data = []
    chart_left, chart_right, chart_top, chart_bottom = 58, 620, 28, 158
    for group in grouped_forecasts.values():
        rows = group["rows"]
        values = [float(row.predicted_quantity or 0) for row in rows]
        if comparison_run:
            values.extend(float(row.comparison_quantity) for row in rows if row.comparison_quantity is not None)
        chart_max = max(values, default=0) or 1
        current_points, comparison_points = [], []
        for index, row in enumerate(rows):
            x = chart_left + index * (chart_right - chart_left) / max(len(rows) - 1, 1)
            current_y = chart_bottom - (float(row.predicted_quantity or 0) / chart_max) * (chart_bottom - chart_top)
            current_points.append({
                "x": round(x, 1), "y": round(current_y, 1),
                "date": f"{row.forecast_date.strftime('%b')} {row.forecast_date.day}",
                "value": row.predicted_quantity,
                "show_label": index % (5 if len(rows) > 10 else 1) == 0 or index == len(rows) - 1,
            })
            if row.comparison_quantity is not None:
                comparison_y = chart_bottom - (float(row.comparison_quantity) / chart_max) * (chart_bottom - chart_top)
                comparison_points.append({
                    "x": round(x, 1), "y": round(comparison_y, 1),
                    "date": f"{row.forecast_date.strftime('%b')} {row.forecast_date.day}",
                    "value": row.comparison_quantity,
                })
        group["points"] = current_points
        group["path"] = " ".join(f"{point['x']},{point['y']}" for point in current_points)
        group["comparison_path"] = " ".join(f"{point['x']},{point['y']}" for point in comparison_points)
        group["comparison_points"] = comparison_points
        group["axis"] = [
            {"y": chart_bottom, "amount": 0},
            {"y": round((chart_top + chart_bottom) / 2, 1), "amount": round(chart_max / 2, 1)},
            {"y": chart_top, "amount": round(chart_max, 1)},
        ]
        item_charts.append(group)
        comparison_by_date = {
            row.forecast_date.isoformat(): float(row.comparison_quantity)
            for row in rows if getattr(row, "comparison_quantity", None) is not None
        }
        chart_data.append({
            "name": group["item"].name,
            "unit": group["item"].unit,
            "labels": [f"{row.forecast_date.strftime('%b')} {row.forecast_date.day}" for row in rows],
            "values": [float(row.predicted_quantity or 0) for row in rows],
            "comparison": [comparison_by_date.get(row.forecast_date.isoformat()) for row in rows],
        })
    avg_mape = sum(scores) / len(scores) if scores else None
    return render(request, "forecasting/view_forecast.html", {
        "forecasts": future, "history": history, "category_data": category_data,
        "item_charts": item_charts,
        "chart_data": chart_data,
        "days": days, "mape": round(avg_mape, 2) if avg_mape is not None else None,
        "accuracy": round(max(0, 100 - avg_mape), 2) if avg_mape is not None else None,
        "latest_run": latest_run, "snapshot_runs": snapshot_runs,
        "previous_runs": previous_runs, "snapshot_menu_runs": snapshot_menu_runs,
        "comparison_run": comparison_run,
    })


