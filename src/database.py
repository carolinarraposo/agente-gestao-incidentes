import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base

load_dotenv()


def _build_database_url() -> str:
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_NAME")

    if server and database:
        driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"Trusted_Connection=yes;"
        )
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"

    return "sqlite:///./incidents.db"


DATABASE_URL = _build_database_url()

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()