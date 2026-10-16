import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.models import DatajudRegistro


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Remove todos os registros do Datajud ou apenas os registros de um ano."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Confirma a remoção definitiva dos registros.",
        )
        parser.add_argument(
            "--ano",
            type=int,
            help="Limpa somente os registros deste ano. Sem este argumento, limpa todos.",
        )

    def handle(self, *args, **options):
        if not options["confirmar"]:
            logger.error("Tentativa de limpeza sem a confirmação obrigatória")
            raise CommandError(
                "A operação é destrutiva. Execute novamente com --confirmar."
            )

        ano = options["ano"]
        if ano is not None and ano <= 0:
            raise CommandError("--ano deve ser maior que zero.")

        tabela = DatajudRegistro._meta.db_table
        quoted_table = connection.ops.quote_name(tabela)

        escopo = f"ano {ano}" if ano is not None else "todos os anos"
        logger.warning("Iniciando limpeza da tabela %s: %s", tabela, escopo)
        try:
            with transaction.atomic():
                if ano is None and connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute(f"TRUNCATE TABLE {quoted_table} RESTART IDENTITY")
                    removidos = "todos"
                else:
                    consulta = DatajudRegistro.objects.all()
                    if ano is not None:
                        consulta = consulta.filter(ano=ano)
                    removidos, _ = consulta.delete()
        except Exception:
            logger.exception("Falha ao limpar a tabela %s", tabela)
            raise

        self.stdout.write(
            self.style.SUCCESS(f"Registros do Datajud removidos ({escopo}): {removidos}.")
        )
        logger.warning("Limpeza concluída da tabela %s (%s): %s", tabela, escopo, removidos)
