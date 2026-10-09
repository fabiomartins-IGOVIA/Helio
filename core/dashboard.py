from django.db.models import Count
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import DatajudRegistro


def formatar_numero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def adicionar_percentual(itens: list[dict]) -> list[dict]:
    maior = itens[0]["total"] if itens else 1
    return [
        {
            **item,
            "percentual": round((item["total"] / maior) * 100, 1),
            "percentual_css": f"{(item['total'] / maior) * 100:.1f}",
        }
        for item in itens
    ]


@require_GET
def dashboard(request):
    """Painel público com visão agregada das fontes do Hélio."""

    registros = DatajudRegistro.objects.all()
    por_ano = list(
        registros.values("ano")
        .annotate(total=Count("id"))
        .order_by("ano")
    )
    por_grau = list(
        registros.values("grau")
        .annotate(total=Count("id"))
        .order_by("-total", "grau")
    )
    municipios = list(
        registros.values("municipio")
        .annotate(total=Count("id"))
        .order_by("-total", "municipio")[:10]
    )
    classes = list(
        registros.values("nome_classe")
        .annotate(total=Count("id"))
        .order_by("-total", "nome_classe")[:10]
    )

    context = {
        "total_registros": formatar_numero(registros.count()),
        "total_municipios": formatar_numero(
            registros.values("id_municipio").distinct().count()
        ),
        "total_orgaos": formatar_numero(
            registros.values("codigo_orgao").distinct().count()
        ),
        "total_classes": formatar_numero(
            registros.values("nome_classe").distinct().count()
        ),
        "anos": por_ano,
        "graus": adicionar_percentual(por_grau),
        "municipios": adicionar_percentual(municipios),
        "classes": adicionar_percentual(classes),
        "ibge_disponivel": False,
    }
    return render(request, "core/dashboard.html", context)
