"""
orchestrator.py
===============
Agente Orquestador.

Es el unico punto de entrada desde el usuario. Su responsabilidad es:
  1) recibir el mensaje del usuario,
  2) clasificar el intent y elegir el subagente principal,
  3) ejecutar el subagente,
  4) reaccionar a eventos relevantes (stock.agotado, conflicto.stock),
  5) consolidar la respuesta final y devolverla.

No invoca tools MCP directamente: todo el trabajo lo hacen los subagentes.
Eso mantiene los roles sin solapamiento (Criterio 1 de la rubrica).
"""
from __future__ import annotations

import time
from typing import Any

from agents.agent import Agent, AgentResponse
from agents.brain import (
    Decision, _detectar_intent, _extraer_producto_id, _extraer_pedido_id,
    _extraer_categoria, _extraer_precio_max, _extraer_metodo_pago,
    _extraer_query, _extraer_cantidad, _normalizar
)
from agents.event_bus import EventBus, EventType
from agents.mcp_client import MCPClient
from agents.shared_state import SharedState
from agents.subagents import (
    CatalogoAgent, InventarioAgent, VentasAgent, PagosAgent, SoporteAgent,
)
from server.store_logic import TIENDA
from agents.gemini_nlu import interpretar_intencion
from agents.context_resolver import (
    inferir_intent_seguimiento, detectar_seguimiento, resolver_referencia,
)


import re

def resolver_producto_id(val: str | None) -> str | None:
    if not val:
        return None
    val_upper = val.upper().strip()
    
    # Si ya es un ID
    if val_upper in TIENDA._catalogo:
        return val_upper
        
    # Buscar por nombre o marca
    for pid, p in TIENDA._catalogo.items():
        if val_upper in p.nombre.upper() or p.nombre.upper() in val_upper:
            return pid
        if val_upper in p.marca.upper():
            return pid
            
    # Intentar con regex P\d{3}
    match = re.search(r'\bP\d{3}\b', val_upper)
    if match:
        pid = match.group(0)
        if pid in TIENDA._catalogo:
            return pid
            
    return None


def extraer_producto_de_texto(mensaje: str) -> str | None:
    m = _normalizar(mensaje)
    
    # 1. Buscar si hay un ID directo (P001, etc.)
    if pid := _extraer_producto_id(mensaje):
        return pid
        
    # 2. Buscar por nombre completo/específico del producto
    for pid, p in sorted(TIENDA._catalogo.items(), key=lambda x: len(x[1].nombre), reverse=True):
        nom_norm = _normalizar(p.nombre)
        if nom_norm in m:
            return pid
            
    # 3. Buscar por tokens significativos del nombre (catalogo de ropa).
    keywords_especificas = {
        "P001": ["polo basico", "polo blanco", "solenne essentials", "basico"],
        "P002": ["polo premium", "polo negro", "pima"],
        "P003": ["jeans slim", "jeans azul", "denim lab", "denim"],
        "P004": ["pantalon chino", "chino beige", "urban co"],
        "P005": ["vestido floral", "floral verano", "bloom"],
        "P006": ["vestido negro", "noir studio", "noir"],
        "P007": ["zapatillas urban", "urban sneakers", "sneakers"],
        "P008": ["mocasines", "lazaro", "marron"],
        "P009": ["chaqueta cuero", "chaqueta negra", "moto lab", "biker"],
        "P010": ["abrigo lana", "abrigo beige", "soft wool abrigo"],
        "P011": ["cinturon", "cuir", "trenzado"],
        "P012": ["bufanda", "lana suave", "merino"],
    }
    for pid, kws in keywords_especificas.items():
        for kw in kws:
            if _normalizar(kw) in m:
                return pid
                
    return None


# Mapeo intent -> subagente principal.
# El Jefe usa esta tabla para distribuir el trabajo. Cada delegacion se
# publica en el event bus como JEFE_DELEGA para que el panel del front
# muestre el flujo en vivo.
INTENT_AGENTE = {
    "buscar_producto":     "consultas",
    "ver_detalle":         "consultas",
    "verificar_stock":     "inventarios",
    "ver_historial_stock": "inventarios",
    "agregar_carrito":     "ventas",
    "ver_carrito":         "ventas",
    "vaciar_carrito":      "ventas",
    "confirmar_compra":    "ventas",      # ventas cierra la orden
    "crear_pedido":        "ventas",      # ventas crea el pedido y luego deriva a finanzas
    "procesar_pago":       "finanzas",
    "consultar_pedido":    "soporte",
    "soporte":             "consultas",  # consultas ahora cubre soporte tambien
}


class Orquestador(Agent):
    def __init__(self, mcp_client: MCPClient,
                 state: SharedState, bus: EventBus) -> None:
        super().__init__("jefe", "jefe.md", mcp_client, state, bus)
        # Equipo de subagentes (grafo). Las claves son los nombres de rol que
        # ve el cliente: jefe -> consultas / inventarios / ventas / finanzas.
        self.equipo = {
            "consultas":   CatalogoAgent(mcp_client, state, bus),
            "inventarios": InventarioAgent(mcp_client, state, bus),
            "ventas":      VentasAgent(mcp_client, state, bus),
            "finanzas":    PagosAgent(mcp_client, state, bus),
            "soporte":     SoporteAgent(mcp_client, state, bus),
        }
        # El orquestador escucha conflictos para post-procesar la respuesta.
        bus.subscribe(EventType.CONFLICTO_STOCK, self._on_conflicto)
        bus.subscribe(EventType.STOCK_AGOTADO, self._on_stock_agotado)
        self._eventos_recientes: list[tuple[EventType, dict[str, Any]]] = []

    # Punto de entrada principal del usuario.
    async def atender(self, mensaje_usuario: str,
                      usuario_id: str = "anonimo") -> AgentResponse:
        t0 = time.perf_counter()
        # Reiniciamos buffer de eventos recientes por turno.
        self._eventos_recientes.clear()

        # Registrar lo que dijo el usuario.
        self.state.registrar_turno(rol="usuario", mensaje=mensaje_usuario,
                                   datos={"usuario_id": usuario_id})

        # 0) Resolucion de contexto conversacional (sin LLM).
        # Si el mensaje es seguimiento ("agregala", "es la unica?", "si"),
        # inferimos intent+params usando producto_en_foco/candidatos_recientes
        # de la sesion. Asi evitamos perder el hilo entre turnos.
        sesion = self.state.sesion(usuario_id)
        seguimiento = inferir_intent_seguimiento(mensaje_usuario, sesion)
        if seguimiento is not None:
            intent, parametros = seguimiento
            nlu_usado = "contexto"
            conf = 0.95
            self.bus.publish(EventType.INTENT_CLASIFICADO,
                             publicado_por=self.nombre,
                             datos={"intent": intent, "confianza": conf,
                                    "mensaje": mensaje_usuario,
                                    "fuente": "contexto_conversacional"})
            self.bus.publish(EventType.AGENTE_NLU,
                             publicado_por=self.nombre,
                             datos={"intent": intent,
                                    "nlu_usado": nlu_usado,
                                    "variables": parametros})
            self.state.actualizar_sesion(usuario_id, ultimo_intent=intent)
            agente_nombre = INTENT_AGENTE.get(intent, "consultas")
            # El Jefe delega trabajo a un subagente concreto.
            self.bus.publish(EventType.JEFE_DELEGA,
                             publicado_por=self.nombre,
                             datos={"delega_a": agente_nombre,
                                    "intent": intent,
                                    "mensaje": mensaje_usuario,
                                    "via": "contexto_conversacional"})
            subagente = self.equipo[agente_nombre]
            contexto = {"usuario_id": usuario_id, "intent": intent,
                        "nlu_usado": nlu_usado, "parametros": parametros}
            resp = await subagente.manejar(mensaje_usuario, contexto)
            self.state.actualizar_sesion(usuario_id, ultimo_agente=agente_nombre)
            await self._consolidar(resp, usuario_id)
            resp.latencia_ms = (time.perf_counter() - t0) * 1000
            return resp

        # 1) Intentar clasificar e interpretar con Gemini NLU
        nlu_res = await interpretar_intencion(mensaje_usuario)
        nlu_usado = "gemini" if nlu_res is not None else "reglas"

        if nlu_res is not None:
            # Publicar evento gemini.nlu.usado
            self.bus.publish(EventType.GEMINI_NLU_USADO,
                             publicado_por=self.nombre,
                             datos={"mensaje": mensaje_usuario})

            # Mapeo de intención de Gemini NLU a backend
            gemini_intent = nlu_res.get("intent")
            if gemini_intent == "buscar_producto":
                # Ver si es stock
                mn = " " + _normalizar(mensaje_usuario) + " "
                if any(f" {k} " in mn for k in ["stock", "disponible", "disponibilidad", "quedan", "cuantos hay"]):
                    intent = "verificar_stock"
                else:
                    intent = "buscar_producto"
            elif gemini_intent == "pagar":
                intent = "procesar_pago"
            elif gemini_intent == "fallback":
                intent = "desconocido"
            else:
                intent = gemini_intent

            # Mapear y poblar parámetros
            parametros = {}
            producto_val = nlu_res.get("producto")
            pid = None
            if producto_val:
                pid = resolver_producto_id(producto_val)
                if pid:
                    parametros["producto_id"] = pid
                    self.bus.publish(EventType.PRODUCTO_RESUELTO,
                                     publicado_por=self.nombre,
                                     datos={"producto_id": pid, "fuente": "gemini", "original": producto_val})
                else:
                    parametros["query"] = producto_val
                    # Intentar regex si no resolvimos
                    match = re.search(r'\bP\d{3}\b', producto_val.upper())
                    if match:
                        pid = match.group(0)
                        parametros["producto_id"] = pid
                        self.bus.publish(EventType.PRODUCTO_RESUELTO,
                                         publicado_por=self.nombre,
                                         datos={"producto_id": pid, "fuente": "gemini_regex", "original": producto_val})

            # Si no hay producto_id en params pero está en la frase original y no se resolvió
            if "producto_id" not in parametros:
                if pid_regex := _extraer_producto_id(mensaje_usuario):
                    parametros["producto_id"] = pid_regex
                    self.bus.publish(EventType.PRODUCTO_RESUELTO,
                                     publicado_por=self.nombre,
                                     datos={"producto_id": pid_regex, "fuente": "original_regex"})

            # Categoría
            if nlu_res.get("categoria"):
                parametros["categoria"] = nlu_res.get("categoria")

            # Precio max
            if nlu_res.get("precio_max"):
                try:
                    parametros["precio_max"] = float(nlu_res.get("precio_max"))
                except (ValueError, TypeError):
                    pass

            # Método de pago
            if nlu_res.get("metodo_pago"):
                parametros["metodo_pago"] = nlu_res.get("metodo_pago")

            # Cantidad
            if nlu_res.get("cantidad"):
                try:
                    parametros["cantidad"] = int(nlu_res.get("cantidad"))
                except (ValueError, TypeError):
                    parametros["cantidad"] = 1
            else:
                parametros["cantidad"] = 1

            # Pedido ID por regex de la frase
            if ped_regex := _extraer_pedido_id(mensaje_usuario):
                parametros["pedido_id"] = ped_regex

            # Para buscar_producto
            if intent == "buscar_producto" and "query" not in parametros:
                parametros["query"] = nlu_res.get("producto") or _extraer_query(mensaje_usuario)

            conf = 1.0
        else:
            # NLU basado en reglas (Fallback)
            self.bus.publish(EventType.FALLBACK_LOCAL_USADO,
                             publicado_por=self.nombre,
                             datos={"mensaje": mensaje_usuario})

            intent, conf = _detectar_intent(mensaje_usuario)
            
            # Ajuste dinámico de intención para frases naturales implícitas de búsqueda
            m_norm = _normalizar(mensaje_usuario)
            if intent == "desconocido":
                if any(x in m_norm for x in [
                    "quiero", "buscame", "polo", "camiseta", "jeans",
                    "pantalon", "chino", "vestido", "zapatilla", "zapato",
                    "mocasin", "sneakers", "chaqueta", "abrigo", "casaca",
                    "blazer", "cinturon", "bufanda", "accesorio",
                ]):
                    intent = "buscar_producto"
                    conf = 0.8

            parametros = {}
            
            # Resolución robusta de productos mediante catálogo
            pid = extraer_producto_de_texto(mensaje_usuario)
            if pid:
                parametros["producto_id"] = pid
                self.bus.publish(EventType.PRODUCTO_RESUELTO,
                                 publicado_por=self.nombre,
                                 datos={"producto_id": pid, "fuente": "reglas"})

            if ped := _extraer_pedido_id(mensaje_usuario):
                parametros["pedido_id"] = ped
            if cat := _extraer_categoria(mensaje_usuario):
                parametros["categoria"] = cat
            if pmax := _extraer_precio_max(mensaje_usuario):
                parametros["precio_max"] = pmax
            if mp := _extraer_metodo_pago(mensaje_usuario):
                parametros["metodo_pago"] = mp
            if intent in ("buscar_producto",):
                parametros["query"] = _extraer_query(mensaje_usuario)
            if intent == "agregar_carrito":
                parametros["cantidad"] = _extraer_cantidad(mensaje_usuario)

        # Publicar intent clasificado
        self.bus.publish(EventType.INTENT_CLASIFICADO,
                         publicado_por=self.nombre,
                         datos={"intent": intent, "confianza": conf,
                                "mensaje": mensaje_usuario})

        # Publicar agente.nlu
        self.bus.publish(EventType.AGENTE_NLU,
                         publicado_por=self.nombre,
                         datos={"intent": intent, "nlu_usado": nlu_usado, "variables": parametros})

        self.state.actualizar_sesion(usuario_id, ultimo_intent=intent)

        # 2) Elegir subagente o pedir reformular.
        agente_nombre = INTENT_AGENTE.get(intent)
        if not agente_nombre:
            if intent == "saludar":
                resp = AgentResponse(
                    agente=self.nombre, intent=intent,
                    mensaje=("¡Hola! Bienvenida a Tienda Solenne. Soy Solenne, tu asesora personal de moda. ¿Qué te gustaría encontrar hoy? Te recuerdo que tenemos descuentos y cupones exclusivos como SOLENNE10 para ti."),
                    exito=True,
                )
            else:
                resp = AgentResponse(
                    agente=self.nombre, intent=intent,
                    mensaje=("No estoy seguro de que necesitas. Puedo buscar "
                             "productos, ver tu carrito, procesar un pago o "
                             "consultar un pedido. Como te ayudo?"),
                    exito=True,
                )
            resp.latencia_ms = (time.perf_counter() - t0) * 1000
            self.state.actualizar_sesion(usuario_id, ultimo_agente=self.nombre)
            return resp

        # 3) Delegar al subagente con el contexto del usuario.
        self.bus.publish(EventType.JEFE_DELEGA,
                         publicado_por=self.nombre,
                         datos={"delega_a": agente_nombre,
                                "intent": intent,
                                "mensaje": mensaje_usuario,
                                "via": nlu_usado})
        subagente = self.equipo[agente_nombre]
        contexto = {
            "usuario_id": usuario_id,
            "intent": intent,
            "nlu_usado": nlu_usado,
            "parametros": parametros
        }
        resp = await subagente.manejar(mensaje_usuario, contexto)
        self.state.actualizar_sesion(usuario_id, ultimo_agente=agente_nombre)

        # 4) Post-procesar segun eventos generados durante este turno.
        await self._consolidar(resp, usuario_id)
        resp.latencia_ms = (time.perf_counter() - t0) * 1000
        return resp

    # Agent.manejar abstracto: cuando alguien invoca al orquestador como
    # subagente (no es el caso), reusamos `atender` con un contexto vacio.
    async def _ejecutar(self, decision: Decision,
                        contexto: dict[str, Any]) -> AgentResponse:
        return AgentResponse(agente=self.nombre,
                             mensaje="El orquestador no se invoca como subagente.")

    # Callbacks de eventos: capturamos para enriquecer la respuesta final.
    def _on_conflicto(self, evento) -> None:
        self._eventos_recientes.append((EventType.CONFLICTO_STOCK, evento.datos))

    def _on_stock_agotado(self, evento) -> None:
        self._eventos_recientes.append((EventType.STOCK_AGOTADO, evento.datos))

    async def _consolidar(self, resp: AgentResponse, usuario_id: str) -> None:
        """Agrega alternativas/avisos a la respuesta segun eventos del turno."""
        for tipo, datos in self._eventos_recientes:
            pid = datos.get("producto_id")
            if not pid:
                continue
            alternativas = self.state.leer(f"alternativas_para_{pid}")
            if alternativas:
                lineas = [f"  - {a['id']} {a['nombre']} (S/ {a['precio']:.0f}, "
                          f"rating {a['rating']})" for a in alternativas]
                aviso = (f"\n\nNota: {pid} esta agotado o sin stock suficiente. "
                         f"Te sugiero estas alternativas:\n" + "\n".join(lineas))
                resp.mensaje += aviso
                resp.datos["alternativas"] = alternativas
                resp.siguiente_agente = "ventas"
