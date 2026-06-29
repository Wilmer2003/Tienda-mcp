"""demo_fluidez3.py — varios candidatos + ordinales + nombre completo."""
import asyncio, itertools

from agents.event_bus import EventBus
from agents.mcp_client import MCPClient
from agents.orchestrator import Orquestador
from agents.shared_state import SharedState
import server.store_logic as store_logic
from server.store_data import CATALOGO, INVENTARIO_INICIAL


def _reset():
    t = store_logic.TIENDA
    t._catalogo = {p.id: p for p in CATALOGO}
    t._inventario = dict(INVENTARIO_INICIAL)
    t._carritos = {}
    t._pedidos = {}
    t._contador_pedidos = itertools.count(1)


async def main():
    _reset()
    state = SharedState(); bus = EventBus(); mcp = MCPClient("demo")
    orq = Orquestador(mcp, state, bus)
    user = "cliente-A"

    conv = [
        "quiero audifonos",          # P005 y P006 (2 candidatos)
        "el mas economico",          # debe elegir P006 (S/399 < S/1199)
        "no, mejor el mas caro",     # debe pivotar a P005 (S/1199)
        "el mejor rateado",          # mejor rating: P005 (4.9) vs P006 (4.3) -> P005
        "agregalo",                  # P005 al carrito
        "muestrame mi carrito",
        "pagar yape",
    ]

    print("=" * 72)
    print(" DEMO 3 — VARIOS CANDIDATOS + ORDINALES DE PRECIO/RATING")
    print("=" * 72)
    for msg in conv:
        print(f"\n[CLIENTE]  {msg}")
        r = await orq.atender(msg, usuario_id=user)
        s = state.sesion(user).contexto
        print(f"[{r.agente.upper():>10}] intent={r.intent}  foco={s.get('producto_en_foco')}")
        for ln in r.mensaje.splitlines():
            print(f"            {ln}")


if __name__ == "__main__":
    asyncio.run(main())
