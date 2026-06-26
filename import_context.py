"""
import_context.py
-----------------
Importa os dados de extração (notícias e redes sociais da Covilhã)
para a base de dados do agente, numa tabela independente.

Em produção lê os ficheiros do Cloudflare R2.
Em desenvolvimento lê do caminho local definido em EXTRACTION_RAW_PATH.

Uso:
    python import_context.py
    python import_context.py --force
"""

import csv
import json
import os
import sys
from urllib.parse import urlparse
import tempfile
from datetime import datetime
from pathlib import Path

from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine, and_
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


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

    return f"sqlite:///{BASE_DIR / 'incidents.db'}"


DATABASE_URL = _build_database_url()

Base = declarative_base()

R2_FILES = [
    "data/raw/news_posts.json",
    "data/raw/reddit_posts.json",
    "data/raw/bluesky_posts.json",
    "data/raw/youtube_posts.json",
    "data/raw/facebook_test.json",
]


class ContextDocumentDB(Base):
    __tablename__ = "context_documents"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False)
    source_name = Column(String, nullable=True)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    url = Column(String, nullable=True)
    published_at = Column(String, nullable=True)
    imported_at = Column(DateTime, default=datetime.utcnow)


def _already_exists(session, source_name: str, url: str = None, content: str = None) -> bool:
    if url:
        return session.query(ContextDocumentDB).filter(
            and_(ContextDocumentDB.source_name == source_name, ContextDocumentDB.url == url)
        ).first() is not None
    if content:
        return session.query(ContextDocumentDB).filter(
            and_(ContextDocumentDB.source_name == source_name, ContextDocumentDB.content == content)
        ).first() is not None
    return False


def _extract_site_name(url: str) -> str:
    if not url:
        return "Google News"
    try:
        domain = urlparse(url).netloc
        domain = domain.replace("www.", "")
        return domain or "Google News"
    except Exception:
        return "Google News"


def download_from_r2() -> Path:
    """Descarrega os ficheiros do R2 para uma pasta temporária e devolve o caminho."""
    try:
        import boto3
    except ImportError:
        print("[ERRO] boto3 não instalado. Corre: pip install boto3")
        sys.exit(1)

    endpoint = os.getenv("R2_ENDPOINT_URL")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET_NAME")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    tmp_dir = Path(tempfile.mkdtemp())
    raw_dir = tmp_dir / "data" / "raw"
    raw_dir.mkdir(parents=True)

    for file_path in R2_FILES:
        dest = tmp_dir / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            client.download_file(bucket, file_path, str(dest))
            print(f"[R2] Download OK: {file_path}")
        except Exception as e:
            print(f"[R2] AVISO: {file_path} não encontrado no R2 — {e}")

    return raw_dir


def get_raw_path() -> Path:
    """Devolve o caminho local para os ficheiros de extração."""
    env_path = os.getenv("EXTRACTION_RAW_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        print(f"[AVISO] EXTRACTION_RAW_PATH definido mas não encontrado: {env_path}")

    default = BASE_DIR.parent / "extracao_dados_covilha" / "data" / "raw"
    if default.exists():
        return default

    print("[ERRO] Não foi possível encontrar a pasta data/raw da extração.")
    print("       Define a variável EXTRACTION_RAW_PATH no .env com o caminho correto.")
    sys.exit(1)


def import_news(session, raw_path: Path) -> int:
    # Tenta JSON primeiro (R2), depois CSV (local)
    json_path = raw_path / "news_posts.json"
    csv_path = raw_path / "news_posts.csv"

    count = 0

    if json_path.exists():
        with open(json_path, encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for item in data if isinstance(data, list) else []:
            text = (item.get("text") or "").strip()
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip() or None
            if not text:
                continue
            site_name = _extract_site_name(url)
            if _already_exists(session, site_name, url=url, content=text):
                continue
            doc = ContextDocumentDB(
                source="news",
                source_name=site_name,
                title=title[:500] if title else None,
                content=text,
                url=url,
                published_at=str(item.get("created_at") or "").strip() or None,
            )
            session.add(doc)
            count += 1
    elif csv_path.exists():
        with open(csv_path, encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                text = (row.get("text") or "").strip()
                title = (row.get("title") or "").strip()
                url = (row.get("url") or "").strip() or None
                if not text:
                    continue
                site_name = _extract_site_name(url)
                if _already_exists(session, site_name, url=url, content=text):
                    continue
                doc = ContextDocumentDB(
                    source="news",
                    source_name=site_name,
                    title=title[:500] if title else None,
                    content=text,
                    url=url,
                    published_at=(row.get("created_at") or "").strip() or None,
                )
                session.add(doc)
                count += 1
    else:
        print("[AVISO] news_posts não encontrado, a saltar.")

    session.commit()
    return count


def import_reddit(session, raw_path: Path) -> int:
    filepath = raw_path / "reddit_posts.json"
    if not filepath.exists():
        print(f"[AVISO] {filepath.name} não encontrado, a saltar.")
        return 0

    count = 0
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    for item in data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or item.get("Texto") or "").strip()
        title = (item.get("title") or item.get("Título") or "").strip()
        if not text and not title:
            continue
        content = f"{title}\n{text}".strip() if title else text
        url = (item.get("url") or item.get("URL") or "").strip() or None
        if _already_exists(session, "Reddit", url=url, content=content):
            continue
        doc = ContextDocumentDB(
            source="social_media",
            source_name="Reddit",
            title=title[:500] if title else None,
            content=content,
            url=url,
            published_at=(item.get("created_at") or item.get("Data") or "").strip() or None,
        )
        session.add(doc)
        count += 1

    session.commit()
    return count


def import_bluesky(session, raw_path: Path) -> int:
    # Tenta JSON primeiro (R2), depois CSV (local)
    json_path = raw_path / "bluesky_posts.json"
    csv_path = raw_path / "bluesky_posts.csv"

    count = 0

    if json_path.exists():
        with open(json_path, encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for item in data if isinstance(data, list) else []:
            text = (item.get("text") or item.get("Texto") or "").strip()
            if not text:
                continue
            if _already_exists(session, "Bluesky", content=text):
                continue
            doc = ContextDocumentDB(
                source="social_media",
                source_name="Bluesky",
                title=None,
                content=text,
                url=None,
                published_at=(item.get("created_at") or item.get("Data") or "").strip() or None,
            )
            session.add(doc)
            count += 1
    elif csv_path.exists():
        with open(csv_path, encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                text = (row.get("Texto") or row.get("text") or "").strip()
                if not text:
                    continue
                if _already_exists(session, "Bluesky", content=text):
                    continue
                doc = ContextDocumentDB(
                    source="social_media",
                    source_name="Bluesky",
                    title=None,
                    content=text,
                    url=None,
                    published_at=(row.get("Data") or row.get("created_at") or "").strip() or None,
                )
                session.add(doc)
                count += 1
    else:
        print("[AVISO] bluesky_posts não encontrado, a saltar.")

    session.commit()
    return count


def import_youtube(session, raw_path: Path) -> int:
    filepath = raw_path / "youtube_posts.json"
    if not filepath.exists():
        print(f"[AVISO] {filepath.name} não encontrado, a saltar.")
        return 0

    count = 0
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    for item in data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        title = (item.get("title") or "").strip()
        if not text and not title:
            continue
        content = f"{title}\n{text}".strip() if title else text
        url = (item.get("url") or "").strip() or None
        if _already_exists(session, "YouTube", url=url, content=content):
            continue
        doc = ContextDocumentDB(
            source="social_media",
            source_name="YouTube",
            title=title[:500] if title else None,
            content=content,
            url=url,
            published_at=(item.get("created_at") or "").strip() or None,
        )
        session.add(doc)
        count += 1

    session.commit()
    return count


def main(force: bool = False):
    connect_args = {}
    if DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    existing = session.query(ContextDocumentDB).count()
    print(f"[INFO] Documentos existentes na base de dados: {existing}")

    # Usa R2 se as credenciais estiverem definidas, caso contrário usa caminho local
    if os.getenv("R2_ENDPOINT_URL") and os.getenv("R2_ACCESS_KEY_ID"):
        print("[INFO] A descarregar dados do Cloudflare R2...")
        raw_path = download_from_r2()
    else:
        raw_path = get_raw_path()

    print(f"[INFO] A ler dados de: {raw_path}")

    n_news = import_news(session, raw_path)
    print(f"[OK] Notícias importadas: {n_news}")

    n_reddit = import_reddit(session, raw_path)
    print(f"[OK] Reddit importado: {n_reddit}")

    n_bluesky = import_bluesky(session, raw_path)
    print(f"[OK] Bluesky importado: {n_bluesky}")

    n_youtube = import_youtube(session, raw_path)
    print(f"[OK] YouTube importado: {n_youtube}")

    novos = n_news + n_reddit + n_bluesky + n_youtube
    total = existing + novos
    print(f"\n[CONCLUÍDO] Novos documentos importados: {novos}")
    print(f"[CONCLUÍDO] Total na base de dados: {total}")

    session.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Reimporta sem pedir confirmação")
    args = parser.parse_args()
    main(force=args.force)