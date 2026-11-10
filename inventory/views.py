from datetime import timedelta
import csv
import io
import ipaddress
import socket
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4
from decimal import Decimal, InvalidOperation
from math import ceil

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.core.files.base import ContentFile
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


def _verify_product_image(image_file):
    from PIL import Image, UnidentifiedImageError
    if not image_file or image_file.size > 5 * 1024 * 1024:
        raise ValueError("Upload a product image up to 5 MB.")
    try:
        image_file.seek(0)
        with Image.open(image_file) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Use a JPG, PNG, or WEBP product image.")
            image.verify()
        image_file.seek(0)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("The selected file is not a valid product image.")
    return image_file


def _download_csv_product_image(url):
    from PIL import Image, UnidentifiedImageError
    from urllib.error import HTTPError, URLError

    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("Invalid Image_URL (use a public HTTPS image link).")
    try:
        addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError("Invalid Image_URL (private or local hosts are not allowed).")
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = build_opener()
        opener.handlers = [handler for handler in opener.handlers if not isinstance(handler, HTTPRedirectHandler)]
        opener.add_handler(NoRedirect())
        request = Request(url, headers={"User-Agent": "FoodBankHub product image importer"})
        with opener.open(request, timeout=5) as response:
            if response.status != 200 or not response.headers.get_content_type().startswith("image/"):
                raise ValueError("Invalid Image_URL (the link must return an image).")
            data = response.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise ValueError("Image_URL file is larger than 5 MB.")
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Invalid Image_URL (use a JPG, PNG, or WEBP image).")
            image_format = image.format
            image.verify()
        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
        return ContentFile(data, name=f"bulk-{uuid4().hex}{extension}")
    except ValueError:
        raise
    except (OSError, HTTPError, URLError, TimeoutError, socket.gaierror, UnidentifiedImageError, Image.DecompressionBombError):
        raise ValueError("Invalid Image_URL (the image could not be reached or read).")


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
    response = HttpResponse("name,category,unit,price,stock,Image_URL\n", content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="foodbankhub-products-template.csv"'
    return response


@role_required("SUPPLIER")
def supplier_product_upload(request):
    error = ""
    row_errors = []
    if request.method == "POST":
        upload = request.FILES.get("csv_file")
        if not upload or not upload.name.lower().endswith(".csv"):
            error = "Choose a CSV file."
        elif upload.size > 2 * 1024 * 1024:
            error = "CSV files must be 2 MB or smaller."
        else:
            try:
                reader = csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig")))
                required = {"name", "category", "unit", "price", "stock", "image_url"}
                if not reader.fieldnames or not required.issubset({field.strip().lower() for field in reader.fieldnames}):
                    raise ValueError("CSV needs name, category, unit, price, stock, and Image_URL columns.")
                rows = []
                for row_number, row in enumerate(reader, start=2):
                    normalized = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
                    try:
                        if not all(normalized.get(key) for key in ("name", "category", "unit", "image_url")):
                            raise ValueError("Missing product details or Image_URL.")
                        price = Decimal(normalized["price"])
                        stock = _whole_number(normalized["stock"])
                        if not price.is_finite() or price < 0 or stock is None:
                            raise ValueError("Invalid price or stock quantity.")
                        image = _download_csv_product_image(normalized["image_url"])
                        rows.append((normalized, price, stock, image))
                    except (InvalidOperation, KeyError, ValueError) as exc:
                        row_errors.append(f"Row {row_number}: {exc}")
                if not rows:
                    error = "No valid products were added. Fix the rows listed below and upload the CSV again."
                else:
                    supplier = request.user.supplier_profile
                    with transaction.atomic():
                        for row, price, stock, image in rows:
                            item = Item.objects.create(name=row["name"][:200], category=row["category"][:100], unit=row["unit"][:50])
                            SupplierProduct.objects.create(supplier=supplier, item=item, price=price, stock=stock, image=image)
                    messages.success(request, f"Added {len(rows)} product(s) with valid images.")
                    return render(request, "inventory/supplier_product_upload.html", {
                        "active_nav": "products", "row_errors": row_errors,
                        "success_count": len(rows), "error": error,
                    })
            except (UnicodeDecodeError, csv.Error, ValueError) as exc:
                error = str(exc) or "Check the CSV format and try again."
    return render(request, "inventory/supplier_product_upload.html", {"active_nav": "products", "error": error, "row_errors": row_errors})


@role_required("SUPPLIER")
def supplier_product_add(request):
    error = ""
    if request.method == "POST":
        name = request.POST.get("product_name", "").strip()
        category = request.POST.get("category", "").strip()
        unit = request.POST.get("unit", "").strip()
        image = request.FILES.get("image")
        try:
            price = Decimal(request.POST.get("price", "").strip())
            stock = _whole_number(request.POST.get("stock"))
            if not name or not category or not unit or not price.is_finite() or price < 0 or stock is None:
                raise ValueError
            if not image:
                raise ValueError("Product image is required for donors to see.")
            _verify_product_image(image)
        except (InvalidOperation, ValueError) as exc:
            error = str(exc) or "Enter product details, a non-negative price, and whole-number stock."
        else:
            item = Item.objects.create(name=name, category=category, unit=unit)
            SupplierProduct.objects.create(supplier=request.user.supplier_profile, item=item, price=price, stock=stock, image=image, status="ACTIVE")
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
            image = request.FILES.get("image")
            if not price.is_finite() or price < 0 or stock is None or status not in {"ACTIVE", "INACTIVE"}:
                raise ValueError
            if image:
                _verify_product_image(image)
            elif not product.image:
                raise ValueError("Product image is required for donors to see.")
        except (InvalidOperation, ValueError) as exc:
            error = str(exc) or "Enter a valid non-negative price and whole-number stock."
        else:
            product.price, product.stock, product.status = price, stock, status
            if image:
                product.image = image
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




