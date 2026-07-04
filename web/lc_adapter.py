"""
web/lc_adapter.py
=================
Puente entre FastAPI y el grafo LangGraph.

Reemplaza al Orquestador en web/api.py con el mínimo de cambios posibles.
El resto de api.py (auth, productos, carrito, Niubiz, voucher) NO cambia.

Cómo integrar en api.py:
--------------------------
1. Elimina (o comenta) las líneas:
       from agents.orchestrator import Orquestador
       ORQ = Orquestador(MCP_CLIENT, STATE, BUS)

2. Agrega al inicio de api.py:
       from web.lc_adapter import LC_ADAPTER

3. En el startup de FastAPI (lifespan o @app.on_event("startup")):
       await LC_ADAPTER.init()

4. En el endpoint POST /api/chat, reemplaza:
       resp = await ORQ.atender(req.mensaje, usuario_id=usuario_id)
   por:
       resp = await LC_ADAPTER.atender(req.mensaje, usuario_id=usuario_id)

5. Para el endpoint /api/voucher donde se llama a finanzas directamente,
   reemplaza:
       finanzas = ORQ.equipo["finanzas"]
       resp = await finanzas.confirmar_voucher(...)
   por:
       resp = await LC_ADAPTER.atender(
           f"confirmar voucher del pedido {pedido_id}",
           usuario_id=usuario_id,
       )
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

from langchain_core.messages import HumanMessage

from dataclasses import dataclass


@dataclass
class AgentResponse:
    agente: str
    mensaje: str
    latencia_ms: float
    exito: bool
    tools_invocadas: list[str] = field(default_factory=list)
class _LCAdapter:
    """Wrapper que expone la misma interfaz que Orquestador.atender()
    pero por debajo usa el grafo LangGraph."""

    _graph: Any = field(default=None, init=False)
    _ready: bool = field(default=False, init=False)

    async def init(self) -> None:
        """Llama esto una vez en el startup de FastAPI."""
        from graph.builder import build_graph
        self._graph = build_graph()
        self._ready = True

    async def atender(self, mensaje: str,
                      usuario_id: str = "anonimo") -> AgentResponse:
        if not self._ready:
            raise RuntimeError("LC_ADAPTER no inicializado. Llama await LC_ADAPTER.init() en el startup.")

        t0 = time.perf_counter()
        config = {"configurable": {"thread_id": usuario_id}}

        result = await self._graph.ainvoke(
            {
                "messages": [HumanMessage(content=mensaje)],
                "user_id": usuario_id,
                "session_id": usuario_id
            },
            config=config,
        )

        # El último mensaje del grafo es la respuesta final
        last_msg = result["messages"][-1]
        respuesta_texto = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # Extraer el nombre del agente que respondió
        agente = result.get("current_agent", "agente")
        
        # Extraer tools invocadas en este turno
        tools_invocadas = []
        for msg in result.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tools_invocadas.append(tc.get("name", "unknown_tool"))

        latencia = (time.perf_counter() - t0) * 1000

        return AgentResponse(
            agente=agente,
            mensaje=respuesta_texto,
            latencia_ms=latencia,
            exito=True,
            tools_invocadas=tools_invocadas
        )

    async def get_history(self, usuario_id: str) -> list[dict[str, Any]]:
        if not self._ready:
            return []
            
        config = {"configurable": {"thread_id": usuario_id}}
        state_snapshot = self._graph.get_state(config)
        
        if not state_snapshot or not state_snapshot.values:
            return []
            
        messages = state_snapshot.values.get("messages", [])
        
        out = []
        for m in messages:
            rol = "usuario" if isinstance(m, HumanMessage) else "agente"
            if rol == "agente" and not m.content: 
                # Omitir Tool calls vacios que Llama devuelve
                continue
                
            out.append({
                "rol": rol,
                "mensaje": m.content,
                "timestamp": datetime.now().isoformat() # Aprox
            })
            
        return out

# Instancia global — importar desde api.py
LC_ADAPTER = _LCAdapter()
