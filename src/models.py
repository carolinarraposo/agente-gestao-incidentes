from enum import Enum
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


# =========================
# Enums
# =========================

class IncidentType(str, Enum):
    BURACO = "buraco"
    ILUMINACAO = "iluminacao"
    LIXO = "lixo"
    SANEAMENTO = "saneamento"
    OUTROS = "outros"

class PriorityLevel(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"

class TicketStatus(str, Enum):
    AGUARDANDO_INFORMACAO = "aguardando_informacao"
    RECEBIDO = "recebido"
    EM_ANALISE = "em_analise"
    ENCAMINHADO = "encaminhado"
    EM_EXECUCAO = "em_execucao"
    RESOLVIDO = "resolvido"

# =========================
# SQLAlchemy Models
# =========================

class IncidentDB(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(String, index=True, nullable=False)

    incident_type = Column(String, nullable=True)
    description = Column(Text, nullable=False)
    location = Column(String, nullable=True)

    priority = Column(String, nullable=True)
    priority_justification = Column(Text, nullable=True)

    risk_analysis = Column(Text, nullable=True)

    department = Column(String, nullable=True)
    protocol = Column(String, unique=True, index=True, nullable=True)
    status = Column(String, default=TicketStatus.RECEBIDO.value)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("MessageDB", back_populates="incident")


class MessageDB(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(String, index=True, nullable=False)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)

    sender = Column(String, nullable=False)  # citizen / agent
    content = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    incident = relationship("IncidentDB", back_populates="messages")


class StatusUpdateDB(Base):
    __tablename__ = "status_updates"

    id = Column(Integer, primary_key=True, index=True)
    protocol = Column(String, index=True, nullable=False)
    status = Column(String, nullable=False)
    message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


# =========================
# Pydantic Schemas
# =========================

class MessageRequest(BaseModel):
    citizen_id: str = Field(..., example="citizen_001")
    message: str = Field(..., example="Há um buraco enorme perto da escola.")


class MessageResponse(BaseModel):
    response: str
    protocol: Optional[str] = None
    status: Optional[str] = None


class IncidentData(BaseModel):
    citizen_id: str
    incident_type: Optional[IncidentType] = None
    description: str
    location: Optional[str] = None
    priority: Optional[PriorityLevel] = None
    priority_justification: Optional[str] = None
    department: Optional[str] = None
    missing_fields: List[str] = []
    protocol: Optional[str] = None
    status: Optional[TicketStatus] = None


class TicketResponse(BaseModel):
    protocol: str
    incident_type: Optional[str]
    description: str
    location: Optional[str]
    priority: Optional[str]
    department: Optional[str]
    status: str
    created_at: datetime


class StatusUpdateRequest(BaseModel):
    protocol: str = Field(..., example="INC-2026-0001")
    status: TicketStatus = Field(..., example="em_execucao")
    message: Optional[str] = Field(
        default=None,
        example="A equipa técnica já foi encaminhada para o local."
    )


class StatusHistoryDB(Base):
    __tablename__ = "status_history"

    id = Column(Integer, primary_key=True, index=True)

    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)

    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)

    message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class CitizenUpdate(BaseModel):
    protocol: str
    incident_type: Optional[str]
    location: Optional[str]
    old_status: str
    new_status: str
    message: Optional[str]
    updated_at: str


class CitizenUpdatesResponse(BaseModel):
    citizen_id: str
    updates: list[CitizenUpdate]
    total: int
