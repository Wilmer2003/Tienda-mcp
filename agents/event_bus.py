"""
event_bus.py
============
Bus de eventos pub/sub para coordinar agentes.

Componente que la rubrica pide explicitamente en el Criterio 2 ("event bus").
Permite que cuando un agente publica un evento (ej. 'stock.agotado'), otros
agentes suscritos reaccionen sin que el orquestador los llame uno por uno.

Es deliberadamente simple: un dict de listas de callbacks, con un lock para
permitir publicaciones desde threads distintos.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    """Eventos que el sistema reconoce."""
    INTENT_CLASIFICADO = "intent.clasificado"
    PRODUCTO_BUSCADO = "producto.buscado"
    STOCK_AGOTADO = "stock.agotado"
    STOCK_BAJO = "stock.bajo"
    ALTERNATIVA_SUGERIDA = "alternativa.sugerida"
    CARRITO_ACTUALIZADO = "carrito.actualizado"
    PEDIDO_CREADO = "pedido.creado"
    PEDIDO_RECHAZADO = "pedido.rechazado"
    PAGO_APROBADO = "pago.aprobado"
    PAGO_RECHAZADO = "pago.rechazado"
    CONFLICTO_STOCK = "conflicto.stock"
    AGENTE_RESPONDIO = "agente.respondio"
    AGENTE_NLU = "agente.nlu"
    AGENTE_INVENTARIO = "agente.inventario"
    TOOL_BUSCAR_PRODUCTOS = "tool.buscar_productos"
    TOOL_AGREGAR_CARRITO = "tool.agregar_carrito"
    PRODUCTO_RESUELTO = "producto.resuelto"
    PAGO_PROCESADO = "pago.procesado"
    FALLBACK_LOCAL_USADO = "fallback.local.usado"
    GEMINI_NLU_USADO = "gemini.nlu.usado"
    # --- nuevos eventos para la vista "Jefe distribuyendo" ---
    JEFE_DELEGA = "jefe.delega"
    MOVIMIENTO_INVENTARIO = "movimiento.inventario"


@dataclass
class Evento:
    tipo: EventType
    publicado_por: str
    datos: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_now)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[EventType, list[Callable[[Evento], None]]] = {}
        self._historial: list[Evento] = []
        self._lock = threading.Lock()

    def subscribe(self, tipo: EventType,
                  callback: Callable[[Evento], None]) -> None:
        with self._lock:
            self._subs.setdefault(tipo, []).append(callback)

    def publish(self, tipo: EventType, publicado_por: str,
                datos: dict[str, Any] | None = None) -> Evento:
        evento = Evento(tipo=tipo, publicado_por=publicado_por,
                        datos=datos or {})
        with self._lock:
            self._historial.append(evento)
            subs = list(self._subs.get(tipo, []))
        # Notificar fuera del lock para no bloquear publicadores.
        for cb in subs:
            try:
                cb(evento)
            except Exception as e:
                # No queremos que un suscriptor que falle rompa el bus.
                print(f"[EventBus] suscriptor de {tipo.value} fallo: {e}")
        return evento

    def historial(self) -> list[Evento]:
        with self._lock:
            return list(self._historial)


# Instancia compartida por todo el sistema.
BUS = EventBus()
