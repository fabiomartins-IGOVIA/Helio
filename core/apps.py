from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    # Preserva o app label histórico para não invalidar as migrações já criadas.
    label = "dados"
    verbose_name = "Dados do Hélio"
