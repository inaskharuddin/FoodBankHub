def admin_approval_counts(request):
    if not request.user.is_authenticated or request.user.role != "ADMIN":
        return {}

    from .models import Provider, Supplier

    return {
        "pending_provider_count": Provider.objects.filter(is_approved=False, rejected_at__isnull=True).count(),
        "pending_supplier_count": Supplier.objects.filter(is_approved=False, rejected_at__isnull=True).count(),
    }
