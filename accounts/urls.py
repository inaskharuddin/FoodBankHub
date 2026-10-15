from django.urls import path
from . import views

urlpatterns = [
    path("", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("provider-dashboard/", views.provider_dashboard, name="provider_dashboard"),
    path("donor-dashboard/", views.donor_dashboard, name="donor_dashboard"),
    path("supplier-dashboard/", views.supplier_dashboard, name="supplier_dashboard"),
    path("needy-dashboard/", views.needy_dashboard, name="needy_dashboard"),
]