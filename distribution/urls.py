from django.urls import path
from . import views

urlpatterns = [
    path("offline-paper-log/", views.offline_paper_log, name="offline_paper_log"),
    path("admin/data-retention/", views.data_retention_settings, name="data_retention_settings"),
    path("service-areas/", views.service_area_manage, name="service_area_manage"),
    path("reports/", views.provider_reports, name="provider_reports"),
    path("donations/", views.provider_donation_monitoring, name="provider_donation_monitoring"),
    path("allowances/", views.allowance_manage, name="allowance_manage"),
    path("reports/daily/", views.provider_daily_summary, name="provider_daily_summary"),
    path("reports/usage/", views.needy_usage_report, name="needy_usage_report"),
    path("self-report/qr.png", views.provider_self_report_qr, name="provider_self_report_qr"),
    path("self-report/<str:token>/", views.needy_self_report, name="needy_self_report"),
]
