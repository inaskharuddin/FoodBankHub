from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.cart import Cart
from .models.cart_item import CartItem
from .models.donation import Donation
from .models.donation_item import DonationItem
from .models.transaction import Transaction

admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Donation)
admin.site.register(DonationItem)
admin.site.register(Transaction)