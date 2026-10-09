from django.db import models


class DatajudRegistro(models.Model):
    """Registro bruto extraído do arquivo Parquet do Datajud.

    Esta é uma tabela de staging, ainda em granularidade de processo. O campo
    ``processo`` não deve ser exposto em endpoints públicos enquanto o projeto
    mantiver a diretriz de trabalhar com metadados agregados.
    """

    ano = models.PositiveSmallIntegerField()
    grau = models.CharField(max_length=2)
    processo = models.CharField(max_length=25, db_index=True)
    id_municipio = models.CharField(max_length=4)
    municipio = models.CharField(max_length=27)
    codigo_classe = models.TextField(
        help_text="Lista de códigos serializada, por exemplo: [198,460].",
    )
    nome_classe = models.CharField(max_length=310)
    codigo_assunto = models.TextField(
        help_text="Lista de códigos serializada no arquivo.",
    )
    nome_assunto = models.TextField(blank=True)
    codigo_orgao = models.CharField(max_length=5)
    nome_orgao = models.CharField(max_length=155)

    class Meta:
        db_table = "datajud_registros"
        ordering = ["-ano", "processo"]
        verbose_name = "registro do Datajud"
        verbose_name_plural = "registros do Datajud"
        indexes = [
            models.Index(fields=["ano", "grau"]),
            models.Index(fields=["id_municipio", "ano"]),
            models.Index(fields=["codigo_orgao", "ano"]),
        ]

    def __str__(self) -> str:
        return self.processo


class IBGE(models.Model):
    """Placeholder para o modelo do IBGE, ainda sem campos definidos."""

    class Meta:
        abstract = True
