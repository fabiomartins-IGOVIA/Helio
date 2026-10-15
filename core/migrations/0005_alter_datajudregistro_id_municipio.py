from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dados", "0004_remove_cargaapi_cargas_api_fonte_51586a_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datajudregistro",
            name="id_municipio",
            field=models.CharField(
                help_text="Código do município no padrão IBGE, com até 7 dígitos.",
                max_length=7,
            ),
        ),
    ]
