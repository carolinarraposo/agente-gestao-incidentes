from datetime import datetime
import json

#from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

#from src.config import GOOGLE_API_KEY, MODEL_NAME
from src.config import GROQ_API_KEY, MODEL_NAME

from src.database import SessionLocal
from src.models import IncidentDB
from src.state import AgentState
from src.logger import logger
from src.context_search import get_relevant_context


#llm = ChatGoogleGenerativeAI(
#    model=MODEL_NAME,
#    google_api_key=GOOGLE_API_KEY,
#    temperature=0
#)

llm = ChatGroq(
    model=MODEL_NAME,
    api_key=GROQ_API_KEY,
    temperature=0
)

# =========================
# 1. Classificação
# =========================

def classify_incident(state: AgentState):
    prompt = f"""
    Analisa a seguinte reclamação de um cidadão.

    Reclamação:
    {state["message"]}

    Classifica o tipo de incidente.

    Possíveis categorias:
    - buraco
    - iluminacao
    - lixo
    - dengue
    - saneamento
    - outros

    Responde apenas com o nome da categoria.
    """

    response = llm.invoke(prompt)
    incident_type = response.content.strip().lower()
    logger.info(f"Classificação concluída | tipo={incident_type}")

    return {
        **state,
        "incident_type": incident_type,
        "description": state["message"]
    }


# =========================
# 2. Verificar dados em falta
# =========================

def check_missing_data(state: AgentState):
    prompt = f"""
    Analisa a seguinte reclamação e identifica se existe uma localização.

    Reclamação:
    {state["message"]}

    Deves distinguir entre:
    1. Sem localização;
    2. Localização vaga;
    3. Localização suficientemente específica.

    Uma localização é vaga quando usa expressões como:
    - "perto da escola"
    - "junto ao mercado"
    - "ao pé da biblioteca"
    - "na rua principal"
    sem indicar nome específico, rua, bairro, número ou referência única.

    Uma localização é suficientemente específica quando inclui:
    - nome de rua;
    - nome da escola, hospital, biblioteca ou edifício;
    - bairro;
    - número;
    - coordenadas;
    - ponto de referência claramente identificável.

    Responde APENAS em JSON válido:

    {{
      "has_location": true,
      "location": "localização extraída",
      "is_specific": true,
      "needs_clarification": false,
      "clarification_question": null
    }}

    Se a localização for vaga:

    {{
      "has_location": true,
      "location": "perto da escola",
      "is_specific": false,
      "needs_clarification": true,
      "clarification_question": "Pode indicar o nome da escola, rua ou outro ponto de referência mais específico?"
    }}

    Se não existir localização:

    {{
      "has_location": false,
      "location": null,
      "is_specific": false,
      "needs_clarification": true,
      "clarification_question": "Pode indicar a localização da ocorrência?"
    }}
    """

    response = llm.invoke(prompt)
    content = response.content.strip()

    logger.info(f"Resposta LLM localização | raw={content}")

    content = content.replace("```json", "")
    content = content.replace("```", "")
    content = content.strip()

    missing_fields = []
    location = None
    location_clarification_question = None

    try:
        data = json.loads(content)

        has_location = data.get("has_location", False)
        location = data.get("location")
        is_specific = data.get("is_specific", False)
        needs_clarification = data.get("needs_clarification", True)
        location_clarification_question = data.get(
            "clarification_question",
            "Pode indicar uma localização mais específica?"
        )

        if not has_location:
            missing_fields.append("location")

        elif needs_clarification or not is_specific:
            missing_fields.append("location_clarification")

    except Exception as e:
        logger.error(f"Erro parsing localização | erro={e}")
        missing_fields.append("location")
        location_clarification_question = "Pode indicar a localização da ocorrência?"

    logger.info(
        f"Verificação de dados | location={location} | missing_fields={missing_fields}"
    )

    return {
        **state,
        "location": location,
        "missing_fields": missing_fields,
        "location_clarification_question": location_clarification_question
    }


# =========================
# 3. Priorização
# =========================

def prioritize_incident(state):
    """
    Versão enriquecida com contexto da base de dados de extração.
    """
    from src.context_search import get_relevant_context
    import json

    context = get_relevant_context(
        state.get("incident_type"),
        state.get("description"),
        state.get("location")
    )

    context_block = ""
    if context:
        context_block = f"""
Informação adicional de notícias e redes sociais locais (Covilhã):
{context}

Usa este contexto para ajustar a prioridade se houver padrões recorrentes,
problemas conhecidos na zona, ou cobertura mediática relevante.
"""

    prompt = f"""
Analisa o seguinte incidente urbano.

Tipo:
{state["incident_type"]}

Descrição:
{state["description"]}

Localização:
{state["location"]}
{context_block}
Avalia:
- risco para pessoas;
- risco para saúde pública;
- impacto urbano;
- urgência;
- se há padrões recorrentes ou contexto local relevante.

Define uma prioridade:
- baixa
- media
- alta
- critica

Responde APENAS em JSON válido.

Exemplo:
{{
  "priority": "alta",
  "justification": "Possível risco para a saúde pública.",
  "risk_analysis": "O incidente pode afetar a população próxima."
}}
"""

    response = llm.invoke(prompt)
    content = response.content.strip()

    from src.logger import logger
    logger.info(f"Resposta LLM prioridade | raw={content}")

    content = content.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(content)
        priority = data.get("priority", "media")
        justification = data.get("justification", "Sem justificação.")
        risk_analysis = data.get("risk_analysis", "Sem análise.")
        if not isinstance(risk_analysis, str):
            risk_analysis = json.dumps(risk_analysis, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro parsing prioridade | erro={e}")
        priority = "media"
        justification = "Fallback por erro de parsing."
        risk_analysis = "Não foi possível analisar risco."

    logger.info(f"Priorização concluída | prioridade={priority} | contexto_usado={bool(context)}")

    return {
        **state,
        "priority": priority,
        "priority_justification": justification,
        "risk_analysis": risk_analysis
    }


# =========================
# 4. Encaminhamento
# =========================

def route_incident(state: AgentState):

    prompt = f"""
    Analisa o seguinte incidente urbano e decide qual serviço municipal deve tratar o caso.

    Tipo:
    {state["incident_type"]}

    Descrição:
    {state["description"]}

    Localização:
    {state["location"]}

    Prioridade:
    {state["priority"]}

    Serviços possíveis:
    - Secretaria de Obras: buracos, estradas, passeios, iluminação pública, sinalização, manutenção urbana.
    - Vigilância Sanitária: dengue, focos de mosquitos, saúde pública, pragas, riscos sanitários.
    - Serviços Urbanos: lixo, resíduos, limpeza urbana, contentores, recolha.
    - Serviços de Saneamento: esgotos, águas residuais, drenagem, ruturas de água.
    - Proteção Civil: risco imediato à vida, incêndios, desabamentos, cheias, fios elétricos expostos.
    - Atendimento Geral: casos pouco claros ou que não se enquadram nos anteriores.

    Responde APENAS em JSON válido:

    {{
      "department": "nome do serviço",
      "routing_justification": "motivo do encaminhamento"
    }}
    """

    response = llm.invoke(prompt)

    content = response.content.strip()

    logger.info(f"Resposta LLM encaminhamento | raw={content}")

    content = content.replace("```json", "")
    content = content.replace("```", "")
    content = content.strip()

    try:
        data = json.loads(content)

        department = data.get("department", "Atendimento Geral")
        routing_justification = data.get(
            "routing_justification",
            "Encaminhamento definido automaticamente."
        )

    except Exception as e:
        logger.error(f"Erro parsing encaminhamento | erro={e}")

        department = "Atendimento Geral"
        routing_justification = "Fallback por erro de parsing."

    logger.info(
        f"Encaminhamento concluído | tipo={state['incident_type']} | departamento={department}"
    )

    return {
        **state,
        "department": department,
        "routing_justification": routing_justification
    }


# =========================
# 5. Criar chamado
# =========================

def create_ticket(state: AgentState):
    if state["missing_fields"]:
        logger.info("Chamado não criado | existem dados em falta")
        return {
            **state,
            "protocol": None,
            "status": None
        }

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    protocol = f"INC-{timestamp}"

    logger.info(
        f"Chamado criado | protocolo={protocol} | status=recebido"
    )

    return {
        **state,
        "protocol": protocol,
        "status": "recebido"
    }


# =========================
# 6. Guardar incidente
# =========================

def save_incident(state: AgentState):
    db = SessionLocal()

    try:
        status = (
            "aguardando_informacao"
            if state["missing_fields"]
            else state["status"]
        )

        pending_incident_id = state.get("pending_incident_id")

        if pending_incident_id:
            incident = (
                db.query(IncidentDB)
                .filter(IncidentDB.id == pending_incident_id)
                .first()
            )

            if incident:
                incident.incident_type = state["incident_type"]
                incident.description = state["description"]
                incident.location = state["location"]
                incident.priority = state["priority"]
                incident.priority_justification = state["priority_justification"]
                incident.risk_analysis = state["risk_analysis"]
                incident.department = state["department"]
                incident.protocol = state["protocol"]
                incident.status = status

                db.commit()
                logger.info(
                    f"Incidente pendente atualizado | id={pending_incident_id} | protocolo={state['protocol']}"
                )
                return state

        incident = IncidentDB(
            citizen_id=state["citizen_id"],
            incident_type=state["incident_type"],
            description=state["description"],
            location=state["location"],
            priority=state["priority"],
            priority_justification=state["priority_justification"],
            risk_analysis=state["risk_analysis"],
            department=state["department"],
            protocol=state["protocol"],
            status=status
        )

        db.add(incident)
        logger.info(
            f"Incidente guardado | citizen_id={state['citizen_id']} | protocolo={state['protocol']} | status={status}"
        )
        db.commit()

    finally:
        db.close()

    return state


# =========================
# 7. Gerar resposta
# =========================

def generate_response(state: AgentState):
    if state["missing_fields"]:

        if "location_clarification" in state["missing_fields"]:
            response = state.get(
                "location_clarification_question",
                "Pode indicar uma localização mais específica?"
            )
        else:
            response = (
                "Preciso de mais informações para processar "
                "a ocorrência. Pode indicar a localização?"
            )

    else:
        prompt = f"""
És um assistente virtual da Câmara Municipal da Covilhã.
Gera uma resposta curta, clara e empática para confirmar ao cidadão
que a sua ocorrência foi registada.

Dados do chamado:
- Protocolo: {state["protocol"]}
- Tipo de incidente: {state["incident_type"]}
- Localização: {state["location"]}
- Departamento responsável: {state["department"]}
- Prioridade: {state["priority"]}
- Justificação da prioridade: {state["priority_justification"]}

Regras:
- Máximo 3 frases.
- Menciona sempre o número de protocolo.
- Tom institucional mas acessível, não robótico.
- Não uses linguagem técnica como "LLM", "grafo" ou "nó".
- Não inventes informação que não está nos dados acima.
"""

        try:
            llm_response = llm.invoke(prompt)
            response = llm_response.content.strip()
        except Exception as e:
            logger.error(f"Erro ao gerar resposta com LLM | erro={e}")
            response = (
                f"A sua ocorrência foi registada com o protocolo "
                f"{state['protocol']} e encaminhada para {state['department']}."
            )

    logger.info(f"Resposta gerada | response={response}")

    return {
        **state,
        "response": response
    }