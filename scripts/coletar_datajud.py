"""Coleta e consolida os dados públicos do Datajud para o projeto Hélio.

O script porta a lógica do notebook ``pipeline_datajud_projeto.ipynb`` para
execução não interativa no servidor. A coleta é retomável por ano e utiliza
checkpoints após cada página confirmada pela API.

Exemplos:

    python scripts/coletar_datajud.py --ano 2009
    python scripts/coletar_datajud.py --anos 2009-2024
    python scripts/coletar_datajud.py --ano 2009 --limite 1000

As variáveis também podem ser definidas no arquivo ``.env``:

    DATAJUD_API_KEY=...
    DATAJUD_ANOS=2009-2024
    DATAJUD_LIMITE_POR_ANO=0
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq
import requests


CHECKPOINT_VERSION = 7
LOTE_INICIAL = 5_000
LOTE_MINIMO = 2_500
LOTE_MAXIMO = 10_000
LOTE_PASSO_SUCESSO = 500
LOTE_PASSO_FALHA = 500
LOTE_PASSO_CONGESTIONAMENTO = 1_000
SUCESSOS_PARA_AUMENTAR = 3
RETRY_INICIAL = 12
RETRY_MINIMO = 9
RETRY_MAXIMO = 15
RETRY_PASSO = 3
TIMEOUT_CONEXAO = 30
TIMEOUT_LEITURA = 300
STATUS_CONGESTIONAMENTO = {429, 502, 503, 504}

CAMPOS_API = [
    "grau",
    "numeroProcesso",
    "orgaoJulgador.codigo",
    "orgaoJulgador.nome",
    "orgaoJulgador.codigoMunicipioIBGE",
    "classe.codigo",
    "classe.nome",
    "assuntos.codigo",
    "assuntos.nome",
]

LIMITES_MODELO = {
    "grau": 2,
    "processo": 25,
    "id_municipio": 7,
    "municipio": 27,
    "nome_classe": 310,
    "codigo_orgao": 5,
    "nome_orgao": 155,
}

COLUNAS_PARQUET = [
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
]

SCHEMA_PARQUET = pa.schema(
    [pa.field(coluna, pa.string()) for coluna in COLUNAS_PARQUET]
)


def localizar_projeto(configurado: str | None = None) -> Path:
    """Localiza a raiz do projeto pelo ambiente ou pela pasta atual."""

    configurado = configurado or os.getenv("HELIO_PROJECT_ROOT")
    if configurado:
        raiz = Path(configurado).expanduser().resolve()
        if (raiz / "manage.py").is_file():
            return raiz

    atual = Path.cwd().resolve()
    for raiz in (atual, *atual.parents):
        if (raiz / "manage.py").is_file():
            return raiz

    raise RuntimeError(
        "Execute o script dentro do projeto Hélio ou defina HELIO_PROJECT_ROOT."
    )


def carregar_env(caminho: Path) -> None:
    """Carrega variáveis simples do .env sem substituir o ambiente existente."""

    if not caminho.is_file():
        return

    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip().lstrip("\ufeff")
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(chave, valor)


def parse_anos(valor: str) -> list[int]:
    """Aceita anos separados por vírgula ou intervalo, como 2009-2024."""

    anos: set[int] = set()
    for item in valor.split(","):
        item = item.strip()
        if not item:
            continue
        intervalo = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", item)
        if intervalo:
            inicio, fim = map(int, intervalo.groups())
            if inicio > fim:
                raise ValueError(f"Intervalo de anos inválido: {item}")
            anos.update(range(inicio, fim + 1))
            continue
        if not re.fullmatch(r"\d{4}", item):
            raise ValueError(
                f"Ano inválido: {item!r}. Use, por exemplo, 2009 ou 2009-2024."
            )
        anos.add(int(item))

    if not anos:
        raise ValueError("Nenhum ano foi informado.")
    return sorted(anos)


def codigo_numerico(valor: Any) -> int | str:
    texto = str(valor).strip()
    return int(texto) if texto.isdigit() else texto


def json_lista(valores: Iterable[Any]) -> str:
    return json.dumps(list(valores), ensure_ascii=False)


def formatar_processo(valor: Any) -> str:
    bruto = str(valor or "").strip()
    if re.fullmatch(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", bruto):
        return bruto
    if re.fullmatch(r"\d{1,20}", bruto):
        numero = bruto.zfill(20)
        return (
            f"{numero[:7]}-{numero[7:9]}.{numero[9:13]}."
            f"{numero[13]}.{numero[14:16]}.{numero[16:20]}"
        )
    if re.fullmatch(r"sigiloso\(.*\)", bruto, flags=re.IGNORECASE):
        return bruto
    raise ValueError(f"Número de processo inválido: {bruto!r}")


class DatajudPipeline:
    """Executa coleta, retomada por checkpoint e consolidação anual."""

    def __init__(
        self,
        project_root: Path,
        anos: list[int],
        limite_por_ano: int | None = None,
        municipios_csv: str | None = None,
    ) -> None:
        self.project_root = project_root
        self.anos = anos
        self.limite_por_ano = limite_por_ano
        self.api_key = os.getenv("DATAJUD_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError(
                "DATAJUD_API_KEY não encontrada. Preencha o .env; "
                "não coloque a chave no script."
            )

        self.url_datajud = os.getenv(
            "DATAJUD_URL",
            "https://api-publica.datajud.cnj.jus.br/api_publica_tjba/_search",
        )
        self.pasta_raw = project_root / "data" / "raw" / "datajud"
        self.pasta_processed = project_root / "data" / "processed" / "datajud"
        self.arquivo_parquet_atual = (
            self.pasta_processed / "tabela_principal_helios.parquet"
        )
        self.pasta_raw.mkdir(parents=True, exist_ok=True)
        self.pasta_processed.mkdir(parents=True, exist_ok=True)

        self.municipios_csv = self._localizar_dicionario_municipios(municipios_csv)
        self.mapa_municipios = self._carregar_municipios(self.municipios_csv)

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"ApiKey {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            }
        )

        self.lote = LOTE_INICIAL
        self.espera_retry_atual = RETRY_INICIAL
        self.sucessos_consecutivos = 0

    def arquivo_parquet_ano(self, ano: int) -> Path:
        return self.pasta_processed / f"tabela_principal_helios_{ano}.parquet"

    def caminho_ano(self, ano: int) -> dict[str, Path]:
        pasta = self.pasta_raw / str(ano)
        pasta.mkdir(parents=True, exist_ok=True)
        return {
            "parcial": pasta / f"tjba_{ano}_raw.jsonl.part",
            "final": pasta / f"tjba_{ano}_raw.jsonl",
            "checkpoint": pasta / f"checkpoint_{ano}_raw.json",
        }

    def _localizar_dicionario_municipios(self, configurado: str | None) -> Path:
        candidatos = [
            Path(configurado).expanduser() if configurado else None,
            self.project_root / "data" / "raw" / "ibge" / "municipios_bahia.csv",
            Path.home() / "Downloads" / "municipios_bahia.csv",
        ]
        for candidato in candidatos:
            if candidato and candidato.is_file():
                return candidato.resolve()
        raise FileNotFoundError(
            "Dicionário de municípios não encontrado. "
            "Defina MUNICIPIOS_BAHIA_CSV."
        )

    @staticmethod
    def _carregar_municipios(caminho: Path) -> dict[str, str]:
        mapa: dict[str, str] = {}
        with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
            leitor = csv.DictReader(arquivo)
            campos = {
                (campo or "").strip().upper(): campo
                for campo in leitor.fieldnames or []
            }
            coluna_codigo = campos.get("CÓDIGO IBGE") or campos.get("CODIGO_IBGE")
            coluna_nome = campos.get("MUNICÍPIO") or campos.get("MUNICIPIO")
            if not coluna_codigo or not coluna_nome:
                raise ValueError(
                    f"Colunas incompatíveis no dicionário: {leitor.fieldnames}"
                )
            for registro in leitor:
                codigo = str(registro.get(coluna_codigo) or "").strip()
                nome = str(registro.get(coluna_nome) or "").strip().upper()
                if re.fullmatch(r"\d{7}", codigo) and nome:
                    mapa[codigo] = nome
        return mapa

    def transformar_hit(self, hit: dict[str, Any], ano: int) -> dict[str, str]:
        source = hit.get("_source") or {}
        orgao = source.get("orgaoJulgador") or {}
        classe = source.get("classe") or {}
        assuntos = source.get("assuntos") or []
        if isinstance(assuntos, dict):
            assuntos = [assuntos]
        assuntos = [
            item
            for item in assuntos
            if isinstance(item, dict) and item.get("codigo") is not None
        ]

        codigo_municipio = str(orgao.get("codigoMunicipioIBGE") or "").strip()
        codigos_classe = (
            [codigo_numerico(classe["codigo"])]
            if classe.get("codigo") is not None
            else []
        )
        nomes_classe = [str(classe.get("nome") or "")] if codigos_classe else []
        codigos_assunto = [codigo_numerico(item["codigo"]) for item in assuntos]
        nomes_assunto = [str(item.get("nome") or "") for item in assuntos]

        registro = {
            "ano": str(ano),
            "grau": str(source.get("grau") or ""),
            "processo": formatar_processo(source.get("numeroProcesso")),
            "id_municipio": codigo_municipio,
            "municipio": self.mapa_municipios.get(codigo_municipio, ""),
            "codigo_classe": json_lista(codigos_classe),
            "nome_classe": json_lista(nomes_classe),
            "codigo_assunto": json_lista(codigos_assunto),
            "nome_assunto": json_lista(nomes_assunto),
            "codigo_orgao": str(orgao.get("codigo") or ""),
            "nome_orgao": str(orgao.get("nome") or ""),
        }
        for campo, limite in LIMITES_MODELO.items():
            if len(registro[campo]) > limite:
                raise ValueError(
                    f"{campo} excede o limite do modelo: "
                    f"{len(registro[campo])} > {limite}"
                )
        return registro

    @staticmethod
    def filtro_ano(ano: int) -> dict[str, Any]:
        return {
            "range": {
                "dataAjuizamento": {
                    "gte": f"{ano}0101000000",
                    "lt": f"{ano + 1}0101000000",
                }
            }
        }

    def post_retry(
        self, payload: dict[str, Any], contexto: str
    ) -> tuple[dict[str, Any], float, int]:
        tentativa = 0
        while True:
            tentativa += 1
            lote_usado = self.lote
            requisicao = dict(payload)
            requisicao["size"] = lote_usado
            params = {
                "allow_partial_search_results": "false",
                "filter_path": "timed_out,_shards.failed,hits.hits._source,hits.hits.sort",
            }
            erro_curto: str | None = None
            congestionamento = False
            try:
                inicio = time.perf_counter()
                resposta = self.session.post(
                    self.url_datajud,
                    json=requisicao,
                    params=params,
                    timeout=(TIMEOUT_CONEXAO, TIMEOUT_LEITURA),
                )
                duracao = time.perf_counter() - inicio
                if resposta.status_code != 200:
                    erro_curto = f"HTTP {resposta.status_code}"
                    congestionamento = resposta.status_code in STATUS_CONGESTIONAMENTO
                else:
                    dados = resposta.json()
                    if not isinstance(dados, dict):
                        erro_curto = "JSON inválido"
                    elif dados.get("timed_out"):
                        erro_curto = "timeout da API"
                        congestionamento = True
                    else:
                        shards = dados.get("_shards") or {}
                        falhos = (
                            int(shards.get("failed", 0) or 0)
                            if isinstance(shards, dict)
                            else 1
                        )
                        hits_obj = dados.get("hits")
                        hits = (
                            hits_obj.get("hits")
                            if isinstance(hits_obj, dict)
                            else None
                        )
                        if falhos == 0 and not isinstance(hits, list):
                            verificacao = self.session.post(
                                self.url_datajud,
                                json=requisicao,
                                params={"allow_partial_search_results": "false"},
                                timeout=(TIMEOUT_CONEXAO, TIMEOUT_LEITURA),
                            )
                            if verificacao.status_code == 200:
                                integral = verificacao.json()
                                if integral.get("timed_out"):
                                    erro_curto = "timeout da API"
                                    congestionamento = True
                                    falhos = 1
                                else:
                                    integral_shards = integral.get("_shards") or {}
                                    falhos = int(integral_shards.get("failed", 0) or 0)
                                    dados = integral
                                    hits_obj = integral.get("hits")
                                    hits = (
                                        hits_obj.get("hits")
                                        if isinstance(hits_obj, dict)
                                        else None
                                    )
                            else:
                                erro_curto = f"HTTP {verificacao.status_code}"
                                congestionamento = (
                                    verificacao.status_code
                                    in STATUS_CONGESTIONAMENTO
                                )
                        if falhos:
                            erro_curto = f"{falhos} shards com falha"
                            congestionamento = True
                        elif not isinstance(hits, list):
                            erro_curto = "resposta sem hits.hits"
                        elif hits and (
                            not isinstance(hits[-1], dict)
                            or not hits[-1].get("sort")
                        ):
                            erro_curto = "página sem sort"
                        else:
                            self.espera_retry_atual = max(
                                RETRY_MINIMO,
                                self.espera_retry_atual - RETRY_PASSO,
                            )
                            self.sucessos_consecutivos += 1
                            if self.sucessos_consecutivos >= SUCESSOS_PARA_AUMENTAR:
                                self.lote = min(
                                    LOTE_MAXIMO,
                                    self.lote + LOTE_PASSO_SUCESSO,
                                )
                                self.sucessos_consecutivos = 0
                            return dados, duracao, lote_usado
            except requests.exceptions.Timeout:
                erro_curto = "timeout de conexão/leitura"
                congestionamento = True
            except requests.exceptions.RequestException as erro:
                erro_curto = type(erro).__name__
            except (ValueError, TypeError, KeyError) as erro:
                erro_curto = type(erro).__name__

            self.sucessos_consecutivos = 0
            queda = (
                LOTE_PASSO_CONGESTIONAMENTO
                if congestionamento
                else LOTE_PASSO_FALHA
            )
            self.lote = max(LOTE_MINIMO, self.lote - queda)
            self.espera_retry_atual = min(
                RETRY_MAXIMO,
                self.espera_retry_atual + RETRY_PASSO,
            )
            if tentativa <= 3 or tentativa % 10 == 0:
                print(
                    f"[retry] {contexto} | {erro_curto} | "
                    f"tentativa {tentativa} | lote {self.lote:,} | "
                    f"espera {self.espera_retry_atual}s",
                    flush=True,
                )
            time.sleep(self.espera_retry_atual)

    def consultar_pagina(
        self, ano: int, search_after: list[Any] | None = None
    ) -> tuple[dict[str, Any], float, int]:
        payload: dict[str, Any] = {
            "track_total_hits": False,
            "_source": CAMPOS_API,
            "query": self.filtro_ano(ano),
            "sort": [{"id.keyword": {"order": "asc"}}],
        }
        if search_after is not None:
            payload["search_after"] = search_after
        return self.post_retry(payload, str(ano))

    @staticmethod
    def salvar_checkpoint(caminho: Path, estado: dict[str, Any]) -> None:
        temporario = caminho.with_suffix(".tmp")
        with temporario.open("w", encoding="utf-8") as arquivo:
            json.dump(estado, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)

    def coletar_ano(self, ano: int) -> Path:
        caminhos = self.caminho_ano(ano)
        if caminhos["final"].is_file() and caminhos["final"].stat().st_size > 0:
            print(f"{ano}: arquivo final já existe; coleta não repetida.")
            return caminhos["final"]

        parcial = caminhos["parcial"]
        checkpoint_path = caminhos["checkpoint"]
        if checkpoint_path.is_file():
            estado = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        elif parcial.is_file() and parcial.stat().st_size > 0:
            raise RuntimeError(
                f"{ano}: existe arquivo parcial sem checkpoint; "
                "não vou sobrescrever o progresso."
            )
        else:
            estado = {
                "version": CHECKPOINT_VERSION,
                "ano": ano,
                "search_after": None,
                "processos": 0,
                "paginas": 0,
                "file_size": 0,
                "concluido": False,
            }

        if int(estado.get("ano", ano)) != ano or int(
            estado.get("version", CHECKPOINT_VERSION)
        ) != CHECKPOINT_VERSION:
            raise RuntimeError(
                f"{ano}: checkpoint incompatível com o ano solicitado "
                "ou com a versão atual."
            )

        tamanho_checkpoint = int(estado.get("file_size", 0))
        tamanho_atual = parcial.stat().st_size if parcial.is_file() else 0
        if tamanho_atual < tamanho_checkpoint:
            raise RuntimeError(
                f"{ano}: o arquivo parcial é menor que o checkpoint; "
                "não é seguro continuar."
            )
        if tamanho_atual > tamanho_checkpoint:
            with parcial.open("r+b") as arquivo:
                arquivo.truncate(tamanho_checkpoint)

        if estado.get("concluido"):
            if not parcial.is_file():
                raise RuntimeError(
                    f"{ano}: checkpoint concluído sem o arquivo parcial correspondente."
                )
            parcial.replace(caminhos["final"])
            return caminhos["final"]

        total = int(estado.get("processos", 0))
        search_after = estado.get("search_after")
        pagina = int(estado.get("paginas", 0))
        self.lote = LOTE_INICIAL
        self.espera_retry_atual = RETRY_INICIAL
        self.sucessos_consecutivos = 0
        print(
            f"{ano}: lote adaptativo {self.lote:,} | "
            f"mínimo {LOTE_MINIMO:,} | máximo {LOTE_MAXIMO:,}"
        )

        concluido = False
        with parcial.open("ab") as arquivo:
            while True:
                dados, duracao, lote_usado = self.consultar_pagina(ano, search_after)
                hits = (dados.get("hits") or {}).get("hits")
                if not isinstance(hits, list):
                    raise RuntimeError(f"{ano}: resposta sem hits.hits após retry.")

                if not hits:
                    arquivo.flush()
                    os.fsync(arquivo.fileno())
                    estado.update(
                        {
                            "version": CHECKPOINT_VERSION,
                            "ano": ano,
                            "search_after": search_after,
                            "processos": total,
                            "paginas": pagina,
                            "file_size": arquivo.tell(),
                            "concluido": True,
                        }
                    )
                    self.salvar_checkpoint(checkpoint_path, estado)
                    concluido = True
                    break

                novo_search_after = (
                    hits[-1].get("sort") if isinstance(hits[-1], dict) else None
                )
                if not novo_search_after or novo_search_after == search_after:
                    raise RuntimeError(f"{ano}: search_after não avançou.")

                bloco = (
                    "\n".join(
                        json.dumps(
                            self.transformar_hit(hit, ano),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        for hit in hits
                    )
                    + "\n"
                ).encode("utf-8")
                arquivo.write(bloco)
                arquivo.flush()
                os.fsync(arquivo.fileno())
                pagina += 1
                total += len(hits)
                search_after = novo_search_after
                estado.update(
                    {
                        "version": CHECKPOINT_VERSION,
                        "ano": ano,
                        "search_after": search_after,
                        "processos": total,
                        "paginas": pagina,
                        "file_size": arquivo.tell(),
                        "concluido": False,
                    }
                )
                self.salvar_checkpoint(checkpoint_path, estado)
                print(
                    f"{ano} | página {pagina:,} | recebidos {len(hits):,}/"
                    f"{lote_usado:,} | {duracao:.2f}s | total {total:,} | "
                    f"próximo lote {self.lote:,}",
                    flush=True,
                )

                if self.limite_por_ano and total >= self.limite_por_ano:
                    print(
                        f"{ano}: limite de teste atingido; "
                        "arquivo parcial preservado."
                    )
                    return parcial

        if concluido:
            parcial.replace(caminhos["final"])
            print(f"{ano}: coleta concluída com {total:,} registros.")
            return caminhos["final"]

        raise RuntimeError(f"{ano}: coleta terminou sem conclusão confirmada.")

    @staticmethod
    def normalizar_lista(valor: Any, numerico: bool = False) -> list[Any]:
        if valor is None:
            valores: Any = []
        elif isinstance(valor, list):
            valores = valor
        elif isinstance(valor, str):
            texto = valor.strip()
            if texto.startswith("[") and texto.endswith("]"):
                try:
                    valores = json.loads(texto)
                except json.JSONDecodeError:
                    valores = [texto]
                if not isinstance(valores, list):
                    valores = [valores]
            else:
                valores = [parte.strip() for parte in texto.split("|")]
        else:
            valores = [valor]

        if numerico:
            return [
                codigo_numerico(item)
                for item in valores
                if str(item).strip()
            ]
        return [str(item).strip() for item in valores if str(item).strip()]

    def normalizar_registro(self, registro: dict[str, Any], ano: int) -> dict[str, str]:
        id_municipio = str(registro.get("id_municipio") or "").strip()
        municipio = (
            str(registro.get("municipio") or "").strip().upper()
            or self.mapa_municipios.get(id_municipio, "")
        )
        normalizado = {
            "ano": str(registro.get("ano") or ano),
            "grau": str(registro.get("grau") or ""),
            "processo": formatar_processo(registro.get("processo")),
            "id_municipio": id_municipio,
            "municipio": municipio,
            "codigo_classe": json_lista(
                self.normalizar_lista(registro.get("codigo_classe"), numerico=True)
            ),
            "nome_classe": json_lista(
                self.normalizar_lista(registro.get("nome_classe"))
            ),
            "codigo_assunto": json_lista(
                self.normalizar_lista(registro.get("codigo_assunto"), numerico=True)
            ),
            "nome_assunto": json_lista(
                self.normalizar_lista(registro.get("nome_assunto"))
            ),
            "codigo_orgao": str(registro.get("codigo_orgao") or ""),
            "nome_orgao": str(registro.get("nome_orgao") or ""),
        }
        return {
            campo: str(normalizado.get(campo) or "")
            for campo in COLUNAS_PARQUET
        }

    def fontes_coletadas(self) -> list[tuple[int, Path, int]]:
        fontes: list[tuple[int, Path, int]] = []
        for ano in self.anos:
            caminhos = self.caminho_ano(ano)
            if caminhos["final"].is_file():
                fontes.append(
                    (ano, caminhos["final"], caminhos["final"].stat().st_size)
                )
            elif caminhos["parcial"].is_file():
                if not caminhos["checkpoint"].is_file():
                    raise FileNotFoundError(f"Checkpoint ausente para o ano {ano}.")
                checkpoint = json.loads(
                    caminhos["checkpoint"].read_text(encoding="utf-8")
                )
                fontes.append((ano, caminhos["parcial"], int(checkpoint["file_size"])))
        if not fontes:
            raise FileNotFoundError(
                "Nenhuma coleta encontrada. Execute a coleta antes da consolidação."
            )
        return fontes

    @staticmethod
    def iterar_registros(caminho: Path, limite: int) -> Iterable[dict[str, Any]]:
        with caminho.open("rb") as arquivo:
            while arquivo.tell() < limite:
                linha = arquivo.readline(limite - arquivo.tell())
                if not linha:
                    break
                if linha.strip():
                    yield json.loads(linha.decode("utf-8"))

    def consolidar_parquet_ano(
        self, ano: int, caminho: Path, limite: int
    ) -> Path:
        arquivo_final = self.arquivo_parquet_ano(ano)
        temporario = Path(str(arquivo_final) + ".tmp")
        total = 0
        lote: list[dict[str, str]] = []
        temporario.unlink(missing_ok=True)
        with pq.ParquetWriter(
            temporario,
            SCHEMA_PARQUET,
            compression="snappy",
        ) as escritor:
            for registro in self.iterar_registros(caminho, limite):
                lote.append(self.normalizar_registro(registro, ano))
                total += 1
                if len(lote) >= 10_000:
                    escritor.write_table(
                        pa.Table.from_pylist(lote, schema=SCHEMA_PARQUET)
                    )
                    lote.clear()
            if lote:
                escritor.write_table(pa.Table.from_pylist(lote, schema=SCHEMA_PARQUET))

        if total == 0:
            temporario.unlink(missing_ok=True)
            raise RuntimeError(f"Nenhum registro foi consolidado para o ano {ano}.")

        validacao = pq.ParquetFile(temporario)
        linhas_validadas = validacao.metadata.num_rows
        esquema_validado = validacao.schema_arrow
        validacao.close()
        if linhas_validadas != total or esquema_validado != SCHEMA_PARQUET:
            temporario.unlink(missing_ok=True)
            raise RuntimeError(f"A validação do Parquet falhou para o ano {ano}.")

        temporario.replace(arquivo_final)
        tamanho_mb = arquivo_final.stat().st_size / 1024**2
        print(
            f"{ano}: Parquet salvo em {arquivo_final} "
            f"({total:,} registros; {tamanho_mb:,.2f} MB)"
        )
        return arquivo_final

    def consolidar_parquets(self) -> list[Path]:
        arquivos: list[Path] = []
        for ano, caminho, limite in self.fontes_coletadas():
            arquivos.append(self.consolidar_parquet_ano(ano, caminho, limite))
        print(f"{len(arquivos)} arquivo(s) anual(is) consolidado(s).")
        return arquivos

    def executar(self, consolidar: bool = True) -> None:
        print(f"Projeto: {self.project_root}")
        print(f"API configurada: {self.url_datajud}")
        print(f"Anos configurados: {self.anos}")
        print(f"Limite por ano: {self.limite_por_ano or 'sem limite'}")
        print(f"Pasta dos arquivos brutos: {self.pasta_raw}")
        print(f"Pasta dos Parquets anuais: {self.pasta_processed}")
        print(f"Arquivo existente preservado: {self.arquivo_parquet_atual}")
        print(
            f"Dicionário de municípios: {self.municipios_csv} "
            f"({len(self.mapa_municipios):,} entradas)"
        )

        for ano in self.anos:
            self.coletar_ano(ano)

        if consolidar:
            self.consolidar_parquets()


def criar_parser(project_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Coleta e consolida dados do Datajud por ano."
    )
    parser.add_argument(
        "--anos",
        default=os.getenv("DATAJUD_ANOS", "2009-2024"),
        help="Anos separados por vírgula ou intervalo. Padrão: 2009-2024.",
    )
    parser.add_argument(
        "--ano",
        type=int,
        help="Coleta somente este ano; substitui --anos.",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=int(os.getenv("DATAJUD_LIMITE_POR_ANO", "0") or 0),
        help="Limite de registros por ano; 0 significa sem limite.",
    )
    parser.add_argument(
        "--project-root",
        default=str(project_root),
        help="Raiz do projeto Hélio.",
    )
    parser.add_argument(
        "--municipios",
        default=os.getenv("MUNICIPIOS_BAHIA_CSV"),
        help="Caminho alternativo para municipios_bahia.csv.",
    )
    parser.add_argument(
        "--sem-consolidar",
        action="store_true",
        help="Somente coleta os arquivos brutos; não cria Parquet.",
    )
    return parser


def main() -> int:
    projeto_inicial = localizar_projeto()
    carregar_env(projeto_inicial / ".env")
    parser = criar_parser(projeto_inicial)
    argumentos = parser.parse_args()

    project_root = Path(argumentos.project_root).expanduser().resolve()
    if project_root != projeto_inicial:
        carregar_env(project_root / ".env")

    anos = [argumentos.ano] if argumentos.ano else parse_anos(argumentos.anos)
    limite = argumentos.limite or None
    if limite is not None and limite < 1:
        raise ValueError("--limite deve ser maior que zero ou omitido.")

    pipeline = DatajudPipeline(
        project_root=project_root,
        anos=anos,
        limite_por_ano=limite,
        municipios_csv=argumentos.municipios,
    )
    pipeline.executar(consolidar=not argumentos.sem_consolidar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
