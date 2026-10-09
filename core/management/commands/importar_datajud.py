from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import DatajudRegistro


COLUNAS_OBRIGATORIAS = {
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
}


def texto(valor) -> str:
    """Converte valores do Arrow para texto sem transformar nulos em 'None'."""

    return "" if valor is None else str(valor)


class Command(BaseCommand):
    help = "Importa registros de um arquivo Parquet do Datajud para o banco."

    def add_arguments(self, parser):
        parser.add_argument(
            "--arquivo",
            type=Path,
            default=Path(settings.BASE_DIR) / "data" / "processed" / "datajud" / "tabela_principal_helios.parquet",
            help="Caminho do arquivo Parquet. O padrão é data/processed/datajud/.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=10_000,
            help="Quantidade de linhas lidas e gravadas por lote.",
        )
        parser.add_argument(
            "--limpar-antes",
            action="store_true",
            help="Apaga os registros atuais do Datajud antes da importação.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida o arquivo e conta as linhas sem gravar no banco.",
        )

    def handle(self, *args, **options):
        arquivo = options["arquivo"].expanduser().resolve()
        batch_size = options["batch_size"]

        if not arquivo.is_file():
            raise CommandError(f"Arquivo Parquet não encontrado: {arquivo}")
        if batch_size <= 0:
            raise CommandError("--batch-size deve ser maior que zero.")

        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise CommandError(
                "pyarrow não está instalado. Execute: pip install pyarrow"
            ) from exc

        parquet = pq.ParquetFile(arquivo)
        colunas = set(parquet.schema_arrow.names)
        ausentes = sorted(COLUNAS_OBRIGATORIAS - colunas)
        if ausentes:
            raise CommandError(
                "O Parquet não possui as colunas obrigatórias: " + ", ".join(ausentes)
            )

        self.stdout.write(f"Arquivo: {arquivo}")
        self.stdout.write(f"Linhas declaradas: {parquet.metadata.num_rows:,}".replace(",", "."))
        self.stdout.write(f"Lotes: {parquet.metadata.num_row_groups}")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Validação concluída; nada foi gravado."))
            return

        if options["limpar_antes"]:
            apagados, _ = DatajudRegistro.objects.all().delete()
            self.stdout.write(f"Registros removidos antes da carga: {apagados:,}".replace(",", "."))

        total_importado = 0
        for batch in parquet.iter_batches(
            batch_size=batch_size,
            columns=sorted(COLUNAS_OBRIGATORIAS),
        ):
            objetos = []
            for row in batch.to_pylist():
                try:
                    ano = int(row["ano"])
                except (TypeError, ValueError) as exc:
                    raise CommandError(f"Ano inválido no arquivo: {row['ano']!r}") from exc

                objetos.append(
                    DatajudRegistro(
                        ano=ano,
                        grau=texto(row["grau"]),
                        processo=texto(row["processo"]),
                        id_municipio=texto(row["id_municipio"]),
                        municipio=texto(row["municipio"]),
                        codigo_classe=texto(row["codigo_classe"]),
                        nome_classe=texto(row["nome_classe"]),
                        codigo_assunto=texto(row["codigo_assunto"]),
                        nome_assunto=texto(row["nome_assunto"]),
                        codigo_orgao=texto(row["codigo_orgao"]),
                        nome_orgao=texto(row["nome_orgao"]),
                    )
                )

            with transaction.atomic():
                DatajudRegistro.objects.bulk_create(objetos, batch_size=batch_size)

            total_importado += len(objetos)
            if total_importado % 100_000 < len(objetos):
                self.stdout.write(
                    f"Importados: {total_importado:,}".replace(",", ".")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Importação concluída: {total_importado:,} registros.".replace(",", ".")
            )
        )
