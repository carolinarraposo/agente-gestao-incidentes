from langgraph.graph import StateGraph, END

from src.state import AgentState
from src.nodes import (
    classify_incident,
    verify_authenticity,
    check_missing_data,
    prioritize_incident,
    route_incident,
    create_ticket,
    generate_response,
    save_incident,
)


# =========================
# Criar grafo
# =========================

workflow = StateGraph(AgentState)


# =========================
# Adicionar nós
# =========================

workflow.add_node(
    "classify_incident",
    classify_incident
)

workflow.add_node(
    "verify_authenticity",
    verify_authenticity
)

workflow.add_node(
    "check_missing_data",
    check_missing_data
)

workflow.add_node(
    "prioritize_incident",
    prioritize_incident
)

workflow.add_node(
    "route_incident",
    route_incident
)

workflow.add_node(
    "create_ticket",
    create_ticket
)

workflow.add_node(
    "generate_response",
    generate_response
)

workflow.add_node(
    "save_incident",
    save_incident
)

def route_after_authenticity(state: AgentState) -> str:
    if state.get("authenticity_flag") == "fake":
        return "generate_response"
    return "check_missing_data"

def route_after_missing_data(state: AgentState) -> str:
    if state["missing_fields"]:
        return "create_ticket"
    return "prioritize_incident"

# =========================
# Definir fluxo
# =========================

workflow.set_entry_point("classify_incident")

workflow.add_edge(
    "classify_incident",
    "verify_authenticity"
)

workflow.add_conditional_edges(
    "verify_authenticity",
    route_after_authenticity,
    {
        "check_missing_data": "check_missing_data",
        "generate_response": "generate_response",
    }
)
workflow.add_conditional_edges(
    "check_missing_data",
    route_after_missing_data,
    {
        "create_ticket": "create_ticket",
        "prioritize_incident": "prioritize_incident",
    }
)

workflow.add_edge(
    "prioritize_incident",
    "route_incident"
)

workflow.add_edge(
    "route_incident",
    "create_ticket"
)

workflow.add_edge(
    "create_ticket",
    "save_incident"
)

workflow.add_edge(
    "save_incident",
    "generate_response"
)

workflow.add_edge(
    "generate_response",
    END
)


# =========================
# Compilar grafo
# =========================

graph = workflow.compile()