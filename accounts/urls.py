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
    path("admin/suppliers/<int:supplier_id>/reject/", views.reject_supplier, name="reject_supplier"),
    path("admin/providers/<int:provider_id>/approve/", views.approve_provider, name="approve_provider"),
    path("admin/providers/<int:provider_id>/reject/", views.reject_provider, name="reject_provider"),
    path("admin/suppliers/<int:supplier_id>/license/", views.supplier_license, name="supplier_license"),
    path("admin/users/", views.admin_user_directory, name="admin_user_directory"),
    path("admin/users/<int:user_id>/", views.admin_user_detail, name="admin_user_detail"),
    path("admin/users/<int:user_id>/provider-file/<str:asset>/", views.admin_provider_asset, name="admin_provider_asset"),
    path("admin/users/<int:user_id>/update/", views.admin_user_update, name="admin_user_update"),
    path("admin/users/<int:user_id>/delete/", views.admin_user_delete, name="admin_user_delete"),
    path("admin/users/<int:user_id>/allowances/<int:usage_id>/update/", views.admin_needy_allowance_update, name="admin_needy_allowance_update"),
    path("provider/settings/", views.provider_settings, name="provider_settings"),
    path("supplier/settings/", views.supplier_settings, name="supplier_settings"),

    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin/approvals/", views.admin_approvals, name="admin_approvals"),
    path("provider-dashboard/", views.provider_dashboard, name="provider_dashboard"),
    path("provider-guide/complete/", views.provider_tour_complete, name="provider_tour_complete"),
    path("provider-guide/restart/", views.provider_tour_restart, name="provider_tour_restart"),
    path("donor-dashboard/", views.donor_dashboard, name="donor_dashboard"),
    path("supplier-dashboard/", views.supplier_dashboard, name="supplier_dashboard"),
    path("supplier-guide/complete/", views.supplier_tour_complete, name="supplier_tour_complete"),
    path("supplier-guide/restart/", views.supplier_tour_restart, name="supplier_tour_restart"),
    path("supplier-panel/", views.supplier_panel, name="supplier_panel"),
    path("needy-dashboard/", views.needy_dashboard, name="needy_dashboard"),
    path("needy/find/", views.needy_provider_finder, name="needy_provider_finder"),
    path("needy/history/", views.needy_history, name="needy_history"),
    path("needy/scan/", views.needy_scan, name="needy_scan"),
]


