"""
Importa o dataset de ruas da Covilhã para a base de dados do agente.

Uso:
    python import_streets.py
    python import_streets.py --csv caminho/para/streets_covilha.csv
"""
import argparse
import os
import unicodedata

import pandas as pd

from src.database import SessionLocal, create_tables
from src.models import StreetDB
from src.logger import logger


def normalize_name(name: str) -> str:
    nfd = unicodedata.normalize("NFD", name)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "data", "streets_covilha.csv")

def import_streets(csv_path: str = DEFAULT_CSV):
    create_tables()
    df = pd.read_csv(csv_path, sep=';', encoding='utf-8-sig')
    db = SessionLocal()
    db.query(StreetDB).delete()
    objects = []
    for _, row in df.iterrows():
        name = str(row["Nome da rua"]).strip()
        freguesia = str(row["Freguesia"]).strip().title()
        objects.append(StreetDB(
            name=name,
            name_normalized=normalize_name(name),
            freguesia=freguesia,
        ))
    db.bulk_save_objects(objects)
    db.commit()
    db.close()
    logger.info(f"Import concluído: {len(objects)} ruas importadas de {csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Caminho para o CSV de ruas")
    args = parser.parse_args()
    import_streets(args.csv)
