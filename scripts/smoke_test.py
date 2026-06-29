"""Smoke test: verifica que el servidor MCP carga y expone sus 9 herramientas.

Se ejecuta como: py -m scripts.smoke_test
desde la raiz del proyecto.
"""
import asyncio

from server.mcp_server import mcp
from server.store_logic import TIENDA


async def main() -> None:
    tools = await mcp.list_tools()
    print(f"[OK] Servidor MCP cargado. Tools registradas: {len(tools)}")
    for t in tools:
        descr = (t.description or "").splitlines()[0]
        print(f"  - {t.name}: {descr}")

    print()
    print("[OK] Catalogo cargado:")
    productos = TIENDA.buscar()
    for p in productos:
        stock = TIENDA.stock(p.id)
        marca = "AGOTADO" if stock == 0 else f"stock={stock}"
        print(f"  {p.id}  {p.nombre:30s}  S/ {p.precio:7.2f}  {marca}")

    print()
    print("[OK] Flujo end-to-end mini:")
    r1 = TIENDA.agregar_al_carrito("u1", "P003", 1)
    print(f"  agregar_al_carrito -> exito={r1.exito}  {r1.mensaje}")
    carrito = TIENDA.ver_carrito("u1")
    print(f"  ver_carrito        -> {carrito.cantidad_items} item(s), total S/ {carrito.total}")
    r2 = TIENDA.crear_pedido("u1")
    print(f"  crear_pedido       -> exito={r2.exito}  {r2.mensaje}")
    pedido_id = r2.datos.get("pedido_id")
    if pedido_id:
        r3 = TIENDA.procesar_pago(pedido_id, "yape")
        print(f"  procesar_pago      -> exito={r3.exito}  {r3.mensaje}")
        stock_final = TIENDA.stock("P003")
        print(f"  stock P003 final   -> {stock_final}  (debe haber bajado en 1)")


if __name__ == "__main__":
    asyncio.run(main())
