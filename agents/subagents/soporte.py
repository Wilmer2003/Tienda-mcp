"""Agente Soporte: consulta pedidos y responde preguntas post-venta."""
from __future__ import annotations

from typing import Any

from agents.agent import Agent, AgentResponse
from agents.brain import Decision


POLITICAS = {
    "devolucion": "Aceptamos devoluciones hasta 30 dias despues de la entrega, "
                  "siempre que el producto este sin uso.",
    "garantia":   "Todos los productos tienen 1 ano de garantia del fabricante.",
    "envio":      "El envio en Lima Metropolitana toma 24-48 horas habiles.",
}


class SoporteAgent(Agent):
    def __init__(self, mcp_client, state, bus) -> None:
        super().__init__("soporte", "soporte.md", mcp_client, state, bus)

    async def _ejecutar(self, decision: Decision,
                        contexto: dict[str, Any]) -> AgentResponse:
        params = decision.parametros

        if decision.intent == "consultar_pedido":
            pedido_id = params.get("pedido_id")
            if not pedido_id:
                return AgentResponse(
                    agente=self.nombre,
                    mensaje="Comparteme tu numero de pedido (formato ORD-XXXX).",
                )
            from tools.store_tools import consultar_pedido
            res_pedido = consultar_pedido.invoke({"pedido_id": pedido_id})
            res = res_pedido.model_dump() if hasattr(res_pedido, "model_dump") else res_pedido
            if isinstance(res, dict) and "exito" in res and not res["exito"]:
                return AgentResponse(agente=self.nombre, exito=False,
                                     mensaje=res.get("mensaje", "No encontrado."),
                                     datos=res)
            return AgentResponse(
                agente=self.nombre,
                mensaje=f"Pedido {res.get('pedido_id')} esta en estado '{res.get('estado')}'. "
                        f"Total: S/ {res.get('total', 0):.2f}.",
                datos=res,
            )

        # intent = soporte (devoluciones, garantia, envio, etc.)
        m = " ".join((decision.parametros.get("query", ""),
                      decision.motivacion)).lower()
        for k, texto in POLITICAS.items():
            if k in m:
                return AgentResponse(agente=self.nombre, mensaje=texto,
                                     datos={"politica": k})
        # Default: politica general
        return AgentResponse(
            agente=self.nombre,
            mensaje=("Estoy para ayudarte. Puedo darte el estado de un pedido "
                     "(ORD-XXXX) o informarte sobre devoluciones, garantia o envios."),
        )
