from datetime import timedelta
import csv
import io
from decimal import Decimal, InvalidOperation
from math import ceil

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.views import role_required
from accounts.models.supplier import Supplier
from distribution.models.provider_supplier import ProviderSupplier
from inventory.models.inventory import Inventory
from inventory.models.item import Item
from inventory.models.supplier_product import SupplierProduct
from forecasting.models.forecast_run import current_forecasts


def _sync_supplier_product_prices(product):
    from urgent_needs.services import sync_provider_urgent_needs

    price = product.price if product.status == "ACTIVE" else Decimal("0.00")
    for relation in ProviderSupplier.objects.filter(supplier=product.supplier, status="ACTIVE").select_related("provider"):
        Inventory.objects.filter(provider=relation.provider, item=product.item).update(price_per_unit=price)
        sync_provider_urgent_needs(relation.provider)

def _whole_number(value):
    value = str(value or "").strip()
    return int(value) if value.isascii() and value.isdecimal() else None


@role_required("PROVIDER")
def inventory_list(request):
    provider = request.user.provider_profile
    relation = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").first()
    if relation:
        for product in SupplierProduct.objects.filter(supplier=relation.supplier, status="ACTIVE"):
            Inventory.objects.filter(provider=provider, item=product.item).exclude(
                price_per_unit=product.price
            ).update(price_per_unit=product.price)
    inventory = Inventory.objects.filter(provider=provider).select_related("item").order_by("item__name")
    stocked_count = 0
    low_count = 0
    for record in inventory:
        stocked_count += int(record.quantity > 0)
        record.is_low = record.quantity <= record.threshold_level
        record.stock_width = min(100, round(record.quantity * 100 / max(record.threshold_level * 2, 1)))
        low_count += int(record.is_low)
    return render(request, "inventory/inventory_list.html", {
        "inventory": inventory, "selected_supplier": relation,
        "stocked_count": stocked_count, "low_count": low_count,
    })


@role_required("PROVIDER")
def inventory_add(request):
    provider = request.user.provider_profile
    relation = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").first()
    if not relation:
        return redirect("supplier_list")
    products = SupplierProduct.objects.filter(supplier=relation.supplier, status="ACTIVE").select_related("item")
    if request.method == "POST":
        product = get_object_or_404(products, product_id=request.POST.get("product"))
        quantity = _whole_number(request.POST.get("quantity"))
        threshold = _whole_number(request.POST.get("threshold_level", "0"))
        if quantity is None or threshold is None:
            return render(request, "inventory/inventory_add.html", {"selected_supplier": relation, "supplier_products": products, "error": "Stock and threshold must be whole numbers zero or greater."})
        with transaction.atomic():
            inventory, created = Inventory.objects.get_or_create(
                provider=provider, item=product.item,
                defaults={"quantity": quantity, "price_per_unit": product.price, "threshold_level": threshold},
            )
            if not created:
                inventory.quantity = quantity
                inventory.price_per_unit = product.price
                inventory.threshold_level = threshold
                inventory.save(update_fields=["quantity", "price_per_unit", "threshold_level", "updated_at"])
        return redirect("inventory_list")
    return render(request, "inventory/inventory_add.html", {"selected_supplier": relation, "supplier_products": products})


@role_required("PROVIDER")
def inventory_edit(request, inventory_id):
    inventory = get_object_or_404(Inventory, inventory_id=inventory_id, provider=request.user.provider_profile)
    if request.method == "POST":
        quantity = _whole_number(request.POST.get("quantity"))
        threshold = _whole_number(request.POST.get("threshold_level", "0"))
        if quantity is None or threshold is None:
            return render(request, "inventory/inventory_edit.html", {"inventory": inventory, "error": "Stock and threshold must be whole numbers zero or greater."})
        inventory.quantity = quantity
        inventory.threshold_level = threshold
        inventory.save(update_fields=["quantity", "threshold_level", "updated_at"])
        return redirect("inventory_list")
    return render(request, "inventory/inventory_edit.html", {"inventory": inventory})


@role_required("PROVIDER")
def inventory_delete(request, inventory_id):
    inventory = get_object_or_404(Inventory, inventory_id=inventory_id, provider=request.user.provider_profile)
    if request.method == "POST":
        from urgent_needs.models import UrgentNeed
        UrgentNeed.objects.filter(provider=inventory.provider, item=inventory.item, status="OPEN").update(status="FULFILLED", remaining_quantity=0)
        inventory.delete()
        return redirect("inventory_list")
    return render(request, "inventory/inventory_delete.html", {"inventory": inventory})


@role_required("SUPPLIER")
def supplier_product_list(request):
    supplier = request.user.supplier_profile
    products = SupplierProduct.objects.filter(supplier=supplier).select_related("item").annotate(
        order_count=Sum("po_items__quantity"),
    ).order_by("item__name")
    search = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    if search:
        products = products.filter(item__name__icontains=search)
    if category:
        products = products.filter(item__category=category)
    if status in {"ACTIVE", "INACTIVE"}:
        products = products.filter(status=status)
    return render(request, "inventory/supplier_product_list.html", {
        "active_nav": "products", "products": products,
        "categories": Item.objects.filter(supplier_products__supplier=supplier).values_list("category", flat=True).distinct().order_by("category"),
        "search": search, "selected_category": category, "selected_status": status,
        "product_count": SupplierProduct.objects.filter(supplier=supplier).count(),
        "active_count": SupplierProduct.objects.filter(supplier=supplier, status="ACTIVE").count(),
        "low_stock_count": SupplierProduct.objects.filter(supplier=supplier, status="ACTIVE", stock__lte=10).count(),
    })


@role_required("SUPPLIER")
def supplier_product_csv_template(request):
    from django.http import HttpResponse
    response = HttpResponse("name,category,unit,price,stock\nRice,Grains,kg,3.20,100\n", content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="foodbankhub-products-template.csv"'
    return response


@role_required("SUPPLIER")
def supplier_product_upload(request):
    error = ""
    if request.method == "POST":
        upload = request.FILES.get("csv_file")
        if not upload or not upload.name.lower().endswith(".csv"):
            error = "Choose a CSV file."
        else:
            try:
                reader = csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig")))
                required = {"name", "category", "unit", "price", "stock"}
                if not reader.fieldnames or not required.issubset({field.strip().lower() for field in reader.fieldnames}):
                    raise ValueError("CSV needs name, category, unit, price, and stock columns.")
                rows = []
                for row in reader:
                    normalized = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
                    price = Decimal(normalized["price"])
                    stock = _whole_number(normalized["stock"])
                    if not all(normalized.get(key) for key in ("name", "category", "unit")) or price < 0 or stock is None:
                        raise ValueError("Every row needs product details, a valid price, and whole-number stock.")
                    rows.append((normalized, price, stock))
                if not rows:
                    raise ValueError("The CSV has no product rows.")
                supplier = request.user.supplier_profile
                with transaction.atomic():
                    for row, price, stock in rows:
                        item = Item.objects.create(name=row["name"][:200], category=row["category"][:100], unit=row["unit"][:50])
                        SupplierProduct.objects.create(supplier=supplier, item=item, price=price, stock=stock)
                return redirect("supplier_product_list")
            except (UnicodeDecodeError, csv.Error, InvalidOperation, KeyError, ValueError) as exc:
                error = str(exc) or "Check the CSV format and try again."
    return render(request, "inventory/supplier_product_upload.html", {"active_nav": "products", "error": error})


@role_required("SUPPLIER")
def supplier_product_add(request):
    error = ""
    if request.method == "POST":
        name = request.POST.get("product_name", "").strip()
        category = request.POST.get("category", "").strip()
        unit = request.POST.get("unit", "").strip()
        try:
            price = Decimal(request.POST.get("price", "").strip())
            stock = _whole_number(request.POST.get("stock"))
            if not name or not category or not unit or price < 0 or stock is None:
                raise ValueError
        except (InvalidOperation, ValueError):
            error = "Enter product details, a non-negative price, and whole-number stock."
        else:
            item = Item.objects.create(name=name, category=category, unit=unit)
            SupplierProduct.objects.create(supplier=request.user.supplier_profile, item=item, price=price, stock=stock, status="ACTIVE")
            return redirect("supplier_product_list")
    return render(request, "inventory/supplier_product_add.html", {"active_nav": "products", "error": error})


@role_required("SUPPLIER")
def supplier_product_edit(request, product_id):
    product = get_object_or_404(SupplierProduct.objects.select_related("item"), product_id=product_id, supplier=request.user.supplier_profile)
    error = ""
    if request.method == "POST":
        try:
            price = Decimal(request.POST.get("price", "").strip())
            stock = _whole_number(request.POST.get("stock"))
            status = request.POST.get("status", "ACTIVE")
            if price < 0 or stock is None or status not in {"ACTIVE", "INACTIVE"}:
                raise ValueError
        except (InvalidOperation, ValueError):
            error = "Enter a valid non-negative price and whole-number stock."
        else:
            product.price, product.stock, product.status = price, stock, status
            product.save()
            _sync_supplier_product_prices(product)
            return redirect("supplier_product_list")
    return render(request, "inventory/supplier_product_edit.html", {"active_nav": "products", "product": product, "error": error})


@role_required("SUPPLIER")
def supplier_product_delete(request, product_id):
    product = get_object_or_404(SupplierProduct, product_id=product_id, supplier=request.user.supplier_profile)
    if request.method == "POST":
        product.status = "INACTIVE"
        product.save(update_fields=["status", "updated_at"])
        _sync_supplier_product_prices(product)
        return redirect("supplier_product_list")
    return render(request, "inventory/supplier_product_delete.html", {"active_nav": "products", "product": product})


@role_required("PROVIDER")
def supplier_list(request):
    from urgent_needs.models import UrgentNeed

    provider = request.user.provider_profile
    suppliers = Supplier.objects.filter(is_approved=True, user__is_active=True).order_by("business_name")
    for supplier in suppliers:
        supplier.active_product_count = supplier.products.filter(status="ACTIVE").count()
    current = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").first()
    active_urgent_need_count = UrgentNeed.objects.filter(
        provider=provider, status__in=["OPEN", "FUNDED"],
    ).count()
    for supplier in suppliers:
        supplier.is_current = bool(current and current.supplier_id == supplier.supplier_id)
        supplier.switch_blocked = bool(active_urgent_need_count and not supplier.is_current)
    return render(request, "inventory/supplier_list.html", {
        "suppliers": suppliers, "current_supplier": current,
        "active_urgent_need_count": active_urgent_need_count,
    })


@role_required("PROVIDER")
def supplier_select(request, supplier_id):
    if request.method != "POST":
        return redirect("supplier_list")
    provider = request.user.provider_profile
    from .services import select_provider_supplier

    supplier, error = select_provider_supplier(provider, supplier_id)
    if error:
        messages.error(request, error)
        return redirect("supplier_list")
    if supplier:
        messages.success(request, f"{supplier.business_name} is now your selected supplier.")
    return redirect("selected_supplier_products")


@role_required("PROVIDER")
def selected_supplier_products(request):
    relation = ProviderSupplier.objects.filter(provider=request.user.provider_profile, status="ACTIVE").select_related("supplier").first()
    if not relation:
        return redirect("supplier_list")
    products = SupplierProduct.objects.filter(supplier=relation.supplier, status="ACTIVE").select_related("item").order_by("item__name")
    return render(request, "inventory/selected_supplier_products.html", {"selected_supplier": relation, "products": products})


@role_required("PROVIDER")
def low_stock_alerts(request):
    from urgent_needs.services import sync_provider_urgent_needs

    provider = request.user.provider_profile
    sync_provider_urgent_needs(provider)
    days = request.GET.get("days", "7")
    if days not in {"7", "30"}:
        days = "7"
    forecast_days = int(days)
    today = timezone.localdate()
    period_end = today + timedelta(days=forecast_days)
    rows = list(Inventory.objects.filter(provider=provider).values(
        "item_id", "item__name", "item__category", "item__unit",
    ).annotate(current_stock=Sum("quantity"), threshold_level=Sum("threshold_level")).order_by("item__name"))
    forecasts = current_forecasts(provider).filter(forecast_date__gt=today, forecast_date__lte=period_end).values("item_id").annotate(forecast_demand=Sum("predicted_quantity"))
    forecast_by_item = {row["item_id"]: row["forecast_demand"] for row in forecasts}
    alerts, missing = [], []
    for row in rows:
        if row["item_id"] not in forecast_by_item:
            missing.append(row)
        demand = Decimal(forecast_by_item.get(row["item_id"], 0) or 0)
        stock = Decimal(row["current_stock"] or 0)
        threshold = Decimal(row["threshold_level"] or 0)
        required = (demand * Decimal("1.1")).quantize(Decimal("0.01"))
        shortage = max(Decimal("0"), required - stock).quantize(Decimal("0.01"))
        if shortage > 0 or stock <= threshold:
            coverage_hours = (stock / (demand / Decimal(forecast_days)) * Decimal(24)) if demand > 0 else None
            supplier_product = SupplierProduct.objects.filter(
                supplier__provider_relationships__provider=provider,
                supplier__provider_relationships__status="ACTIVE",
                item_id=row["item_id"], status="ACTIVE",
            ).first()
            suggested_order = ceil(max(shortage, threshold - stock, Decimal("0")))
            if supplier_product:
                suggested_order = min(suggested_order, supplier_product.stock)
            alerts.append({
                "item_id": row["item_id"], "name": row["item__name"], "category": row["item__category"], "unit": row["item__unit"],
                "forecast_demand": demand, "required_stock": required, "current_stock": stock,
                "threshold_level": threshold, "shortage": shortage,
                "suggested_order": suggested_order,
                "product_id": supplier_product.product_id if supplier_product else None,
                "priority": "HIGH" if coverage_hours is not None and coverage_hours < 48 else "NORMAL",
                "reason": "Less than 48 hours of projected stock remains." if coverage_hours is not None and coverage_hours < 48 else ("Forecast demand exceeds stock with safety buffer." if shortage > 0 else "Stock is at or below threshold."),
            })
    from inventory.notifications import email_new_low_stock_alerts
    from inventory.models import LowStockAlert
    email_status = email_new_low_stock_alerts(provider, alerts, forecast_days)
    return render(request, "inventory/low_stock_alerts.html", {
        "alerts": alerts, "items_without_forecasts": missing,
        "in_app_alerts": LowStockAlert.objects.filter(provider=provider, is_active=True).select_related("item").order_by("-priority", "item__name"),
        "has_inventory": bool(rows), "has_forecasts": bool(forecast_by_item),
        "period_start": today + timedelta(days=1), "period_end": period_end, "forecast_days": forecast_days,
        "email_status": email_status,
    })


@role_required("PROVIDER")
def mark_low_stock_alert_read(request, alert_id):
    if request.method == "POST":
        from inventory.models import LowStockAlert
        LowStockAlert.objects.filter(
            pk=alert_id, provider=request.user.provider_profile,
        ).update(is_read=True)
    return redirect("low_stock_alerts")




