from django.urls import path
from . import views

urlpatterns = [
    path("", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("donor-register/", views.donor_register, name="donor_register"),
    path("needy-register/", views.needy_register, name="needy_register"),
    path("provider-register/", views.provider_register, name="provider_register"),
    path("supplier-register/", views.supplier_register, name="supplier_register"),
    path("admin/suppliers/<int:supplier_id>/approve/", views.approve_supplier, name="approve_supplier"),
    path("admin/suppliers/<int:supplier_id>/license/", views.supplier_license, name="supplier_license"),
    path("provider/settings/", views.provider_settings, name="provider_settings"),

    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("provider-dashboard/", views.provider_dashboard, name="provider_dashboard"),
    path("donor-dashboard/", views.donor_dashboard, name="donor_dashboard"),
    path("supplier-dashboard/", views.supplier_dashboard, name="supplier_dashboard"),
    path("supplier-panel/", views.supplier_panel, name="supplier_panel"),
    path("needy-dashboard/", views.needy_dashboard, name="needy_dashboard"),
    path("needy/find/", views.needy_provider_finder, name="needy_provider_finder"),
    path("needy/history/", views.needy_history, name="needy_history"),
    path("needy/scan/", views.needy_scan, name="needy_scan"),
]


