"""
Teste de integração ponta-a-ponta do agente de gestão de incidentes.

Cobre três cenários:
1. Fluxo completo com localização — chamado criado numa única mensagem
2. Fluxo multi-turno — agente pede localização, cidadão responde, chamado criado
3. Feedback proativo — atualização de status visível no endpoint de updates

Executa com:
    pytest tests/test_integration.py -v
"""

import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.database import engine, SessionLocal
from src.models import Base, IncidentDB, MessageDB, StatusHistoryDB, StatusUpdateDB


client = TestClient(app)


# =========================
# Limpeza da base de dados
# antes e depois de cada teste
# =========================

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(StatusHistoryDB).delete()
        db.query(StatusUpdateDB).delete()
        db.query(MessageDB).delete()
        db.query(IncidentDB).delete()
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
        db.commit()
    finally:
        db.close()


# =========================
# Cenário 1: Fluxo completo
# com localização desde o início
# =========================

def test_fluxo_completo_com_localizacao():
    """
    Cidadão reporta um incidente com localização suficiente.
    Espera-se que o chamado seja criado numa única mensagem,
    com protocolo, departamento e status corretos.
    """

    response = client.post("/message", json={
        "citizen_id": "test_citizen_001",
        "message": "Há um buraco enorme na Rua Marquês d'Ávila e Bolama na Covilhã"
    })

    assert response.status_code == 200

    data = response.json()

    assert data["protocol"] is not None, "Protocolo não foi gerado"
    assert data["protocol"].startswith("INC-"), "Formato do protocolo inválido"
    assert data["status"] == "recebido", f"Status inesperado: {data['status']}"
    assert data["response"] is not None, "Resposta não foi gerada"
    assert len(data["response"]) > 10, "Resposta demasiado curta"

    ticket = client.get(f"/ticket/{data['protocol']}")
    assert ticket.status_code == 200

    ticket_data = ticket.json()
    assert ticket_data["incident_type"] is not None
    assert ticket_data["department"] is not None
    assert ticket_data["location"] is not None
    assert ticket_data["priority"] is not None


# =========================
# Cenário 2: Fluxo multi-turno
# agente pede localização
# =========================

def test_fluxo_multi_turno_sem_localizacao():
    """
    Cidadão reporta incidente sem localização.
    Espera-se que o agente peça a localização na primeira mensagem.
    Na segunda mensagem, com localização, o chamado deve ser criado.
    """

    resposta_1 = client.post("/message", json={
        "citizen_id": "test_citizen_002",
        "message": "Há um foco de mosquitos perto da minha casa, acho que pode ser dengue"
    })

    assert resposta_1.status_code == 200

    data_1 = resposta_1.json()

    assert data_1["protocol"] is None, \
        "Não devia criar protocolo sem localização"
    assert data_1["status"] is None or data_1["status"] == "aguardando_informacao", \
        f"Status inesperado na primeira mensagem: {data_1['status']}"
    assert data_1["response"] is not None
    assert len(data_1["response"]) > 5, "Agente não respondeu a pedir localização"

    resposta_2 = client.post("/message", json={
        "citizen_id": "test_citizen_002",
        "message": "É na Rua do Comércio, junto ao número 15"
    })

    assert resposta_2.status_code == 200

    data_2 = resposta_2.json()

    assert data_2["protocol"] is not None, \
        "Protocolo devia ter sido criado após fornecer localização"
    assert data_2["protocol"].startswith("INC-")
    assert data_2["status"] == "recebido"

    ticket = client.get(f"/ticket/{data_2['protocol']}")
    assert ticket.status_code == 200

    ticket_data = ticket.json()
    assert ticket_data["location"] is not None, "Localização não foi guardada"


# =========================
# Cenário 3: Atualização de status
# e feedback proativo
# =========================

def test_feedback_proativo():
    """
    Após criação do chamado, o status é atualizado.
    O cidadão deve conseguir ver a atualização no endpoint de updates.
    """

    msg = client.post("/message", json={
        "citizen_id": "test_citizen_003",
        "message": "Candeeiro avariado na Rua da Estação na Covilhã"
    })

    assert msg.status_code == 200
    protocol = msg.json()["protocol"]
    assert protocol is not None

    update = client.post("/status/update", json={
        "protocol": protocol,
        "status": "em_execucao",
        "message": "Equipa técnica a caminho."
    })

    assert update.status_code == 200

    updates = client.get("/citizen/test_citizen_003/updates?since_hours=24")
    assert updates.status_code == 200

    data = updates.json()
    assert data["total"] >= 1, "Devia existir pelo menos uma atualização"

    entry = data["updates"][0]
    assert entry["protocol"] == protocol
    assert entry["new_status"] == "em_execucao"
    assert entry["old_status"] == "recebido"
    assert entry["message"] == "Equipa técnica a caminho."