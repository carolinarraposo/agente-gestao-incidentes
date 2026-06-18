"""
Testes aos endpoints públicos (sem autenticação) e à proteção dos endpoints
reservados a funcionários.

Endpoints públicos testados:
  POST /message
  GET  /ticket/{protocol}
  GET  /history/{protocol}
  GET  /citizen/{citizen_id}/updates

Endpoints protegidos (funcionário):
  POST /status/update
  GET  /incidents

Executa com:
    pytest tests/test_public_endpoints.py -v
"""

import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.database import engine, SessionLocal
from src.models import Base, IncidentDB, MessageDB, StatusHistoryDB, StatusUpdateDB, UserDB
from src.auth import hash_password

client = TestClient(app)

FUNCIONARIO_EMAIL = "func_pub@teste.pt"
FUNCIONARIO_PASSWORD = "senha_func_pub"


def _get_funcionario_token() -> dict:
    r = client.post("/auth/login", json={"email": FUNCIONARIO_EMAIL, "password": FUNCIONARIO_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(StatusHistoryDB).delete()
        db.query(StatusUpdateDB).delete()
        db.query(MessageDB).delete()
        db.query(IncidentDB).delete()
        db.query(UserDB).filter(UserDB.email == FUNCIONARIO_EMAIL).delete()
        db.commit()
        db.add(UserDB(
            email=FUNCIONARIO_EMAIL,
            hashed_password=hash_password(FUNCIONARIO_PASSWORD),
            role="funcionario"
        ))
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.query(StatusHistoryDB).delete()
        db.query(StatusUpdateDB).delete()
        db.query(MessageDB).delete()
        db.query(IncidentDB).delete()
        db.query(UserDB).filter(UserDB.email == FUNCIONARIO_EMAIL).delete()
        db.commit()
    finally:
        db.close()


# =========================
# /message — público
# =========================

def test_message_sem_token_aceite():
    r = client.post("/message", json={
        "citizen_id": "pub_citizen_001",
        "message": "Há um buraco na Rua da Estação na Covilhã"
    })
    assert r.status_code == 200
    data = r.json()
    assert "response" in data
    assert "protocol" in data


# =========================
# /ticket — público
# =========================

def test_ticket_sem_token_aceite():
    msg = client.post("/message", json={
        "citizen_id": "pub_citizen_002",
        "message": "Candeeiro avariado na Rua da Estação na Covilhã. São 2 candeeiros afetados numa zona de peões."
    })
    protocol = msg.json().get("protocol")
    assert protocol is not None, "Protocolo não criado — ajusta a mensagem para incluir localização suficiente"

    r = client.get(f"/ticket/{protocol}")
    assert r.status_code == 200
    data = r.json()
    assert data["protocol"] == protocol
    assert "incident_type" in data
    assert "status" in data


def test_ticket_protocolo_inexistente_devolve_404():
    r = client.get("/ticket/INC-0000000")
    assert r.status_code == 404


# =========================
# /history — público
# =========================

def test_history_sem_token_aceite():
    msg = client.post("/message", json={
        "citizen_id": "pub_citizen_003",
        "message": "Buraco na Rua do Comércio na Covilhã, junto ao número 10"
    })
    protocol = msg.json().get("protocol")
    assert protocol is not None

    r = client.get(f"/history/{protocol}")
    assert r.status_code == 200
    data = r.json()
    assert data["protocol"] == protocol
    assert "messages" in data
    assert "status_history" in data
    assert len(data["messages"]) >= 1


def test_history_protocolo_inexistente_devolve_404():
    r = client.get("/history/INC-0000000")
    assert r.status_code == 404


# =========================
# /citizen/{id}/updates — público
# =========================

def test_citizen_updates_sem_token_aceite():
    msg = client.post("/message", json={
        "citizen_id": "pub_citizen_004",
        "message": "Árvore caída na Rua da Estação na Covilhã, bloqueia a passagem"
    })
    protocol = msg.json().get("protocol")
    assert protocol is not None

    func_headers = _get_funcionario_token()
    client.post("/status/update", json={
        "protocol": protocol,
        "status": "em_execucao",
        "message": "Equipa a caminho."
    }, headers=func_headers)

    r = client.get("/citizen/pub_citizen_004/updates?since_hours=24")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["updates"][0]["protocol"] == protocol


def test_citizen_updates_sem_incidentes_devolve_lista_vazia():
    r = client.get("/citizen/cidadao_inexistente/updates")
    assert r.status_code == 200
    assert r.json()["total"] == 0


# =========================
# Endpoints de funcionário
# continuam protegidos
# =========================

def test_status_update_sem_token_rejeitado():
    r = client.post("/status/update", json={
        "protocol": "INC-0000001",
        "status": "em_execucao",
        "message": "teste"
    })
    assert r.status_code == 401


def test_incidents_sem_token_rejeitado():
    r = client.get("/incidents")
    assert r.status_code == 401