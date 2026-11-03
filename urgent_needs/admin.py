from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.urgent_need import UrgentNeed

admin.site.register(UrgentNeed)
