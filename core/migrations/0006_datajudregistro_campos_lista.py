import ast
import json

from django.db import migrations, models


CAMPOS_LISTA = (
    "codigo_classe",
    "nome_classe",
    "codigo_assunto",
    "nome_assunto",
)


def normalizar_lista(valor, numerico=False):
    if valor is None:
        valores = []
    elif isinstance(valor, list):
        valores = valor
    elif isinstance(valor, str):
        bruto = valor.strip()
        if not bruto:
            valores = []
        else:
            try:
                valores = json.loads(bruto)
            except json.JSONDecodeError:
                try:
                    valores = ast.literal_eval(bruto)
                except (ValueError, SyntaxError):
                    valores = [bruto]
            if not isinstance(valores, list):
                valores = [valores]
    else:
        valores = [valor]

    resultado = []
    for item in valores:
        if item is None or (isinstance(item, str) and not item.strip()):
            continue
        if numerico:
            try:
                resultado.append(int(item))
                continue
            except (TypeError, ValueError):
                pass
        resultado.append(str(item).strip())
    return resultado


def converter_dados_existentes(apps, schema_editor):
    DatajudRegistro = apps.get_model("dados", "DatajudRegistro")
    campos_numericos = {"codigo_classe", "codigo_assunto"}
    atualizacoes = []

    for registro in DatajudRegistro.objects.all().iterator(chunk_size=2_000):
        alterado = False
        for campo in CAMPOS_LISTA:
            novo_valor = json.dumps(
                normalizar_lista(
                    getattr(registro, campo), numerico=campo in campos_numericos
                ),
                ensure_ascii=False,
            )
            if getattr(registro, campo) != novo_valor:
                setattr(registro, campo, novo_valor)
                alterado = True
        if alterado:
            atualizacoes.append(registro)

        if len(atualizacoes) >= 2_000:
            DatajudRegistro.objects.bulk_update(atualizacoes, CAMPOS_LISTA)
            atualizacoes.clear()

    if atualizacoes:
        DatajudRegistro.objects.bulk_update(atualizacoes, CAMPOS_LISTA)


class Migration(migrations.Migration):

    dependencies = [
        ("dados", "0005_alter_datajudregistro_id_municipio"),
    ]

    operations = [
        migrations.RunPython(
            converter_dados_existentes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="datajudregistro",
            name="id_municipio",
            field=models.CharField(
                help_text="Código do município no padrão IBGE, com até 7 dígitos.",
                max_length=7,
            ),
        ),
        migrations.AlterField(
            model_name="datajudregistro",
            name="codigo_classe",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Lista de códigos numéricos da classe processual.",
            ),
        ),
        migrations.AlterField(
            model_name="datajudregistro",
            name="nome_classe",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Lista de nomes das classes processuais.",
            ),
        ),
        migrations.AlterField(
            model_name="datajudregistro",
            name="codigo_assunto",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Lista de códigos numéricos dos assuntos.",
            ),
        ),
        migrations.AlterField(
            model_name="datajudregistro",
            name="nome_assunto",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Lista de nomes dos assuntos.",
            ),
        ),
    ]
