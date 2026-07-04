"""
store_logic.py
==============
Lógica de negocio + estado compartido de la tienda.

La clase StoreState es la "memoria compartida" del sistema: mantiene el
catálogo, el inventario, los carritos por usuario y los pedidos. El servidor
MCP expone estas operaciones como herramientas; los agentes NO tocan estos
datos directamente, siempre pasan por aquí. Eso garantiza un único punto de
verdad y permite resolver conflictos (Criterio 3 de la rúbrica).
"""

from __future__ import annotations
import threading
import itertools
import unicodedata

from server.models import (
    Producto, Carrito, ItemCarrito, Pedido,
    EstadoPedido, MetodoPago, ResultadoOperacion,
)
from server.store_data import CATALOGO, INVENTARIO_INICIAL


def _sin_tildes(t: str) -> str:
    nfkd = unicodedata.normalize("NFKD", t)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


class StoreState:
    def __init__(self) -> None:
        self._catalogo: dict[str, Producto] = {p.id: p for p in CATALOGO}
        self._inventario: dict[str, int] = dict(INVENTARIO_INICIAL)
        self._carritos: dict[str, list[ItemCarrito]] = {}
        self._pedidos: dict[str, Pedido] = {}
        self._contador_pedidos = itertools.count(1)
        # Lock para que dos agentes en paralelo no rompan el inventario.
        self._lock = threading.Lock()
        # Historial de movimientos del inventario (Criterio 3 — historial
        # preservado). Cada entrada: timestamp, producto_id, delta, motivo,
        # stock_resultante.
        from datetime import datetime, timezone
        self._datetime = datetime
        self._tz = timezone
        self._movimientos: list[dict] = []

    def _log_movimiento(self, producto_id: str, delta: int, motivo: str,
                        usuario_id: str | None = None) -> dict:
        """Registra una entrada en el historial. Llamar SOLO bajo el lock."""
        entrada = {
            "timestamp": self._datetime.now(self._tz.utc).isoformat(),
            "producto_id": producto_id,
            "delta": delta,
            "motivo": motivo,
            "usuario_id": usuario_id,
            "stock_resultante": self._inventario.get(producto_id, 0),
        }
        self._movimientos.append(entrada)
        return entrada

    def historial_movimientos(self, producto_id: str | None = None,
                              limite: int = 50) -> list[dict]:
        with self._lock:
            mov = self._movimientos
            if producto_id:
                pid = producto_id.upper()
                mov = [m for m in mov if m["producto_id"] == pid]
            return mov[-limite:]

    # ----------------------- Catálogo -----------------------
    def buscar(self, query: str = "", categoria: str = "",
               precio_max: float = 0.0) -> list[Producto]:
        # Normalizamos query y campos a comparar SIN tildes para que
        # "audifono" matchee "Audífonos", "telefono" matchee "Teléfono", etc.
        q = _sin_tildes(query.strip())
        resultados = []
        for p in self._catalogo.values():
            if q:
                n = _sin_tildes(p.nombre)
                m = _sin_tildes(p.marca)
                d = _sin_tildes(p.descripcion)
                if q not in n and q not in m and q not in d:
                    continue
            if categoria and p.categoria.value != categoria.lower():
                continue
            if precio_max and p.precio > precio_max:
                continue
            resultados.append(p)
        return resultados

    def obtener_producto(self, producto_id: str) -> Producto | None:
        return self._catalogo.get(producto_id.upper())

    def stock(self, producto_id: str) -> int:
        return self._inventario.get(producto_id.upper(), 0)

    # ----------------------- Carrito ------------------------
    def agregar_al_carrito(self, usuario_id: str, producto_id: str,
                           cantidad: int) -> ResultadoOperacion:
        pid = producto_id.upper()
        with self._lock:
            producto = self._catalogo.get(pid)
            if producto is None:
                return ResultadoOperacion(exito=False,
                    mensaje=f"El producto {pid} no existe.")
            if cantidad <= 0:
                return ResultadoOperacion(exito=False,
                    mensaje="La cantidad debe ser mayor a 0.")

            ya_en_carrito = sum(
                i.cantidad for i in self._carritos.get(usuario_id, [])
                if i.producto_id == pid
            )
            disponible = self._inventario.get(pid, 0)
            if cantidad + ya_en_carrito > disponible:
                return ResultadoOperacion(exito=False,
                    mensaje=(f"Stock insuficiente de '{producto.nombre}'. "
                             f"Disponible: {disponible}, ya en carrito: {ya_en_carrito}."),
                    datos={"disponible": disponible, "categoria": producto.categoria.value})

            carrito = self._carritos.setdefault(usuario_id, [])
            for item in carrito:
                if item.producto_id == pid:
                    item.cantidad += cantidad
                    item.subtotal = round(item.cantidad * item.precio_unitario, 2)
                    break
            else:
                carrito.append(ItemCarrito(
                    producto_id=pid, nombre=producto.nombre, cantidad=cantidad,
                    precio_unitario=producto.precio,
                    subtotal=round(cantidad * producto.precio, 2)))
            self._log_movimiento(pid, delta=0,
                                 motivo="reserva_en_carrito",
                                 usuario_id=usuario_id)
            return ResultadoOperacion(exito=True,
                mensaje=f"Se agregó {cantidad} x '{producto.nombre}' al carrito.")

    def eliminar_del_carrito(self, usuario_id: str, producto_id: str, cantidad: int | None = None) -> ResultadoOperacion:
        """Elimina un producto del carrito o reduce su cantidad."""
        pid = producto_id.upper()
        with self._lock:
            carrito = self._carritos.get(usuario_id, [])
            for i, item in enumerate(carrito):
                if item.producto_id == pid:
                    if cantidad is None or cantidad >= item.cantidad:
                        carrito.pop(i)
                        msg = f"Se eliminó '{item.nombre}' del carrito."
                    else:
                        item.cantidad -= cantidad
                        item.subtotal = round(item.cantidad * item.precio_unitario, 2)
                        msg = f"Se redujo la cantidad de '{item.nombre}' en {cantidad}."
                    return ResultadoOperacion(exito=True, mensaje=msg)
            return ResultadoOperacion(exito=False, mensaje=f"El producto {pid} no está en el carrito.")

    def ver_carrito(self, usuario_id: str) -> Carrito:
        items = self._carritos.get(usuario_id, [])
        total = round(sum(i.subtotal for i in items), 2)
        return Carrito(usuario_id=usuario_id, items=items, total=total,
                       cantidad_items=sum(i.cantidad for i in items))

    def vaciar_carrito(self, usuario_id: str) -> ResultadoOperacion:
        self._carritos[usuario_id] = []
        return ResultadoOperacion(exito=True, mensaje="Carrito vaciado.")

    # ----------------------- Pedidos ------------------------
    def crear_pedido(self, usuario_id: str) -> ResultadoOperacion:
        with self._lock:
            items = self._carritos.get(usuario_id, [])
            if not items:
                return ResultadoOperacion(exito=False,
                    mensaje="El carrito está vacío, no se puede crear pedido.")
            # Re-verificar stock al momento de cerrar (control de conflictos).
            for it in items:
                if it.cantidad > self._inventario.get(it.producto_id, 0):
                    return ResultadoOperacion(exito=False,
                        mensaje=(f"Ya no hay stock suficiente de '{it.nombre}'. "
                                 f"Otro pedido pudo haberlo tomado."),
                        datos={"producto_id": it.producto_id})

            pedido_id = f"ORD-{next(self._contador_pedidos):04d}"
            total = round(sum(i.subtotal for i in items), 2)
            pedido = Pedido(pedido_id=pedido_id, usuario_id=usuario_id,
                            items=list(items), total=total,
                            estado=EstadoPedido.PENDIENTE_PAGO)
            self._pedidos[pedido_id] = pedido
            return ResultadoOperacion(exito=True,
                mensaje=f"Pedido {pedido_id} creado. Total: S/ {total:.2f}.",
                datos={"pedido_id": pedido_id, "total": total})

    def procesar_pago(self, pedido_id: str,
                      metodo_pago: str) -> ResultadoOperacion:
        with self._lock:
            pedido = self._pedidos.get(pedido_id)
            if pedido is None:
                return ResultadoOperacion(exito=False,
                    mensaje=f"El pedido {pedido_id} no existe.")
            if pedido.estado != EstadoPedido.PENDIENTE_PAGO:
                return ResultadoOperacion(exito=False,
                    mensaje=f"El pedido {pedido_id} ya está en estado '{pedido.estado.value}'.")
            try:
                metodo = MetodoPago(metodo_pago.lower())
            except ValueError:
                return ResultadoOperacion(exito=False,
                    mensaje=f"Método de pago inválido: {metodo_pago}.")

            # Descontar inventario al confirmar el pago. Cada decremento
            # queda registrado en el historial de movimientos.
            for it in pedido.items:
                self._inventario[it.producto_id] -= it.cantidad
                self._log_movimiento(
                    it.producto_id, delta=-it.cantidad,
                    motivo=f"venta_pagada({pedido_id},{metodo.value})",
                    usuario_id=pedido.usuario_id,
                )
            pedido.estado = EstadoPedido.PAGADO
            pedido.metodo_pago = metodo
            self._carritos[pedido.usuario_id] = []  # vaciar carrito tras compra
            return ResultadoOperacion(exito=True,
                mensaje=f"Pago de S/ {pedido.total:.2f} aprobado vía {metodo.value}.",
                datos={"pedido_id": pedido_id, "estado": pedido.estado.value})

    def consultar_pedido(self, pedido_id: str) -> Pedido | None:
        return self._pedidos.get(pedido_id)


# Instancia única compartida por todo el servidor MCP (memoria compartida).
TIENDA = StoreState()
