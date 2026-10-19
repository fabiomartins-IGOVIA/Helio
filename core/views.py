from django.db import connection
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import DatajudRegistro
from .serializers import DatajudRegistroSerializer


def health_check(request):
    """Verifica se a aplicação está de pé e consegue acessar o banco."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok", "servico": "helio-backend"})


@extend_schema_view(
    list=extend_schema(
        tags=["Datajud"],
        summary="Lista registros do Datajud",
        description="Retorna registros do Datajud.",
    ),
    retrieve=extend_schema(
        tags=["Datajud"],
        summary="Consulta um registro do Datajud",
    ),
)
class DatajudRegistroViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta pública e somente leitura dos registros do Datajud."""

    queryset = DatajudRegistro.objects.all()
    serializer_class = DatajudRegistroSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)
    search_fields = (
        "processo",
        "municipio",
        "nome_classe",
        "nome_assunto",
        "nome_orgao",
    )
    ordering_fields = ("ano", "grau", "municipio", "codigo_orgao")
