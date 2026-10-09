from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from .views import DatajudRegistroViewSet, health_check

router = DefaultRouter()
# Os registros do Datajud são públicos e possuem CRUD completo.
router.register("datajud-registros", DatajudRegistroViewSet, basename="datajud-registro")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path(
        "schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[AllowAny]),
        name="swagger-ui",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(url_name="schema", permission_classes=[AllowAny]),
        name="redoc",
    ),
    path("", include(router.urls)),
]
