from django.urls import path
from . import views

urlpatterns = [
    path("profile/", views.donor_profile, name="donor_profile"),
    path("providers/", views.provider_directory, name="provider_directory"),
    path("providers/<int:provider_id>/", views.provider_public_profile, name="provider_public_profile"),
    path("cart/", views.donor_cart, name="donor_cart"),
    path("needs/", views.donor_needs, name="donor_needs"),
    path("needs/<int:need_id>/add/", views.add_need_to_cart, name="add_need_to_cart"),
    path("cart/<int:cart_id>/checkout/", views.donation_checkout, name="donation_checkout"),
    path("billplz/callback/", views.billplz_callback, name="billplz_callback"),
    path("complete/", views.donation_complete, name="donation_complete"),
    path("history/", views.donation_history, name="donation_history"),
    path("history/<int:donation_id>/receipt.pdf", views.donation_receipt, name="donation_receipt"),
    path("impact/certificate.pdf", views.impact_certificate, name="impact_certificate"),
    path("history/<int:donation_id>/provider/<int:provider_id>/review/", views.rate_provider, name="rate_provider"),
    path("admin/", views.admin_donation_list, name="admin_donation_list"),
    path("admin/transactions/<int:transaction_id>/verify-failed/", views.admin_verify_failed_payment, name="admin_verify_failed_payment"),
]
