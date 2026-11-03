from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.urls import reverse
from .models import User


def role_required(allowed_role):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):

            if not request.user.is_authenticated:
                return redirect("login")

            if request.user.role != allowed_role:
                return redirect_by_role(request.user)
            if allowed_role == "SUPPLIER" and (
                not hasattr(request.user, "supplier_profile")
                or not request.user.supplier_profile.is_approved
            ):
                return redirect("login")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def login_view(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        from .models import Supplier
        if Supplier.objects.filter(user__email__iexact=email or "", is_approved=False).exists():
            return render(request, "accounts/login.html", {"error": "Your supplier account is waiting for admin approval."})

        user = authenticate(
            request,
            email=email,
            password=password
        )

        if user is not None:
            if user.role == "SUPPLIER" and hasattr(user, "supplier_profile") and not user.supplier_profile.is_approved:
                return render(request, "accounts/login.html", {"error": "Your supplier account is waiting for admin approval."})
            login(request, user)
            return redirect_by_role(user)

        return render(
            request,
            "accounts/login.html",
            {"error": "Invalid email or password."}
        )

    return render(request, "accounts/login.html")


def needy_register(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = ""
    if request.method == "POST":
        name=request.POST.get("name", "").strip(); email=request.POST.get("email", "").strip().lower() or None
        phone=request.POST.get("phone", "").strip(); house=request.POST.get("house_number", "").strip(); street=request.POST.get("street", "").strip()
        postcode=request.POST.get("postcode", "").strip(); city=request.POST.get("city", "").strip(); state=request.POST.get("state", "").strip(); password=request.POST.get("password", "")
        if not all((name, phone, house, street, postcode, city, state)):
            error="Complete your name, phone, and full home address."
        elif not email:
            error="An email address is required to sign in."
        else:
            try:
                validate_password(password)
                with transaction.atomic():
                    user=User.objects.create_user(email=email,name=name,password=password,role="NEEDY")
                    from .models import Needy
                    Needy.objects.create(user=user,phone=phone,address=f"{house}, {street}",postcode=postcode,city=city,state=state)
                login(request,user); return redirect("needy_dashboard")
            except ValidationError as exc: error=" ".join(exc.messages)
            except IntegrityError: error="An account with that email already exists."
    return render(request,"accounts/needy_register.html",{"error":error})


def donor_register(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = ""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        if not name or not email:
            error = "Enter your name and email address."
        else:
            try:
                validate_password(password)
                user = User.objects.create_user(
                    email=email, name=name, password=password, role="DONOR",
                )
                login(request, user)
                return redirect("donor_dashboard")
            except ValidationError as exc:
                error = " ".join(exc.messages)
            except IntegrityError:
                error = "An account with that email already exists. Please sign in."
    return render(request, "accounts/donor_register.html", {"error": error})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


def redirect_by_role(user):

    if user.role == "ADMIN":
        return redirect("admin_dashboard")

    elif user.role == "PROVIDER":
        return redirect("provider_dashboard")

    elif user.role == "DONOR":
        return redirect("donor_dashboard")

    elif user.role == "SUPPLIER":
        return redirect("supplier_dashboard")

    elif user.role == "NEEDY":
        return redirect("needy_dashboard")

    return redirect("login")


@role_required("ADMIN")
def admin_dashboard(request):
    from .models import Supplier
    return render(request, "accounts/admin_dashboard.html", {
        "pending_suppliers": Supplier.objects.filter(is_approved=False).select_related("user").order_by("created_at"),
    })


@role_required("ADMIN")
def approve_supplier(request, supplier_id):
    from django.utils import timezone
    from .models import Supplier
    supplier = get_object_or_404(Supplier, supplier_id=supplier_id)
    if request.method == "POST" and not supplier.is_approved:
        supplier.is_approved = True
        supplier.approved_at = timezone.now()
        supplier.user.is_active = True
        supplier.user.status = "ACTIVE"
        supplier.user.save(update_fields=["is_active", "status"])
        supplier.save(update_fields=["is_approved", "approved_at"])
        login_url = request.build_absolute_uri("/")
        try:
            send_mail(
                subject="Your FoodBankHub supplier account is approved",
                message=(
                    f"Hello {supplier.contact_person},\n\n"
                    f"Your supplier account for {supplier.business_name} has been approved. "
                    f"You can now sign in to FoodBankHub at {login_url} using {supplier.user.email}.\n\n"
                    "Thank you,\nFoodBankHub Admin"
                ),
                from_email=None,
                recipient_list=[supplier.user.email],
                fail_silently=False,
            )
            messages.success(request, f"{supplier.business_name} was approved and an email notice was sent.")
        except Exception:
            messages.warning(request, f"{supplier.business_name} was approved, but the email could not be sent. Check Gmail SMTP settings.")
    return redirect("admin_dashboard")


@role_required("ADMIN")
def supplier_license(request, supplier_id):
    from django.http import FileResponse
    from .models import Supplier
    supplier = get_object_or_404(Supplier, supplier_id=supplier_id)
    if not supplier.business_license:
        from django.http import Http404
        raise Http404
    return FileResponse(supplier.business_license.open("rb"), as_attachment=False, filename=supplier.business_license.name.rsplit("/", 1)[-1])


@role_required("PROVIDER")
def provider_dashboard(request):
    from django.core import signing
    from donations.models import DonationItem
    from distribution.models import Report
    from inventory.models import Inventory
    from django.db.models import F, DecimalField, ExpressionWrapper
    from django.db.models.functions import ExtractMonth, ExtractYear
    from distribution.models import ProviderSupplier
    from forecasting.models import ForecastRun
    from orders.models import PurchaseOrder
    from urgent_needs.models import UrgentNeed

    provider = request.user.provider_profile
    selected_supplier = ProviderSupplier.objects.filter(
        provider=provider, status="ACTIVE",
    ).select_related("supplier").first()
    completed_reports = Report.objects.filter(
        provider=provider, status__in=["DISTRIBUTED", "COMPLETED"],
    )
    distributed_rows = list(completed_reports.values(
        "item__name", "item__unit",
    ).annotate(total=Sum("quantity")).order_by("-total"))
    distributed_items = distributed_rows[:5]
    if len(distributed_rows) > 5:
        distributed_items.append({"item__name": "Other food", "item__unit": "items",
                                  "total": sum(row["total"] for row in distributed_rows[5:])})
    pie_colors = ["#ef4444", "#f97316", "#facc15", "#22c55e", "#06b6d4", "#3b82f6", "#8b5cf6", "#ec4899"]
    distributed_total = sum(row["total"] for row in distributed_items)
    pie_segments, running = [], 0
    for index, row in enumerate(distributed_items):
        start = running * 100 / distributed_total if distributed_total else 0
        running += row["total"]
        end = running * 100 / distributed_total if distributed_total else 0
        row["percent"] = round(row["total"] * 100 / distributed_total) if distributed_total else 0
        row["color"] = pie_colors[index % len(pie_colors)]
        pie_segments.append(f"{row['color']} {start:.2f}% {end:.2f}%")
    pie_style = f"conic-gradient({', '.join(pie_segments)})" if pie_segments else "conic-gradient(#e8eeea 0% 100%)"

    from datetime import date
    from decimal import Decimal

    today = timezone.localdate()
    current_month = date(today.year, today.month, 1)
    month_starts = []
    for offset in range(11, -1, -1):
        absolute_month = current_month.year * 12 + current_month.month - 1 - offset
        year, month_index = divmod(absolute_month, 12)
        month_starts.append(date(year, month_index + 1, 1))
    chart_start = month_starts[0]
    chart_end = date(current_month.year + (current_month.month == 12), current_month.month % 12 + 1, 1)
    monthly_totals = DonationItem.objects.filter(
        provider=provider, donation__status="PAID",
        donation__created_at__date__gte=chart_start,
        donation__created_at__date__lt=chart_end,
    ).annotate(
        year=ExtractYear("donation__created_at"),
        month=ExtractMonth("donation__created_at"),
    ).values("year", "month").annotate(total=Sum(ExpressionWrapper(
        F("quantity") * F("price"), output_field=DecimalField(max_digits=14, decimal_places=2),
    )))
    monthly_amounts = {(row["year"], row["month"]): row["total"] or Decimal("0.00") for row in monthly_totals}
    donation_months = [{
        "label": month.strftime("%b %Y"),
        "amount": monthly_amounts.get((month.year, month.month), Decimal("0.00")),
    } for month in month_starts]
    chart_width, chart_top, chart_bottom = 620, 24, 190
    donation_max = max((float(row["amount"]) for row in donation_months), default=0)
    chart_ceiling = donation_max or 1
    donation_line_points = []
    for index, row in enumerate(donation_months):
        x = 64 + index * (chart_width - 100) / max(len(donation_months) - 1, 1)
        y = chart_bottom - (float(row["amount"]) / chart_ceiling) * (chart_bottom - chart_top)
        donation_line_points.append({"x": round(x, 1), "y": round(y, 1),
                                     "label": row["label"], "amount": row["amount"]})
    donation_line_path = " ".join(f"{point['x']},{point['y']}" for point in donation_line_points)
    donation_line_axis = [
        {"y": chart_bottom, "amount": 0},
        {"y": round((chart_top + chart_bottom) / 2, 1), "amount": round(chart_ceiling / 2, 2)},
        {"y": chart_top, "amount": round(chart_ceiling, 2)},
    ]

    provider_self_report_token = signing.dumps(
        provider.provider_id, salt="distribution.provider-self-report", compress=True,
    )
    return render(request, "accounts/provider_dashboard.html", {
        "provider": provider,
        "selected_supplier": selected_supplier,
        "low_stock_count": Inventory.objects.filter(provider=provider, quantity__lte=F("threshold_level")).count(),
        "latest_forecast_run": ForecastRun.latest_for_provider(provider),
        "provider_self_report_token": provider_self_report_token,
        "inventory_count": Inventory.objects.filter(provider=provider).count(),
        "open_need_count": UrgentNeed.objects.filter(provider=provider, status="OPEN", remaining_quantity__gt=0).count(),
        "active_order_count": PurchaseOrder.objects.filter(provider=provider, status__in=["PENDING", "ACCEPTED", "SHIPPED"]).count(),
        "blocked_report_count": Report.objects.filter(provider=provider, status__startswith="BLOCKED").count(),
        "donated_quantity": DonationItem.objects.filter(provider=provider, donation__status="PAID").aggregate(total=Sum("quantity"))["total"] or 0,
        "total_stock": Inventory.objects.filter(provider=provider).aggregate(total=Sum("quantity"))["total"] or 0,
        "distributed_quantity": completed_reports.aggregate(total=Sum("quantity"))["total"] or 0,
        "distribution_count": completed_reports.count(),
        "distributed_items": distributed_items,
        "distributed_total": distributed_total,
        "distribution_pie_style": pie_style,
        "donation_months": donation_months,
        "donated_total_amount": sum((row["amount"] for row in donation_months), Decimal("0.00")),
        "donation_line_points": donation_line_points,
        "donation_line_path": donation_line_path,
        "donation_line_axis": donation_line_axis,
        "recent_reports": completed_reports.select_related(
            "needy__user", "item",
        ).order_by("-reported_at")[:6],
    })


@role_required("DONOR")
def donor_dashboard(request):
    from donations.models import Cart, Donation, DonationItem, Transaction
    carts = Cart.objects.filter(donor=request.user, status="ACTIVE").prefetch_related("items__urgent_need__item")
    donations = Donation.objects.filter(donor=request.user).order_by("-created_at")
    paid = Donation.objects.filter(donor=request.user, status="PAID")
    total_donated = paid.aggregate(total=Sum("total_amount"))["total"] or 0
    donated_items = DonationItem.objects.filter(donation__in=paid).select_related("item")
    kilograms = sum(item.quantity for item in donated_items if item.item.unit.lower() in {"kg", "kilogram", "kilograms"})
    people_helped = int(kilograms / 2)
    return render(request, "accounts/donor_dashboard.html", {
        "carts": carts, "donations": donations, "total_donated": total_donated,
        "kilograms": kilograms, "people_helped": people_helped,
    })


@role_required("SUPPLIER")
def supplier_dashboard(request):
    from orders.models import PurchaseOrder, Payout
    from distribution.models import ProviderSupplier
    supplier = request.user.supplier_profile
    orders = PurchaseOrder.objects.filter(supplier=supplier)
    pending_payments = orders.filter(status="DELIVERED", delivery_confirmed=True).exclude(payouts__status="PAID")
    paid_payouts = Payout.objects.filter(supplier=supplier, status="PAID")
    return render(request, "accounts/supplier_dashboard.html", {
        "supplier": supplier,
        "active_nav": "dashboard",
        "pending_orders": orders.filter(status__in=["PENDING", "ACCEPTED", "SHIPPED"]),
        "pending_order_count": orders.filter(status__in=["PENDING", "ACCEPTED", "SHIPPED"]).count(),
        "pending_payments": pending_payments.count(),
        "pending_payment_total": pending_payments.aggregate(total=Sum("total_amount"))["total"] or 0,
        "active_product_count": supplier.products.filter(status="ACTIVE").count(),
        "paid_total": paid_payouts.aggregate(total=Sum("amount"))["total"] or 0,
        "recent_orders": orders.select_related("provider").order_by("-created_at", "-po_id")[:5],
        "selected_providers": ProviderSupplier.objects.filter(supplier=supplier, status="ACTIVE").select_related("provider", "provider__user").order_by("provider__food_bank_name"),
    })


@role_required("SUPPLIER")
def supplier_panel(request):
    from distribution.models import ProviderSupplier
    from orders.models import PurchaseOrder
    supplier = request.user.supplier_profile
    providers = ProviderSupplier.objects.filter(
        supplier=supplier, status="ACTIVE",
    ).select_related("provider", "provider__user").order_by("provider__food_bank_name")
    for relation in providers:
        relation.order_count = PurchaseOrder.objects.filter(supplier=supplier, provider=relation.provider).count()
        relation.latest_order = PurchaseOrder.objects.filter(
            supplier=supplier, provider=relation.provider,
        ).order_by("-created_at").first()
    return render(request, "accounts/supplier_panel.html", {
        "active_nav": "panel", "supplier": supplier, "providers": providers,
        "provider_count": providers.count(), "active_product_count": supplier.products.filter(status="ACTIVE").count(),
    })


@role_required("NEEDY")
def needy_dashboard(request):
    from distribution.models import AllowanceUsage, ProviderAllowance, Report
    from datetime import timedelta
    from types import SimpleNamespace
    needy=request.user.needy_profile; today=timezone.localdate(); week_start=today-timedelta(days=today.weekday())
    usages=list(AllowanceUsage.objects.filter(needy=needy,week_start_date=week_start).select_related("provider","item").order_by("provider__food_bank_name","item__name"))
    seen={(use.provider_id,use.item_id) for use in usages}
    for limit in ProviderAllowance.objects.select_related("provider","item").order_by("provider__food_bank_name","item__name"):
        if (limit.provider_id,limit.item_id) not in seen:
            usages.append(SimpleNamespace(provider=limit.provider,item=limit.item,used_quantity=0,allowed_quantity=limit.weekly_limit,remaining_quantity=limit.weekly_limit))
    reports=Report.objects.filter(needy=needy,status__in=["DISTRIBUTED","COMPLETED"]).select_related("provider","item").order_by("-reported_at")
    blocked_count=Report.objects.filter(needy=needy,status__startswith="BLOCKED",reported_at__date__gte=week_start).count()
    return render(request,"accounts/needy_dashboard.html",{"needy":needy,"usages":usages,"reports":reports[:5],"collection_count":reports.count(),"blocked_count":blocked_count,"today":today,"week_start":week_start})


def _needy_provider_rows(postcode=""):
    from urllib.parse import urlencode
    from .models import Provider
    providers=Provider.objects.select_related("user").prefetch_related("service_areas","inventory_items__item")
    if postcode: providers=providers.filter(service_areas__postcode__iexact=postcode).distinct()
    rows=[]
    for provider in providers.order_by("food_bank_name"):
        rows.append({"provider":provider,"areas":list(provider.service_areas.all()),"stock":list(provider.inventory_items.select_related("item").all()),"has_coordinates":provider.latitude is not None and provider.longitude is not None})
    map_providers=[{"name":r["provider"].food_bank_name,"address":r["provider"].address,"hours":r["provider"].operating_hours,"lat":float(r["provider"].latitude),"lng":float(r["provider"].longitude),"url":"https://www.google.com/maps/search/?"+urlencode({"api":1,"query":r["provider"].address})} for r in rows if r["has_coordinates"]]
    return rows,map_providers


@role_required("NEEDY")
def needy_provider_finder(request):
    needy=request.user.needy_profile
    postcode=request.GET.get("postcode")
    if request.GET.get("all") == "1": postcode=""
    elif postcode is None: postcode=needy.postcode
    postcode=postcode.strip()
    rows,map_providers=_needy_provider_rows(postcode)
    return render(request,"accounts/needy_provider_finder.html",{"needy":needy,"provider_rows":rows,"map_providers":map_providers,"postcode_filter":postcode,"matching_count":len(rows)})


@role_required("NEEDY")
def needy_history(request):
    from distribution.models import Report
    from datetime import timedelta
    today=timezone.localdate();period=request.GET.get("period","")
    reports=Report.objects.filter(needy=request.user.needy_profile).select_related("provider","item").order_by("-reported_at")
    if period=="week": reports=reports.filter(reported_at__date__gte=today-timedelta(days=today.weekday()))
    elif period=="month": reports=reports.filter(reported_at__year=today.year,reported_at__month=today.month)
    report_rows=list(reports[:200]);week_rows=list(Report.objects.filter(needy=request.user.needy_profile,reported_at__date__gte=today-timedelta(days=today.weekday()),status__in=["DISTRIBUTED","COMPLETED"]).select_related("item"))
    return render(request,"accounts/needy_history.html",{"reports":report_rows,"period":period,"summary_count":len(week_rows),"summary_items":{name:sum(float(r.quantity) for r in week_rows if r.item.name.lower()==name) for name in {r.item.name.lower() for r in week_rows}}})


@role_required("NEEDY")
def needy_scan(request):
    return render(request,"accounts/needy_scan.html")


def provider_register(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = ""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        food_bank_name = request.POST.get("food_bank_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        address = request.POST.get("address", "").strip()
        operating_hours = request.POST.get("operating_hours", "").strip()
        if not all((name, email, food_bank_name, phone, address, operating_hours)):
            error = "Complete all required fields."
        else:
            try:
                validate_password(password)
                with transaction.atomic():
                    user = User.objects.create_user(
                        email=email, name=name, password=password, role="PROVIDER",
                    )
                    from .models import Provider
                    Provider.objects.create(
                        user=user, food_bank_name=food_bank_name, phone=phone,
                        address=address, operating_hours=operating_hours,
                    )
                login(request, user)
                return redirect("provider_dashboard")
            except ValidationError as exc:
                error = " ".join(exc.messages)
            except IntegrityError:
                error = "An account with that email already exists."
    return render(request, "accounts/provider_register.html", {"error": error})


def supplier_register(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = ""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        fields = {key: request.POST.get(key, "").strip() for key in (
            "business_name", "ssm_registration_no", "contact_person", "phone", "bank_account", "bank_name",
        )}
        license_file = request.FILES.get("business_license")
        if not name or not email or not all(fields.values()) or not license_file:
            error = "Complete all fields and attach your business license."
        elif not license_file.name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
            error = "Upload a PDF, PNG, or JPG business license."
        else:
            try:
                validate_password(password)
                with transaction.atomic():
                    user = User.objects.create_user(
                        email=email, name=name, password=password, role="SUPPLIER", is_active=False, status="INACTIVE",
                    )
                    from .models import Supplier
                    Supplier.objects.create(user=user, business_license=license_file, is_approved=False, **fields)
                return render(request, "accounts/supplier_register.html", {"submitted": True})
            except ValidationError as exc:
                error = " ".join(exc.messages)
            except IntegrityError:
                error = "An account with that email already exists."
    return render(request, "accounts/supplier_register.html", {"error": error})


@role_required("PROVIDER")
def provider_settings(request):
    provider = request.user.provider_profile
    saved = False
    if request.method == "POST":
        provider.food_bank_name = request.POST.get("food_bank_name", "").strip()
        provider.phone = request.POST.get("phone", "").strip()
        provider.address = request.POST.get("address", "").strip()
        provider.operating_hours = request.POST.get("operating_hours", "").strip()
        if all((provider.food_bank_name, provider.phone, provider.address, provider.operating_hours)):
            provider.save(update_fields=["food_bank_name", "phone", "address", "operating_hours"])
            saved = True
        else:
            saved = False
    return render(request, "accounts/provider_settings.html", {"provider": provider, "saved": saved})

