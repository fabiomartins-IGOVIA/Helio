from django.contrib import admin

from .models import DatajudRegistro


@admin.register(DatajudRegistro)
class DatajudRegistroAdmin(admin.ModelAdmin):
    list_display = (
        "ano",
        "grau",
        "processo",
        "municipio",
        "nome_classe",
        "nome_orgao",
    )
    list_filter = ("ano", "grau", "municipio")
    search_fields = ("processo", "municipio", "nome_classe", "nome_assunto", "nome_orgao")
