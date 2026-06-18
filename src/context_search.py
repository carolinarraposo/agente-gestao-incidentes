"""
context_search.py
-----------------
Pesquisa contexto relevante na tabela context_documents da base de dados
do agente para enriquecer a priorização de incidentes.

Os dados são importados previamente via import_context.py.
Coloca este ficheiro em: agente_gestao_incidentes/src/context_search.py
"""

import re
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = f"sqlite:///{BASE_DIR / 'incidents.db'}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

MAX_RESULTS = 5
MAX_TEXT_LENGTH = 300


def _keywords_from_incident(
    incident_type: Optional[str],
    description: Optional[str],
    location: Optional[str]
) -> list:
    keywords = []

    type_map = {
        "buraco": ["buraco", "pavimento", "estrada", "passeio", "alcatrão"],
        "iluminacao": ["iluminação", "iluminacao", "candeeiro", "luz", "poste"],
        "lixo": ["lixo", "resíduos", "contentor", "limpeza", "recolha"],
        "dengue": ["dengue", "mosquito", "mosquitos", "saúde", "foco"],
        "saneamento": ["esgoto", "saneamento", "água", "drenagem", "canos"],
        "incendio": ["incêndio", "incendio", "fogo", "fumo", "chamas"],
        "neve": ["neve", "gelo", "geada", "estrada cortada", "frio"],
        "arvore": ["árvore", "arvore", "ramo", "queda", "tronco"],
        "estrutura": ["estrutura", "colapso", "desabamento", "fissura", "muro"],
        "ruido": ["ruído", "ruido", "barulho", "som", "obras"],
        "vandalismo": ["vandalismo", "graffiti", "grafiti", "pichação", "danos"],
        "estacionamento": ["estacionamento", "carro", "veículo", "abandonado", "via"],
        "animais": ["animal", "animais", "cão", "gato", "abandonado"],
        "agua": ["água", "agua", "fuga", "rede", "abastecimento"],
        "sinalizacao": ["sinalização", "sinalizacao", "sinal", "trânsito", "placa"],
        "outros": [],
    }

    if incident_type and incident_type in type_map:
        keywords.extend(type_map[incident_type])

    if location:
        parts = re.split(r"[\s,]+", location)
        keywords.extend([p for p in parts if len(p) > 3])

    if description:
        stop_words = {
            "que", "uma", "tem", "está", "para", "com", "mais",
            "num", "nas", "nos", "dos", "das", "por", "como",
            "não", "mas", "ela", "ele", "seu", "sua", "foi"
        }
        words = re.findall(r"\b\w{4,}\b", description.lower())
        keywords.extend([w for w in words if w not in stop_words][:8])

    seen = set()
    unique = []
    for k in keywords:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            unique.append(k)

    return unique[:12]


def _table_exists() -> bool:
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='context_documents'"
            ))
            return result.fetchone() is not None
    except Exception:
        return False


def _count_documents() -> int:
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM context_documents"))
            return result.fetchone()[0]
    except Exception:
        return 0


def _search_db(keywords: list) -> list:
    if not keywords or not _table_exists() or _count_documents() == 0:
        return []

    try:
        conditions = " OR ".join(
            [f"content LIKE :kw{i} OR title LIKE :kw{i}" for i in range(len(keywords))]
        )
        params = {f"kw{i}": f"%{k}%" for i, k in enumerate(keywords)}

        query = text(f"""
            SELECT source, title, content, url, published_at
            FROM context_documents
            WHERE {conditions}
            ORDER BY published_at DESC
            LIMIT {MAX_RESULTS}
        """)

        with engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            results.append({
                "source": row[0] or "news",
                "title": (row[1] or "")[:100],
                "text": (row[2] or "")[:MAX_TEXT_LENGTH],
                "url": row[3],
                "date": (row[4] or "")[:10],
            })

        return results

    except Exception as e:
        logger.warning(f"Erro a pesquisar context_documents | erro={e}")
        return []


def get_relevant_context(
    incident_type: Optional[str],
    description: Optional[str],
    location: Optional[str]
) -> str:
    """
    Devolve uma string com contexto relevante para injetar
    no prompt de priorização, ou string vazia se não encontrar nada.
    """
    keywords = _keywords_from_incident(incident_type, description, location)

    if not keywords:
        return ""

    logger.info(f"Pesquisa de contexto | keywords={keywords[:5]}")

    results = _search_db(keywords)

    if not results:
        logger.info("Pesquisa de contexto | sem resultados relevantes")
        return ""

    logger.info(f"Pesquisa de contexto | {len(results)} resultado(s) encontrado(s)")

    lines = ["Contexto local relevante encontrado em notícias/redes sociais:"]
    for i, r in enumerate(results, 1):
        date_str = f" ({r['date']})" if r["date"] else ""
        title_str = f"{r['title']} — " if r["title"] else ""
        lines.append(
            f"{i}. [{r['source'].upper()}{date_str}] {title_str}{r['text']}"
        )

    return "\n".join(lines)