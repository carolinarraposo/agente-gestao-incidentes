from typing import TypedDict, Optional, List


class AgentState(TypedDict):
    citizen_id: str
    message: str
    last_reply: Optional[str]

    pending_incident_id: Optional[int]

    authenticity_flag: Optional[str]
    authenticity_reason: Optional[str]

    incident_type: Optional[str]
    description: Optional[str]
    location: Optional[str]
    clarification_question: Optional[str]

    priority: Optional[str]
    priority_justification: Optional[str]
    risk_analysis: Optional[str]

    department: Optional[str]
    routing_justification: Optional[str]

    missing_fields: List[str]

    protocol: Optional[str]
    status: Optional[str]

    extra_data: Optional[dict]

    response: Optional[str]

