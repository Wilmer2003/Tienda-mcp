"""
test_contexto.py
================
Tests de fluidez conversacional: el sistema debe mantener el hilo entre turnos.

Simula el flujo del screenshot del profesor:
  "quiero tablet" -> Catalogo
  "es la unica?"  -> Catalogo (re-confirma con contexto)
  "cuanto cuesta?"-> Catalogo (detalle del producto en foco)
  "agregala"      -> Ventas (sin que el usuario diga P007)
  "pagar yape"    -> Pagos (confirma con mensaje verificable)
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_flujo_conversacional_vestido(orquestador):
    """Cliente pide vestido (hay dos), elige uno, lo agrega y paga.
    El producto en foco debe heredarse entre los 5 turnos sin que el usuario
    repita el ID.
    """
    # 1) Usuario pide categoria. Hay 2 vestidos (P005, P006).
    r1 = await orquestador.atender("quiero un vestido", usuario_id="conv_user")
    assert r1.exito
    assert "P005" in r1.mensaje or "P006" in r1.mensaje or "floral" in r1.mensaje.lower() or "negro" in r1.mensaje.lower()

    # 2) "el mas elegante" / "el negro" -> el vestido negro P006
    r2 = await orquestador.atender("el negro", usuario_id="conv_user")

    # 3) "cuanto cuesta?" -> Catalogo da detalle del producto en foco.
    r3 = await orquestador.atender("cuanto cuesta?", usuario_id="conv_user")
    assert "S/" in r3.mensaje

    # 4) "agregala" -> Ventas con el vestido en foco.
    r4 = await orquestador.atender("agregala", usuario_id="conv_user")
    assert r4.exito
    carrito_resp = await orquestador.atender("ver carrito",
                                             usuario_id="conv_user")
    assert "Vestido" in carrito_resp.mensaje

    # 5) Pagar con yape -> Finanzas con confirmacion verificable.
    r5 = await orquestador.atender("quiero pagar con yape",
                                   usuario_id="conv_user")
    assert r5.exito
    assert "CONFIRMADO" in r5.mensaje.upper() or "aprobado" in r5.mensaje.lower()


@pytest.mark.asyncio
async def test_upsell_aceptado_con_si(orquestador):
    """El upsell de Ventas debe poder aceptarse con un simple 'si'."""
    # P003 = Jeans Slim Fit. Ventas sugiere cinturon (P011) como look completo.
    await orquestador.atender("agrega P003 al carrito",
                              usuario_id="upsell_user")
    r = await orquestador.atender("si", usuario_id="upsell_user")
    # El 'si' debe interpretarse como 'agregar P011' (cinturon).
    assert r.exito
    rc = await orquestador.atender("ver carrito", usuario_id="upsell_user")
    assert "P011" in rc.mensaje or "Cinturón" in rc.mensaje or "Cinturon" in rc.mensaje


@pytest.mark.asyncio
async def test_referencia_implicita_stock(orquestador):
    """'tiene stock?' debe heredar el producto en foco del catalogo."""
    await orquestador.atender("buscame el pantalon chino",
                              usuario_id="ref_user")
    r = await orquestador.atender("tiene stock?", usuario_id="ref_user")
    # Inventario o catalogo deben responder sobre P004, no pedir mas info.
    assert r.exito
    assert "P004" in r.mensaje or "Chino" in r.mensaje or "unidad" in r.mensaje.lower()


@pytest.mark.asyncio
async def test_pago_rechazado_es_explicito(orquestador):
    """Si el pago falla, el mensaje debe decirlo claramente con motivo."""
    # No agregamos nada al carrito; el pedido fallara por 'carrito vacio'.
    r = await orquestador.atender("quiero pagar con tarjeta",
                                  usuario_id="rechazo_user")
    assert not r.exito
    msg = r.mensaje.lower()
    # Debe explicar el motivo de forma comprensible.
    assert any(s in msg for s in ("vac", "no se puede", "pagar nada"))
