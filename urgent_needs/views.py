from django.shortcuts import render
from accounts.views import role_required
from .models import UrgentNeed


@role_required("PROVIDER")
def provider_urgent_needs(request):
    from distribution.models import ProviderSupplier
    relationship = ProviderSupplier.objects.filter(provider=request.user.provider_profile, status="ACTIVE").select_related("supplier").first()
    needs = UrgentNeed.objects.filter(provider=request.user.provider_profile).select_related("item").order_by("status", "item__name")
    for need in needs:
        product = relationship.supplier.products.filter(item=need.item, status="ACTIVE").first() if relationship else None
        need.supplier_product_id = product.product_id if product else None
        need.suggested_order_quantity = min(max(need.remaining_quantity, 1), product.stock) if product else 0
        need.progress_percent = int(need.funded_quantity * 100 / need.required_quantity) if need.required_quantity else 0
    return render(request, "urgent_needs/provider_needs.html", {"needs": needs})
