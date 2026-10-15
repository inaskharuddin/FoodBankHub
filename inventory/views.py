from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models.inventory import Inventory
from .models.item import Item
from accounts.views import role_required
from .models.supplier_product import SupplierProduct
from distribution.models.provider_supplier import ProviderSupplier
from accounts.models.supplier import Supplier

@role_required("PROVIDER")
def inventory_list(request):
    inventory = Inventory.objects.filter(provider__user=request.user)

    return render(
        request,
        "inventory/inventory_list.html",
        {"inventory": inventory}
    )


@role_required("PROVIDER")
def inventory_add(request):

    provider = request.user.provider_profile

    if request.method == "POST":
        item_id = request.POST.get("item")
        quantity = request.POST.get("quantity")

        item = Item.objects.get(item_id=item_id)

        Inventory.objects.create(
            provider=provider,
            item=item,
            quantity=quantity
        )

        return redirect("inventory_list")

    selected_suppliers = ProviderSupplier.objects.filter(
        provider=provider,
        status="ACTIVE"
    ).values_list("supplier_id", flat=True)

    supplier_products = SupplierProduct.objects.filter(
        supplier_id__in=selected_suppliers,
        status="ACTIVE"
    ).select_related("item")

    return render(
        request,
        "inventory/inventory_add.html",
        {"supplier_products": supplier_products}
    )

@role_required("PROVIDER")
def inventory_edit(request, inventory_id):

    provider = request.user.provider_profile

    inventory = Inventory.objects.get(
        inventory_id=inventory_id,
        provider=provider
    )

    if request.method == "POST":
        quantity = request.POST.get("quantity")

        inventory.quantity = quantity
        inventory.save()

        return redirect("inventory_list")

    return render(
        request,
        "inventory/inventory_edit.html",
        {"inventory": inventory}
    ) 

@role_required("SUPPLIER")
def supplier_product_list(request):

    supplier = request.user.supplier_profile

    products = SupplierProduct.objects.filter(
        supplier=supplier
    ).select_related("item")

    return render(
        request,
        "inventory/supplier_product_list.html",
        {"products": products}
    )

@role_required("SUPPLIER")
def supplier_product_add(request):

    supplier = request.user.supplier_profile

    if request.method == "POST":

        product_name = request.POST.get("product_name")
        category = request.POST.get("category")
        unit = request.POST.get("unit")
        price = request.POST.get("price")
        stock = request.POST.get("stock")

        item = Item.objects.create(
            name=product_name,
            category=category,
            unit=unit
        )

        SupplierProduct.objects.create(
            supplier=supplier,
            item=item,
            price=price,
            stock=stock,
            status="ACTIVE"
        )

        return redirect("supplier_product_list")

    return render(
        request,
        "inventory/supplier_product_add.html"
    )

@role_required("SUPPLIER")
def supplier_product_edit(request, product_id):

    supplier = request.user.supplier_profile

    product = SupplierProduct.objects.get(
        product_id=product_id,
        supplier=supplier
    )

    if request.method == "POST":
        product.price = request.POST.get("price")
        product.stock = request.POST.get("stock")
        product.status = request.POST.get("status")

        product.save()

        return redirect("supplier_product_list")

    return render(
        request,
        "inventory/supplier_product_edit.html",
        {"product": product}
    )

@role_required("SUPPLIER")
def supplier_product_delete(request, product_id):

    supplier = request.user.supplier_profile

    product = SupplierProduct.objects.get(
        product_id=product_id,
        supplier=supplier
    )

    if request.method == "POST":
        product.delete()
        return redirect("supplier_product_list")

    return render(
        request,
        "inventory/supplier_product_delete.html",
        {"product": product}
    )

@role_required("PROVIDER")
def supplier_list(request):

    suppliers = Supplier.objects.all()

    return render(
        request,
        "inventory/supplier_list.html",
        {"suppliers": suppliers}
    )

@role_required("PROVIDER")
def supplier_select(request, supplier_id):

    provider = request.user.provider_profile

    # Check if provider already selected a supplier
    current_supplier = ProviderSupplier.objects.filter(
        provider=provider
    ).first()

    if current_supplier:
        return redirect("supplier_list")

    supplier = Supplier.objects.get(
        supplier_id=supplier_id
    )

    ProviderSupplier.objects.create(
        provider=provider,
        supplier=supplier
    )

    return redirect("supplier_list")

@role_required("PROVIDER")
def selected_supplier_products(request):

    provider = request.user.provider_profile

    selected_supplier = ProviderSupplier.objects.filter(
        provider=provider
    ).select_related("supplier").first()

    if not selected_supplier:
        return redirect("supplier_list")

    products = SupplierProduct.objects.filter(
        supplier=selected_supplier.supplier,
        status="ACTIVE"
    ).select_related("item")

    return render(
        request,
        "inventory/selected_supplier_products.html",
        {
            "selected_supplier": selected_supplier,
            "products": products,
        }
    )

@role_required("PROVIDER")
def inventory_add(request):

    provider = request.user.provider_profile

    selected_supplier = ProviderSupplier.objects.filter(
        provider=provider
    ).select_related("supplier").first()

    if not selected_supplier:
        return redirect("supplier_list")

    supplier_products = SupplierProduct.objects.filter(
        supplier=selected_supplier.supplier,
        status="ACTIVE"
    ).select_related("item")

    if request.method == "POST":

        product_id = request.POST.get("product")

        product = SupplierProduct.objects.get(
            product_id=product_id,
            supplier=selected_supplier.supplier,
            status="ACTIVE"
        )

        quantity = request.POST.get("quantity")

        Inventory.objects.create(
            provider=provider,
            item=product.item,
            quantity=quantity,
            price_per_unit=product.price
        )

        return redirect("inventory_list")

    return render(
        request,
        "inventory/inventory_add.html",
        {
            "selected_supplier": selected_supplier,
            "supplier_products": supplier_products,
        }
    )

@role_required("PROVIDER")
def inventory_delete(request, inventory_id):

    provider = request.user.provider_profile

    inventory = Inventory.objects.get(
        inventory_id=inventory_id,
        provider=provider
    )

    if request.method == "POST":
        inventory.delete()
        return redirect("inventory_list")

    return render(
        request,
        "inventory/inventory_delete.html",
        {"inventory": inventory}
    )
@role_required("PROVIDER")
def low_stock_alerts(request):
    from datetime import timedelta
    from decimal import Decimal

    from django.db.models import Sum
    from django.utils import timezone
    from forecasting.models.forecast import Forecast

    provider = request.user.provider_profile
    period_value = request.GET.get("days", "7")
    if period_value not in {"7", "30"}:
        period_value = "7"
    forecast_days = int(period_value)
    today = timezone.localdate()
    period_end = today + timedelta(days=forecast_days)

    inventory_rows = list(
        Inventory.objects.filter(provider=provider)
        .values("item_id", "item__name", "item__category", "item__unit")
        .annotate(
            current_stock=Sum("quantity"),
            threshold_level=Sum("threshold_level"),
        )
        .order_by("item__name")
    )
    forecast_rows = Forecast.objects.filter(
        provider=provider,
        forecast_date__gt=today,
        forecast_date__lte=period_end,
    ).values("item_id").annotate(forecast_demand=Sum("predicted_quantity"))
    forecast_by_item = {
        row["item_id"]: row["forecast_demand"] for row in forecast_rows
    }

    alerts = []
    items_without_forecasts = []
    for row in inventory_rows:
        if row["item_id"] not in forecast_by_item:
            items_without_forecasts.append(row)
            continue

        forecast_demand = max(
            Decimal("0"), Decimal(forecast_by_item[row["item_id"]] or 0)
        )
        current_stock = Decimal(row["current_stock"] or 0)
        threshold_level = Decimal(row["threshold_level"] or 0)
        required_stock = (forecast_demand * Decimal("1.2")).quantize(Decimal("0.01"))
        shortage = max(Decimal("0"), required_stock - current_stock).quantize(Decimal("0.01"))

        if shortage > 0:
            reason = "Forecast demand exceeds available stock with the 20% buffer."
        elif current_stock <= threshold_level:
            reason = "Current stock is at or below the configured inventory threshold."
        else:
            continue

        alerts.append({
            "name": row["item__name"],
            "category": row["item__category"],
            "unit": row["item__unit"],
            "forecast_demand": forecast_demand,
            "required_stock": required_stock,
            "current_stock": current_stock,
            "threshold_level": threshold_level,
            "shortage": shortage,
            "reason": reason,
        })

    return render(request, "inventory/low_stock_alerts.html", {
        "alerts": alerts,
        "items_without_forecasts": items_without_forecasts,
        "has_inventory": bool(inventory_rows),
        "has_forecasts": any(
            row["item_id"] in forecast_by_item for row in inventory_rows
        ),
        "period_start": today + timedelta(days=1),
        "period_end": period_end,
        "forecast_days": forecast_days,
    })
