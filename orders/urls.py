from django.urls import path
from . import views

urlpatterns = [
    path("", views.purchase_order_list, name="purchase_order_list"),
    path("create/", views.purchase_order_create, name="purchase_order_create"),
    path("supplier/", views.supplier_order_list, name="supplier_order_list"),
    path("supplier/payouts/", views.supplier_payout_list, name="supplier_payout_list"),
    path("admin/payouts/", views.admin_payout_list, name="admin_payout_list"),
    path("supplier/<int:po_id>/status/", views.supplier_update_order_status, name="supplier_update_order_status"),
    path("<int:po_id>/confirm-delivery/", views.confirm_purchase_order_delivery, name="confirm_purchase_order_delivery"),
    path("admin/<int:po_id>/record-payment/", views.record_purchase_order_payment, name="record_purchase_order_payment"),
    path("<int:po_id>/", views.purchase_order_detail, name="purchase_order_detail"),
]
