# Agente Inteligente para Gestão de Incidentes Urbanos

API para triagem, priorização e encaminhamento automático de incidentes urbanos reportados pelos cidadãos do município da Covilhã.

## Descrição

O agente recebe mensagens em linguagem natural dos cidadãos, classifica o tipo de incidente, valida a localização, recolhe informação estruturada por categoria, define a prioridade e encaminha para o departamento municipal responsável. O diálogo é multi-turno — o agente pede esclarecimentos quando a informação é insuficiente.

## Arquitetura

O sistema é construído com **LangGraph** (grafo de estados) sobre **FastAPI**, com persistência em **SQLite** e LLM via **Groq** (llama-3.3-70b-versatile).

### Fluxo do grafo

```
classificar → verificar autenticidade → verificar dados em falta → priorizar → encaminhar → criar chamado → guardar → responder
```

- Se a mensagem for **fake**, vai diretamente para a resposta
- Se faltarem dados (localização, descrição, campos extra), o agente pergunta e fica em `aguardando_informacao`
- Quando completo, o incidente é priorizado com contexto local (notícias, Reddit, Bluesky) e encaminhado

### Estrutura do projeto

```
src/
  app.py                   # FastAPI — endpoints e lifespan
  graph.py                 # Grafo LangGraph
  nodes.py                 # Lógica de cada nó do grafo
  state.py                 # Definição do estado do agente
  models.py                # Modelos SQLAlchemy e Pydantic
  auth.py                  # Autenticação JWT
  context_search.py        # Pesquisa de contexto local
  location_validation.py   # Validação de ruas contra dataset oficial
  database.py              # Configuração da BD
  config.py                # Variáveis de ambiente
  logger.py                # Configuração de logs

data/
  streets_covilha.csv      # Dataset oficial de ruas do município (1265 entradas)

tests/
  test_integration.py      # Testes de integração end-to-end
  test_context_search.py   # Testes unitários do context search

import_streets.py          # Importa o dataset de ruas para a BD
import_context.py          # Importa dados de contexto (notícias, redes sociais)
```

## Instalação

### Pré-requisitos

- Python 3.11+
- Conta Groq com API key

### Setup

```bash
# Clonar o repositório
git clone https://github.com/carolinarraposo/agente-gestao-incidentes.git
cd agente-gestao-incidentes

# Criar ambiente virtual
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # Linux/Mac

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com as chaves necessárias
```

### Variáveis de ambiente

```env
GROQ_API_KEY=...           # Chave da API Groq (obrigatório)
JWT_SECRET_KEY=...         # Chave secreta JWT (obrigatório em produção)
EXTRACTION_RAW_PATH=...    # Caminho para dados de extração (opcional)
```

## Arranque

```bash
uvicorn src.app:app --reload
```

O servidor arranca em `http://localhost:8000`. Na primeira execução o dataset de ruas e os dados de contexto são importados automaticamente.

A documentação interativa da API está disponível em `http://localhost:8000/docs`.

## Endpoints

### Autenticação

| Método | Endpoint | Descrição | Acesso |
|--------|----------|-----------|--------|
| POST | `/auth/register` | Registar utilizador | Público |
| POST | `/auth/login` | Login — devolve token JWT | Público |

### Incidentes

| Método | Endpoint | Descrição | Acesso |
|--------|----------|-----------|--------|
| POST | `/message` | Enviar mensagem ao agente | Cidadão |
| GET | `/ticket/{protocol}` | Consultar chamado | Cidadão |
| GET | `/history/{protocol}` | Histórico de mensagens | Cidadão |
| GET | `/citizen/{id}/updates` | Atualizações recentes | Cidadão |
| GET | `/incidents` | Listar todos os incidentes | Funcionário |
| POST | `/status/update` | Atualizar estado de um chamado | Funcionário |

### Roles

- **cidadao** — pode reportar incidentes e consultar os seus chamados
- **funcionario** — pode ver todos os incidentes e atualizar estados

## Categorias de incidente

`buraco` · `iluminacao` · `lixo` · `dengue` · `saneamento` · `incendio` · `neve` · `arvore` · `estrutura` · `ruido` · `vandalismo` · `estacionamento` · `animais` · `agua` · `sinalizacao` · `outros`

Para as categorias `estacionamento`, `animais`, `ruido`, `incendio`, `vandalismo` e `iluminacao`, o agente recolhe campos estruturados adicionais (ex: marca/modelo/cor/matrícula para estacionamento).

## Testes

```bash
pytest tests/ -v
```

17 testes: 3 de integração end-to-end + 14 unitários ao módulo de pesquisa de contexto.

## Dados de contexto

O agente enriquece a priorização com notícias e publicações em redes sociais locais (Covilhã). Os dados são extraídos pelo repositório `extracao-dados-covilha` e importados via `import_context.py`.

## Dataset de ruas

O ficheiro `data/streets_covilha.csv` contém 1265 entradas de ruas oficiais do município da Covilhã com os nomes de freguesia pós-2013, usado para validar e desambiguar localizações mencionadas pelos cidadãos.
