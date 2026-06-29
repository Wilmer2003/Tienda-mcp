"""
test_flujos.py
==============
Suite de pruebas con casos felices y casos adversariales.

Cubre lo que la rubrica pide en el Criterio 5 ("inputs adversariales o edge
cases"). Cada test es independiente gracias al fixture `orquestador` que
reinicializa la tienda.
"""
from __future__ import annotations

import asyncio
import pytest


# ---------------------------------------------------------------------------
# CAMINO FELIZ
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flujo_feliz_completo(orquestador):
    r1 = await orquestador.atender("Busca polos", usuario_id="u1")
    assert r1.agente == "consultas"
    assert r1.exito
    assert "P001" in r1.mensaje or "P002" in r1.mensaje

    r2 = await orquestador.atender("Agrega P001 al carrito", usuario_id="u1")
    assert r2.agente == "ventas"
    assert r2.exito

    r3 = await orquestador.atender("Quiero pagar con tarjeta", usuario_id="u1")
    assert r3.agente == "finanzas"
    assert r3.exito
    assert "aprobado" in r3.mensaje.lower()


# ---------------------------------------------------------------------------
# CASO CONDICIONAL: agotado -> sugiere alternativa
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_producto_agotado_sugiere_alternativa(orquestador):
    # P010 (Abrigo Lana Beige) esta agotado. La alternativa de la misma
    # categoria 'chaquetas' deberia ser P009 (Chaqueta de Cuero Negra).
    r = await orquestador.atender("Agrega P010 al carrito", usuario_id="u2")
    assert not r.exito
    assert ("alternativas" in r.datos
            or "Chaqueta" in r.mensaje
            or "P009" in r.mensaje)


# ---------------------------------------------------------------------------
# CONFLICTO POR STOCK = 1
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_conflicto_stock_uno(orquestador):
    # uA y uB compiten por P009 (stock = 1).
    await asyncio.gather(
        orquestador.atender("Agrega P009 al carrito", usuario_id="uA"),
        orquestador.atender("Agrega P009 al carrito", usuario_id="uB"),
    )
    rA = await orquestador.atender("Quiero crear pedido y pagar con yape",
                                   usuario_id="uA")
    rB = await orquestador.atender("Quiero crear pedido y pagar con yape",
                                   usuario_id="uB")
    # Exactamente uno gana.
    exitos = [rA.exito, rB.exito]
    assert exitos.count(True) == 1
    assert exitos.count(False) == 1


# ---------------------------------------------------------------------------
# EDGE CASES / ADVERSARIALES
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_producto_inexistente(orquestador):
    r = await orquestador.atender("Agrega P999 al carrito", usuario_id="u1")
    assert not r.exito
    assert "no existe" in r.mensaje.lower() or "no encontr" in r.mensaje.lower()


@pytest.mark.asyncio
async def test_metodo_pago_invalido(orquestador):
    await orquestador.atender("Agrega P003 al carrito", usuario_id="u1")
    r = await orquestador.atender("Pagar con bitcoin", usuario_id="u1")
    # bitcoin no es un metodo valido: el agente debe listar los aceptados.
    msg = r.mensaje.lower()
    assert any(m in msg for m in ("tarjeta", "yape", "paypal", "contra_entrega"))


@pytest.mark.asyncio
async def test_carrito_vacio_no_crea_pedido(orquestador):
    r = await orquestador.atender("Quiero pagar con tarjeta", usuario_id="sin_carrito")
    assert not r.exito
    assert "vac" in r.mensaje.lower() or "no se puede" in r.mensaje.lower()


@pytest.mark.asyncio
async def test_consultar_pedido_inexistente(orquestador):
    r = await orquestador.atender("Estado del pedido ORD-9999", usuario_id="u1")
    assert not r.exito
    assert "no existe" in r.mensaje.lower()


@pytest.mark.asyncio
async def test_mensaje_desconocido_pide_reformular(orquestador):
    r = await orquestador.atender("blablabla foo bar", usuario_id="u1")
    assert r.intent == "desconocido"
    assert "ayud" in r.mensaje.lower() or "reform" in r.mensaje.lower() or "no estoy" in r.mensaje.lower()


@pytest.mark.asyncio
async def test_doble_pago_no_se_procesa(orquestador):
    await orquestador.atender("Agrega P003 al carrito", usuario_id="u1")
    r1 = await orquestador.atender("Quiero pagar con yape", usuario_id="u1")
    assert r1.exito
    # Reintentar pagar tras vaciar el carrito debe fallar por uno de dos
    # motivos validos: (a) pedido ya pagado, (b) carrito vacio para crear
    # uno nuevo.
    r2 = await orquestador.atender("Quiero pagar con yape", usuario_id="u1")
    assert not r2.exito
    msg = r2.mensaje.lower()
    assert any(s in msg for s in ("vac", "pagado", "ya est"))


# ---------------------------------------------------------------------------
# HISTORIAL / ESTADO COMPARTIDO
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_historial_preserva_turnos(orquestador):
    await orquestador.atender("Busca laptops", usuario_id="u1")
    await orquestador.atender("Agrega P001 al carrito", usuario_id="u1")
    historial = orquestador.state.historial()
    # Al menos: 2 turnos de usuario + 4 turnos de agentes (recibe+responde).
    assert len(historial) >= 6
    roles = {t.rol for t in historial}
    assert "usuario" in roles
    assert any(r in roles for r in ("consultas", "ventas"))


# ---------------------------------------------------------------------------
# FRASES NATURALES NLU & FALSOS POSITIVOS DE CANTIDAD
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_frases_naturales_nlu(orquestador):
    # 1. "Hola quiero un Pantalón Chino"
    r1 = await orquestador.atender("Hola quiero un Pantalón Chino", usuario_id="u_nlu")
    assert r1.agente == "consultas"
    assert r1.exito
    assert any(x in r1.mensaje for x in ["Chino", "P004"])

    # 2. "Búscame pantalones de menos de 150 soles"
    r2 = await orquestador.atender("Búscame pantalones de menos de 150 soles",
                                   usuario_id="u_nlu")
    assert r2.agente == "consultas"
    assert r2.exito
    # Chino cuesta S/ 119 (entra), Jeans cuestan S/ 159 (no entra)
    assert any(x in r2.mensaje for x in ["Chino", "P004"])
    assert "Jeans" not in r2.mensaje

    # 3. "Quiero vestidos"
    r3 = await orquestador.atender("Quiero vestidos", usuario_id="u_nlu")
    assert r3.agente == "consultas"
    assert r3.exito
    assert any(x in r3.mensaje for x in ["Floral", "Negro", "P005", "P006"])

    # 4. "Agrega el Pantalón Chino al carrito"
    r4 = await orquestador.atender("Agrega el Pantalón Chino al carrito",
                                   usuario_id="u_nlu")
    assert r4.agente == "ventas"
    assert r4.exito

    # 5. "Ver carrito"
    r5 = await orquestador.atender("Ver carrito", usuario_id="u_nlu")
    assert r5.agente == "ventas"
    assert r5.exito
    assert "Chino" in r5.mensaje
    assert "1 x" in r5.mensaje

    # 6. "Pagar yape"
    r6 = await orquestador.atender("Pagar yape", usuario_id="u_nlu")
    assert r6.agente == "finanzas"
    assert r6.exito
    assert "aprobado" in r6.mensaje.lower()


@pytest.mark.asyncio
async def test_falsos_positivos_cantidad(orquestador):
    from agents.brain import _extraer_cantidad

    # "Pixel 8" no debe interpretarse como cantidad 8.
    assert _extraer_cantidad("Agrega el Pixel 8 al carrito") == 1

    # "Tab S9" no debe interpretarse como cantidad 9.
    assert _extraer_cantidad("Agrega el Tab S9 al carrito") == 1

    # "Quiero 2 audífonos" sí debe interpretarse como cantidad 2.
    assert _extraer_cantidad("Quiero 2 audífonos") == 2
    assert _extraer_cantidad("Agrega 2 audífonos al carrito") == 2
