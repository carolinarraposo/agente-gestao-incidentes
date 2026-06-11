from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session

from src.graph import graph
from src.database import create_tables, get_db
from src.logger import logger
from src.models import (
    MessageRequest,
    MessageResponse,
    TicketResponse,
    StatusUpdateRequest,
    StatusUpdateDB,
    IncidentDB,
    MessageDB,
    StatusHistoryDB,
    CitizenUpdate,
    CitizenUpdatesResponse,
)


app = FastAPI(
    title="Agente Inteligente para Gestão de Incidentes",
    description="API para triagem, encaminhamento e acompanhamento de incidentes urbanos.",
    version="0.1.0"
)


@app.on_event("startup")
def startup_event():
    create_tables()


@app.get("/")
def root():
    return {
        "message": "API do Agente de Gestão de Incidentes ativa."
    }


@app.post("/message", response_model=MessageResponse)
def process_message(request: MessageRequest, db: Session = Depends(get_db)):
    logger.info(
        f"Pedido recebido | citizen_id={request.citizen_id} | message={request.message}"
    )

    citizen_message = MessageDB(
        citizen_id=request.citizen_id,
        incident_id=None,
        sender="citizen",
        content=request.message
    )

    db.add(citizen_message)
    db.commit()
    db.refresh(citizen_message)

    pending_incident = (
        db.query(IncidentDB)
        .filter(
            IncidentDB.citizen_id == request.citizen_id,
            IncidentDB.status == "aguardando_informacao"
        )
        .first()
    )

    if pending_incident:
        combined_message = (
            f"{pending_incident.description} "
            f"{request.message}"
        )
    else:
        combined_message = request.message

    initial_state = {
        "citizen_id": request.citizen_id,
        "message": combined_message,

        "pending_incident_id": pending_incident.id if pending_incident else None,

        "incident_type": None,
        "description": combined_message,
        "location": None,
        "location_clarification_question": None,

        "priority": None,
        "priority_justification": None,
        "risk_analysis": None,

        "department": None,
        "routing_justification": None,

        "missing_fields": [],

        "protocol": None,
        "status": None,

        "response": None
    }

    result = graph.invoke(initial_state)

    if result["protocol"]:
        incident = (
            db.query(IncidentDB)
            .filter(IncidentDB.protocol == result["protocol"])
            .first()
        )
    else:
        incident = (
            db.query(IncidentDB)
            .filter(
                IncidentDB.citizen_id == request.citizen_id,
                IncidentDB.status == "aguardando_informacao"
            )
            .order_by(IncidentDB.created_at.desc())
            .first()
        )

    if incident:
        citizen_message.incident_id = incident.id

        agent_message = MessageDB(
            citizen_id=request.citizen_id,
            incident_id=incident.id,
            sender="agent",
            content=result["response"]
        )

        db.add(agent_message)
        db.commit()

    logger.info(
        f"Resposta enviada | citizen_id={request.citizen_id} | protocolo={result['protocol']} | status={result['status']}"
    )

    return MessageResponse(
        response=result["response"],
        protocol=result["protocol"],
        status=result["status"]
    )


@app.post("/status/update")
def update_status(request: StatusUpdateRequest, db: Session = Depends(get_db)):

    incident = (
        db.query(IncidentDB)
        .filter(IncidentDB.protocol == request.protocol)
        .first()
    )

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Chamado não encontrado."
        )

    old_status = incident.status
    incident.status = request.status.value

    status_update = StatusUpdateDB(
        protocol=request.protocol,
        status=request.status.value,
        message=request.message
    )

    db.add(status_update)

    history_entry = StatusHistoryDB(
        incident_id=incident.id,
        old_status=old_status,
        new_status=request.status.value,
        message=request.message
    )

    db.add(history_entry)
    db.commit()

    logger.info(
        f"Estado atualizado | protocolo={request.protocol} | novo_status={request.status.value}"
    )

    feedback = (
        f"O chamado {request.protocol} foi atualizado para "
        f"'{request.status.value}'."
    )

    if request.message:
        feedback += f" {request.message}"

    return {
        "response": feedback,
        "protocol": request.protocol,
        "status": request.status.value
    }


@app.get("/incidents")
def get_incidents(db: Session = Depends(get_db)):

    incidents = db.query(IncidentDB).all()

    return [
        {
            "id": incident.id,
            "protocol": incident.protocol,
            "citizen_id": incident.citizen_id,
            "incident_type": incident.incident_type,
            "description": incident.description,
            "location": incident.location,
            "priority": incident.priority,
            "priority_justification": incident.priority_justification,
            "risk_analysis": incident.risk_analysis,
            "department": incident.department,
            "status": incident.status,
            "created_at": incident.created_at
        }
        for incident in incidents
    ]


@app.get("/ticket/{protocol}", response_model=TicketResponse)
def get_ticket(protocol: str, db: Session = Depends(get_db)):

    incident = (
        db.query(IncidentDB)
        .filter(IncidentDB.protocol == protocol)
        .first()
    )

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Chamado não encontrado."
        )

    return TicketResponse(
        protocol=incident.protocol,
        incident_type=incident.incident_type,
        description=incident.description,
        location=incident.location,
        priority=incident.priority,
        department=incident.department,
        status=incident.status,
        created_at=incident.created_at
    )


@app.get("/history/{protocol}")
def get_history(protocol: str, db: Session = Depends(get_db)):

    incident = (
        db.query(IncidentDB)
        .filter(IncidentDB.protocol == protocol)
        .first()
    )

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Chamado não encontrado."
        )

    messages = (
        db.query(MessageDB)
        .filter(MessageDB.incident_id == incident.id)
        .order_by(MessageDB.created_at.asc())
        .all()
    )

    status_history = (
        db.query(StatusHistoryDB)
        .filter(StatusHistoryDB.incident_id == incident.id)
        .order_by(StatusHistoryDB.created_at.asc())
        .all()
    )

    return {
        "protocol": protocol,
        "incident_id": incident.id,

        "messages": [
            {
                "sender": msg.sender,
                "content": msg.content,
                "created_at": msg.created_at
            }
            for msg in messages
        ],

        "status_history": [
            {
                "old_status": status.old_status,
                "new_status": status.new_status,
                "message": status.message,
                "created_at": status.created_at
            }
            for status in status_history
        ]
    }


@app.get("/citizen/{citizen_id}/updates", response_model=CitizenUpdatesResponse)
def get_citizen_updates(
    citizen_id: str,
    since_hours: int = 24,
    db: Session = Depends(get_db)
):
    since = datetime.utcnow() - timedelta(hours=since_hours)

    incidents = (
        db.query(IncidentDB)
        .filter(IncidentDB.citizen_id == citizen_id)
        .all()
    )

    if not incidents:
        return CitizenUpdatesResponse(
            citizen_id=citizen_id,
            updates=[],
            total=0
        )

    incident_ids = [i.id for i in incidents]
    incident_map = {i.id: i for i in incidents}

    history_entries = (
        db.query(StatusHistoryDB)
        .filter(StatusHistoryDB.incident_id.in_(incident_ids))
        .order_by(StatusHistoryDB.created_at.desc())
        .all()
    )

    updates = []
    for entry in history_entries:
        created = entry.created_at
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                continue
        if created < since:
            continue

        incident = incident_map.get(entry.incident_id)
        if not incident:
            continue

        updates.append(CitizenUpdate(
            protocol=incident.protocol or "",
            incident_type=incident.incident_type,
            location=incident.location,
            old_status=entry.old_status,
            new_status=entry.new_status,
            message=entry.message,
            updated_at=str(entry.created_at)
        ))

    return CitizenUpdatesResponse(
        citizen_id=citizen_id,
        updates=updates,
        total=len(updates)
    )