from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models.historical_data import HistoricalData
from .models.forecast import Forecast
from .models.forecast_run import ForecastRun

admin.site.register(HistoricalData)
admin.site.register(Forecast)
admin.site.register(ForecastRun)
