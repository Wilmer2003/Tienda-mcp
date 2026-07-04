"""
agent.py
========
Clase base para todos los agentes del sistema.

Cada agente:
- Tiene un nombre y un system prompt cargado desde `prompts/{nombre}.md`.
- Tiene un Brain (motor de decision, ver brain.py).
- Comparte el MCPClient, el SharedState y el EventBus con el resto del equipo.
- Implementa `_ejecutar(decision, contexto)` que es lo unico que cambia por
  subclase: define que tools MCP llama y como compone su respuesta.

El metodo publico `manejar(mensaje, contexto)` hace 4 cosas:
1) deja que el Brain clasifique el intent,
2) registra el turno en shared_state,
3) delega a `_ejecutar`,
4) mide latencia y devuelve un AgentResponse estructurado.

Asi cada subagente queda corto, focalizado y comparable.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.brain import crear_brain, Decision
from agents.event_bus import EventBus, EventType
from agents.mcp_client import MCPClient, pretty
from agents.shared_state import SharedState


PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class AgentResponse:
    agente: str
    mensaje: str
    datos: dict[str, Any] = field(default_factory=dict)
    tools_invocadas: list[str] = field(default_factory=list)
    eventos_publicados: list[str] = field(default_factory=list)
    latencia_ms: float = 0.0
    exito: bool = True
    intent: str = ""
    siguiente_agente: str | None = None      # ruteo opcional


class Agent(ABC):
    """Clase base de los subagentes especializados."""

    def __init__(self, nombre: str, prompt_file: str,
                 mcp_client: MCPClient,
                 state: SharedState, bus: EventBus) -> None:
        self.nombre = nombre
        prompt_mapping = {
            "consultas": "catalogo_prompt",
            "inventarios": "inventario_prompt",
            "finanzas": "pagos_prompt",
            "soporte": "soporte_prompt",
            "ventas": "ventas_prompt"
        }
        mod_name = f"prompts.{prompt_mapping.get(self.nombre, self.nombre + '_prompt')}"
        import importlib
        try:
            mod = importlib.import_module(mod_name)
            self.system_prompt = mod.SYSTEM_PROMPT
        except ImportError:
            prompt_path = PROMPTS_DIR / prompt_file
            if not prompt_path.exists():
                raise FileNotFoundError(f"Falta el prompt {prompt_path} ni modulo {mod_name}")
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        self.brain = crear_brain(self.system_prompt, nombre)
        self.mcp = mcp_client
        self.state = state
        self.bus = bus

    async def manejar(self, mensaje: str,
                      contexto: dict[str, Any]) -> AgentResponse:
        t0 = time.perf_counter()
        # 1) Decision del brain.
        decision = self.brain.decidir(mensaje, contexto)
        # 1.b) Fusionar parametros ya resueltos por el Orquestador (Gemini
        #      NLU o `extraer_producto_de_texto`). Los del contexto tienen
        #      prioridad porque el Orquestador tiene mas informacion (catalogo,
        #      historial de sesion) que el brain local del subagente.
        ctx_params = contexto.get("parametros") or {}
        if ctx_params:
            merged = dict(decision.parametros)
            for k, v in ctx_params.items():
                if v not in (None, "", 0):
                    merged[k] = v
            decision.parametros = merged
        # El intent del orquestador SIEMPRE manda sobre el del brain local
        # del subagente: el orquestador tiene contexto conversacional (foco,
        # historial) que el brain del subagente no ve.
        ctx_intent = contexto.get("intent")
        if ctx_intent:
            decision.intent = ctx_intent
        # 2) Registrar en shared_state.
        self.state.registrar_turno(
            rol=self.nombre, mensaje=f"[recibe] {mensaje}",
            datos={"intent": decision.intent,
                   "parametros": decision.parametros}
        )
        # 3) Delegar a la subclase. La subclase decide `exito`; si lanza
        #    excepcion, marcamos exito=False.
        tools_antes = len(self.mcp.llamadas)
        try:
            resp = await self._ejecutar(decision, contexto)
        except Exception as e:
            resp = AgentResponse(agente=self.nombre,
                                 mensaje=f"Error en {self.nombre}: {e}",
                                 exito=False)
        # 4) Completar metricas y registrar.
        resp.intent = decision.intent
        resp.tools_invocadas = [
            l.tool for l in self.mcp.llamadas[tools_antes:]
        ]
        resp.latencia_ms = (time.perf_counter() - t0) * 1000
        self.state.registrar_turno(
            rol=self.nombre, mensaje=f"[responde] {resp.mensaje}",
            datos={"datos": resp.datos, "tools": resp.tools_invocadas}
        )
        self.bus.publish(EventType.AGENTE_RESPONDIO,
                         publicado_por=self.nombre,
                         datos={"intent": resp.intent,
                                "mensaje": resp.mensaje,
                                "exito": resp.exito})
        return resp

    @abstractmethod
    async def _ejecutar(self, decision: Decision,
                        contexto: dict[str, Any]) -> AgentResponse: ...

    # Utilidad usada por varios subagentes para describir productos.
    @staticmethod
    def _descripcion_corta(p: dict) -> str:
        return (f"{p['id']} {p['nombre']} ({p['marca']}) — "
                f"S/ {p['precio']:.0f}, rating {p['rating']}")

    def __repr__(self) -> str:
        return f"<Agent {self.nombre}>"
