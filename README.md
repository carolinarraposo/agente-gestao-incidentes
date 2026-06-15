# Agente Inteligente Autónomo para Gestão de Incidentes

Sistema de inteligência artificial para triagem, encaminhamento e acompanhamento automático de incidentes urbanos reportados por cidadãos ao município da Covilhã.

## Descrição

O agente recebe reclamações de cidadãos em linguagem natural, analisa o conteúdo, solicita informação em falta quando necessário, e encaminha automaticamente cada caso para o departamento municipal responsável — sem intervenção humana constante.

O sistema integra dados de notícias e redes sociais locais para enriquecer a análise de prioridade de cada incidente, considerando contexto real da cidade.

### Funcionalidades principais

- **Triagem e qualificação** — classifica o tipo de incidente e verifica se a localização foi fornecida; se não, interage com o cidadão para a obter
- **Encaminhamento inteligente** — direciona cada chamado para o departamento correto (Secretaria de Obras, Vigilância Sanitária, Serviços Urbanos, Saneamento, Proteção Civil)
- **Priorização com contexto local** — analisa o risco e urgência do incidente, enriquecida com notícias e posts de redes sociais da Covilhã
- **Feedback proativo** — permite ao cidadão consultar atualizações de estado dos seus chamados
- **Respostas naturais** — gera respostas personalizadas e empáticas via LLM, não templates fixos

## Arquitetura

O agente é implementado com **LangGraph**, onde cada etapa do processamento corresponde a um nó do grafo:

```
                                     Mensagem do cidadão
                                            ↓
                                  Classificação do incidente
                                            ↓
                                Verificação de dados em falta
                                            ↓
                                Priorização (com contexto local)
                                            ↓
                               Encaminhamento para departamento
                                            ↓
                                     Criação do chamado
                                            ↓
                                  Guardar na base de dados
                                            ↓
                                Geração de resposta ao cidadão
```

A API é construída com **FastAPI** e os dados são persistidos em **SQLite** via **SQLAlchemy**.

## Pré-requisitos

- Python 3.11+
- Chave de API Groq 

## Instalação

```bash
git clone https://github.com/carolinarraposo/agente-gestao-incidentes.git
cd agente-gestao-incidentes

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

## Configuração

Cria um ficheiro `.env` na raiz do projeto com base no `.env.example`:

```bash
cp .env.example .env
```

Preenche as variáveis:

```
GROQ_API_KEY=a_tua_chave_groq

# Opcional — só necessário se os repositórios não estiverem na mesma pasta pai
# EXTRACTION_RAW_PATH=../extracao_dados_covilha/data/raw
```

## Importação de dados de contexto

O agente utiliza dados de notícias e redes sociais da Covilhã para enriquecer a priorização de incidentes. Para importar os dados pela primeira vez:

```bash
python import_context.py
```

Este passo é opcional — o agente corre `import_context.py` automaticamente no arranque se a base de dados de contexto estiver vazia.

## Execução

```bash
uvicorn src.app:app --reload
```

A API fica disponível em `http://localhost:8000`.

A documentação interativa (Swagger UI) está disponível em `http://localhost:8000/docs`.

## Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/message` | Envia uma mensagem do cidadão ao agente |
| `POST` | `/status/update` | Atualiza o estado de um chamado |
| `GET` | `/ticket/{protocol}` | Consulta os detalhes de um chamado |
| `GET` | `/history/{protocol}` | Consulta o histórico de mensagens e estados |
| `GET` | `/incidents` | Lista todos os incidentes registados |
| `GET` | `/citizen/{citizen_id}/updates` | Consulta atualizações recentes de um cidadão |

## Exemplo de utilização

**Reportar um incidente:**

```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"citizen_id": "citizen_001", "message": "Há um buraco na Rua do Comércio na Covilhã"}'
```

Resposta:
```json
{
  "response": "A sua ocorrência foi registada com o protocolo INC-20260611145207. A Secretaria de Obras irá tratar do caso com prioridade média.",
  "protocol": "INC-20260611145207",
  "status": "recebido"
}
```

**Consultar atualizações:**

```bash
curl http://localhost:8000/citizen/citizen_001/updates?since_hours=24
```

## Testes

```bash
pytest tests/test_integration.py -v
```

Os testes cobrem três cenários de integração ponta-a-ponta:
- Fluxo completo com localização fornecida desde o início
- Fluxo multi-turno onde o agente solicita a localização
- Atualização de estado e consulta de feedback proativo

## Estrutura do projeto

```
agente_gestao_incidentes/
├── src/
│   ├── app.py              # API FastAPI e endpoints
│   ├── graph.py            # Definição do grafo LangGraph
│   ├── nodes.py            # Nós do grafo (lógica do agente)
│   ├── models.py           # Modelos SQLAlchemy e Pydantic
│   ├── database.py         # Configuração da base de dados
│   ├── context_search.py   # Pesquisa de contexto local
│   ├── state.py            # Estado do agente
│   └── logger.py           # Configuração de logging
├── tests/
│   └── test_integration.py # Testes de integração
├── .github/
│   └── workflows/
│       └── import_context.yml  # Workflow de sincronização de dados
├── import_context.py       # Script de importação de dados de contexto
├── requirements.txt
├── .env.example
└── README.md
```

## Autor

Carolina Raposo — Licenciatura em Inteligência Artificial e Ciência de Dados, Universidade da Beira Interior