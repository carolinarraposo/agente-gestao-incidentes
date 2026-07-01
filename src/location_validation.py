from __future__ import annotations

import re
import unicodedata

from src.database import SessionLocal
from src.models import StreetDB
from src.logger import logger


def normalize_name(name: str) -> str:
    nfd = unicodedata.normalize("NFD", name)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


def _extract_street_candidate(location: str) -> str:
    """Remove sufixos geográficos genéricos para isolar o nome da rua."""
    cleaned = re.sub(
        r"\b(na|em|da|de|do|ao?|junto|perto|pr[oó]ximo)\s+(covilh[aã]|centro|cidade)\b",
        "",
        location,
        flags=re.IGNORECASE
    )
    # Remove sufixo ", Covilhã" ou ", covilha" adicionado pelo LLM
    cleaned = re.sub(r",?\s*covilh[aã]\b", "", cleaned, flags=re.IGNORECASE)
    # Remove número de porta e código postal
    cleaned = re.sub(r"\b\d{4}-\d{3}\b", "", cleaned)
    cleaned = re.sub(r"\bn[oº°]?\s*\d+\b", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ,;")


def validate_location(location: str) -> tuple[str, str | None]:
    """
    Verifica se a rua mencionada existe no dataset do município.

    Retorna:
        ("ok", None)           — rua encontrada sem ambiguidade
        ("ambiguous", pergunta) — rua existe em várias freguesias
        ("not_found", None)    — rua não encontrada (pode ser landmark; não bloquear)
    """
    if not location:
        return ("not_found", None)

    candidate = _extract_street_candidate(location)
    name_norm = normalize_name(candidate)

    if not name_norm:
        return ("not_found", None)

    db = SessionLocal()
    try:
        # Correspondência exata
        streets = db.query(StreetDB).filter(
            StreetDB.name_normalized == name_norm
        ).all()

        # Correspondência parcial se não encontrou exata
        if not streets:
            streets = db.query(StreetDB).filter(
                StreetDB.name_normalized.contains(name_norm)
            ).all()

        if not streets:
            logger.info(f"Rua não encontrada no dataset | nome_norm={name_norm}")
            return ("not_found", None)

        parishes = sorted({s.freguesia for s in streets})

        if len(parishes) == 1:
            logger.info(f"Rua encontrada | nome_norm={name_norm} | freguesia={parishes[0]}")
            return ("ok", None)

        parish_list = ", ".join(parishes)
        logger.info(f"Rua ambígua | nome_norm={name_norm} | freguesias={parish_list}")
        question = (
            f"Encontrei \"{streets[0].name}\" em várias zonas do município "
            f"({parish_list}). "
            f"Pode indicar a zona ou um ponto de referência próximo para localizarmos com precisão?"
        )
        return ("ambiguous", question)

    finally:
        db.close()
