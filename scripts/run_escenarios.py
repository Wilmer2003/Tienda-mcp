"""
run_escenarios.py
=================
Corre los 3 escenarios principales del sistema multi-agente y genera el
reporte de metricas en docs/METRICAS.md (Criterio 4 y 5 de la rubrica).

Escenarios:
  1) Feliz       : busca laptop -> agrega -> paga.
  2) Agotado     : pide producto agotado -> recibe alternativa.
  3) Conflicto   : dos usuarios compiten por stock=1.

Ejecutar: py -m scripts.run_escenarios
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from agents.event_bus import BUS
from agents.mcp_client import MCPClient
from agents.metrics import Metrics
from agents.orchestrator import Orquestador
from agents.shared_state import STATE


DOCS = Path(__file__).resolve().parent.parent / "docs"


async def _conversar(orq: Orquestador, mensajes: list[tuple[str, str]],
                     metrics: Metrics) -> None:
    """Atiende una secuencia (usuario_id, mensaje) por el orquestador."""
    for usuario_id, mensaje in mensajes:
        resp = await orq.atender(mensaje, usuario_id=usuario_id)
        print(f"\n[{usuario_id}] -> {mensaje}")
        print(f"  ({resp.agente}, intent={resp.intent}, "
              f"lat={resp.latencia_ms:.1f}ms)")
        for ln in resp.mensaje.splitlines():
            print(f"  {ln}")
        metrics.registrar(
            usuario=usuario_id, mensaje=mensaje, agente=resp.agente,
            intent=resp.intent, latencia_ms=resp.latencia_ms, exito=resp.exito,
            tools_invocadas=resp.tools_invocadas,
            tokens_estimados=Metrics.estimar_tokens(mensaje, resp.mensaje),
        )


def _nueva_instancia() -> tuple[Orquestador, Metrics]:
    """Crea un orquestador con su propio MCPClient (estado del MCP global es
    el unico compartido, por diseno)."""
    mcp_client = MCPClient(etiqueta="demo")
    return Orquestador(mcp_client, STATE, BUS), Metrics()


async def escenario_feliz() -> Metrics:
    print("=" * 60)
    print("ESCENARIO 1: FELIZ")
    print("=" * 60)
    orq, metrics = _nueva_instancia()
    await _conversar(orq, [
        ("u1", "Hola, quiero ver laptops menos de 4000 soles"),
        ("u1", "Agrega 1 unidad de P001 al carrito"),
        ("u1", "Muestra mi carrito"),
        ("u1", "Quiero pagar con yape"),
    ], metrics)
    return metrics


async def escenario_agotado() -> Metrics:
    print("\n" + "=" * 60)
    print("ESCENARIO 2: PRODUCTO AGOTADO -> ALTERNATIVA")
    print("=" * 60)
    orq, metrics = _nueva_instancia()
    await _conversar(orq, [
        ("u2", "Tienes la Consola PlayBox X?"),
        ("u2", "Verifica stock de P010"),
        ("u2", "Agrega P010 al carrito"),     # debe sugerir alternativa
    ], metrics)
    return metrics


async def escenario_conflicto() -> Metrics:
    """Dos usuarios intentan llevar P009 (stock=1) al carrito a la vez.

    Lanzamos las dos atenciones en `asyncio.gather` para forzar concurrencia.
    El lock del StoreState debe garantizar un solo ganador.
    """
    print("\n" + "=" * 60)
    print("ESCENARIO 3: CONFLICTO POR P009 (stock=1)")
    print("=" * 60)
    orq, metrics = _nueva_instancia()

    async def turno(usuario_id: str, mensaje: str) -> None:
        resp = await orq.atender(mensaje, usuario_id=usuario_id)
        print(f"\n[{usuario_id}] -> {mensaje}")
        print(f"  ({resp.agente}, intent={resp.intent}, "
              f"lat={resp.latencia_ms:.1f}ms, exito={resp.exito})")
        for ln in resp.mensaje.splitlines():
            print(f"  {ln}")
        metrics.registrar(
            usuario=usuario_id, mensaje=mensaje, agente=resp.agente,
            intent=resp.intent, latencia_ms=resp.latencia_ms, exito=resp.exito,
            tools_invocadas=resp.tools_invocadas,
            tokens_estimados=Metrics.estimar_tokens(mensaje, resp.mensaje),
        )

    # Los dos usuarios piden la ultima unidad en paralelo.
    await asyncio.gather(
        turno("uA", "Agrega P009 al carrito"),
        turno("uB", "Agrega P009 al carrito"),
    )
    # Despues, uno intenta pagar.
    for u in ("uA", "uB"):
        await turno(u, "Quiero crear pedido y pagar con tarjeta")

    return metrics


async def main() -> None:
    DOCS.mkdir(exist_ok=True)

    m1 = await escenario_feliz()
    m2 = await escenario_agotado()
    m3 = await escenario_conflicto()

    # Combinar las tres en un solo Metrics para reporte unico.
    global_m = Metrics()
    for t in (*m1.turnos, *m2.turnos, *m3.turnos):
        global_m.turnos.append(t)

    print("\n" + "=" * 60)
    print("METRICAS GLOBALES")
    print("=" * 60)
    import json
    print(json.dumps(global_m.resumen(), indent=2, ensure_ascii=False))

    global_m.guardar_markdown(DOCS / "METRICAS.md")
    global_m.guardar_json(DOCS / "metricas.json")
    print(f"\nReportes generados en {DOCS}")


if __name__ == "__main__":
    asyncio.run(main())
