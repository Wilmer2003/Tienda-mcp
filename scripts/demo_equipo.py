"""demo_equipo.py — el Jefe distribuye trabajo entre el equipo completo."""
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
    t._movimientos = []
    t._contador_pedidos = itertools.count(1)


async def main():
    _reset()
    state = SharedState(); bus = EventBus(); mcp = MCPClient("demo")
    orq = Orquestador(mcp, state, bus)
    user = "cliente-01"

    conv = [
        ("CONSULTA",     "quiero audifonos"),
        ("ORDINAL",      "el mas economico"),
        ("VENTA",        "agregalo"),
        ("INVENTARIO",   "muestrame el historial de movimientos"),
        ("FINANZAS",     "pagar con tarjeta"),
        ("AUDITORIA",    "ahora muestrame de nuevo el historial"),
    ]

    print("=" * 76)
    print(" DEMO — JEFE DISTRIBUYE A SU EQUIPO (consultas / inventarios / ventas / finanzas)")
    print("=" * 76)

    for etiqueta, msg in conv:
        print(f"\n[{etiqueta}] CLIENTE: {msg}")
        r = await orq.atender(msg, usuario_id=user)
        print(f"   JEFE delego a -> {r.agente.upper()}  (intent={r.intent})")
        for ln in r.mensaje.splitlines():
            print(f"            {ln}")


if __name__ == "__main__":
    asyncio.run(main())
