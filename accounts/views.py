from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


def role_required(allowed_role):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):

            if not request.user.is_authenticated:
                return redirect("login")

            if request.user.role != allowed_role:
                return redirect_by_role(request.user)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def login_view(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(
            request,
            email=email,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect_by_role(user)

        return render(
            request,
            "accounts/login.html",
            {"error": "Invalid email or password."}
        )

    return render(request, "accounts/login.html")


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
    return render(request, "accounts/admin_dashboard.html")


@role_required("PROVIDER")
def provider_dashboard(request):
    return render(request, "accounts/provider_dashboard.html")


@role_required("DONOR")
def donor_dashboard(request):
    from donations.models import Cart, Donation
    carts = Cart.objects.filter(donor=request.user, status="ACTIVE").prefetch_related("items__urgent_need__item")
    donations = Donation.objects.filter(donor=request.user).order_by("-created_at")
    return render(request, "accounts/donor_dashboard.html", {"carts": carts, "donations": donations})


@role_required("SUPPLIER")
def supplier_dashboard(request):
    return render(request, "accounts/supplier_dashboard.html")


@role_required("NEEDY")
def needy_dashboard(request):
    return render(request, "accounts/needy_dashboard.html")
