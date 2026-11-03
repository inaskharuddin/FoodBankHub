from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Avg
from django.shortcuts import get_object_or_404, redirect, render

from accounts.views import role_required
from distribution.models.provider_supplier import ProviderSupplier
from inventory.models.inventory import Inventory
from inventory.models.supplier_product import SupplierProduct
from .models.payout import Payout
from distribution.models.supplier_review import SupplierReview
from .models.po_item import POItem
from .models.purchase_order import PurchaseOrder
from urgent_needs.models import UrgentNeed


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
            from donations.services import allocate_paid_donations_to_order
            allocate_paid_donations_to_order(order)
            for product in selected_products:
                UrgentNeed.objects.filter(provider=provider, item=product.item, status__in=["OPEN", "FUNDED"]).update(status="ORDERED")
        return redirect("purchase_order_detail", po_id=order.po_id)

    suggested_id = request.GET.get("product", "")
    suggested_qty = request.GET.get("quantity", "")
    for product in products:
        product.suggested_quantity = suggested_qty if str(product.product_id) == suggested_id and suggested_qty.isascii() and suggested_qty.isdecimal() and int(suggested_qty) <= product.stock else 0
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
        "supplier_review": order.supplier_reviews.first(),
    })


@role_required("SUPPLIER")
def supplier_order_list(request):
    supplier = request.user.supplier_profile
    orders = PurchaseOrder.objects.filter(supplier=supplier).select_related(
        "provider", "provider__user"
    ).prefetch_related("items__product__item").order_by("-created_at", "-po_id")
    view = request.GET.get("view", "all")
    allowed_views = {"pending", "accepted", "shipped", "delivered", "history", "all"}
    if view not in allowed_views:
        view = "all"
    status_map = {
        "pending": "PENDING", "accepted": "ACCEPTED", "shipped": "SHIPPED", "delivered": "DELIVERED",
    }
    if view == "history":
        orders = orders.exclude(status__in=["PENDING", "ACCEPTED", "SHIPPED"])
    elif view in status_map:
        orders = orders.filter(status=status_map[view])
    search = request.GET.get("q", "").strip()
    if search:
        orders = orders.filter(provider__food_bank_name__icontains=search) if not search.isdecimal() else orders.filter(po_id=int(search))
    return render(request, "orders/supplier_order_list.html", {
        "active_nav": "orders", "orders": orders, "view": view, "search": search,
        "pending_count": PurchaseOrder.objects.filter(supplier=supplier, status="PENDING").count(),
        "accepted_count": PurchaseOrder.objects.filter(supplier=supplier, status="ACCEPTED").count(),
        "shipped_count": PurchaseOrder.objects.filter(supplier=supplier, status="SHIPPED").count(),
    })


@role_required("SUPPLIER")
def supplier_update_order_status(request, po_id):
    if request.method != "POST":
        return redirect("supplier_order_list")

    with transaction.atomic():
        order = get_object_or_404(
            PurchaseOrder.objects.select_for_update(),
            po_id=po_id,
            supplier=request.user.supplier_profile,
        )
        action = request.POST.get("action")
        if order.status == "PENDING" and action == "accept":
            order.status = "ACCEPTED"
            order.save(update_fields=["status"])
        elif order.status == "PENDING" and action == "reject":
            reason = request.POST.get("rejection_reason", "").strip()
            if reason:
                order.status = "REJECTED"
                order.rejection_reason = reason[:2000]
                order.save(update_fields=["status", "rejection_reason"])
        elif order.status == "ACCEPTED" and action == "ship":
            order.status = "SHIPPED"
            order.tracking_number = request.POST.get("tracking_number", "").strip()[:100]
            order.delivery_note = request.POST.get("delivery_note", "").strip()[:2000]
            order.save(update_fields=["status", "tracking_number", "delivery_note"])
        elif order.status == "SHIPPED" and action == "mark-delivered":
            order.status = "DELIVERED"
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
                from .models.inventory_lot import InventoryLot
                InventoryLot.objects.get_or_create(
                    purchase_order_item=order_item,
                    defaults={"inventory": inventory, "received_quantity": order_item.quantity, "remaining_quantity": order_item.quantity},
                )
            for item_id in {row.product.item_id for row in items}:
                UrgentNeed.objects.filter(provider=provider, item_id=item_id, status="ORDERED").update(status="FULFILLED", remaining_quantity=0)
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
    supplier = request.user.supplier_profile
    payouts = Payout.objects.filter(
        supplier=supplier
    ).select_related("po", "po__provider").order_by("-created_at", "-payout_id")
    pending_orders = PurchaseOrder.objects.filter(supplier=supplier, status="DELIVERED", delivery_confirmed=True).exclude(payouts__status="PAID").select_related("provider").order_by("-created_at")
    tab = request.GET.get("tab", "pending")
    if tab not in {"pending", "history"}:
        tab = "pending"
    return render(request, "orders/supplier_payout_list.html", {
        "active_nav": "payouts", "payouts": payouts, "pending_orders": pending_orders,
        "tab": tab, "pending_total": sum((order.total_amount for order in pending_orders), Decimal("0.00")),
        "paid_total": sum((payout.amount for payout in payouts if payout.status == "PAID"), Decimal("0.00")),
    })


@role_required("SUPPLIER")
def supplier_invoice(request, po_id):
    from django.http import HttpResponse
    order = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier", "provider").prefetch_related("items__product__item", "payouts"),
        po_id=po_id, supplier=request.user.supplier_profile, status="DELIVERED", delivery_confirmed=True,
    )
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="foodbankhub-invoice-PO-{order.po_id}.pdf"'
    lines = [
        "FoodBankHub Supplier Invoice", f"Invoice for PO {order.po_id}",
        f"Supplier: {order.supplier.business_name}", f"Provider: {order.provider.food_bank_name}",
        f"Order date: {order.created_at:%Y-%m-%d}", "", "Item | Qty | Unit price (RM) | Subtotal (RM)",
    ]
    for item in order.items.all():
        lines.append(f"{item.product.item.name[:45]} | {item.quantity} | {item.price} | {item.subtotal}")
    lines.append(f"Total: RM {order.total_amount}")
    payout = order.payouts.filter(status="PAID").first()
    if payout:
        lines.append(f"Payment reference: {payout.transfer_reference or 'Not provided'}")
    # Write a small standards-compliant PDF directly to avoid adding a package dependency.
    def pdf_text(value):
        value = value.encode("latin-1", "replace").decode("latin-1")
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    commands = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
    for index, line in enumerate(lines[:48]):
        if index:
            commands.append("T*")
        commands.append(f"({pdf_text(line[:110])}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("ascii"))
    response.write(bytes(pdf))
    return response



@role_required("PROVIDER")
def rate_supplier(request, po_id):
    if request.method != "POST":
        return redirect("purchase_order_detail", po_id=po_id)
    order = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier"),
        po_id=po_id, provider=request.user.provider_profile,
        status="DELIVERED", delivery_confirmed=True,
    )
    rating = request.POST.get("rating", "")
    if rating not in {"1", "2", "3", "4", "5"}:
        return redirect("purchase_order_detail", po_id=po_id)
    SupplierReview.objects.update_or_create(
        po=order,
        defaults={
            "supplier": order.supplier, "provider": order.provider,
            "rating": int(rating), "comment": request.POST.get("comment", "").strip()[:500],
        },
    )
    average = SupplierReview.objects.filter(supplier=order.supplier).aggregate(value=Avg("rating"))["value"]
    order.supplier.rating = average or 0
    order.supplier.save(update_fields=["rating"])
    return redirect("purchase_order_detail", po_id=po_id)



