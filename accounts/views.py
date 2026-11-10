from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseNotAllowed
from django.template.loader import render_to_string
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
            if allowed_role == "PROVIDER" and (
                not hasattr(request.user, "provider_profile")
                or not request.user.provider_profile.is_approved
            ):
                return redirect("login")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def login_view(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password")

        from .models import Provider, Supplier
        pending_supplier = Supplier.objects.filter(user__email__iexact=email, is_approved=False, rejected_at__isnull=True).select_related("user").first()
        if pending_supplier and pending_supplier.user.check_password(password or ""):
            return render(request, "accounts/login.html", {
                "pending_approval": "Your supplier account is waiting for admin approval. We’ll email you when it’s approved.",
                "email": email,
            })
        pending_provider = Provider.objects.filter(user__email__iexact=email, is_approved=False, rejected_at__isnull=True).select_related("user").first()
        if pending_provider and pending_provider.user.check_password(password or ""):
            return render(request, "accounts/login.html", {
                "pending_approval": "Your provider account is waiting for admin approval. We’ll email you when it’s approved.",
                "email": email,
            })

        user = authenticate(request, email=email, password=password)
        if user is None and email:
            from .models import Needy
            matching_accounts = User.objects.filter(role="NEEDY", needy_profile__phone=email)
            if matching_accounts.count() == 1:
                candidate = matching_accounts.first()
                if candidate.is_active and candidate.check_password(password or ""):
                    user = candidate

        if user is not None:
            if user.role == "SUPPLIER" and hasattr(user, "supplier_profile") and not user.supplier_profile.is_approved:
                return render(request, "accounts/login.html", {
                    "pending_approval": "Your supplier account is waiting for admin approval. We’ll email you when it’s approved.",
                    "email": email,
                })
            if user.role == "PROVIDER" and hasattr(user, "provider_profile") and not user.provider_profile.is_approved:
                return render(request, "accounts/login.html", {
                    "pending_approval": "Your provider account is waiting for admin approval. We’ll email you when it’s approved.",
                    "email": email,
                })
            login(request, user)
            return redirect_by_role(user)

        return render(
            request,
            "accounts/login.html",
            {"error": "Invalid email or password.", "email": email}
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
        else:
            try:
                validate_password(password)
                from .models import Needy
                if Needy.objects.filter(phone=phone).exists():
                    raise ValidationError("An account already uses this phone number. Sign in with your phone or use a different number.")
                with transaction.atomic():
                    if not email:
                        from uuid import uuid4
                        email = f"needy-{uuid4().hex}@no-email.foodbankhub.invalid"
                    user=User.objects.create_user(email=email,name=name,password=password,role="NEEDY")
                    Needy.objects.create(user=user,phone=phone,address=f"{house}, {street}",postcode=postcode,city=city,state=state)
                login(request,user); return redirect("needy_dashboard")
            except ValidationError as exc: error=" ".join(exc.messages)
            except IntegrityError: error="An account with that email already exists."
            except DatabaseError: error="Registration is temporarily unavailable. Please try again shortly."
    return render(request,"accounts/needy_register.html",{"error":error})


def donor_register(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = ""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        if not name or not email:
            error = "Enter your name and email address."
        else:
            try:
                validate_password(password)
                user = User.objects.create_user(
                    email=email, name=name, password=password, role="DONOR", phone=phone,
                )
                login(request, user)
                return redirect("donor_dashboard")
            except ValidationError as exc:
                error = " ".join(exc.messages)
            except IntegrityError:
                error = "An account with that email already exists. Please sign in."
            except DatabaseError:
                error = "Registration is temporarily unavailable. Please try again shortly."
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
    from datetime import date, timedelta
    from decimal import Decimal
    import re
    from django.conf import settings
    from django.db.models import Avg, Count, Sum, Q
    from django.db.models.functions import ExtractMonth, ExtractWeekDay, ExtractYear, TruncDate
    from .models import Provider, Supplier
    from donations.models import Donation, Transaction
    from distribution.models import Report
    from forecasting.models import Forecast, ForecastRun
    from orders.models import Payout, PurchaseOrder
    from urgent_needs.models import UrgentNeed

    today = timezone.localdate()
    providers = Provider.objects.select_related("user").annotate(
        service_area_count=Count("service_areas", distinct=True),
        blocked_count=Count("distribution_reports", filter=Q(distribution_reports__status__startswith="BLOCKED"), distinct=True),
    ).order_by("food_bank_name")
    pending_suppliers = Supplier.objects.filter(is_approved=False, rejected_at__isnull=True).select_related("user").order_by("created_at")
    pending_providers = Provider.objects.filter(is_approved=False, rejected_at__isnull=True).select_related("user").order_by("created_at")
    approved_suppliers = Supplier.objects.filter(is_approved=True, user__is_active=True)
    paid_donations = Donation.objects.filter(status="PAID")
    completed_reports = Report.objects.filter(status__in=["DISTRIBUTED", "COMPLETED"])
    pending_payouts = Payout.objects.filter(status="PENDING")
    all_donation_total = paid_donations.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    po_total = PurchaseOrder.objects.exclude(status="CANCELLED").aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    platform_fee_rate = Decimal("0.022")

    revenue_period = request.GET.get("revenue_period", "30")
    if revenue_period not in {"7", "30", "365"}:
        revenue_period = "30"
    revenue_labels, revenue_values = [], []
    if revenue_period == "365":
        month_start = date(today.year, today.month, 1)
        months = []
        for offset in range(11, -1, -1):
            month_number = month_start.year * 12 + month_start.month - 1 - offset
            year, month_index = divmod(month_number, 12)
            months.append(date(year, month_index + 1, 1))
        grouped_revenue = paid_donations.filter(
            created_at__date__gte=months[0],
            created_at__date__lte=today,
        ).annotate(year=ExtractYear("created_at"), month=ExtractMonth("created_at")).values("year", "month").annotate(total=Sum("total_amount"))
        revenue_by_period = {(row["year"], row["month"]): row["total"] for row in grouped_revenue}
        for month in months:
            amount = revenue_by_period.get((month.year, month.month), Decimal("0.00")) or Decimal("0.00")
            revenue_labels.append(month.strftime("%b %Y"))
            revenue_values.append(float(amount * platform_fee_rate))
    else:
        days = int(revenue_period)
        start = today - timedelta(days=days - 1)
        grouped_revenue = paid_donations.filter(created_at__date__gte=start, created_at__date__lte=today).annotate(day=TruncDate("created_at")).values("day").annotate(total=Sum("total_amount"))
        revenue_by_period = {row["day"]: row["total"] for row in grouped_revenue}
        for offset in range(days):
            period_day = start + timedelta(days=offset)
            amount = revenue_by_period.get(period_day, Decimal("0.00")) or Decimal("0.00")
            revenue_labels.append(period_day.strftime("%d %b"))
            revenue_values.append(float(amount * platform_fee_rate))

    current_forecasts = []
    for provider in Provider.objects.only("provider_id"):
        current_run = ForecastRun.latest_for_provider(provider)
        rows = Forecast.objects.filter(provider=provider, run=current_run) if current_run else Forecast.objects.filter(provider=provider, run__isnull=True)
        current_forecasts.extend(rows.select_related("item"))
    forecast_scored = [row for row in current_forecasts if row.mape_score is not None]
    current_mape = sum((row.mape_score for row in forecast_scored), Decimal("0.00")) / len(forecast_scored) if forecast_scored else None

    growth_start = date(today.year, today.month, 1)
    growth_labels = []
    growth_months = []
    for offset in range(11, -1, -1):
        month_value = growth_start.year * 12 + growth_start.month - 1 - offset
        year, month_index = divmod(month_value, 12)
        month_date = date(year, month_index + 1, 1)
        growth_months.append((year, month_index + 1))
        growth_labels.append(month_date.strftime("%b %Y"))
    growth_rows = User.objects.filter(created_at__date__gte=date(growth_months[0][0], growth_months[0][1], 1)).annotate(
        year=ExtractYear("created_at"), month=ExtractMonth("created_at"),
    ).values("year", "month", "role").annotate(total=Count("user_id"))
    growth_lookup = {(row["year"], row["month"], row["role"]): row["total"] for row in growth_rows}
    growth_series = [{
        "label": label,
        "data": [growth_lookup.get((year, month, role), 0) for year, month in growth_months],
    } for label, role in (("Providers", "PROVIDER"), ("Donors", "DONOR"), ("Needy", "NEEDY"), ("Suppliers", "SUPPLIER"))]

    supplier_rows = approved_suppliers.annotate(
        average_rating=Avg("provider_reviews__rating"),
        review_count=Count("provider_reviews", distinct=True),
        order_count=Count("purchase_orders", distinct=True),
        delivered_count=Count("purchase_orders", filter=Q(purchase_orders__status="DELIVERED"), distinct=True),
    ).order_by("-average_rating", "-delivered_count", "business_name")[:10]
    needy_active_week = Report.objects.filter(
        reported_at__date__gte=today - timedelta(days=today.weekday()),
        reported_at__date__lte=today,
        status__in=("DISTRIBUTED", "COMPLETED"),
    ).values("needy_id").distinct().count()

    malaysia_states = [
        "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang",
        "Perak", "Perlis", "Pulau Pinang", "Sabah", "Sarawak", "Selangor",
        "Terengganu", "Kuala Lumpur", "Labuan", "Putrajaya",
    ]
    provider_state_counts = {state: 0 for state in malaysia_states}
    provider_state_counts["Unspecified"] = 0
    state_aliases = {"Penang": "Pulau Pinang", "Wilayah Persekutuan Kuala Lumpur": "Kuala Lumpur"}
    for address in Provider.objects.values_list("address", flat=True):
        address_lower = (address or "").lower()
        matched_state = next((state for state in malaysia_states if re.search(r"\b" + re.escape(state.lower()) + r"\b", address_lower)), None)
        if not matched_state:
            matched_alias = next((alias for alias in state_aliases if re.search(r"\b" + re.escape(alias.lower()) + r"\b", address_lower)), None)
            matched_state = state_aliases.get(matched_alias)
        provider_state_counts[matched_state or "Unspecified"] += 1

    top_supplier_transfers = list(Payout.objects.filter(status="PAID").values(
        "supplier__business_name",
    ).annotate(total=Sum("amount")).order_by("-total", "supplier__business_name")[:10])

    weekday_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday_counts = [0] * 7
    collection_trend_start = today - timedelta(days=364)
    weekday_rows = completed_reports.filter(
        reported_at__date__gte=collection_trend_start,
        reported_at__date__lte=today,
    ).annotate(weekday=ExtractWeekDay("reported_at")).values("weekday").annotate(
        collection_count=Count("report_id"),
    )
    for row in weekday_rows:
        weekday_counts[(row["weekday"] + 5) % 7] = row["collection_count"]

    context = {
        "pending_suppliers": pending_suppliers,
        "pending_providers": pending_providers,
        "providers": providers,
        "suppliers": Supplier.objects.select_related("user").order_by("business_name"),
        "donors": User.objects.filter(role="DONOR").order_by("name", "email"),
        "provider_count": Provider.objects.count(), "supplier_count": Supplier.objects.count(),
        "today": today,
        "active_needy_week_start": today - timedelta(days=today.weekday()),
        "active_supplier_count": approved_suppliers.count(),
        "pending_provider_count": pending_providers.count(),
        "pending_supplier_count": pending_suppliers.count(),
        "donor_count": User.objects.filter(role="DONOR").count(),
        "needy_count": User.objects.filter(role="NEEDY").count(), "user_count": User.objects.count(),
        "donation_count": paid_donations.count(),
        "donation_total": all_donation_total,
        "purchase_order_total": po_total,
        "platform_fee_revenue": all_donation_total * platform_fee_rate,
        "platform_fee_rate_percent": 2.2,
        "supplier_annual_fee_proposed": Decimal("240.00"),
        "distributed_total": completed_reports.aggregate(total=Sum("quantity"))["total"] or 0,
        "distributed_report_count": completed_reports.count(),
        "blocked_total": Report.objects.filter(status__startswith="BLOCKED").count(),
        "providers_without_areas": Provider.objects.filter(service_areas__isnull=True).count(),
        "pending_payout_count": pending_payouts.count(),
        "pending_payout_total": pending_payouts.aggregate(total=Sum("amount"))["total"] or 0,
        "urgent_need_count": UrgentNeed.objects.filter(status="OPEN", remaining_quantity__gt=0).count(),
        "current_mape": current_mape,
        "active_needy_week": needy_active_week,
        "supplier_rows": supplier_rows,
        "revenue_period": revenue_period,
        "revenue_chart": {"labels": revenue_labels, "values": revenue_values},
        "growth_chart": {"labels": growth_labels, "series": growth_series},
        "provider_state_chart": {"labels": list(provider_state_counts.keys()), "values": list(provider_state_counts.values())},
        "supplier_transfer_chart": {"labels": [row["supplier__business_name"] for row in top_supplier_transfers], "values": [float(row["total"] or 0) for row in top_supplier_transfers]},
        "needy_weekday_chart": {"labels": weekday_labels, "values": weekday_counts},
        "recent_transactions": Transaction.objects.select_related("donation", "donation__donor").order_by("-created_at")[:8],
        "fpx_configured": all((settings.BILLPLZ_SANDBOX_API_KEY, settings.BILLPLZ_SANDBOX_COLLECTION_ID, settings.BILLPLZ_X_SIGNATURE_KEY)),
    }
    return render(request, "accounts/admin_dashboard.html", context)


@role_required("ADMIN")
def admin_approvals(request):
    from .models import Provider, Supplier

    return render(request, "accounts/admin_approvals.html", {
        "pending_suppliers": Supplier.objects.filter(
            is_approved=False, rejected_at__isnull=True,
        ).select_related("user").order_by("created_at"),
        "pending_providers": Provider.objects.filter(
            is_approved=False, rejected_at__isnull=True,
        ).select_related("user").order_by("created_at"),
    })


@role_required("ADMIN")
def admin_user_directory(request):
    from django.core.paginator import Paginator
    from django.db.models import Q

    users = User.objects.select_related(
        "provider_profile", "supplier_profile", "needy_profile",
    ).order_by("name", "email")
    role = request.GET.get("role", "").strip().upper()
    allowed_roles = {value for value, _label in User.Role.choices}
    if role in allowed_roles:
        users = users.filter(role=role)
    else:
        role = ""
    search = request.GET.get("q", "").strip()
    if search:
        users = users.filter(Q(name__icontains=search) | Q(email__icontains=search))
    page = Paginator(users, 50).get_page(request.GET.get("page"))
    return render(request, "accounts/admin_user_directory.html", {
        "user_page": page, "role_choices": User.Role.choices,
        "selected_role": role, "search": search,
        "result_count": page.paginator.count,
    })


@role_required("ADMIN")
def admin_user_detail(request, user_id):
    from datetime import timedelta
    from django.db.models import Avg, Count, Sum
    from django.db.models.functions import ExtractHour
    from django.utils import timezone
    from distribution.models import AllowanceUsage, Report, ProviderSupplier
    from donations.models import Donation, DonationItem
    from forecasting.models import Forecast
    from inventory.models import Inventory, Item
    from orders.models import PurchaseOrder
    from urgent_needs.models import UrgentNeed
    account = get_object_or_404(
        User.objects.select_related("provider_profile", "supplier_profile", "needy_profile"),
        user_id=user_id,
    )
    template_by_role = {
        "PROVIDER": "accounts/admin_users/provider_detail.html",
        "NEEDY": "accounts/admin_users/needy_detail.html",
        "DONOR": "accounts/admin_users/donor_detail.html",
        "SUPPLIER": "accounts/admin_users/supplier_detail.html",
        "ADMIN": "accounts/admin_users/admin_detail.html",
    }
    context = {"account": account}
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    if account.role == "PROVIDER":
        provider = getattr(account, "provider_profile", None)
        context["provider"] = provider
        context["service_area_text"] = "\n".join(
            f"{area.postcode} | {area.zone_name}"
            for area in provider.service_areas.order_by("postcode", "zone_name")
        ) if provider else ""
        if provider:
            provider_reports = Report.objects.filter(provider=provider)
            today_reports = provider_reports.filter(reported_at__date=today, status__in=("DISTRIBUTED", "COMPLETED"))
            forecast_base = Forecast.objects.filter(provider=provider)
            forecast_months = list(forecast_base.dates("forecast_date", "month", order="DESC"))
            forecast_items = Item.objects.filter(forecasts__provider=provider).distinct().order_by("name")
            selected_forecast_item = request.GET.get("forecast_item", "")
            valid_item_ids = {str(item.pk) for item in forecast_items}
            if selected_forecast_item not in valid_item_ids:
                selected_forecast_item = ""
            selected_forecast_month = request.GET.get("forecast_month", "")
            valid_months = {month.strftime("%Y-%m") for month in forecast_months}
            if selected_forecast_month not in valid_months:
                selected_forecast_month = forecast_months[0].strftime("%Y-%m") if forecast_months else ""
            filtered_forecasts = forecast_base
            if selected_forecast_item:
                filtered_forecasts = filtered_forecasts.filter(item_id=selected_forecast_item)
            if selected_forecast_month:
                month_year, month_number = (int(part) for part in selected_forecast_month.split("-", 1))
                filtered_forecasts = filtered_forecasts.filter(forecast_date__year=month_year, forecast_date__month=month_number)
            context.update({
                "admin_inventory": Inventory.objects.filter(provider=provider).select_related("item").order_by("item__name"),
                "admin_urgent_needs": UrgentNeed.objects.filter(provider=provider).select_related("item").order_by("status", "item__name"),
                "admin_purchase_orders": PurchaseOrder.objects.filter(provider=provider).select_related("supplier", "supplier__user").prefetch_related("items__product__item").order_by("-created_at"),
                "admin_forecasts": filtered_forecasts.select_related("item").order_by("-forecast_date", "item__name"),
                "admin_forecast_items": forecast_items,
                "admin_forecast_months": forecast_months,
                "selected_forecast_item": selected_forecast_item,
                "selected_forecast_month": selected_forecast_month,
                "admin_provider_mape": filtered_forecasts.filter(mape_score__isnull=False).aggregate(value=Avg("mape_score"))["value"],
                "admin_open_need_count": UrgentNeed.objects.filter(provider=provider, status="OPEN", remaining_quantity__gt=0).count(),
                "admin_purchase_order_count": PurchaseOrder.objects.filter(provider=provider, status__in=("PENDING", "ACCEPTED", "SHIPPED")).count(),
                "admin_daily_distributed": today_reports.aggregate(value=Sum("quantity"))["value"] or 0,
                "admin_daily_donations": DonationItem.objects.filter(provider=provider, donation__status="PAID", donation__created_at__date=today).aggregate(value=Sum("quantity"))["value"] or 0,
                "admin_daily_donation_count": DonationItem.objects.filter(provider=provider, donation__status="PAID", donation__created_at__date=today).values("donation_id").distinct().count(),
                "admin_daily_pos": PurchaseOrder.objects.filter(provider=provider, created_at__date=today).count(),
                "admin_provider_suppliers": ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").order_by("supplier__business_name"),
                "admin_daily_stock_used": today_reports.aggregate(value=Sum("quantity"))["value"] or 0,
                "admin_needy_usage": provider_reports.filter(status__in=("DISTRIBUTED", "COMPLETED")).values("item__name").annotate(total=Sum("quantity")).order_by("-total"),
                "admin_peak_hours": provider_reports.filter(status__in=("DISTRIBUTED", "COMPLETED")).annotate(hour=ExtractHour("reported_at")).values("hour").annotate(total=Count("report_id")).order_by("-total")[:5],
            })
    elif account.role == "NEEDY":
        needy = getattr(account, "needy_profile", None)
        context["needy"] = needy
        if needy:
            context["admin_allowances"] = AllowanceUsage.objects.filter(needy=needy, week_start_date=week_start).select_related("provider", "item").order_by("provider__food_bank_name", "item__name")
            context["admin_needy_reports"] = Report.objects.filter(needy=needy).select_related("provider", "item").order_by("-reported_at")
            context["admin_week_start"] = week_start
    elif account.role == "SUPPLIER":
        supplier = getattr(account, "supplier_profile", None)
        context["supplier"] = supplier
        if supplier:
            context["admin_supplier_orders"] = PurchaseOrder.objects.filter(supplier=supplier).select_related("provider", "provider__user").prefetch_related("items__product__item").order_by("-created_at")
            context["admin_supplier_panels"] = ProviderSupplier.objects.filter(supplier=supplier, status="ACTIVE").select_related("provider", "provider__user").order_by("provider__food_bank_name")
    elif account.role == "DONOR":
        donations = Donation.objects.filter(donor=account).order_by("-created_at")
        context["admin_donations"] = donations
        context["admin_donation_total"] = donations.filter(status="PAID").aggregate(value=Sum("total_amount"))["value"] or 0
    return render(request, template_by_role.get(account.role, "accounts/admin_users/admin_detail.html"), context)


@role_required("ADMIN")
def admin_user_update(request, user_id):
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    from distribution.models import ServiceArea

    if request.method != "POST":
        return redirect("admin_user_directory")
    account = get_object_or_404(User, user_id=user_id)
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip().lower()
    status = request.POST.get("status", "").strip().upper()
    error = None
    if not name or len(name) > 100:
        error = "Enter a name with no more than 100 characters."
    elif not email:
        error = "Enter an email address."
    else:
        try:
            validate_email(email)
        except ValidationError:
            error = "Enter a valid email address."
    if not error and User.objects.filter(email__iexact=email).exclude(pk=account.pk).exists():
        error = "That email address is already used by another account."
    if not error and status not in User.Status.values:
        error = "Choose a valid account status."
    if not error and account.pk == request.user.pk and status != "ACTIVE":
        error = "You cannot deactivate the account you are currently using."
    profile_fields = {
        "PROVIDER": ("provider_profile", ("food_bank_name", "phone", "address", "operating_hours")),
        "NEEDY": ("needy_profile", ("phone", "address", "postcode", "city", "state")),
        "SUPPLIER": ("supplier_profile", ("business_name", "ssm_registration_no", "contact_person", "phone", "bank_account", "bank_name")),
    }
    profile_uploads = {"PROVIDER": ("photo", "service_document"), "SUPPLIER": ("business_license",)}
    profile = None
    cleaned_profile = {}
    if not error and account.role in profile_fields:
        relation, fields = profile_fields[account.role]
        profile = getattr(account, relation, None)
        if profile is None:
            error = "This account has no profile record to update."
        else:
            for field_name in fields:
                try:
                    cleaned_profile[field_name] = profile._meta.get_field(field_name).clean(
                        request.POST.get(field_name, "").strip(), profile,
                    )
                except ValidationError as exc:
                    error = " ".join(exc.messages)
                    break
            if not error:
                for field_name in profile_uploads.get(account.role, ()):
                    uploaded = request.FILES.get(field_name)
                    if uploaded:
                        try:
                            cleaned_profile[field_name] = profile._meta.get_field(field_name).clean(uploaded, profile)
                        except ValidationError as exc:
                            error = " ".join(exc.messages)
                            break

    parsed_areas = None
    if not error and account.role == "PROVIDER":
        parsed_areas = []
        for line in request.POST.get("service_areas", "").splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" not in line:
                error = "Enter each service area as postcode | zone name, one per line."
                break
            postcode, zone_name = (part.strip() for part in line.split("|", 1))
            try:
                postcode = ServiceArea._meta.get_field("postcode").clean(postcode, None)
                zone_name = ServiceArea._meta.get_field("zone_name").clean(zone_name, None)
            except ValidationError as exc:
                error = " ".join(exc.messages)
                break
            if not postcode or not zone_name:
                error = "Each service area needs both a postcode and zone name."
                break
            parsed_areas.append((postcode, zone_name))

    if not error and account.role == "SUPPLIER":
        from .models import Supplier
        if Supplier.objects.filter(
            ssm_registration_no__iexact=cleaned_profile.get("ssm_registration_no", ""),
        ).exclude(pk=profile.pk).exists():
            error = "This SSM number is already registered."

    if error:
        messages.error(request, error)
        return redirect("admin_user_detail", user_id=account.pk)

    try:
        with transaction.atomic():
            account.name = name
            account.email = email
            account.status = status
            account.is_active = status == "ACTIVE"
            account.save(update_fields=["name", "email", "status", "is_active"])
            if profile:
                for field_name, value in cleaned_profile.items():
                    setattr(profile, field_name, value)
                profile.save()
            if account.role == "PROVIDER" and profile is not None:
                existing_areas = list(profile.service_areas.order_by("postcode", "zone_name").values_list("postcode", "zone_name"))
                if existing_areas != parsed_areas:
                    profile.service_areas.all().delete()
                    ServiceArea.objects.bulk_create([
                        ServiceArea(provider=profile, postcode=postcode, zone_name=zone_name)
                        for postcode, zone_name in parsed_areas
                    ])
    except IntegrityError as exc:
        if account.role == "SUPPLIER" and "ssm" in str(exc).lower():
            messages.error(request, "This SSM number is already registered.")
        else:
            messages.error(request, "Those changes conflict with an existing account record. Check the details and try again.")
        return redirect("admin_user_detail", user_id=account.pk)
    except DatabaseError:
        messages.error(request, "We couldn't save those changes right now. Please try again shortly.")
        return redirect("admin_user_detail", user_id=account.pk)
    messages.success(request, f"Changes to {account.name}'s account were saved.")
    return redirect("admin_user_directory")


@role_required("ADMIN")
def admin_user_delete(request, user_id):
    from django.db.models.deletion import ProtectedError

    if request.method != "POST":
        return redirect("admin_user_directory")
    account = get_object_or_404(User, user_id=user_id)
    if account.pk == request.user.pk:
        messages.error(request, "You cannot delete the account you are currently using.")
        return redirect("admin_user_directory")
    display_name = account.name
    try:
        account.delete()
    except ProtectedError:
        messages.error(request, f"{display_name}'s account is linked to protected records and cannot be deleted.")
    else:
        messages.success(request, f"{display_name}'s account and linked profile were deleted.")
    return redirect("admin_user_directory")


@role_required("ADMIN")
def admin_needy_allowance_update(request, user_id, usage_id):
    from distribution.models import AllowanceUsage
    if request.method != "POST":
        return redirect("admin_user_detail", user_id=user_id)
    account = get_object_or_404(User, user_id=user_id, role="NEEDY")
    usage = get_object_or_404(AllowanceUsage, allowance_id=usage_id, needy__user=account)
    try:
        weekly_limit = int(request.POST.get("weekly_limit", ""))
        if weekly_limit < 0:
            raise ValueError
    except (TypeError, ValueError):
        messages.error(request, "Enter a weekly limit of zero or more.")
    else:
        usage.allowed_quantity = weekly_limit
        usage.remaining_quantity = max(0, weekly_limit - usage.used_quantity)
        usage.admin_override = True
        usage.save(update_fields=["allowed_quantity", "remaining_quantity", "admin_override", "updated_at"])
        messages.success(request, f"This week's {usage.item.name} allowance was updated.")
    return redirect("admin_user_detail", user_id=account.pk)


@role_required("ADMIN")
def approve_supplier(request, supplier_id):
    from django.utils import timezone
    from .models import Supplier
    supplier = get_object_or_404(Supplier.objects.select_related("user"), supplier_id=supplier_id)
    if request.method == "POST" and not supplier.is_approved:
        if request.POST.get("documents_reviewed") != "on":
            messages.error(request, "Review all submitted supplier documents and confirm before approving.")
            return redirect("admin_user_detail", user_id=supplier.user_id)
        supplier.is_approved = True
        supplier.approved_at = timezone.now()
        supplier.rejected_at = None
        supplier.documents_reviewed_at = timezone.now()
        supplier.documents_reviewed_by = request.user
        supplier.user.is_active = True
        supplier.user.status = "ACTIVE"
        supplier.user.save(update_fields=["is_active", "status"])
        supplier.save(update_fields=["is_approved", "approved_at", "rejected_at", "documents_reviewed_at", "documents_reviewed_by"])
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
                html_message=render_to_string("accounts/emails/account_approved.html", {
                    "account_type": "Supplier", "organization_name": supplier.business_name,
                    "recipient_name": supplier.contact_person, "account_email": supplier.user.email,
                    "login_url": login_url,
                }),
                fail_silently=False,
            )
            messages.success(request, f"{supplier.business_name} was approved and an email notice was sent.")
        except Exception:
            messages.warning(request, f"{supplier.business_name} was approved, but the email could not be sent. Check Gmail SMTP settings.")
    return redirect("admin_user_directory")


@role_required("ADMIN")
def reject_supplier(request, supplier_id):
    from .models import Supplier
    from distribution.models import ProviderSupplier
    supplier = get_object_or_404(Supplier.objects.select_related("user"), supplier_id=supplier_id)
    if request.method == "POST":
        with transaction.atomic():
            supplier.is_approved = False
            supplier.rejected_at = timezone.now()
            supplier.user.is_active = False
            supplier.user.status = "INACTIVE"
            supplier.user.save(update_fields=["is_active", "status"])
            supplier.save(update_fields=["is_approved", "rejected_at"])
            ProviderSupplier.objects.filter(supplier=supplier, status="ACTIVE").update(status="INACTIVE")
        messages.success(request, f"{supplier.business_name} was rejected and its account was deactivated.")
    return redirect("admin_user_directory")


@role_required("ADMIN")
def approve_provider(request, provider_id):
    from .models import Provider
    provider = get_object_or_404(Provider.objects.select_related("user"), provider_id=provider_id)
    if request.method == "POST" and not provider.is_approved:
        if request.POST.get("documents_reviewed") != "on":
            messages.error(request, "Review all submitted provider documents and confirm before approving.")
            return redirect("admin_user_detail", user_id=provider.user_id)
        provider.is_approved = True
        provider.approved_at = timezone.now()
        provider.rejected_at = None
        provider.documents_reviewed_at = timezone.now()
        provider.documents_reviewed_by = request.user
        provider.user.is_active = True
        provider.user.status = "ACTIVE"
        provider.user.save(update_fields=["is_active", "status"])
        provider.save(update_fields=["is_approved", "approved_at", "rejected_at", "documents_reviewed_at", "documents_reviewed_by"])
        login_url = request.build_absolute_uri("/")
        try:
            send_mail(
                subject="Your FoodBankHub provider account is approved",
                message=(
                    f"Hello {provider.user.name},\n\n"
                    f"Your provider account for {provider.food_bank_name} has been approved. "
                    f"You can now sign in to FoodBankHub at {login_url} using {provider.user.email}.\n\n"
                    "Thank you,\nFoodBankHub Admin"
                ),
                from_email=None,
                recipient_list=[provider.user.email],
                html_message=render_to_string("accounts/emails/account_approved.html", {
                    "account_type": "Provider", "organization_name": provider.food_bank_name,
                    "recipient_name": provider.user.name, "account_email": provider.user.email,
                    "login_url": login_url,
                }),
                fail_silently=False,
            )
            messages.success(request, f"{provider.food_bank_name} was approved and an email notice was sent.")
        except Exception:
            messages.warning(request, f"{provider.food_bank_name} was approved, but the email could not be sent. Check email settings.")
    return redirect("admin_user_detail", user_id=provider.user_id)


@role_required("ADMIN")
def reject_provider(request, provider_id):
    from .models import Provider
    provider = get_object_or_404(Provider.objects.select_related("user"), provider_id=provider_id)
    if request.method == "POST":
        provider.is_approved = False
        provider.rejected_at = timezone.now()
        provider.user.is_active = False
        provider.user.status = "INACTIVE"
        provider.user.save(update_fields=["is_active", "status"])
        provider.save(update_fields=["is_approved", "rejected_at"])
        messages.success(request, f"{provider.food_bank_name} was rejected and deactivated.")
    return redirect("admin_user_detail", user_id=provider.user_id)


@role_required("ADMIN")
def admin_provider_asset(request, user_id, asset):
    from django.http import FileResponse, Http404
    account = get_object_or_404(User.objects.select_related("provider_profile"), user_id=user_id, role="PROVIDER")
    provider = getattr(account, "provider_profile", None)
    field_name = {"photo": "photo", "document": "service_document"}.get(asset)
    if not provider or not field_name:
        raise Http404
    uploaded = getattr(provider, field_name)
    if not uploaded:
        raise Http404
    response = FileResponse(uploaded.open("rb"), as_attachment=asset == "document", filename=uploaded.name.rsplit("/", 1)[-1])
    response["Cache-Control"] = "private, no-store"
    return response


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
def provider_tour_complete(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    request.user.provider_tour_completed = True
    request.user.save(update_fields=["provider_tour_completed"])
    return JsonResponse({"ok": True})


@role_required("PROVIDER")
def provider_tour_restart(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    request.user.provider_tour_completed = False
    request.user.save(update_fields=["provider_tour_completed"])
    messages.success(request, "Your provider guide has restarted. Follow the steps to explore your dashboard.")
    return redirect("provider_dashboard")


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
    from distribution.models import ServiceArea
    from .models import Provider

    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        food_bank_name = request.POST.get("food_bank_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        address = request.POST.get("address", "").strip()
        operating_hours = request.POST.get("operating_hours", "").strip()
        service_areas = request.POST.get("service_areas", "")
        photo = request.FILES.get("photo")
        service_document = request.FILES.get("service_document")
        parsed_areas = []
        if email and Provider.objects.filter(user__email__iexact=email, is_approved=False, rejected_at__isnull=True).exists():
            error = "Your provider account is waiting for admin approval. We’ll email you when it’s approved."
        elif not all((email, password, food_bank_name, phone, address, operating_hours, service_areas.strip(), photo, service_document)):
            error = "Complete every required field and upload the food bank photo and supporting document."
        else:
            try:
                if len(password) < 12 or not any(char.islower() for char in password) or not any(char.isupper() for char in password) or not any(char.isdigit() for char in password) or not any(not char.isalnum() for char in password):
                    raise ValidationError("Use at least 12 characters with uppercase and lowercase letters, a number, and a symbol.")
                validate_password(password)
                for line in service_areas.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if "|" not in line:
                        raise ValidationError("Enter each service area as postcode | zone name, one per line.")
                    postcode, zone_name = (part.strip() for part in line.split("|", 1))
                    postcode = ServiceArea._meta.get_field("postcode").clean(postcode, None)
                    zone_name = ServiceArea._meta.get_field("zone_name").clean(zone_name, None)
                    if not postcode or not zone_name:
                        raise ValidationError("Each service area needs both a postcode and zone name.")
                    parsed_areas.append((postcode, zone_name))
                if not parsed_areas:
                    raise ValidationError("Enter at least one service postcode or zone.")
                if photo.name.lower().rsplit(".", 1)[-1] not in {"jpg", "jpeg", "png", "webp"}:
                    raise ValidationError("Food bank photo must be a JPG, PNG, or WEBP image.")
                if service_document.name.lower().rsplit(".", 1)[-1] not in {"pdf", "jpg", "jpeg", "png"}:
                    raise ValidationError("Supporting document must be a PDF, JPG, or PNG file.")
                if photo.size > 5 * 1024 * 1024 or service_document.size > 10 * 1024 * 1024:
                    raise ValidationError("Photo must be 5 MB or smaller and supporting document must be 10 MB or smaller.")
                Provider._meta.get_field("photo").clean(photo, None)
                Provider._meta.get_field("service_document").clean(service_document, None)
                with transaction.atomic():
                    user = User.objects.create_user(
                        email=email, name=food_bank_name, password=password, role="PROVIDER", is_active=False, status="INACTIVE",
                    )
                    provider = Provider.objects.create(
                        user=user, food_bank_name=food_bank_name, phone=phone,
                        address=address, operating_hours=operating_hours, is_approved=False,
                        photo=photo, service_document=service_document,
                    )
                    ServiceArea.objects.bulk_create([
                        ServiceArea(provider=provider, postcode=postcode, zone_name=zone_name)
                        for postcode, zone_name in parsed_areas
                    ])
                messages.success(request, "Your provider registration was received and is waiting for admin approval. We’ll email you when it’s approved.")
                return redirect("login")
            except ValidationError as exc:
                error = " ".join(exc.messages)
            except IntegrityError:
                if Provider.objects.filter(user__email__iexact=email, is_approved=False, rejected_at__isnull=True).exists():
                    error = "Your provider account is waiting for admin approval. We’ll email you when it’s approved."
                else:
                    error = "An account with that email already exists."
            except DatabaseError:
                error = "Registration is temporarily unavailable. Please try again shortly."
    return render(request, "accounts/provider_register.html", {"error": error})


def supplier_register(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = ""
    if request.method == "POST":
        from .models import Supplier
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        fields = {key: request.POST.get(key, "").strip() for key in (
            "business_name", "ssm_registration_no", "contact_person", "phone", "bank_account", "bank_name",
        )}
        license_file = request.FILES.get("business_license")
        if email and Supplier.objects.filter(user__email__iexact=email, is_approved=False, rejected_at__isnull=True).exists():
            error = "Your supplier account is waiting for admin approval. We’ll email you when it’s approved."
        elif not email or not all(fields.values()) or not license_file:
            error = "Complete all fields and attach your business license."
        elif Supplier.objects.filter(ssm_registration_no__iexact=fields["ssm_registration_no"]).exists():
            error = "This SSM number is already registered."
        elif not license_file.name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
            error = "Upload a PDF, PNG, or JPG business license."
        else:
            try:
                validate_password(password)
                with transaction.atomic():
                    user = User.objects.create_user(
                        email=email, name=fields["contact_person"], password=password, role="SUPPLIER", is_active=False, status="INACTIVE",
                    )
                    Supplier.objects.create(user=user, business_license=license_file, is_approved=False, **fields)
                messages.success(request, "Your supplier registration was received and is waiting for admin approval. We’ll email you when it’s approved.")
                return redirect("login")
            except ValidationError as exc:
                error = " ".join(exc.messages)
            except IntegrityError as exc:
                if "ssm" in str(exc).lower():
                    error = "This SSM number is already registered."
                elif Supplier.objects.filter(user__email__iexact=email, is_approved=False, rejected_at__isnull=True).exists():
                    error = "Your supplier account is waiting for admin approval. We’ll email you when it’s approved."
                else:
                    error = "An account with that email already exists."
            except DatabaseError:
                error = "Registration is temporarily unavailable. Please try again shortly."
    return render(request, "accounts/supplier_register.html", {"error": error})


@role_required("PROVIDER")
def provider_settings(request):
    from accounts.models import Supplier
    from distribution.models import ProviderSupplier
    from inventory.services import select_provider_supplier
    from urgent_needs.models import UrgentNeed

    provider = request.user.provider_profile
    saved = False
    if request.method == "POST":
        if request.POST.get("action") == "select_supplier":
            supplier, error = select_provider_supplier(provider, request.POST.get("supplier_id", ""))
            if error:
                messages.error(request, error)
            elif supplier:
                messages.success(request, f"{supplier.business_name} is now your selected supplier.")
            return redirect("provider_settings")
        provider.food_bank_name = request.POST.get("food_bank_name", "").strip()
        provider.phone = request.POST.get("phone", "").strip()
        provider.address = request.POST.get("address", "").strip()
        provider.operating_hours = request.POST.get("operating_hours", "").strip()
        if all((provider.food_bank_name, provider.phone, provider.address, provider.operating_hours)):
            provider.save(update_fields=["food_bank_name", "phone", "address", "operating_hours"])
            saved = True
        else:
            saved = False
    return render(request, "accounts/provider_settings.html", {
        "provider": provider, "saved": saved,
        "approved_suppliers": Supplier.objects.filter(is_approved=True, user__is_active=True).order_by("business_name"),
        "selected_supplier": ProviderSupplier.objects.filter(provider=provider, status="ACTIVE").select_related("supplier").first(),
        "active_urgent_need_count": UrgentNeed.objects.filter(provider=provider, status__in=["OPEN", "FUNDED"]).count(),
    })

