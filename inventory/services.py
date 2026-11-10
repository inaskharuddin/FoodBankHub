from decimal import Decimal

from django.db import transaction

from distribution.models import ProviderSupplier
from .models import Inventory, SupplierProduct


def select_provider_supplier(provider, supplier_id):
    """Change a provider's panel only when it has no open or fully funded donor needs."""
    from accounts.models import Supplier
    from urgent_needs.models import UrgentNeed
    from urgent_needs.services import sync_provider_urgent_needs

    raw_supplier_id = str(supplier_id or "").strip()
    if not raw_supplier_id.isascii() or not raw_supplier_id.isdecimal():
        return None, "Choose an approved, active supplier."
    supplier = Supplier.objects.filter(
        is_approved=True, user__is_active=True,
    ).filter(supplier_id=int(raw_supplier_id)).first()
    if supplier is None:
        return None, "Choose an approved, active supplier."

    current = ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").first()
    if current and current.supplier_id == supplier.supplier_id:
        return supplier, ""

    sync_provider_urgent_needs(provider)
    if UrgentNeed.objects.filter(provider=provider, status__in=["OPEN", "FUNDED"]).exists():
        return None, "Resolve all active urgent needs before changing suppliers. This protects existing donor funding and supplier orders."

    with transaction.atomic():
        ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").update(status="INACTIVE")
        relationship, _ = ProviderSupplier.objects.get_or_create(
            provider=provider, supplier=supplier, defaults={"status": "ACTIVE"},
        )
        if relationship.status != "ACTIVE":
            relationship.status = "ACTIVE"
            relationship.save(update_fields=["status"])
        Inventory.objects.filter(provider=provider).update(price_per_unit=Decimal("0.00"))
        for product in SupplierProduct.objects.filter(supplier=supplier, status="ACTIVE"):
            Inventory.objects.filter(provider=provider, item=product.item).update(price_per_unit=product.price)
        sync_provider_urgent_needs(provider)
    return supplier, ""
