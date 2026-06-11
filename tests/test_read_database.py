from src.database import SessionLocal
from src.models import IncidentDB

db = SessionLocal()

incidents = db.query(IncidentDB).all()

for incident in incidents:
    print(
        incident.id,
        incident.protocol,
        incident.incident_type,
        incident.location,
        incident.priority,
        incident.department,
        incident.status
    )

db.close()