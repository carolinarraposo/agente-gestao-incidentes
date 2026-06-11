"""
import_context.py
-----------------
Importa os dados de extração (notícias e redes sociais da Covilhã)
para a base de dados do agente, numa tabela independente.

Depois desta importação, o agente não depende do repositório de extração
— funciona em qualquer máquina com apenas o seu próprio repositório.

Uso:
    python import_context.py

Corre uma vez antes de arrancar o servidor, ou sempre que os dados
de extração forem atualizados.

Coloca este ficheiro na raiz do agente_gestao_incidentes/
"""

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR / 'incidents.db'}"

Base = declarative_base()


class ContextDocumentDB(Base):
    __tablename__ = "context_documents"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    url = Column(String, nullable=True)
    published_at = Column(String, nullable=True)
    imported_at = Column(DateTime, default=datetime.utcnow)


def get_raw_path() -> Path:
    """
    Localiza a pasta data/raw da extração.
    Tenta primeiro a variável de ambiente, depois o caminho relativo padrão.
    """
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
    filepath = raw_path / "news_posts.csv"
    if not filepath.exists():
        print(f"[AVISO] {filepath.name} não encontrado, a saltar.")
        return 0

    count = 0
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("text") or "").strip()
            title = (row.get("title") or "").strip()
            if not text:
                continue

            doc = ContextDocumentDB(
                source="news",
                title=title[:500] if title else None,
                content=text,
                url=(row.get("url") or "").strip() or None,
                published_at=(row.get("created_at") or "").strip() or None,
            )
            session.add(doc)
            count += 1

    session.commit()
    return count


def import_reddit(session, raw_path: Path) -> int:
    filepath = raw_path / "reddit_posts_clean.json"
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

        doc = ContextDocumentDB(
            source="reddit",
            title=title[:500] if title else None,
            content=content,
            url=(item.get("url") or item.get("URL") or "").strip() or None,
            published_at=(
                item.get("created_at") or item.get("Data") or ""
            ).strip() or None,
        )
        session.add(doc)
        count += 1

    session.commit()
    return count


def import_bluesky(session, raw_path: Path) -> int:
    filepath = raw_path / "bluesky_posts.csv"
    if not filepath.exists():
        print(f"[AVISO] {filepath.name} não encontrado, a saltar.")
        return 0

    count = 0
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("Texto") or row.get("text") or "").strip()
            if not text:
                continue

            doc = ContextDocumentDB(
                source="bluesky",
                title=None,
                content=text,
                url=None,
                published_at=(row.get("Data") or row.get("created_at") or "").strip() or None,
            )
            session.add(doc)
            count += 1

    session.commit()
    return count


def main():
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    existing = session.query(ContextDocumentDB).count()
    if existing > 0:
        print(f"[INFO] Já existem {existing} documentos importados.")
        resp = input("Reimportar tudo? (s/N): ").strip().lower()
        if resp != "s":
            print("Importação cancelada.")
            session.close()
            return
        session.query(ContextDocumentDB).delete()
        session.commit()
        print("[INFO] Documentos anteriores removidos.")

    raw_path = get_raw_path()
    print(f"[INFO] A ler dados de: {raw_path}")

    n_news = import_news(session, raw_path)
    print(f"[OK] Notícias importadas: {n_news}")

    n_reddit = import_reddit(session, raw_path)
    print(f"[OK] Reddit importado: {n_reddit}")

    n_bluesky = import_bluesky(session, raw_path)
    print(f"[OK] Bluesky importado: {n_bluesky}")

    total = n_news + n_reddit + n_bluesky
    print(f"\n[CONCLUÍDO] Total de documentos importados: {total}")

    session.close()


if __name__ == "__main__":
    main()