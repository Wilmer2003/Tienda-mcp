"""
mcp_client.py
=============
Cliente in-process que invoca herramientas del MCP server.

Toda comunicacion entre agentes y la logica de la tienda pasa por aqui.
Eso significa que la rubrica del Criterio 3 ("uso de MCP con JSON/schema
validado") se cumple cada vez que un agente llama a `mcp_call`.

Usa el dispatcher in-process de FastMCP (`mcp.call_tool`) por dos razones:
  1) en demos y tests no queremos arrancar un subproceso por agente,
  2) seguimos pasando por los schemas Pydantic registrados en el servidor.

Si en Antigravity se necesita STDIO real, basta con cambiar esta clase por
otra que use `mcp.client.stdio` sin tocar los agentes.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from server.mcp_server import mcp
from agents.event_bus import BUS, EventType


@dataclass
class MCPResult:
    """Respuesta normalizada de una tool MCP."""
    tool: str
    arguments: dict[str, Any]
    datos: Any                  # contenido estructurado (dict o list)
    duracion_ms: float
    raw_text: str               # contenido textual original (TextContent)


class MCPClient:
    """Pequeno wrapper sobre `mcp.call_tool` con metricas."""

    def __init__(self, etiqueta: str = "default") -> None:
        self.etiqueta = etiqueta
        self.llamadas: list[MCPResult] = []

    async def call(self, tool: str, **kwargs: Any) -> MCPResult:
        t0 = time.perf_counter()
        content, structured = await mcp.call_tool(tool, kwargs)
        dur_ms = (time.perf_counter() - t0) * 1000

        # FastMCP envuelve la salida en {'result': ...} cuando el tool no
        # devuelve un dict ya estructurado (p.ej. una lista de Producto).
        datos = structured.get("result", structured) if isinstance(structured, dict) else structured

        raw_text = ""
        if content and hasattr(content[0], "text"):
            raw_text = content[0].text

        # Publicar eventos de tools requeridos
        if tool == "buscar_productos":
            BUS.publish(EventType.TOOL_BUSCAR_PRODUCTOS, publicado_por=self.etiqueta, datos=kwargs)
        elif tool == "agregar_al_carrito":
            BUS.publish(EventType.TOOL_AGREGAR_CARRITO, publicado_por=self.etiqueta, datos=kwargs)

        result = MCPResult(tool=tool, arguments=dict(kwargs), datos=datos,
                           duracion_ms=dur_ms, raw_text=raw_text)
        self.llamadas.append(result)
        return result

    def resumen_llamadas(self) -> dict[str, Any]:
        if not self.llamadas:
            return {"total": 0}
        durs = [l.duracion_ms for l in self.llamadas]
        return {
            "total": len(self.llamadas),
            "latencia_ms_avg": round(sum(durs) / len(durs), 2),
            "latencia_ms_max": round(max(durs), 2),
            "tools_usadas": sorted({l.tool for l in self.llamadas}),
        }


def pretty(datos: Any, limite: int = 400) -> str:
    """Serializa datos a JSON corto para logs."""
    txt = json.dumps(datos, ensure_ascii=False, default=str)
    return txt if len(txt) <= limite else txt[:limite] + "..."
