from django.urls import path
from . import views

urlpatterns = [
    path("", views.inventory_list, name="inventory_list"),
    path("low-stock-alerts/", views.low_stock_alerts, name="low_stock_alerts"),
    path("low-stock-alerts/<int:alert_id>/read/", views.mark_low_stock_alert_read, name="mark_low_stock_alert_read"),
    path("add/", views.inventory_add, name="inventory_add"),
    path("edit/<int:inventory_id>/", views.inventory_edit, name="inventory_edit"),
    path("supplier-products/", views.supplier_product_list, name="supplier_product_list"),
    path("supplier-products/add/", views.supplier_product_add, name="supplier_product_add"),
    path("supplier-products/upload/", views.supplier_product_upload, name="supplier_product_upload"),
    path("supplier-products/template.csv", views.supplier_product_csv_template, name="supplier_product_csv_template"),
    path("supplier-products/edit/<int:product_id>/", views.supplier_product_edit, name="supplier_product_edit"),
    path("supplier-products/delete/<int:product_id>/", views.supplier_product_delete, name="supplier_product_delete"),
    path("suppliers/", views.supplier_list, name="supplier_list"),
    path("suppliers/select/<int:supplier_id>/", views.supplier_select, name="supplier_select"),
    path("my-supplier/products/", views.selected_supplier_products, name="selected_supplier_products"),
    path("delete/<int:inventory_id>/", views.inventory_delete, name="inventory_delete"),
]
