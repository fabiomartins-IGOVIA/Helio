from django.urls import path

from .dashboard import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
]
