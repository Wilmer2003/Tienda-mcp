"""Agente Ventas: maneja el carrito del usuario."""
from __future__ import annotations

from typing import Any

from agents.agent import Agent, AgentResponse
from agents.brain import Decision
from agents.event_bus import EventType


class VentasAgent(Agent):
    def __init__(self, mcp_client, state, bus) -> None:
        super().__init__("ventas", "ventas.md", mcp_client, state, bus)

    async def _ejecutar(self, decision: Decision,
                        contexto: dict[str, Any]) -> AgentResponse:
        params = decision.parametros
        usuario_id = contexto.get("usuario_id", "anonimo")

        if decision.intent == "vaciar_carrito":
            from tools.store_tools import vaciar_carrito
            res_vaciar = vaciar_carrito.invoke({"usuario_id": usuario_id})
            r_datos = res_vaciar.model_dump() if hasattr(res_vaciar, "model_dump") else res_vaciar
            return AgentResponse(agente=self.nombre,
                                 mensaje=r_datos.get("mensaje", "Carrito vaciado."),
                                 datos=r_datos)

        if decision.intent == "ver_carrito":
            from tools.store_tools import ver_carrito
            res_ver = ver_carrito.invoke({"usuario_id": usuario_id})
            r_datos = res_ver.model_dump() if hasattr(res_ver, "model_dump") else res_ver
            return self._resumir_carrito(r_datos)

        # --- CIERRE DE ORDEN ---
        # Cuando el cliente quiere comprar/finalizar/cerrar, Ventas:
        #   1) muestra el resumen final del carrito
        #   2) pide confirmacion EXPLICITA ("¿confirmas?")
        #   3) anota una "ultima_sugerencia" = derivar a finanzas
        if decision.intent == "crear_pedido":
            from tools.store_tools import ver_carrito
            res_ver = ver_carrito.invoke({"usuario_id": usuario_id})
            carrito = res_ver.model_dump() if hasattr(res_ver, "model_dump") else res_ver
            items = carrito.get("items", [])
            if not items:
                return AgentResponse(agente=self.nombre, exito=False,
                                     mensaje="Tu carrito está vacío. Te ayudo a buscar algo?")
            lineas = [f"  {i['cantidad']} x {i['nombre']} = S/ {i['subtotal']:.2f}"
                      for i in items]
            total = carrito.get("total", 0)
            # Anotamos la sugerencia: si el cliente confirma, vamos a finanzas.
            self.state.actualizar_sesion(usuario_id, contexto={
                "ultima_sugerencia": {
                    "intent": "procesar_pago",
                    "params": {},
                },
            })
            mensaje = (
                "Perfecto, estos son los items de tu compra:\n"
                + "\n".join(lineas)
                + f"\n\nTotal a pagar: S/ {total:.2f}"
                + "\n\n¿Confirmas la compra? (responde 'si' para continuar "
                "al pago, o 'no' si quieres ajustar algo)"
            )
            return AgentResponse(agente=self.nombre, mensaje=mensaje,
                                 datos={"resumen_compra": carrito,
                                        "espera_confirmacion": True})

        if decision.intent == "confirmar_compra":
            # El cliente confirmo: derivamos al agente Finanzas para crear
            # el pedido. El Jefe captara `siguiente_agente` y lo invocara.
            from tools.store_tools import ver_carrito
            res_ver = ver_carrito.invoke({"usuario_id": usuario_id})
            ver_datos = res_ver.model_dump() if hasattr(res_ver, "model_dump") else res_ver
            if not ver_datos.get("items"):
                return AgentResponse(agente=self.nombre, exito=False,
                                     mensaje="Tu carrito está vacío.")
            return AgentResponse(
                agente=self.nombre,
                mensaje="Orden confirmada. Te paso con el agente de Finanzas "
                        "para procesar el pago. ¿Como deseas pagar? "
                        "(tarjeta / yape / plin / paypal / contra_entrega)",
                datos={"orden_confirmada": True},
                siguiente_agente="finanzas",
            )

        if decision.intent == "agregar_carrito":
            pid = params.get("producto_id")
            # Si no vino, intentar leer del foco de la sesion (producto recien
            # recomendado por Catalogo o consultado por Inventario).
            if not pid:
                sesion = self.state.sesion(usuario_id)
                pid = sesion.contexto.get("producto_en_foco")
            cant = int(params.get("cantidad", 1))
            if not pid:
                return AgentResponse(
                    agente=self.nombre, exito=False,
                    mensaje="No tengo claro que producto agregar. Dime el ID "
                            "(ej. P003) o el nombre.",
                )
            from tools.store_tools import agregar_al_carrito, ver_carrito
            res_agregar = agregar_al_carrito.invoke({
                "usuario_id": usuario_id,
                "producto_id": pid,
                "cantidad": cant
            })
            res = res_agregar.model_dump() if hasattr(res_agregar, "model_dump") else res_agregar
            if isinstance(res, dict) and not res.get("exito", True):
                # Stock insuficiente o producto inexistente.
                info = res.get("datos", {})
                disponible = info.get("disponible")
                if disponible == 0:
                    # Agotado: publicamos STOCK_AGOTADO para que catalogo
                    # proponga alternativas via su suscriptor.
                    self.bus.publish(EventType.STOCK_AGOTADO,
                                     publicado_por=self.nombre,
                                     datos={"producto_id": pid,
                                            "categoria": info.get("categoria", "")})
                elif disponible is not None:
                    # Disponible > 0 pero menos que lo pedido: conflicto.
                    self.bus.publish(EventType.CONFLICTO_STOCK,
                                     publicado_por=self.nombre,
                                     datos={"producto_id": pid,
                                            "disponible": disponible,
                                            "categoria": info.get("categoria", "")})
                return AgentResponse(agente=self.nombre, exito=False,
                                     mensaje=res.get("mensaje", "No se pudo agregar."),
                                     datos=res)

            # Actualizar sesion del usuario.
            self.state.actualizar_sesion(usuario_id, producto_visto=pid)
            self.bus.publish(EventType.CARRITO_ACTUALIZADO,
                             publicado_por=self.nombre,
                             datos={"usuario_id": usuario_id, "producto_id": pid,
                                    "cantidad": cant})
            # Mostrar carrito actual y, si solo hay 1 laptop, sugerir accesorio.
            res_ver = ver_carrito.invoke({"usuario_id": usuario_id})
            ver_datos = res_ver.model_dump() if hasattr(res_ver, "model_dump") else res_ver
            resp = self._resumir_carrito(ver_datos)
            resp.mensaje = res.get("mensaje", "") + "\n" + resp.mensaje
            self._maybe_upsell(ver_datos, resp, usuario_id=usuario_id)
            return resp

        return AgentResponse(
            agente=self.nombre, exito=False,
            mensaje="No entendi que quieres hacer con el carrito. "
                    "Puedo agregar, ver o vaciar.",
        )

    def _resumir_carrito(self, carrito: dict) -> AgentResponse:
        items = carrito.get("items", [])
        if not items:
            return AgentResponse(agente=self.nombre,
                                 mensaje="Tu carrito esta vacio.",
                                 datos=carrito)
        lineas = [f"{i['cantidad']} x {i['nombre']} = S/ {i['subtotal']:.2f}"
                  for i in items]
        return AgentResponse(
            agente=self.nombre,
            mensaje=("Carrito:\n  " + "\n  ".join(lineas)
                     + f"\nTotal: S/ {carrito.get('total', 0):.2f}"),
            datos=carrito,
        )

    def _maybe_upsell(self, carrito: dict, resp: AgentResponse,
                       usuario_id: str = "") -> None:
        items = carrito.get("items", [])
        if len(items) != 1:
            return
        nombre = items[0]["nombre"].lower()
        # Reglas de "look completo" para boutique de ropa.
        if "jeans" in nombre or "pantalon" in nombre or "chino" in nombre:
            sugerido = ("P011", "un cinturon de cuero (P011)",
                        "complementa tu pantalon")
        elif "vestido" in nombre:
            sugerido = ("P012", "una bufanda de lana suave (P012)",
                        "completa tu look")
        elif "polo" in nombre or "camiseta" in nombre:
            sugerido = ("P003", "unos jeans slim fit (P003)",
                        "se ve increible con ese polo")
        elif "chaqueta" in nombre or "abrigo" in nombre:
            sugerido = ("P012", "una bufanda de lana (P012)",
                        "para el frio")
        else:
            return
        pid_s, descr, motivo = sugerido
        resp.mensaje += (f"\nSugerencia: {descr} {motivo}. Lo agrego?")
        resp.datos["upsell"] = pid_s
        if usuario_id:
            self.state.actualizar_sesion(usuario_id, contexto={
                "ultima_sugerencia": {
                    "intent": "agregar_carrito",
                    "params": {"producto_id": pid_s, "cantidad": 1},
                },
                "producto_en_foco": pid_s,
            })
