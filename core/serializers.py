from rest_framework import serializers

from .models import DatajudRegistro


class DatajudRegistroSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatajudRegistro
        fields = (
            "id",
            "ano",
            "grau",
            "processo",
            "id_municipio",
            "municipio",
            "codigo_classe",
            "nome_classe",
            "codigo_assunto",
            "nome_assunto",
            "codigo_orgao",
            "nome_orgao",
        )
        read_only_fields = ("id",)
