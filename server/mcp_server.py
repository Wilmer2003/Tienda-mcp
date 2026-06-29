"""
mcp_server.py
=============
Servidor MCP de la Tienda Virtual.

Expone la lógica de la tienda como HERRAMIENTAS MCP que cualquier cliente
(Antigravity, Claude Code, Claude Desktop) puede invocar. Cada herramienta:
  - tiene tipos declarados -> el SDK genera un JSON Schema automáticamente,
  - devuelve objetos Pydantic -> salida estructurada y validada,
  - tiene un docstring claro -> así el agente sabe cuándo y cómo usarla.

Ejecutar localmente:
    pip install -r requirements.txt
    python -m server.mcp_server          # transporte stdio (para Antigravity)

Inspeccionar con el MCP Inspector (opcional, muy útil para tu demo):
    npx @modelcontextprotocol/inspector python -m server.mcp_server
"""

from mcp.server.fastmcp import FastMCP

from server.store_logic import TIENDA
from server.models import Producto, Carrito, Pedido, ResultadoOperacion

# Nombre que verán los clientes MCP.
mcp = FastMCP("tienda-virtual")


# ----------------------------------------------------------------------
# CATÁLOGO
# ----------------------------------------------------------------------
@mcp.tool()
def buscar_productos(query: str = "", categoria: str = "",
                     precio_max: float = 0.0) -> list[Producto]:
    """Busca productos en el catálogo.

    Args:
        query: texto a buscar en nombre, marca o descripción (ej. 'laptop').
        categoria: filtra por categoría: laptops, smartphones, audio,
                   tablets, accesorios, gaming. Vacío = todas.
        precio_max: precio máximo en soles. 0 = sin límite.

    Devuelve la lista de productos que cumplen los filtros.
    """
    return TIENDA.buscar(query=query, categoria=categoria, precio_max=precio_max)


@mcp.tool()
def obtener_producto(producto_id: str) -> Producto | ResultadoOperacion:
    """Obtiene el detalle completo de un producto por su ID (ej. 'P003')."""
    p = TIENDA.obtener_producto(producto_id)
    if p is None:
        return ResultadoOperacion(exito=False,
                                  mensaje=f"No existe el producto {producto_id}.")
    return p


@mcp.tool()
def verificar_inventario(producto_id: str) -> ResultadoOperacion:
    """Verifica cuántas unidades hay disponibles de un producto.

    Útil ANTES de agregar al carrito o cerrar un pedido. Si el stock es 0,
    el agente debería ofrecer un producto alternativo.
    """
    p = TIENDA.obtener_producto(producto_id)
    if p is None:
        return ResultadoOperacion(exito=False,
                                  mensaje=f"No existe el producto {producto_id}.")
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
@mcp.tool()
def agregar_al_carrito(usuario_id: str, producto_id: str,
                       cantidad: int = 1) -> ResultadoOperacion:
    """Agrega un producto al carrito de un usuario.

    Falla (exito=False) si el producto no existe o no hay stock suficiente;
    en ese caso 'datos' incluye el stock disponible para que el agente decida.
    """
    return TIENDA.agregar_al_carrito(usuario_id, producto_id, cantidad)


@mcp.tool()
def ver_carrito(usuario_id: str) -> Carrito:
    """Muestra el contenido y total del carrito de un usuario."""
    return TIENDA.ver_carrito(usuario_id)


@mcp.tool()
def vaciar_carrito(usuario_id: str) -> ResultadoOperacion:
    """Vacía por completo el carrito de un usuario."""
    return TIENDA.vaciar_carrito(usuario_id)


# ----------------------------------------------------------------------
# PEDIDOS Y PAGOS
# ----------------------------------------------------------------------
@mcp.tool()
def crear_pedido(usuario_id: str) -> ResultadoOperacion:
    """Convierte el carrito del usuario en un pedido pendiente de pago.

    Re-verifica el stock en el momento; si otro pedido tomó las unidades,
    falla (control de conflictos). Devuelve el 'pedido_id' en 'datos'.
    """
    return TIENDA.crear_pedido(usuario_id)


@mcp.tool()
def procesar_pago(pedido_id: str, metodo_pago: str) -> ResultadoOperacion:
    """Procesa el pago de un pedido y descuenta el inventario.

    Args:
        pedido_id: ID devuelto por crear_pedido (ej. 'ORD-0001').
        metodo_pago: tarjeta, yape, paypal o contra_entrega.
    """
    return TIENDA.procesar_pago(pedido_id, metodo_pago)


@mcp.tool()
def consultar_pedido(pedido_id: str) -> Pedido | ResultadoOperacion:
    """Consulta el estado actual de un pedido por su ID."""
    p = TIENDA.consultar_pedido(pedido_id)
    if p is None:
        return ResultadoOperacion(exito=False,
                                  mensaje=f"No existe el pedido {pedido_id}.")
    return p


@mcp.tool()
def consultar_historial_inventario(producto_id: str = "",
                                   limite: int = 50) -> ResultadoOperacion:
    """Devuelve el historial de movimientos de inventario.

    Cada movimiento incluye timestamp, producto, delta (positivo = entrada,
    negativo = venta), motivo y stock_resultante. Si `producto_id` se pasa,
    filtra solo a ese producto. Util para que el Agente de Inventarios
    audite movimientos y responda preguntas tipo 'que paso con P003'.

    Args:
        producto_id: opcional, filtra por un producto (ej. 'P003').
        limite: maximo de movimientos a devolver (default 50, mas recientes).
    """
    mov = TIENDA.historial_movimientos(
        producto_id=producto_id or None, limite=limite)
    return ResultadoOperacion(
        exito=True,
        mensaje=(f"{len(mov)} movimiento(s) registrado(s)"
                 + (f" para {producto_id.upper()}" if producto_id else "")
                 + "."),
        datos={"movimientos": mov, "total": len(mov)},
    )


if __name__ == "__main__":
    # Transporte stdio: así lo conectan Antigravity y Claude Code.
    mcp.run()
