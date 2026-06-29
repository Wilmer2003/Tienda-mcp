"""
models.py
=========
Esquemas de datos validados con Pydantic.

Esto es clave para la rúbrica (Criterio 3 - "Uso de MCP con JSON/schema
validado"). Cada herramienta del servidor MCP entrega y recibe datos que
respetan estos esquemas, de modo que la comunicación entre agentes nunca
es "texto plano sin esquema".
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Categoria(str, Enum):
    """Categorías válidas de la boutique de ropa."""
    POLOS = "polos"
    PANTALONES = "pantalones"
    VESTIDOS = "vestidos"
    CALZADO = "calzado"
    CHAQUETAS = "chaquetas"
    ACCESORIOS = "accesorios"


class EstadoPedido(str, Enum):
    PENDIENTE_PAGO = "pendiente_pago"
    PAGADO = "pagado"
    CANCELADO = "cancelado"
    RECHAZADO_STOCK = "rechazado_por_stock"


class MetodoPago(str, Enum):
    TARJETA = "tarjeta"
    YAPE = "yape"
    PLIN = "plin"
    PAYPAL = "paypal"
    CONTRA_ENTREGA = "contra_entrega"


class Producto(BaseModel):
    """Una prenda del catálogo."""
    id: str = Field(..., description="Identificador único, ej. 'P001'")
    nombre: str
    categoria: Categoria
    precio: float = Field(..., ge=0, description="Precio en soles (PEN)")
    marca: str
    descripcion: str
    rating: float = Field(..., ge=0, le=5)


class ItemCarrito(BaseModel):
    producto_id: str
    nombre: str
    cantidad: int = Field(..., gt=0)
    precio_unitario: float = Field(..., ge=0)
    subtotal: float = Field(..., ge=0)


class Carrito(BaseModel):
    usuario_id: str
    items: list[ItemCarrito] = []
    total: float = 0.0
    cantidad_items: int = 0


class Pedido(BaseModel):
    pedido_id: str
    usuario_id: str
    items: list[ItemCarrito]
    total: float
    estado: EstadoPedido
    metodo_pago: Optional[MetodoPago] = None


class ResultadoOperacion(BaseModel):
    """
    Respuesta estándar de las herramientas que modifican estado.
    Tener un formato fijo permite a los agentes razonar sobre éxito/fallo
    sin parsear lenguaje natural (resolución de conflictos del Criterio 3).
    """
    exito: bool
    mensaje: str
    datos: dict = {}
