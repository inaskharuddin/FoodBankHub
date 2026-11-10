from django.urls import path
from . import views

urlpatterns = [
    path("provider/", views.provider_urgent_needs, name="provider_urgent_needs"),
    path("provider/<int:need_id>/edit/", views.provider_urgent_need_edit, name="provider_urgent_need_edit"),
    path("provider/<int:need_id>/delete/", views.provider_urgent_need_delete, name="provider_urgent_need_delete"),
]
