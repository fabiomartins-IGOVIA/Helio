import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import DatajudRegistro


logger = logging.getLogger(__name__)


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
    help = "Importa um ou mais arquivos Parquet do Datajud para o banco."

    @staticmethod
    def arquivos_padrao():
        pasta = Path(settings.BASE_DIR) / "data" / "processed" / "datajud"
        return [
            pasta / "tabela_principal_helios_2000_2024.parquet",
            pasta / "tabela_principal_helios.parquet",
        ]

    def add_arguments(self, parser):
        parser.add_argument(
            "limite_linhas",
            nargs="?",
            type=int,
            default=None,
            help="Quantidade máxima de linhas a importar. Sem valor, importa tudo.",
        )
        parser.add_argument(
            "--arquivo",
            dest="arquivos",
            type=Path,
            action="append",
            help=(
                "Caminho de um arquivo Parquet. Pode ser repetido para vários arquivos. "
                "Sem este argumento, usa os dois arquivos padrão de data/processed/datajud/."
            ),
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
        arquivos = [
            arquivo.expanduser().resolve()
            for arquivo in (options["arquivos"] or self.arquivos_padrao())
        ]
        batch_size = options["batch_size"]
        limite_linhas = options["limite_linhas"]

        if batch_size <= 0:
            logger.error("Tamanho de lote inválido: %s", batch_size)
            raise CommandError("--batch-size deve ser maior que zero.")
        if limite_linhas is not None and limite_linhas <= 0:
            logger.error("Limite de linhas inválido: %s", limite_linhas)
            raise CommandError("limite_linhas deve ser maior que zero.")

        for arquivo in arquivos:
            if not arquivo.is_file():
                logger.error("Arquivo Parquet não encontrado: %s", arquivo)
                raise CommandError(f"Arquivo Parquet não encontrado: {arquivo}")

        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            logger.exception("pyarrow não está instalado")
            raise CommandError(
                "pyarrow não está instalado. Execute: pip install pyarrow"
            ) from exc

        parquets = []
        total_declarado = 0
        for arquivo in arquivos:
            parquet = pq.ParquetFile(arquivo)
            colunas = set(parquet.schema_arrow.names)
            ausentes = sorted(COLUNAS_OBRIGATORIAS - colunas)
            if ausentes:
                logger.error(
                    "Colunas ausentes no Parquet %s: %s",
                    arquivo,
                    ", ".join(ausentes),
                )
                raise CommandError(
                    f"O Parquet {arquivo} não possui as colunas obrigatórias: "
                    + ", ".join(ausentes)
                )
            parquets.append((arquivo, parquet))
            total_declarado += parquet.metadata.num_rows

            logger.info(
                "Arquivo validado: arquivo=%s, linhas=%s, lotes=%s",
                arquivo,
                parquet.metadata.num_rows,
                parquet.metadata.num_row_groups,
            )
            self.stdout.write(f"Arquivo: {arquivo}")
            self.stdout.write(
                f"Linhas declaradas: {parquet.metadata.num_rows:,}".replace(",", ".")
            )
            self.stdout.write(f"Lotes: {parquet.metadata.num_row_groups}")

        logger.info(
            "Iniciando importação: arquivos=%s, linhas=%s, lote=%s, limite=%s",
            len(parquets),
            total_declarado,
            batch_size,
            limite_linhas,
        )
        self.stdout.write(
            f"Total declarado nos arquivos: {total_declarado:,}".replace(",", ".")
        )
        if limite_linhas is not None:
            self.stdout.write(f"Limite solicitado: {limite_linhas:,}".replace(",", "."))

        if options["dry_run"]:
            logger.info("Dry-run concluído; nenhuma linha foi gravada")
            self.stdout.write(self.style.SUCCESS("Validação concluída; nada foi gravado."))
            return

        if options["limpar_antes"]:
            apagados, _ = DatajudRegistro.objects.all().delete()
            logger.warning("Registros removidos antes da carga: %s", apagados)
            self.stdout.write(f"Registros removidos antes da carga: {apagados:,}".replace(",", "."))

        total_importado = 0
        for arquivo, parquet in parquets:
            if limite_linhas is not None:
                restantes = limite_linhas - total_importado
                if restantes <= 0:
                    break
                tamanho_leitura = min(batch_size, restantes)
            else:
                tamanho_leitura = batch_size

            importado_arquivo = 0
            for batch in parquet.iter_batches(
                batch_size=tamanho_leitura,
                columns=sorted(COLUNAS_OBRIGATORIAS),
            ):
                linhas = batch.to_pylist()
                if limite_linhas is not None:
                    restantes = limite_linhas - total_importado
                    if restantes <= 0:
                        break
                    linhas = linhas[:restantes]

                objetos = []
                for row in linhas:
                    try:
                        ano = int(row["ano"])
                    except (TypeError, ValueError) as exc:
                        logger.exception(
                            "Ano inválido no arquivo %s: %r",
                            arquivo,
                            row["ano"],
                        )
                        raise CommandError(
                            f"Ano inválido no arquivo {arquivo}: {row['ano']!r}"
                        ) from exc

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

                try:
                    with transaction.atomic():
                        DatajudRegistro.objects.bulk_create(objetos, batch_size=batch_size)
                except Exception:
                    logger.exception(
                        "Falha ao gravar lote do Datajud no arquivo %s. "
                        "Registros já processados: %s",
                        arquivo,
                        total_importado,
                    )
                    raise

                total_importado += len(objetos)
                importado_arquivo += len(objetos)
                if total_importado % 100_000 < len(objetos):
                    self.stdout.write(
                        f"Importados: {total_importado:,}".replace(",", ".")
                    )
                    logger.info(
                        "Progresso da importação: %s registros",
                        total_importado,
                    )

                if limite_linhas is not None and total_importado >= limite_linhas:
                    break

            self.stdout.write(
                f"Arquivo concluído: {arquivo.name} — {importado_arquivo:,} registros"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Importação concluída: {total_importado:,} registros.".replace(",", ".")
            )
        )
        logger.info("Importação concluída: %s registros", total_importado)
