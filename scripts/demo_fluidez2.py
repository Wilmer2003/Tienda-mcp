"""
demo_fluidez2.py
================
Reproduce el escenario REAL del segundo screenshot del profe:

  cliente: "quiero mouse"            <- debe mostrar solo P008 (no teclado/monitor)
  cliente: "el mas economico"        <- debe elegir P008 (mas barato)
  cliente: "el Mouse Inalambrico MX" <- nombre completo -> detalle de P008
  cliente: "agregalo"                <- al carrito
  cliente: "pagar con tarjeta"       <- confirmacion verificada
"""
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
    state = SharedState()
    bus = EventBus()
    mcp = MCPClient(etiqueta="demo")
    orq = Orquestador(mcp, state, bus)
    user = "cliente-01"

    conv = [
        "quiero mouse",
        "el mas economico",
        "agregalo",
        "pagar con tarjeta",
    ]

    print("=" * 72)
    print(" DEMO 2 — FLUIDEZ + ORDINALES + NOMBRE COMPLETO DE PRODUCTO")
    print("=" * 72)

    for msg in conv:
        print(f"\n[CLIENTE]  {msg}")
        r = await orq.atender(msg, usuario_id=user)
        foco = state.sesion(user).contexto.get("producto_en_foco")
        cands = state.sesion(user).contexto.get("candidatos_recientes")
        print(f"[{r.agente.upper():>10}] intent={r.intent} foco={foco} "
              f"candidatos={cands} tools={r.tools_invocadas}")
        for ln in r.mensaje.splitlines():
            print(f"            {ln}")


if __name__ == "__main__":
    asyncio.run(main())
