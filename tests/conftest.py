"""Fixtures comunes para los tests.

Cada test recibe una instancia fresca del MCP cliente, shared_state y bus,
ademas de un orquestador con todo el equipo de subagentes. Aislamos el
estado del catalogo entre tests reinicializando la tienda.
"""
from __future__ import annotations

import itertools

import pytest
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from web.lc_adapter import LC_ADAPTER
from server.store_data import CATALOGO, INVENTARIO_INICIAL
import server.store_logic as store_logic


def _reset_tienda() -> None:
    """Reinicia el estado IN-PLACE sobre la misma instancia TIENDA.

    Necesario porque `server.mcp_server` importo TIENDA al cargar, asi que
    reasignar `store_logic.TIENDA` no actualizaria esa referencia.
    """
    t = store_logic.TIENDA
    t._catalogo = {p.id: p for p in CATALOGO}
    t._inventario = dict(INVENTARIO_INICIAL)
    t._carritos = {}
    t._pedidos = {}
    t._contador_pedidos = itertools.count(1)


@pytest_asyncio.fixture
async def orquestador():
    _reset_tienda()
    await LC_ADAPTER.init()
    yield LC_ADAPTER
