from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.historical_data import HistoricalData
from .models.forecast import Forecast

admin.site.register(HistoricalData)
admin.site.register(Forecast)