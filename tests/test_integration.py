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
from src.models import Base, IncidentDB, MessageDB, StatusHistoryDB, StatusUpdateDB, UserDB
from src.auth import hash_password

client = TestClient(app)

CIDADAO_EMAIL = "test_cidadao@teste.pt"
CIDADAO_PASSWORD = "senha_teste"
FUNCIONARIO_EMAIL = "test_func@teste.pt"
FUNCIONARIO_PASSWORD = "senha_func"


def _get_token(email: str, password: str) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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
        db.query(UserDB).filter(UserDB.email.in_([CIDADAO_EMAIL, FUNCIONARIO_EMAIL])).delete()
        db.commit()
        db.add(UserDB(email=CIDADAO_EMAIL, hashed_password=hash_password(CIDADAO_PASSWORD), role="cidadao"))
        db.add(UserDB(email=FUNCIONARIO_EMAIL, hashed_password=hash_password(FUNCIONARIO_PASSWORD), role="funcionario"))
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
        db.query(UserDB).filter(UserDB.email.in_([CIDADAO_EMAIL, FUNCIONARIO_EMAIL])).delete()
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

    headers = _get_token(CIDADAO_EMAIL, CIDADAO_PASSWORD)

    response = client.post("/message", json={
        "citizen_id": "test_citizen_001",
        "message": "Há um buraco enorme na Rua Marquês d'Ávila e Bolama na Covilhã"
    }, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert data["protocol"] is not None, "Protocolo não foi gerado"
    assert data["protocol"].startswith("INC-"), "Formato do protocolo inválido"
    assert data["status"] == "recebido", f"Status inesperado: {data['status']}"
    assert data["response"] is not None, "Resposta não foi gerada"
    assert len(data["response"]) > 10, "Resposta demasiado curta"

    ticket = client.get(f"/ticket/{data['protocol']}", headers=headers)
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

    headers = _get_token(CIDADAO_EMAIL, CIDADAO_PASSWORD)

    resposta_1 = client.post("/message", json={
        "citizen_id": "test_citizen_002",
        "message": "Há um foco de mosquitos perto da minha casa, acho que pode ser dengue"
    }, headers=headers)

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
    }, headers=headers)

    assert resposta_2.status_code == 200

    data_2 = resposta_2.json()

    assert data_2["protocol"] is not None, \
        "Protocolo devia ter sido criado após fornecer localização"
    assert data_2["protocol"].startswith("INC-")
    assert data_2["status"] == "recebido"

    ticket = client.get(f"/ticket/{data_2['protocol']}", headers=headers)
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
    A mensagem inicial inclui todos os campos extra de iluminacao para
    que o ticket seja criado diretamente sem turno adicional.
    """

    cidadao_headers = _get_token(CIDADAO_EMAIL, CIDADAO_PASSWORD)
    funcionario_headers = _get_token(FUNCIONARIO_EMAIL, FUNCIONARIO_PASSWORD)

    msg = client.post("/message", json={
        "citizen_id": "test_citizen_003",
        "message": (
            "Candeeiro avariado na Rua da Estação na Covilhã. "
            "São 3 candeeiros afetados. É uma zona de passagem de peões."
        )
    }, headers=cidadao_headers)

    assert msg.status_code == 200
    protocol = msg.json()["protocol"]
    assert protocol is not None

    update = client.post("/status/update", json={
        "protocol": protocol,
        "status": "em_execucao",
        "message": "Equipa técnica a caminho."
    }, headers=funcionario_headers)

    assert update.status_code == 200

    updates = client.get("/citizen/test_citizen_003/updates?since_hours=24", headers=cidadao_headers)
    assert updates.status_code == 200

    data = updates.json()
    assert data["total"] >= 1, "Devia existir pelo menos uma atualização"

    entry = data["updates"][0]
    assert entry["protocol"] == protocol
    assert entry["new_status"] == "em_execucao"
    assert entry["old_status"] == "recebido"
    assert entry["message"] == "Equipa técnica a caminho."