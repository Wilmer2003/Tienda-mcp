"""Agente Inventario: verifica stock y publica eventos."""
from __future__ import annotations

from typing import Any

from agents.agent import Agent, AgentResponse
from agents.brain import Decision
from agents.event_bus import EventType


class InventarioAgent(Agent):
    def __init__(self, mcp_client, state, bus) -> None:
        super().__init__("inventarios", "inventarios.md", mcp_client, state, bus)

    async def _ejecutar(self, decision: Decision,
                        contexto: dict[str, Any]) -> AgentResponse:
        params = decision.parametros
        usuario_id = contexto.get("usuario_id", "anonimo")

        # --- Historial de movimientos ---
        if decision.intent == "ver_historial_stock":
            pid_param = params.get("producto_id") or ""
            r = await self.mcp.call("consultar_historial_inventario",
                                    producto_id=pid_param, limite=20)
            datos = r.datos.get("datos", {}) if isinstance(r.datos, dict) else {}
            movs = datos.get("movimientos", [])
            if not movs:
                return AgentResponse(agente=self.nombre,
                                     mensaje="No hay movimientos registrados aun.",
                                     datos={"movimientos": []})
            lineas = []
            for m in movs[-10:]:  # ultimos 10
                ts = m["timestamp"][11:19]  # solo HH:MM:SS
                signo = "+" if m["delta"] > 0 else ("" if m["delta"] == 0 else "")
                delta = f"{signo}{m['delta']}" if m["delta"] != 0 else "reserva"
                lineas.append(f"  {ts}  {m['producto_id']}  {delta:>8}  "
                              f"{m['motivo']}  (stock={m['stock_resultante']})")
            cab = f"Historial de inventario" + (f" para {pid_param}" if pid_param else "")
            return AgentResponse(
                agente=self.nombre,
                mensaje=cab + ":\n" + "\n".join(lineas),
                datos={"movimientos": movs[-10:]},
            )

        # --- Verificacion de stock ---
        pid = params.get("producto_id")
        # Heredar el foco si no vino producto_id.
        if not pid:
            sesion = self.state.sesion(usuario_id)
            pid = sesion.contexto.get("producto_en_foco")
        if not pid:
            return AgentResponse(
                agente=self.nombre, exito=False,
                mensaje="Necesito un producto_id (ej. P003) para verificar stock.",
            )
        # Dejar el producto consultado como foco del proximo turno.
        self.state.actualizar_sesion(usuario_id,
                                     contexto={"producto_en_foco": pid})

        r = await self.mcp.call("verificar_inventario", producto_id=pid)
        datos = r.datos

        # ResultadoOperacion: tiene exito, mensaje, datos.
        if isinstance(datos, dict) and not datos.get("exito", True):
            return AgentResponse(agente=self.nombre, exito=False,
                                 mensaje=datos.get("mensaje", "No encontrado."),
                                 datos=datos)

        info = datos.get("datos", {}) if isinstance(datos, dict) else {}
        stock = info.get("stock", 0)
        categoria = info.get("categoria", "")
        agotado = info.get("agotado", stock == 0)

        # Publicar el evento de agente.inventario
        self.bus.publish(EventType.AGENTE_INVENTARIO,
                         publicado_por=self.nombre,
                         datos={"producto_id": pid, "stock": stock})

        eventos_pub: list[str] = []
        if agotado:
            self.bus.publish(EventType.STOCK_AGOTADO,
                             publicado_por=self.nombre,
                             datos={"producto_id": pid,
                                    "categoria": categoria})
            eventos_pub.append(EventType.STOCK_AGOTADO.value)
            riesgo = "agotado"
        elif stock <= 1:
            self.bus.publish(EventType.STOCK_BAJO,
                             publicado_por=self.nombre,
                             datos={"producto_id": pid, "stock": stock})
            eventos_pub.append(EventType.STOCK_BAJO.value)
            riesgo = "bajo"
        else:
            riesgo = "normal"

        resp = AgentResponse(
            agente=self.nombre,
            mensaje=datos.get("mensaje", f"{pid} stock={stock}"),
            datos={"producto_id": pid, "stock": stock,
                   "riesgo": riesgo, "categoria": categoria},
            eventos_publicados=eventos_pub,
        )
        return resp
