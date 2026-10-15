from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.user import User
from .models.provider import Provider
from .models.supplier import Supplier
from .models.needy import Needy


admin.site.register(User)
admin.site.register(Provider)
admin.site.register(Supplier)
admin.site.register(Needy)