from src.graph import graph


initial_state = {
    "citizen_id": "citizen_001",
    "message": "Existe um buraco enorme.",

    "incident_type": None,
    "description": None,
    "location": None,
    "clarification_question": None,

    "priority": None,
    "priority_justification": None,
    "risk_analysis": None,

    "department": None,
    "routing_justification": None,

    "missing_fields": [],

    "protocol": None,
    "status": None,

    "response": None,

    "pending_incident_id": None,

    "authenticity_flag": None,
    "authenticity_reason": None,

    "extra_data": None,
}


result = graph.invoke(initial_state)

print("\nRESULTADO FINAL:\n")
print(result)