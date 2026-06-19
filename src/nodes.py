from datetime import datetime
import json

from langchain_groq import ChatGroq
from src.config import GROQ_API_KEY, MODEL_NAME

from src.database import SessionLocal
from src.models import IncidentDB
from src.state import AgentState
from src.logger import logger
from src.context_search import get_relevant_context
from src.location_validation import validate_location


PRIORITY_ORDER = ["baixa", "media", "alta", "critica"]

MIN_PRIORITY = {
    "incendio": "critica",
    "estrutura": "critica",
    "arvore": "alta",
    "neve": "alta",
    "dengue": "media",
}

REQUIRED_EXTRA_FIELDS = {
    "estacionamento": {
        "marca":     "Qual é a marca do veículo? (ex: Renault, Volkswagen)",
        "modelo":    "Qual é o modelo do veículo? (ex: Clio, Golf)",
        "cor":       "Qual é a cor do veículo?",
        "matricula": "Qual é a matrícula do veículo?"
    },
    "animais": {
        "especie":  "Qual é a espécie do animal? (ex: cão, gato, pombo)",
        "condicao": "Qual é a condição do animal? (ex: ferido, abandonado, agressivo)"
    },
    "ruido": {
        "tipo_ruido":    "Qual é o tipo de ruído? (obras, música, vizinhos, estabelecimento)",
        "horario_ruido": "Em que horário ocorre o ruído? (diurno, noturno, fim_de_semana, permanente)"
    },
    "incendio": {
        "pessoas_em_risco": "Há pessoas em risco? (sim, nao, desconhecido)",
        "incendio_ativo":   "O incêndio ainda está ativo? (sim, nao)"
    },
    "vandalismo": {
        "tipo_vandalismo": "Qual é o tipo de vandalismo? (graffiti, danos_materiais, destruicao)"
    },
    "iluminacao": {
        "num_candeeiros": "Quantos candeeiros estão afetados? (ex: 1, 3, vários)",
        "zona_risco":     "É uma zona de risco? (passagem_peoes, escola, hospital, nao)"
    }
}


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
    - incendio
    - neve
    - arvore
    - estrutura
    - ruido
    - vandalismo
    - estacionamento
    - animais
    - agua
    - sinalizacao
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
# 2. Verificar autenticidade
# =========================

def verify_authenticity(state: AgentState):
    prompt = f"""
    Analisa a seguinte mensagem enviada para o sistema de gestão de
    incidentes urbanos da Câmara Municipal da Covilhã.

    Mensagem:
    {state["message"]}

    Determina se a mensagem é:
    - "ok": relato genuíno e plausível de um problema urbano real.
    - "suspicious": conteúdo duvidoso que pode ser real mas levanta
      dúvidas (ex: muito vago, tom estranho, informação contraditória).
    - "fake": claramente não é um relato real (ex: teste, spam,
      conteúdo sem sentido, mensagem ofensiva, cenário impossível ou
      fictício, mensagem como "teste", "abc", "123", "olá").

    Responde APENAS em JSON válido:

    {{
      "flag": "ok",
      "reason": "Relato plausível de problema urbano."
    }}
    """

    response = llm.invoke(prompt)
    content = response.content.strip().replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(content)
        flag = data.get("flag", "ok")
        reason = data.get("reason", "")
        if flag not in ("ok", "suspicious", "fake"):
            flag = "ok"
    except Exception as e:
        logger.error(f"Erro parsing autenticidade | erro={e}")
        flag = "ok"
        reason = "Fallback por erro de parsing."

    logger.info(f"Autenticidade verificada | flag={flag} | reason={reason}")

    return {
        **state,
        "authenticity_flag": flag,
        "authenticity_reason": reason
    }

# =========================
# 3. Verificar dados em falta
# =========================

def check_missing_data(state: AgentState):
    prompt = f"""
    Analisa a seguinte reclamação e identifica:
    1. Se existe uma localização suficientemente específica;
    2. Se a descrição do problema é suficientemente clara.

    Reclamação:
    {state["message"]}

    LOCALIZAÇÃO
    Distingue entre:
    - Sem localização;
    - Localização vaga (ex: "perto da escola", "junto ao mercado",
      "ao pé da biblioteca", "na rua principal" — sem nome específico,
      rua, bairro, número ou referência única);
    - Localização suficientemente específica (inclui nome de rua,
      escola/hospital/edifício, bairro, número, coordenadas ou
      ponto de referência claramente identificável).
    Trata "localização vaga" e "localização incompleta" da mesma forma:
    "is_specific": false e "needs_clarification_location": true.

    DESCRIÇÃO
    Considera a descrição insuficiente se não for possível entender
    minimamente o que está a acontecer (ex: "há um problema",
    "está tudo mal", sem indicar o que se passa).

    Responde APENAS em JSON válido, seguindo este formato:

    {{
      "has_location": true,
      "location": "localização extraída ou null",
      "is_specific": true,
      "needs_clarification_location": false,
      "location_clarification_question": null,
      "has_sufficient_description": true,
      "description_clarification_question": null
    }}

    Exemplos de valores para "location_clarification_question":
    - "Pode indicar a localização da ocorrência?" (sem localização)
    - "Pode indicar o nome da escola, rua ou outro ponto de referência mais específico?" (localização vaga)
    - "Pode indicar o número de porta (ou um ponto de referência) e a freguesia, para localizarmos com precisão?" (rua/avenida sem número ou freguesia)

    Exemplo de valor para "description_clarification_question":
    - "Pode descrever com mais detalhe o que está a acontecer?"
    """

    response = llm.invoke(prompt)
    content = response.content.strip()

    logger.info(f"Resposta LLM verificação de dados | raw={content}")

    content = content.replace("```json", "")
    content = content.replace("```", "")
    content = content.strip()

    missing_fields = []
    location = None
    clarification_question = None
    extra_data = state.get("extra_data") or {}

    try:
        data = json.loads(content)

        has_location = data.get("has_location", False)
        location = data.get("location")
        is_specific = data.get("is_specific", False)
        needs_clarification_location = data.get("needs_clarification_location", True)
        location_clarification_question = data.get(
            "location_clarification_question",
            "Pode indicar a localização da ocorrência?"
        )

        has_sufficient_description = data.get("has_sufficient_description", True)
        description_clarification_question = data.get(
            "description_clarification_question",
            "Pode descrever com mais detalhe o que está a acontecer?"
        )

        if not has_location:
            missing_fields.append("location")
            clarification_question = location_clarification_question

        elif needs_clarification_location or not is_specific:
            missing_fields.append("location_clarification")
            clarification_question = location_clarification_question

        else:
            # Fase 2b: validação determinística da rua contra o dataset
            # Corre sempre que há localização — sobrepõe-se ao LLM para casos ambíguos
            db_status, db_question = validate_location(location or "")
            if db_status == "ambiguous":
                missing_fields.append("location_ambiguous")
                clarification_question = db_question
            elif not has_sufficient_description:
                missing_fields.append("description_clarification")
                clarification_question = description_clarification_question

        if not missing_fields:
            # Fase 3: campos estruturados por categoria
            incident_type = state.get("incident_type")
            required_extras = REQUIRED_EXTRA_FIELDS.get(incident_type, {})
            if required_extras:
                needed = {k: v for k, v in required_extras.items() if not extra_data.get(k)}
                if needed:
                    fields_str = "\n".join(f'- "{k}": {desc}' for k, desc in needed.items())
                    last_reply = state.get("last_reply") or state["message"]
                    extra_prompt = f"""O cidadão está a responder a perguntas sobre um incidente urbano.

Contexto completo: {state["message"]}
Última resposta do cidadão: {last_reply}

Campos ainda em falta:
{fields_str}

Extrai os valores dos campos em falta com base na última resposta do cidadão.
- Se a última resposta contiver um valor claro para um campo, usa esse valor.
- Se o cidadão disser explicitamente que não sabe (ex: "não sei", "desconheço", "não tenho"), usa "desconhecido".
- Se a última resposta não mencionar o campo, usa null.
Responde APENAS em JSON. Exemplo: {{"campo1": "valor", "campo2": "desconhecido", "campo3": null}}"""
                    try:
                        extra_response = llm.invoke(extra_prompt)
                        extra_content = extra_response.content.strip().replace("```json", "").replace("```", "").strip()
                        extracted = json.loads(extra_content)
                        for k in needed:
                            val = extracted.get(k)
                            if val and str(val).lower() not in ("null", "none", ""):
                                extra_data[k] = str(val)
                    except Exception as e:
                        logger.error(f"Erro a extrair campos extra | erro={e}")

                    still_missing = {k: v for k, v in needed.items() if not extra_data.get(k)}
                    if still_missing:
                        first_key, first_desc = next(iter(still_missing.items()))
                        missing_fields.append(f"extra_{first_key}")
                        clarification_question = first_desc

    except Exception as e:
        logger.error(f"Erro parsing verificação de dados | erro={e}")
        missing_fields.append("location")
        clarification_question = "Pode indicar a localização da ocorrência?"

    logger.info(
        f"Verificação de dados | location={location} | missing_fields={missing_fields} | extra_data={extra_data}"
    )

    return {
        **state,
        "location": location,
        "missing_fields": missing_fields,
        "clarification_question": clarification_question,
        "extra_data": extra_data,
    }


# =========================
# 4. Priorização
# =========================

def prioritize_incident(state):
    """
    Versão enriquecida com contexto da base de dados de extração.
    """
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

    extra_data = state.get("extra_data") or {}
    extra_block = ""
    if extra_data:
        extra_lines = "\n".join(f"- {k}: {v}" for k, v in extra_data.items())
        extra_block = f"""
Informações adicionais recolhidas:
{extra_lines}
"""

    prompt = f"""
Analisa o seguinte incidente urbano.

Tipo:
{state["incident_type"]}

Descrição:
{state["description"]}

Localização:
{state["location"]}
{extra_block}{context_block}
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

    logger.info(f"Resposta LLM prioridade | raw={content}")

    content = content.replace("```json", "").replace("```", "").strip()

    incident_type = state.get("incident_type")
    fallback_priority = MIN_PRIORITY.get(incident_type, "media")

    try:
        data = json.loads(content)
        priority = data.get("priority", fallback_priority)
        justification = data.get("justification", "Sem justificação.")
        risk_analysis = data.get("risk_analysis", "Sem análise.")
        if not isinstance(risk_analysis, str):
            risk_analysis = json.dumps(risk_analysis, ensure_ascii=False)

        if priority not in PRIORITY_ORDER:
            logger.error(f"Prioridade inválida do LLM | valor={priority}")
            priority = fallback_priority
    except Exception as e:
        logger.error(f"Erro parsing prioridade | erro={e}")
        priority = fallback_priority
        justification = "Fallback por erro de parsing."
        risk_analysis = "Não foi possível analisar risco."

    logger.info(f"Priorização concluída | prioridade={priority} | contexto_usado={bool(context)}")

    min_priority = MIN_PRIORITY.get(incident_type)
    if min_priority and PRIORITY_ORDER.index(priority) < PRIORITY_ORDER.index(min_priority):
        logger.info(
            f"Prioridade ajustada por regra de segurança | tipo={incident_type} | "
            f"original={priority} | ajustada={min_priority}"
        )
        priority = min_priority
        justification += (
            f" (prioridade ajustada para o mínimo de segurança definido "
            f"para incidentes do tipo '{incident_type}'.)"
        )

    # Regra extra: incêndio com pessoas em risco → sempre crítica
    extra_data = state.get("extra_data") or {}
    if incident_type == "incendio" and extra_data.get("pessoas_em_risco") == "sim":
        if priority != "critica":
            logger.info("Prioridade forçada a critica: incendio com pessoas em risco")
            priority = "critica"
            justification += " (forçado a crítico: incêndio com pessoas em risco confirmadas.)"

    return {
        **state,
        "priority": priority,
        "priority_justification": justification,
        "risk_analysis": risk_analysis
    }

# =========================
# 5. Encaminhamento
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
    - Secretaria de Obras: buracos, estradas, passeios, iluminação pública, sinalização, manutenção urbana, árvores ou estruturas sem risco imediato.
    - Vigilância Sanitária: dengue, focos de mosquitos, saúde pública, pragas, riscos sanitários.
    - Serviços Urbanos: lixo, resíduos, limpeza urbana, contentores, recolha.
    - Serviços de Saneamento: esgotos, águas residuais, drenagem, ruturas de água, falta de água.
    - Proteção Civil: risco imediato à vida, incêndios, desabamentos, neve e estradas bloqueadas, queda de árvores ou estruturas com risco iminente, cheias, fios elétricos expostos.
    - Fiscalização Municipal: ruído excessivo, vandalismo/graffiti, veículos mal estacionados ou abandonados.
    - Proteção Animal: animais abandonados, feridos ou em sofrimento.
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
# 6. Criar chamado
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
# 7. Guardar incidente
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
                incident.authenticity_flag = state.get("authenticity_flag")
                incident.extra_data = json.dumps(state.get("extra_data") or {}, ensure_ascii=False) if state.get("extra_data") else None

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
            status=status,
            authenticity_flag=state.get("authenticity_flag"),
            extra_data=json.dumps(state.get("extra_data") or {}, ensure_ascii=False) if state.get("extra_data") else None
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
# 8. Gerar resposta
# =========================

def generate_response(state: AgentState):
    if state.get("authenticity_flag") == "fake":
        response = (
            "A sua mensagem não foi reconhecida como uma ocorrência urbana válida "
            "e não foi registada. Se tiver um problema real para reportar, "
            "por favor descreva-o com mais detalhe."
        )
    elif state["missing_fields"]:
        response = state.get(
            "clarification_question",
            "Preciso de mais informações para processar a ocorrência."
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