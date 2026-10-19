from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView


urlpatterns = [
    path("", include("core.dashboard_urls")),
    path("admin/", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("django-admin/", admin.site.urls),
    path("api/", include("core.urls")),
]
