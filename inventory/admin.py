from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.item import Item
from .models.supplier_product import SupplierProduct
from .models.inventory import Inventory


admin.site.register(Item)
admin.site.register(SupplierProduct)
admin.site.register(Inventory)