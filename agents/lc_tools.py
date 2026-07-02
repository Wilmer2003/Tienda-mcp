"""
agents/lc_tools.py
==================
Carga las tools del MCP server via HTTP (proceso persistente).
El MCP server debe estar corriendo en http://localhost:8001
antes de arrancar el servidor web.
"""
from __future__ import annotations

import os
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient

_CLIENT: MultiServerMCPClient | None = None
_TOOLS: list | None = None


async def get_mcp_tools() -> list:
    global _CLIENT, _TOOLS
    if _TOOLS is not None:
        return _TOOLS
    _CLIENT = MultiServerMCPClient(
        {
            "tienda": {
                "url": "http://localhost:8001/mcp",
                "transport": "streamable_http",
            }
        }
    )
    _TOOLS = await _CLIENT.get_tools()
    return _TOOLS


def split_tools(tools: list) -> dict[str, list]:
    mapping = {
        "catalogo":   {"buscar_productos", "obtener_producto"},
        "inventario": {"verificar_inventario", "consultar_historial_inventario"},
        "ventas":     {"agregar_al_carrito", "ver_carrito", "vaciar_carrito", "crear_pedido"},
        "finanzas":   {"procesar_pago", "consultar_pedido", "consultar_transacciones_niubiz"},
        "soporte":    {"buscar_productos", "consultar_pedido"},
    }
    result = {agent: [] for agent in mapping}
    for tool in tools:
        for agent, names in mapping.items():
            if tool.name in names:
                result[agent].append(tool)
    return result
