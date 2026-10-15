from django.urls import path
from . import views

urlpatterns = [
    path("", views.inventory_list, name="inventory_list"),
    path("low-stock-alerts/", views.low_stock_alerts, name="low_stock_alerts"),
    path("add/", views.inventory_add, name="inventory_add"),
    path("edit/<int:inventory_id>/", views.inventory_edit, name="inventory_edit"),
    path("supplier-products/", views.supplier_product_list, name="supplier_product_list"),
    path("supplier-products/add/", views.supplier_product_add, name="supplier_product_add"),
    path("supplier-products/edit/<int:product_id>/", views.supplier_product_edit, name="supplier_product_edit"),
    path("supplier-products/delete/<int:product_id>/", views.supplier_product_delete, name="supplier_product_delete"),
    path("suppliers/", views.supplier_list, name="supplier_list"),
    path("suppliers/select/<int:supplier_id>/", views.supplier_select, name="supplier_select"),
    path("my-supplier/products/", views.selected_supplier_products, name="selected_supplier_products"),
    path("delete/<int:inventory_id>/", views.inventory_delete, name="inventory_delete"),
]
