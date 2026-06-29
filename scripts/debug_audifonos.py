"""Debug: por que 'Quiero audifonos' no encuentra P005/P006?"""
import asyncio
from agents.event_bus import EventBus
from agents.mcp_client import MCPClient
from agents.orchestrator import Orquestador
from agents.shared_state import SharedState
import server.store_logic as store_logic
import itertools
from server.store_data import CATALOGO, INVENTARIO_INICIAL


async def main():
    # Reset tienda
    t = store_logic.TIENDA
    t._catalogo = {p.id: p for p in CATALOGO}
    t._inventario = dict(INVENTARIO_INICIAL)
    t._carritos = {}
    t._pedidos = {}
    t._contador_pedidos = itertools.count(1)

    state = SharedState()
    bus = EventBus()
    mcp = MCPClient(etiqueta="debug")
    orq = Orquestador(mcp, state, bus)

    # Igual al test: tres turnos en secuencia
    for msg in ["Hola quiero un Smartphone Pixel 8",
                "Buscame laptops de menos de 4000 soles",
                "Quiero audifonos"]:
        print(f"\n=== USUARIO: {msg!r} ===")
        r = await orq.atender(msg, usuario_id="u_nlu")
        print(f"  agente={r.agente} intent={r.intent} exito={r.exito}")
        print(f"  tools={r.tools_invocadas}")
        print(f"  mensaje[:200]={r.mensaje[:200]}")

    # Imprimir contexto final de la sesion
    s = state.sesion("u_nlu")
    print(f"\nContexto final: {s.contexto}")


if __name__ == "__main__":
    asyncio.run(main())
