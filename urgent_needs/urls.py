from django.urls import path
from . import views

urlpatterns = [path("provider/", views.provider_urgent_needs, name="provider_urgent_needs")]
