from django.urls import path

from . import views

urlpatterns = [
    path("historical-data/", views.historical_data, name="historical_data"),
    path("view-forecast/", views.view_forecast, name="view_forecast"),
]
