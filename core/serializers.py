from rest_framework import serializers

from .models import DatajudRegistro


class DatajudRegistroSerializer(serializers.ModelSerializer):
    codigo_classe = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    nome_classe = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False, allow_empty=True
    )
    codigo_assunto = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    nome_assunto = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False, allow_empty=True
    )

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
