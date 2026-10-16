from django.contrib import admin

from .models import DatajudRegistro


@admin.register(DatajudRegistro)
class DatajudRegistroAdmin(admin.ModelAdmin):
    list_display = (
        "ano",
        "grau",
        "processo",
        "municipio",
        "classes_resumidas",
        "nome_orgao",
    )
    list_filter = ("ano", "grau", "municipio")
    search_fields = ("processo", "municipio", "nome_classe", "nome_assunto", "nome_orgao")
    list_per_page = 50

    @admin.display(description="Classes")
    def classes_resumidas(self, obj):
        nomes = obj.nome_classe if isinstance(obj.nome_classe, list) else [obj.nome_classe]
        nomes = [str(nome) for nome in nomes if str(nome).strip()]
        texto = ", ".join(nomes)
        return texto[:80] + "…" if len(texto) > 80 else texto
