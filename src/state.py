from typing import TypedDict, Optional, List


class AgentState(TypedDict):
    citizen_id: str
    message: str

    pending_incident_id: Optional[int]

    incident_type: Optional[str]
    description: Optional[str]
    location: Optional[str]
    location_clarification_question: Optional[str]

    priority: Optional[str]
    priority_justification: Optional[str]
    risk_analysis: Optional[str]

    department: Optional[str]
    routing_justification: Optional[str]

    missing_fields: List[str]

    protocol: Optional[str]
    status: Optional[str]

    response: Optional[str]

