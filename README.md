# Projeto Hélio

Plataforma de *analytics* preditivo para o Judiciário: uso de Data Science e modelos estatísticos/ML para antecipar cenários de demanda que impactam o funcionamento dos Tribunais de Justiça.

> Iniciativa idealizada por Fábio (doutorado) e desenvolvida pelo Núcleo de T.I. do EDEP — TJBA.

---

## Sobre o projeto

O Hélio investiga como indicadores demográficos e socioeconômicos ajudam a prever o comportamento da demanda judicial, apoiando o planejamento dos Tribunais de Justiça.

**Recorte da 1ª entrega (MVP):** *previsão de demanda* — a partir de séries históricas, projetar o comportamento futuro do volume processual. A frente de *inferência causal* (relações de causa e efeito entre fatores sociais e judiciais), mais ambiciosa, fica para uma etapa posterior, apoiada nesta base.

**Diretrizes já definidas:**
- Trabalhamos apenas com **metadados** — totais e contagens agregadas, **nunca** processos individuais.
- Início pela **Bahia**, organizando os dados por **comarca** (cada comarca atende um ou mais municípios).
- Classe/assunto processual de partida: *a definir com Fábio*.

## Fontes de dados

| Fonte | O que fornece | Forma de acesso |
|---|---|---|
| **IBGE** | Demografia e indicadores socioeconômicos (população, escolaridade, renda) | API REST pública, sem autenticação (método GET) |
| **Datajud / CNJ** | Metadados processuais dos Tribunais | API sobre Elasticsearch: exige chave pública no cabeçalho e consulta via POST com corpo JSON |

> A chave pública do Datajud muda periodicamente e deve ser sempre copiada da wiki oficial: https://datajud-wiki.cnj.jus.br/api-publica/acesso

## Estrutura do repositório

```
helio/
├── README.md              # este arquivo
├── requirements.txt       # bibliotecas Python do projeto
├── manage.py               # comandos administrativos do Django
├── helio_backend/          # configuração do projeto Django
├── core/                   # aplicação Django: modelos, API e migrações
├── .gitignore             # o que NÃO sobe para o repositório
├── .env.example           # modelo das variáveis de ambiente (ex.: chave do Datajud)
├── docs/                  # documentação, dicionário de dados, decisões
├── notebooks/             # exploração e experimentos (EDA)
├── src/                   # código reutilizável, dividido por etapa:
│   ├── ingestao/          #   conexão com as APIs (IBGE, Datajud)
│   ├── tratamento/        #   limpeza e transformação
│   ├── modelagem/         #   modelos de ML
│   └── visualizacao/      #   gráficos
├── data/                  # dados (conteúdo NÃO versionado — ver aviso abaixo)
│   ├── raw/               #   brutos
│   ├── interim/           #   intermediários
│   └── processed/         #   prontos para modelagem
└── tests/                 # testes
```

## Onde vai cada contribuição

| Tipo de trabalho | Pasta |
|---|---|
| Código de conexão às APIs (IBGE, Datajud) | `src/ingestao/` |
| Limpeza e transformação de dados | `src/tratamento/` |
| Modelos de ML | `src/modelagem/` |
| Geração de gráficos | `src/visualizacao/` |
| Exploração e experimentos | `notebooks/` |
| Documentação e decisões | `docs/` |

> **Atenção — dados não entram no repositório.** O que versionamos é o **código** que coleta e trata os dados, não os dados em si. As pastas dentro de `data/` são ignoradas pelo Git (ver `.gitignore`); os arquivos de dados ficam na máquina de cada um ou em drive compartilhado. A única exceção são resultados pequenos e já processados, e mesmo esses só por decisão combinada.

## Como começar

Pré-requisitos: Git, Python 3 e VS Code instalados.

1. Clone o repositório e entre na pasta:
```bash
   git clone <URL-do-repositório>
   cd <pasta-do-projeto>
```
2. Crie seu arquivo de credenciais a partir do modelo:
```bash
   cp .env.example .env
```
   Abra o `.env` e preencha a `DATAJUD_API_KEY` com a chave vigente (copiada da wiki oficial). O `.env` nunca é enviado ao GitHub.
3. (Recomendado) crie um ambiente virtual e instale as dependências:
```bash
   python -m venv venv
   source venv/Scripts/activate   # Windows (Git Bash)
   pip install -r requirements.txt
```
   > O `requirements.txt` cresce conforme o projeto adota novas bibliotecas.

## Backend Django

O backend inicial está na raiz do projeto e usa SQLite por padrão para desenvolvimento.
Ele também aceita PostgreSQL por meio das variáveis de ambiente do `.env.example`.

Para iniciar:

```bash
python -m venv venv
venv\\Scripts\\activate       # Windows PowerShell
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Banco PostgreSQL do Hélio

O desenvolvimento local usa SQLite por padrão. Para conectar ao banco real, o
túnel SSH deve permanecer aberto em um terminal separado:

```powershell
ssh -N -L 5433:127.0.0.1:5432 tunel_seu_usuario@server.igovia.com.br
```

Em outro terminal, crie o arquivo `.env` a partir do `.env.example` e use:

```dotenv
DB_ENGINE=postgresql
DB_NAME=helio
DB_HOST=127.0.0.1
DB_PORT=5433
DB_USER=seu_usuario
DB_PASSWORD=sua_senha
```

O Django então acessará `localhost:5433`, que é encaminhado pelo túnel para o
PostgreSQL do servidor. Teste a conexão com:

```powershell
python manage.py migrate --plan
```

Depois de confirmar a conexão, as migrações podem ser aplicadas no banco real:

```powershell
python manage.py migrate
```

Com o túnel aberto e o `.env` configurado, o importador do Datajud também
gravará diretamente no PostgreSQL:

```powershell
python manage.py importar_datajud 500000
```

Principais endpoints:

- `GET /api/health/` — verifica a aplicação e a conexão com o banco.
- `/api/datajud-registros/` — CRUD público dos registros do Datajud.
- `/api/docs/` — documentação interativa Swagger UI.
- `/api/schema/` — schema OpenAPI em JSON.
- `/api/redoc/` — documentação ReDoc.
- `/admin/` — painel público com indicadores agregados.
- `/django-admin/` — administração técnica do Django, protegida por login.

O modelo atual contém `DatajudRegistro`, que representa a camada bruta do Datajud.
O modelo `IBGE` está mantido como placeholder abstrato, sem campos, até que os
indicadores do IBGE sejam definidos. A coleta das duas APIs será feita pelos
notebooks, sem uma tabela de controle de cargas no backend.

### Carga do Parquet do Datajud

Coloque o arquivo produzido pelo notebook em:

```text
data/processed/datajud/tabela_principal_helios.parquet
```

Os dados não são versionados pelo Git. Os comandos de carga ficam em
`core/management/commands/` e usam a configuração de banco do Django.

Validar o arquivo sem gravar:

```bash
python manage.py importar_datajud --dry-run
```

Importar os registros em lotes:

```bash
python manage.py importar_datajud
```

Importar somente uma quantidade específica de linhas:

```bash
python manage.py importar_datajud 500000
```

Sem esse argumento, o comando importa todas as linhas do arquivo.

Também é possível informar outro caminho:

```bash
python manage.py importar_datajud --arquivo "C:/caminho/arquivo.parquet"
```

Para substituir completamente a carga atual durante a importação:

```bash
python manage.py importar_datajud --limpar-antes
```

Para limpar o banco separadamente, é necessário confirmar explicitamente:

```bash
python manage.py limpar_datajud --confirmar
```

## Fluxo de trabalho (colaboração)

Depois do clone inicial, o ciclo do dia a dia é:

```bash
git pull        # traz o que os colegas já enviaram
# ... faça seu trabalho ...
git add .
git commit -m "mensagem clara do que mudou"
git push        # envia seu trabalho
```

- Comece cada sessão com `git pull` para não trabalhar sobre uma versão desatualizada.
- Escreva mensagens de commit claras (ex.: "adiciona teste da API do IBGE").
- **Boa prática:** desenvolver cada frente nova em sua própria *branch* e integrar ao ramo principal apenas quando estiver pronta e testada.

## Equipe

| Pessoa | Papel no Hélio |
|---|---|
| Fábio | Idealizador e gestor do projeto - Product Owner — requisitos e coordenação |
| Matheus | Desenvolvimento — ingestão e tratamento / BI |
| Delano | Desenvolvimento — ingestão e tratamento / BI |
| Igor | Desenvolvimento — ingestão e tratamento / BI |

---

*Projeto em fase inicial. Este documento evolui junto com o projeto.*
