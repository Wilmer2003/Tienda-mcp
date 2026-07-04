"""
store_tools.py
==============
Capa de adaptación (Adapter) de las herramientas de la Tienda Virtual para LangChain.

Esta capa reutiliza exactamente la misma lógica de negocio (`TIENDA` en `server.store_logic`)
que actualmente consume el servidor MCP, pero la expone usando el decorador `@tool` de LangChain.
Esto permite que los agentes de LangChain invoquen la lógica sin tener que pasar
por el protocolo MCP, garantizando que el comportamiento no se altere.
"""

from langchain_core.tools import tool
from services import TIENDA
from server.models import Producto, Carrito, Pedido, ResultadoOperacion


# ----------------------------------------------------------------------
# CATÁLOGO
# ----------------------------------------------------------------------
@tool
def buscar_productos(query: str = "", categoria: str = "", precio_max: float = 0.0) -> list[Producto]:
    """Busca productos en el catálogo.

    Args:
        query: texto a buscar en nombre, marca o descripción.
        categoria: filtra por categoría: polos, pantalones, vestidos,
                   calzado, chaquetas, accesorios. Vacío = todas.
        precio_max: precio máximo en soles. 0 = sin límite.
    """
    return TIENDA.buscar(query=query, categoria=categoria, precio_max=precio_max)


@tool
def obtener_producto(producto_id: str) -> Producto | ResultadoOperacion:
    """Obtiene el detalle completo de un producto por su ID (ej. 'P003')."""
    p = TIENDA.obtener_producto(producto_id)
    if p is None:
        return ResultadoOperacion(exito=False, mensaje=f"No existe el producto {producto_id}.")
    return p


@tool
def verificar_inventario(producto_id: str) -> ResultadoOperacion:
    """Verifica cuántas unidades hay disponibles de un producto."""
    p = TIENDA.obtener_producto(producto_id)
    if p is None:
        return ResultadoOperacion(exito=False, mensaje=f"No existe el producto {producto_id}.")
    stock = TIENDA.stock(producto_id)
    return ResultadoOperacion(
        exito=True,
        mensaje=f"'{p.nombre}' tiene {stock} unidad(es) disponible(s).",
        datos={"producto_id": p.id, "stock": stock,
               "categoria": p.categoria.value, "agotado": stock == 0},
    )


# ----------------------------------------------------------------------
# CARRITO
# ----------------------------------------------------------------------
@tool
def agregar_al_carrito(usuario_id: str, producto_id: str, cantidad: int = 1) -> ResultadoOperacion:
    """Agrega un producto al carrito de un usuario."""
    return TIENDA.agregar_al_carrito(usuario_id, producto_id, cantidad)


@tool
def eliminar_del_carrito(usuario_id: str, producto_id: str, cantidad: int | None = None) -> ResultadoOperacion:
    """Elimina un producto del carrito o reduce su cantidad. Si cantidad es None, elimina todo el producto."""
    return TIENDA.eliminar_del_carrito(usuario_id, producto_id, cantidad)


@tool
def ver_carrito(usuario_id: str) -> Carrito:
    """Muestra el contenido y total del carrito de un usuario."""
    return TIENDA.ver_carrito(usuario_id)


@tool
def vaciar_carrito(usuario_id: str) -> ResultadoOperacion:
    """Vacía por completo el carrito de un usuario."""
    return TIENDA.vaciar_carrito(usuario_id)


# ----------------------------------------------------------------------
# PEDIDOS Y PAGOS
# ----------------------------------------------------------------------
@tool
def crear_pedido(usuario_id: str) -> ResultadoOperacion:
    """Convierte el carrito del usuario en un pedido pendiente de pago."""
    return TIENDA.crear_pedido(usuario_id)


@tool
def procesar_pago(pedido_id: str, metodo_pago: str) -> ResultadoOperacion:
    """Procesa el pago de un pedido y descuenta el inventario."""
    return TIENDA.procesar_pago(pedido_id, metodo_pago)


@tool
def consultar_pedido(pedido_id: str) -> Pedido | ResultadoOperacion:
    """Consulta el estado actual de un pedido por su ID."""
    p = TIENDA.consultar_pedido(pedido_id)
    if p is None:
        return ResultadoOperacion(exito=False, mensaje=f"No existe el pedido {pedido_id}.")
    return p


@tool
def consultar_transacciones_niubiz(pedido_id: str = "", limite: int = 50) -> ResultadoOperacion:
    """Consulta transacciones Niubiz registradas localmente."""
    txs = TIENDA.transacciones_niubiz(pedido_id=pedido_id or None, limite=limite)
    return ResultadoOperacion(
        exito=True,
        mensaje=f"{len(txs)} transaccion(es) Niubiz encontradas.",
        datos={"transacciones": txs, "total": len(txs)},
    )


@tool
def consultar_historial_inventario(producto_id: str = "", limite: int = 50) -> ResultadoOperacion:
    """Devuelve el historial de movimientos de inventario."""
    mov = TIENDA.historial_movimientos(producto_id=producto_id or None, limite=limite)
    return ResultadoOperacion(
        exito=True,
        mensaje=f"{len(mov)} movimiento(s) registrado(s).",
        datos={"movimientos": mov, "total": len(mov)},
    )
