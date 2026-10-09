from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", include("core.dashboard_urls")),
    path("django-admin/", admin.site.urls),
    path("api/", include("core.urls")),
]
