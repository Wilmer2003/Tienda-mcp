"""Paquete del sistema multi-agente de la tienda virtual.

Contiene:
- shared_state.py  : memoria compartida (historial, sesiones).
- event_bus.py     : bus de eventos pub/sub para coordinar agentes.
- mcp_client.py    : cliente in-process que invoca tools del MCP.
- brain.py         : motor de decision (reglas o Claude SDK si hay API key).
- agent.py         : clase base Agente.
- orchestrator.py  : agente Orquestador (router central).
- subagents/       : Catalogo, Inventario, Ventas, Pagos, Soporte.
- prompts/         : system prompts especializados por agente.
- metrics.py       : registro de latencia, exito y tokens.
"""
