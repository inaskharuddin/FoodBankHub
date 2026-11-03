from django.urls import path

from . import views

urlpatterns = [
    path("historical-data/", views.historical_data, name="historical_data"),
    path("view-forecast/", views.view_forecast, name="view_forecast"),
    path("view-forecast/snapshots/delete/", views.delete_forecast_run, name="delete_forecast_run"),
]
