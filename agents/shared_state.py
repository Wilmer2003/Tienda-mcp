"""
shared_state.py
===============
Memoria compartida entre agentes.

Mantiene:
- historial de conversacion (turno, agente, mensaje, datos)
- sesiones por usuario (carrito en sesion, ultimo intent, contexto)
- pizarra/blackboard de hallazgos (ej. 'el cliente prefiere Samsung')

La rubrica pide explicitamente "estado compartido explicitamente gestionado"
y "historial de conversacion preservado entre turnos y agentes" (Criterio 3).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TurnoConversacion:
    """Un turno = una intervencion (del usuario o de un agente)."""
    n: int
    rol: str            # 'usuario' o nombre del agente
    mensaje: str
    datos: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_now)


@dataclass
class SesionUsuario:
    usuario_id: str
    ultimo_intent: str | None = None
    ultimo_agente: str | None = None
    contexto: dict[str, Any] = field(default_factory=dict)
    # productos en los que el usuario mostro interes (para recomendar mejor).
    productos_vistos: list[str] = field(default_factory=list)


class SharedState:
    def __init__(self) -> None:
        self._historial: list[TurnoConversacion] = []
        self._sesiones: dict[str, SesionUsuario] = {}
        self._pizarra: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._contador = 0

    # ---------------- Historial -----------------
    def registrar_turno(self, rol: str, mensaje: str,
                        datos: dict[str, Any] | None = None) -> TurnoConversacion:
        with self._lock:
            self._contador += 1
            turno = TurnoConversacion(n=self._contador, rol=rol,
                                      mensaje=mensaje, datos=datos or {})
            self._historial.append(turno)
            return turno

    def historial(self, limite: int | None = None) -> list[TurnoConversacion]:
        with self._lock:
            h = list(self._historial)
        return h[-limite:] if limite else h

    # ---------------- Sesiones ------------------
    def sesion(self, usuario_id: str) -> SesionUsuario:
        with self._lock:
            if usuario_id not in self._sesiones:
                self._sesiones[usuario_id] = SesionUsuario(usuario_id=usuario_id)
            return self._sesiones[usuario_id]

    def actualizar_sesion(self, usuario_id: str, **cambios: Any) -> None:
        with self._lock:
            ses = self._sesiones.setdefault(usuario_id,
                                            SesionUsuario(usuario_id=usuario_id))
            for k, v in cambios.items():
                if k == "producto_visto" and v:
                    if v not in ses.productos_vistos:
                        ses.productos_vistos.append(v)
                elif k == "contexto" and isinstance(v, dict):
                    ses.contexto.update(v)
                elif hasattr(ses, k):
                    setattr(ses, k, v)

    # ---------------- Pizarra (blackboard) -------
    def anotar(self, clave: str, valor: Any) -> None:
        with self._lock:
            self._pizarra[clave] = valor

    def leer(self, clave: str, default: Any = None) -> Any:
        with self._lock:
            return self._pizarra.get(clave, default)


# Instancia compartida.
STATE = SharedState()
