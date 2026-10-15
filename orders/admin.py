from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.purchase_order import PurchaseOrder
from .models.po_item import POItem
from .models.payout import Payout

admin.site.register(PurchaseOrder)
admin.site.register(POItem)
admin.site.register(Payout)