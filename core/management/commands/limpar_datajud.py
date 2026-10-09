from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.models import DatajudRegistro


class Command(BaseCommand):
    help = "Remove todos os registros do Datajud do banco."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Confirma a remoção definitiva dos registros.",
        )

    def handle(self, *args, **options):
        if not options["confirmar"]:
            raise CommandError(
                "A operação é destrutiva. Execute novamente com --confirmar."
            )

        tabela = DatajudRegistro._meta.db_table
        quoted_table = connection.ops.quote_name(tabela)

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute(f"TRUNCATE TABLE {quoted_table} RESTART IDENTITY")
                removidos = "todos"
            else:
                removidos, _ = DatajudRegistro.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(f"Registros do Datajud removidos: {removidos}.")
        )
