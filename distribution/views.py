from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.core import signing
from django.http import HttpResponse
from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.views import role_required
from donations.models import Donation, DonationItem
from forecasting.models.historical_data import HistoricalData
from inventory.models.inventory import Inventory
from inventory.models.item import Item
from orders.models import PurchaseOrder
from .models.provider_supplier import ProviderSupplier
from .models.report import Report
from .models.service_area import ServiceArea


@role_required("PROVIDER")
def offline_paper_log(request):
    response = render(request, "distribution/offline_paper_log.html", {"provider": request.user.provider_profile})
    response["Content-Disposition"] = 'attachment; filename="foodbankhub-offline-distribution-log.html"'
    return response


@role_required("ADMIN")
def data_retention_settings(request):
    from .models.retention_policy import DataRetentionPolicy
    policy = DataRetentionPolicy.current()
    if request.method == "POST":
        raw_months = request.POST.get("retention_months", "12")
        if raw_months.isascii() and raw_months.isdecimal() and 1 <= int(raw_months) <= 120:
            policy.retention_months = int(raw_months)
            policy.enabled = request.POST.get("enabled") == "on"
            policy.save()
            messages.success(request, "Self-report retention settings saved.")
            return redirect("data_retention_settings")
        messages.error(request, "Choose a retention period from 1 to 120 months.")
    return render(request, "distribution/data_retention_settings.html", {"policy": policy})


@role_required("PROVIDER")
def service_area_manage(request):
    provider = request.user.provider_profile
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            postcode = request.POST.get("postcode", "").strip()
            zone_name = request.POST.get("zone_name", "").strip()
            if postcode and zone_name:
                ServiceArea.objects.get_or_create(
                    provider=provider, postcode=postcode,
                    defaults={"zone_name": zone_name},
                )
                messages.success(request, "Service area saved.")
            else:
                messages.error(request, "Enter both a postcode and zone name.")
        elif action == "delete":
            ServiceArea.objects.filter(
                provider=provider, service_area_id=request.POST.get("service_area_id")
            ).delete()
        return redirect("service_area_manage")
    areas = ServiceArea.objects.filter(provider=provider).order_by("postcode")
    return render(request, "distribution/service_areas.html", {"areas": areas})


@role_required("PROVIDER")
def allowance_manage(request):
    from .models import ProviderAllowance
    provider=request.user.provider_profile
    if request.method=="POST":
        try:
            item=Item.objects.get(item_id=request.POST.get("item_id")); limit=int(request.POST.get("weekly_limit",""))
            if limit<0: raise ValueError
            ProviderAllowance.objects.update_or_create(provider=provider,item=item,defaults={"weekly_limit":limit})
            messages.success(request,"Weekly allowance saved.")
        except (Item.DoesNotExist,ValueError): messages.error(request,"Choose an item and enter a non-negative whole-number limit.")
        return redirect("allowance_manage")
    return render(request,"distribution/allowance_manage.html",{"items":Item.objects.order_by("name"),"limits":ProviderAllowance.objects.filter(provider=provider).select_related("item")})


@role_required("PROVIDER")
def provider_reports(request):
    from urgent_needs.models import UrgentNeed

    provider = request.user.provider_profile
    raw_month = request.GET.get("month", "").strip()
    today = timezone.localdate()
    try:
        year_text, month_text = raw_month.split("-")
        selected_month = date(int(year_text), int(month_text), 1)
    except (ValueError, TypeError):
        selected_month = date(today.year, today.month, 1)
    month_end = date(selected_month.year + (selected_month.month == 12), selected_month.month % 12 + 1, 1)
    reports = Report.objects.filter(
        provider=provider, reported_at__date__gte=selected_month,
        reported_at__date__lt=month_end,
    ).select_related("needy__user", "item").order_by("reported_at", "report_id")
    completed_reports = reports.filter(status__in=["DISTRIBUTED", "COMPLETED"])
    blocked = reports.filter(status__startswith="BLOCKED")
    donation_entries = list(DonationItem.objects.filter(
        provider=provider, donation__created_at__date__gte=selected_month,
        donation__created_at__date__lt=month_end,
    ).select_related("donation__donor", "item").order_by("donation__created_at", "donation_item_id"))
    for entry in donation_entries:
        entry.line_total = (entry.price * entry.quantity).quantize(Decimal("0.01"))
    paid_donation_entries = [entry for entry in donation_entries if entry.donation.status == "PAID"]
    orders = list(PurchaseOrder.objects.filter(
        provider=provider, created_at__date__gte=selected_month,
        created_at__date__lt=month_end,
    ).select_related("supplier").prefetch_related("items__product__item").order_by("created_at", "po_id"))
    urgent_needs = UrgentNeed.objects.filter(
        provider=provider, created_at__date__gte=selected_month,
        created_at__date__lt=month_end,
    ).select_related("item").order_by("created_at", "urgent_need_id")
    distribution_total = completed_reports.aggregate(total=Sum("quantity"))["total"] or 0
    paid_donation_total = sum((entry.line_total for entry in paid_donation_entries), Decimal("0.00"))
    paid_donation_quantity = sum(entry.quantity for entry in paid_donation_entries)
    order_total = sum((order.total_amount for order in orders), Decimal("0.00"))
    return render(request, "distribution/provider_reports.html", {
        "provider": provider,
        "reports": reports, "blocked_reports": blocked,
        "completed_reports": completed_reports,
        "donation_entries": donation_entries,
        "orders": orders,
        "urgent_needs": urgent_needs,
        "selected_month": selected_month,
        "month_label": selected_month.strftime("%B %Y"),
        "completed_count": completed_reports.count(),
        "blocked_count": blocked.count(),
        "distribution_total": distribution_total,
        "paid_donation_total": paid_donation_total,
        "paid_donation_quantity": paid_donation_quantity,
        "paid_donation_count": len(paid_donation_entries),
        "order_total": order_total,
        "order_count": len(orders),
    })


@role_required("PROVIDER")
def provider_donation_monitoring(request):
    provider = request.user.provider_profile
    entries = list(DonationItem.objects.filter(provider=provider).select_related(
        "donation__donor", "item", "urgent_need",
    ).order_by("-donation__created_at", "-donation_item_id"))
    for entry in entries:
        entry.line_total = (entry.price * entry.quantity).quantize(Decimal("0.01"))
        if entry.donation.status != "PAID":
            entry.progress_label = "Payment pending"
        elif entry.urgent_need.funded_quantity < entry.urgent_need.required_quantity:
            entry.progress_label = "Paid · need still being funded"
        else:
            order = PurchaseOrder.objects.filter(
                provider=provider, items__product__item=entry.item,
            ).order_by("-created_at").first()
            if order is None:
                entry.progress_label = "Fully funded · ready for order"
            elif order.status in {"PENDING", "ACCEPTED"}:
                entry.progress_label = "Ordered from supplier"
            elif order.status == "SHIPPED":
                entry.progress_label = "Shipped"
            elif order.status == "DELIVERED" and not order.delivery_confirmed:
                entry.progress_label = "Delivered · awaiting confirmation"
            elif order.delivery_confirmed:
                entry.progress_label = "Delivery confirmed · inventory updated"
            else:
                entry.progress_label = order.status.title()
    return render(request, "distribution/provider_donations.html", {"entries": entries})


@role_required("NEEDY")
def needy_self_report(request, token):
    import uuid
    from datetime import timedelta
    from django.db import IntegrityError
    from django.db.models import F
    from .models import AllowanceUsage, ProviderAllowance
    from accounts.models import Provider
    from django.http import Http404
    try: provider_id=signing.loads(token,salt="distribution.provider-self-report")
    except signing.BadSignature: raise Http404
    provider=get_object_or_404(Provider.objects.prefetch_related("service_areas"),provider_id=provider_id)
    needy=request.user.needy_profile; today=timezone.localdate(); week_start=today-timedelta(days=today.weekday())
    stock_rows=Inventory.objects.filter(provider=provider).select_related("item").order_by("item__name")
    allowed=list(provider.service_areas.values_list("postcode","zone_name"))
    allowed_text=", ".join(f"{zone} ({code})" for code,zone in allowed) or "No service areas configured"
    error=""
    if request.method=="POST":
        key=request.POST.get("submission_key","")
        try: submission_key=uuid.UUID(key) if key else uuid.uuid4()
        except (ValueError,TypeError): submission_key=None
        raw_item=request.POST.get("item_id",""); raw_quantity=request.POST.get("quantity","").strip()
        try:
            if submission_key is None or not raw_quantity.isascii() or not raw_quantity.isdecimal() or int(raw_quantity)<1: raise ValueError
            quantity=int(raw_quantity)
        except ValueError:
            error="Enter a valid quantity and reload the page before submitting."
            return render(request,"distribution/needy_self_report.html",{"provider":provider,"stock_rows":stock_rows,"error":error,"allowed_text":allowed_text,"submission_key":uuid.uuid4()},status=400)
        try:
            with transaction.atomic():
                stock=get_object_or_404(Inventory.objects.select_for_update().select_related("item"),provider=provider,item_id=raw_item)
                if not ServiceArea.objects.filter(provider=provider,postcode__iexact=needy.postcode).exists():
                    Report.objects.create(needy=needy,provider=provider,item=stock.item,quantity=quantity,report_method="SELF_REPORT",status="BLOCKED_ADDRESS",submission_key=submission_key)
                    error=f"Sorry, this food bank serves {allowed_text}. Your registered postcode is outside its service area."
                elif stock.quantity<quantity:
                    Report.objects.create(needy=needy,provider=provider,item=stock.item,quantity=quantity,report_method="SELF_REPORT",status="BLOCKED_STOCK",submission_key=submission_key)
                    error=f"Only {stock.quantity} {stock.item.unit} are currently available."
                else:
                    limit=ProviderAllowance.objects.filter(provider=provider,item=stock.item).values_list("weekly_limit",flat=True).first()
                    if limit is None: limit=0
                    usage=AllowanceUsage.objects.select_for_update().filter(needy=needy,provider=provider,item=stock.item,week_start_date=week_start).first()
                    if usage is None:
                        usage=AllowanceUsage.objects.create(needy=needy,provider=provider,item=stock.item,week_start_date=week_start,allowed_quantity=limit,used_quantity=0,remaining_quantity=limit)
                    elif not usage.admin_override:
                        usage.allowed_quantity=limit; usage.remaining_quantity=max(limit-usage.used_quantity,0)
                    if quantity>usage.remaining_quantity:
                        usage.save(update_fields=["allowed_quantity","remaining_quantity","updated_at"])
                        Report.objects.create(needy=needy,provider=provider,item=stock.item,quantity=quantity,report_method="SELF_REPORT",status="BLOCKED_ALLOWANCE",submission_key=submission_key)
                        error=f"This week's allowance is {usage.remaining_quantity} {stock.item.unit}; your request exceeds it."
                    else:
                        stock.quantity=F("quantity")-quantity; stock.save(update_fields=["quantity","updated_at"]); stock.refresh_from_db()
                        usage.used_quantity+=quantity; usage.remaining_quantity=max(0,usage.allowed_quantity-usage.used_quantity); usage.save()
                        report=Report.objects.create(needy=needy,provider=provider,item=stock.item,quantity=quantity,report_method="SELF_REPORT",status="DISTRIBUTED",submission_key=submission_key)
                        from orders.models import InventoryLot
                        from .models import ReportLotAllocation
                        remaining=quantity
                        lots=InventoryLot.objects.select_for_update().filter(inventory=stock,remaining_quantity__gt=0).order_by("received_at","pk")
                        for lot in lots:
                            used=min(remaining,lot.remaining_quantity)
                            if used:
                                lot.remaining_quantity-=used; lot.save(update_fields=["remaining_quantity"])
                                lot_remaining=used
                                if lot.purchase_order_item_id:
                                    for donor_allocation in lot.purchase_order_item.donation_allocations.select_related("donation_item").order_by("donation_item__donation__created_at","pk"):
                                        already=ReportLotAllocation.objects.filter(donation_order_allocation=donor_allocation).aggregate(total=Sum("quantity"))["total"] or 0
                                        donor_remaining=donor_allocation.quantity-already
                                        allocated=min(lot_remaining,donor_remaining)
                                        if allocated:
                                            ReportLotAllocation.objects.create(report=report,inventory_lot=lot,donation_order_allocation=donor_allocation,quantity=allocated)
                                            lot_remaining-=allocated
                                        if not lot_remaining: break
                                if lot_remaining:
                                    ReportLotAllocation.objects.create(report=report,inventory_lot=lot,quantity=lot_remaining,estimated=True)
                                remaining-=used
                            if remaining==0: break
                        if remaining:
                            # Aggregate/manual stock without a known receipt is retained as explicitly estimated lineage.
                            ReportLotAllocation.objects.create(report=report,inventory_lot=None,quantity=remaining,estimated=True)
                        today=timezone.localdate(); relationship=ProviderSupplier.objects.filter(provider=provider,status="ACTIVE").select_related("supplier").first()
                        history=HistoricalData.objects.select_for_update().filter(provider=provider,item=stock.item,date=today,source=HistoricalData.Source.ACTUAL).first()
                        if history: history.quantity+=quantity; history.save(update_fields=["quantity"])
                        else: HistoricalData.objects.create(provider=provider,item=stock.item,date=today,quantity=quantity,source=HistoricalData.Source.ACTUAL,supplier=relationship.supplier if relationship else None)
                        messages.success(request,f"Report recorded. Remaining weekly allowance: {usage.remaining_quantity} {stock.item.unit}.")
                        return redirect("needy_dashboard")
        except IntegrityError:
            messages.info(request,"This report was already submitted."); return redirect("needy_dashboard")
    return render(request,"distribution/needy_self_report.html",{"provider":provider,"stock_rows":stock_rows,"error":error,"allowed_text":allowed_text,"submission_key":uuid.uuid4()})


@role_required("PROVIDER")
def provider_self_report_qr(request):
    import io
    import qrcode
    from django.core import signing

    provider = request.user.provider_profile
    token = signing.dumps(provider.provider_id, salt="distribution.provider-self-report", compress=True)
    report_url = request.build_absolute_uri(
        reverse("needy_self_report", args=[token])
    )
    image = qrcode.make(report_url)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return HttpResponse(output.getvalue(), content_type="image/png")


@role_required("PROVIDER")
def provider_daily_summary(request):
    provider = request.user.provider_profile
    raw_date = request.GET.get("date", "")
    try:
        selected_date = date.fromisoformat(raw_date) if raw_date else timezone.localdate()
    except ValueError:
        selected_date = timezone.localdate()
    reports = Report.objects.filter(
        provider=provider, reported_at__date=selected_date,
        status__in=["DISTRIBUTED", "COMPLETED"],
    )
    donation_items = DonationItem.objects.filter(
        provider=provider, donation__status="PAID", donation__created_at__date=selected_date,
    )
    donations = Donation.objects.filter(
        items__provider=provider, status="PAID", created_at__date=selected_date,
    ).distinct()
    orders = PurchaseOrder.objects.filter(provider=provider, created_at__date=selected_date).select_related("supplier")
    return render(request, "distribution/provider_daily_summary.html", {
        "selected_date": selected_date,
        "distributed_quantity": reports.aggregate(total=Sum("quantity"))["total"] or 0,
        "distribution_count": reports.count(),
        "donated_quantity": donation_items.aggregate(total=Sum("quantity"))["total"] or 0,
        "donation_value": sum(dict(donations.values_list("donation_id", "total_amount")).values(), Decimal("0.00")),
        "purchase_orders": orders,
    })


@role_required("PROVIDER")
def needy_usage_report(request):
    provider = request.user.provider_profile
    reports = Report.objects.filter(
        provider=provider, status__in=["DISTRIBUTED", "COMPLETED"],
    )
    popular_items = reports.values("item__name", "item__unit").annotate(
        total_quantity=Sum("quantity"), report_count=Count("report_id"),
    ).order_by("-total_quantity")
    peak_hours = reports.annotate(hour=ExtractHour("reported_at")).values("hour").annotate(
        total_quantity=Sum("quantity"),
    ).order_by("hour")
    return render(request, "distribution/needy_usage_report.html", {
        "popular_items": popular_items, "peak_hours": peak_hours,
    })





