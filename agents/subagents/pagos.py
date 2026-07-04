"""Agente Pagos: cierra el pedido y procesa el pago."""
from __future__ import annotations

from typing import Any

from agents.agent import Agent, AgentResponse
from agents.brain import Decision
from agents.event_bus import EventType


METODOS_VALIDOS = {"tarjeta", "yape", "paypal", "contra_entrega"}


class PagosAgent(Agent):
    def __init__(self, mcp_client, state, bus) -> None:
        super().__init__("finanzas", "finanzas.md", mcp_client, state, bus)

    async def _ejecutar(self, decision: Decision,
                        contexto: dict[str, Any]) -> AgentResponse:
        usuario_id = contexto.get("usuario_id", "anonimo")
        params = decision.parametros

        if decision.intent == "procesar_pago":
            # Si ya hay pedido_id explicito, vamos directo a pagar.
            if params.get("pedido_id") or self.state.leer(f"ultimo_pedido_id_{usuario_id}"):
                params.setdefault("pedido_id",
                                  self.state.leer(f"ultimo_pedido_id_{usuario_id}"))
                return await self._procesar(params, contexto)
            # Si no, primero hay que crear el pedido del carrito actual.
            # (caer al flujo de abajo, encadenando con el metodo si vino)

        # crear_pedido o derivacion natural desde "comprar".
        from tools.store_tools import crear_pedido
        res_crear = crear_pedido.invoke({"usuario_id": usuario_id})
        res = res_crear.model_dump() if hasattr(res_crear, "model_dump") else res_crear
        if isinstance(res, dict) and not res.get("exito", True):
            # Conflicto: el carrito ya no tiene stock (otro agente se lo llevo).
            self.bus.publish(EventType.PEDIDO_RECHAZADO,
                             publicado_por=self.nombre, datos=res)
            return AgentResponse(agente=self.nombre, exito=False,
                                 mensaje=res.get("mensaje", "No se pudo crear pedido."),
                                 datos=res)

        info = res.get("datos", {}) if isinstance(res, dict) else {}
        pedido_id = info.get("pedido_id")
        total = info.get("total", 0)
        # Persistir el pedido_id en la pizarra para encadenar con el pago.
        if pedido_id:
            self.state.anotar(f"ultimo_pedido_id_{usuario_id}", pedido_id)
        self.bus.publish(EventType.PEDIDO_CREADO, publicado_por=self.nombre,
                         datos={"pedido_id": pedido_id, "total": total,
                                "usuario_id": usuario_id})

        metodo = params.get("metodo_pago")
        if not metodo:
            return AgentResponse(
                agente=self.nombre,
                mensaje=(f"Pedido {pedido_id} creado. Total: S/ {total:.2f}. "
                         "Como deseas pagar? (tarjeta / yape / paypal / contra_entrega)"),
                datos={"pedido_id": pedido_id, "total": total,
                       "estado": "pendiente_pago"},
            )

        # Si vino metodo en el mismo turno, encadenamos el pago.
        return await self._procesar({"pedido_id": pedido_id,
                                     "metodo_pago": metodo}, contexto)

    async def _procesar(self, params: dict[str, Any],
                        contexto: dict[str, Any]) -> AgentResponse:
        pedido_id = params.get("pedido_id") or self.state.leer("ultimo_pedido_id")
        metodo = (params.get("metodo_pago") or "").lower().replace(" ", "_")

        if not pedido_id:
            return AgentResponse(agente=self.nombre, exito=False,
                                 mensaje="No tengo un pedido_id para procesar el pago.")
        if metodo not in METODOS_VALIDOS:
            return AgentResponse(
                agente=self.nombre, exito=False,
                mensaje=("Metodo de pago invalido. Acepto: tarjeta, yape, "
                         "paypal, contra_entrega."),
            )

        from tools.store_tools import procesar_pago
        res_pago = procesar_pago.invoke({"pedido_id": pedido_id, "metodo_pago": metodo})
        res = res_pago.model_dump() if hasattr(res_pago, "model_dump") else res_pago
        if isinstance(res, dict) and not res.get("exito", True):
            self.bus.publish(EventType.PAGO_RECHAZADO,
                             publicado_por=self.nombre, datos=res)
            motivo = res.get("mensaje", "Pago rechazado.")
            return AgentResponse(
                agente=self.nombre, exito=False,
                mensaje=(f"PAGO RECHAZADO. Motivo: {motivo} "
                         f"Tu pedido {pedido_id} NO fue procesado. "
                         "Quieres intentar con otro metodo (tarjeta / yape / "
                         "paypal / contra_entrega)?"),
                datos=res,
            )

        # Confirmacion verificada del pago aprobado.
        self.bus.publish(EventType.PAGO_APROBADO,
                         publicado_por=self.nombre,
                         datos={"pedido_id": pedido_id, "metodo": metodo})
        self.bus.publish(EventType.PAGO_PROCESADO,
                         publicado_por=self.nombre,
                         datos={"pedido_id": pedido_id, "metodo": metodo,
                                "exito": True})

        # Mensaje de cierre explicito y verificable.
        info = res.get("datos", {}) if isinstance(res, dict) else {}
        usuario_id = contexto.get("usuario_id", "anonimo")
        # Limpiar foco/sugerencia: el flujo de venta termino.
        self.state.actualizar_sesion(usuario_id, contexto={
            "producto_en_foco": None,
            "candidatos_recientes": [],
            "ultima_sugerencia": None,
            "ultimo_pedido_pagado": pedido_id,
        })
        mensaje_final = (
            f"PAGO APROBADO Y CONFIRMADO. Pedido {pedido_id} procesado via "
            f"{metodo}. Tu compra fue completada correctamente y el inventario "
            f"se actualizo. Gracias por tu compra!"
        )
        return AgentResponse(
            agente=self.nombre,
            mensaje=mensaje_final,
            datos={"pedido_id": pedido_id, "metodo": metodo,
                   "estado": "pagado", "verificado": True},
        )
