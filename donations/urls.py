from django.urls import path
from . import views

urlpatterns = [
    path("cart/<int:cart_id>/checkout/", views.donation_checkout, name="donation_checkout"),
    path("billplz/callback/", views.billplz_callback, name="billplz_callback"),
    path("complete/", views.donation_complete, name="donation_complete"),
    path("admin/", views.admin_donation_list, name="admin_donation_list"),
]
