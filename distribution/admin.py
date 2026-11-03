from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.provider_supplier import ProviderSupplier
from .models.service_area import ServiceArea
from .models.allowance_usage import AllowanceUsage
from .models.report import Report

admin.site.register(ProviderSupplier)
admin.site.register(ServiceArea)
admin.site.register(AllowanceUsage)
admin.site.register(Report)