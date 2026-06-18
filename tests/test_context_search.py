"""
Testes unitários para o módulo context_search.

Cobre:
1. Extração de keywords a partir do tipo, descrição e localização
2. Pesquisa na BD com documentos reais
3. Comportamento quando não há resultados
4. Formato da string de contexto devolvida
"""

import pytest
from sqlalchemy import text

from src.context_search import (
    _keywords_from_incident,
    _search_db,
    _table_exists,
    get_relevant_context,
    engine,
    SessionLocal,
)


# =========================
# 1. Extração de keywords
# =========================

def test_keywords_tipo_conhecido():
    kws = _keywords_from_incident("iluminacao", None, None)
    assert "iluminação" in kws or "candeeiro" in kws


def test_keywords_inclui_localizacao():
    kws = _keywords_from_incident("lixo", None, "Rua do Rossio")
    assert any(k.lower() in ["rossio", "rua"] for k in kws)


def test_keywords_inclui_descricao():
    kws = _keywords_from_incident(None, "candeeiro avariado junto ao hospital", None)
    assert "candeeiro" in kws or "hospital" in kws or "avariado" in kws


def test_keywords_tipo_desconhecido():
    kws = _keywords_from_incident("tipo_inexistente", None, None)
    assert isinstance(kws, list)


def test_keywords_tudo_none():
    kws = _keywords_from_incident(None, None, None)
    assert isinstance(kws, list)


# =========================
# 2. Pesquisa na BD
# =========================

def test_tabela_existe():
    assert _table_exists() is True


def test_search_db_sem_keywords():
    results = _search_db([])
    assert results == []


def test_search_db_keyword_improvavel():
    results = _search_db(["xyzabc123improvavel"])
    assert results == []


def test_search_db_estacionamento():
    results = _search_db(["estacionamento"])
    assert isinstance(results, list)
    # Se há documentos sobre estacionamento, devem ser devolvidos
    if results:
        for r in results:
            assert "source" in r
            assert "text" in r
            assert "title" in r


def test_search_db_limite_resultados():
    results = _search_db(["Covilhã", "covilha", "município"])
    assert len(results) <= 5


# =========================
# 3. get_relevant_context
# =========================

def test_get_relevant_context_devolve_string():
    result = get_relevant_context("estacionamento", "carro mal estacionado", "Rua do Rossio")
    assert isinstance(result, str)


def test_get_relevant_context_sem_dados():
    result = get_relevant_context(None, None, None)
    assert result == ""


def test_get_relevant_context_com_resultados_tem_formato():
    result = get_relevant_context("estacionamento", "veículo abandonado", "Covilhã")
    if result:
        assert "NEWS" in result.upper() or "REDDIT" in result.upper() or "BLUESKY" in result.upper()


def test_get_relevant_context_keyword_improvavel():
    result = get_relevant_context("outros", "xyzabc123improvavel", "xyzlocalimprovavel")
    assert result == ""
