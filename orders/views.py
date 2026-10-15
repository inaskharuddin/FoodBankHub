from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.views import role_required
from distribution.models.provider_supplier import ProviderSupplier
from inventory.models.inventory import Inventory
from inventory.models.supplier_product import SupplierProduct
from .models.payout import Payout
from .models.po_item import POItem
from .models.purchase_order import PurchaseOrder


@role_required("PROVIDER")
def purchase_order_list(request):
    provider = request.user.provider_profile
    orders = PurchaseOrder.objects.filter(provider=provider).select_related(
        "supplier"
    ).order_by("-created_at", "-po_id")
    return render(request, "orders/purchase_order_list.html", {"orders": orders})


@role_required("PROVIDER")
def purchase_order_create(request):
    provider = request.user.provider_profile
    relationship = ProviderSupplier.objects.filter(
        provider=provider, status="ACTIVE"
    ).select_related("supplier").first()
    if relationship is None:
        return render(request, "orders/purchase_order_create.html", {
            "error": "Select an active supplier before creating a purchase order.",
            "products": [],
        })

    products = SupplierProduct.objects.filter(
        supplier=relationship.supplier, status="ACTIVE"
    ).select_related("item").order_by("item__name")

    if request.method == "POST":
        quantities = {}
        errors = []
        selected_ids = {str(p.product_id) for p in products}
        for key, raw_value in request.POST.items():
            if not key.startswith("quantity_"):
                continue
            product_id = key.removeprefix("quantity_")
            raw_value = raw_value.strip()
            if product_id not in selected_ids:
                errors.append("One or more submitted products are not available from your active supplier.")
                continue
            if not raw_value:
                continue
            if not raw_value.isascii() or not raw_value.isdecimal():
                errors.append("Quantities must be non-negative whole numbers.")
                continue
            quantity = int(raw_value)
            if quantity > 0:
                quantities[product_id] = quantity

        if not quantities and not errors:
            errors.append("Enter a quantity greater than zero for at least one product.")

        selected_products = list(products.filter(product_id__in=quantities))
        for product in selected_products:
            if quantities[str(product.product_id)] > product.stock:
                errors.append(f"{product.item.name}: requested quantity exceeds stock ({product.stock}).")

        if errors:
            return render(request, "orders/purchase_order_create.html", {
                "error": " ".join(errors), "products": products,
                "quantities": quantities,
            })

        try:
            total = sum(
                (product.price * quantities[str(product.product_id)] for product in selected_products),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError):
            return render(request, "orders/purchase_order_create.html", {
                "error": "Could not calculate the order total.", "products": products,
                "quantities": quantities,
            })

        with transaction.atomic():
            order = PurchaseOrder.objects.create(
                provider=provider, supplier=relationship.supplier, total_amount=total
            )
            POItem.objects.bulk_create([
                POItem(
                    po=order,
                    product=product,
                    quantity=quantities[str(product.product_id)],
                    price=product.price,
                    subtotal=(product.price * quantities[str(product.product_id)]).quantize(Decimal("0.01")),
                )
                for product in selected_products
            ])
        return redirect("purchase_order_detail", po_id=order.po_id)

    return render(request, "orders/purchase_order_create.html", {"products": products})


@role_required("PROVIDER")
def purchase_order_detail(request, po_id):
    order = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier").prefetch_related(
            "items__product__item"
        ),
        po_id=po_id,
        provider=request.user.provider_profile,
    )
    return render(request, "orders/purchase_order_detail.html", {
        "order": order,
    })


@role_required("SUPPLIER")
def supplier_order_list(request):
    supplier = request.user.supplier_profile
    orders = PurchaseOrder.objects.filter(supplier=supplier).select_related(
        "provider", "provider__user"
    ).prefetch_related("items__product__item").order_by("-created_at", "-po_id")
    return render(request, "orders/supplier_order_list.html", {"orders": orders})


@role_required("SUPPLIER")
def supplier_update_order_status(request, po_id):
    if request.method != "POST":
        return redirect("supplier_order_list")

    transitions = {
        "PENDING": ("ACCEPTED", "accept"),
        "ACCEPTED": ("SHIPPED", "ship"),
        "SHIPPED": ("DELIVERED", "mark-delivered"),
    }
    with transaction.atomic():
        order = get_object_or_404(
            PurchaseOrder.objects.select_for_update(),
            po_id=po_id,
            supplier=request.user.supplier_profile,
        )
        target = transitions.get(order.status)
        if target and request.POST.get("action") == target[1]:
            order.status = target[0]
            order.save(update_fields=["status"])
    return redirect("supplier_order_list")


@role_required("PROVIDER")
def confirm_purchase_order_delivery(request, po_id):
    if request.method != "POST":
        return redirect("purchase_order_detail", po_id=po_id)

    provider = request.user.provider_profile
    with transaction.atomic():
        order = get_object_or_404(
            PurchaseOrder.objects.select_for_update(),
            po_id=po_id,
            provider=provider,
        )
        if order.status == "DELIVERED" and not order.delivery_confirmed:
            items = list(order.items.select_related("product__item"))
            for order_item in items:
                inventory, created = Inventory.objects.select_for_update().get_or_create(
                    provider=provider,
                    item=order_item.product.item,
                    defaults={
                        "quantity": order_item.quantity,
                        "price_per_unit": order_item.price,
                    },
                )
                if not created:
                    inventory.quantity += order_item.quantity
                    inventory.price_per_unit = order_item.price
                    inventory.save(update_fields=["quantity", "price_per_unit", "updated_at"])
            order.delivery_confirmed = True
            order.save(update_fields=["delivery_confirmed"])
    return redirect("purchase_order_detail", po_id=po_id)


@role_required("ADMIN")
def admin_payout_list(request):
    orders = PurchaseOrder.objects.filter(
        status="DELIVERED", delivery_confirmed=True
    ).select_related("supplier", "provider").prefetch_related("payouts").order_by("po_id")
    return render(request, "orders/admin_payout_list.html", {"orders": orders})


@role_required("ADMIN")
def record_purchase_order_payment(request, po_id):
    if request.method != "POST":
        return redirect("purchase_order_detail", po_id=po_id)

    reference = request.POST.get("transfer_reference", "").strip()
    if not reference or len(reference) > 100:
        return redirect("purchase_order_detail", po_id=po_id)

    with transaction.atomic():
        order = get_object_or_404(
            PurchaseOrder.objects.select_for_update(),
            po_id=po_id,
        )
        if order.status == "DELIVERED" and order.delivery_confirmed:
            Payout.objects.get_or_create(
                po=order,
                defaults={
                    "supplier": order.supplier,
                    "amount": order.total_amount,
                    "status": "PAID",
                    "transfer_reference": reference,
                },
            )
    return redirect("purchase_order_detail", po_id=po_id)


@role_required("SUPPLIER")
def supplier_payout_list(request):
    payouts = Payout.objects.filter(
        supplier=request.user.supplier_profile
    ).select_related("po", "po__provider").order_by("-created_at", "-payout_id")
    return render(request, "orders/supplier_payout_list.html", {"payouts": payouts})
