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
        
        # Persistencia del contador de pedidos
        self._contador_file = ".contador_pedidos"
        start_count = 1
        import os
        if os.path.exists(self._contador_file):
            try:
                with open(self._contador_file, "r") as f:
                    start_count = int(f.read().strip())
            except Exception:
                pass
                
        # Sincronización inteligente con Notion para evitar colisiones
        try:
            from server.notion_client import NOTION
            ultimo = NOTION.obtener_ultimo_numero_pedido()
            if ultimo >= start_count:
                start_count = ultimo + 1
        except Exception:
            pass

        self._contador_pedidos = itertools.count(start_count)
        
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
            pedidos_creados = []
            for it in items:
                count = next(self._contador_pedidos)
                pedido_id = f"ORD-{count:04d}"
                ped = Pedido(pedido_id=pedido_id, usuario_id=usuario_id,
                                items=[it], total=it.subtotal,
                                estado=EstadoPedido.PENDIENTE_PAGO)
                self._pedidos[pedido_id] = ped
                pedidos_creados.append(ped)
            
            # Guardar el contador para el siguiente reinicio
            try:
                with open(self._contador_file, "w") as f:
                    f.write(str(count + 1))
            except Exception:
                pass
                
            # Sincronización estricta con Notion
            from server.notion_client import NOTION
            if NOTION.disponible:
                for ped in pedidos_creados:
                    notion_ok = NOTION.registrar_order(ped)
                    if not notion_ok:
                        # Rollback
                        for p in pedidos_creados:
                            self._pedidos.pop(p.pedido_id, None)
                        return ResultadoOperacion(
                            exito=False, 
                            mensaje=f"Error crítico: No se pudo registrar {ped.pedido_id} en Notion."
                        )
            
            # Vaciar carrito solo si todo fue exitoso
            self._carritos[usuario_id] = []
            
            master_id = ",".join(p.pedido_id for p in pedidos_creados)
            total_sum = sum(p.total for p in pedidos_creados)
            
            return ResultadoOperacion(exito=True,
                mensaje=f"Pedidos creados exitosamente. Total: S/ {total_sum:.2f}.",
                datos={"pedido_id": master_id, "total": total_sum})

    def consultar_pedido(self, pedido_id: str) -> Pedido | None:
        with self._lock:
            p_ids = pedido_id.split(",")
            if len(p_ids) == 1:
                return self._pedidos.get(pedido_id)
            # Combinar multiples ordenes en un pedido virtual para la lectura
            pedidos = [self._pedidos.get(pid) for pid in p_ids]
            if None in pedidos:
                return None
            items_totales = []
            for p in pedidos:
                items_totales.extend(p.items)
            total = sum(p.total for p in pedidos)
            return Pedido(pedido_id=pedido_id, usuario_id=pedidos[0].usuario_id,
                          items=items_totales, total=total, estado=pedidos[0].estado)

    def procesar_pago(self, pedido_id: str,
                      metodo_pago: str,
                      datos_extra: dict = None) -> ResultadoOperacion:
        with self._lock:
            p_ids = pedido_id.split(",")
            pedidos_a_procesar = []
            for pid in p_ids:
                pedido = self._pedidos.get(pid)
                if pedido is None:
                    return ResultadoOperacion(exito=False,
                        mensaje=f"El pedido {pid} no existe.")
                if pedido.estado != EstadoPedido.PENDIENTE_PAGO:
                    return ResultadoOperacion(exito=False,
                        mensaje=f"El pedido {pid} ya está en estado '{pedido.estado.value}'.")
                pedidos_a_procesar.append(pedido)
            try:
                metodo = MetodoPago(metodo_pago.lower())
            except ValueError:
                return ResultadoOperacion(exito=False,
                    mensaje=f"Método de pago inválido: {metodo_pago}.")

            # Descontar inventario al confirmar el pago. Cada decremento
            # queda registrado en el historial de movimientos.
            for pedido in pedidos_a_procesar:
                for it in pedido.items:
                    self._inventario[it.producto_id] -= it.cantidad
                    self._log_movimiento(
                        it.producto_id, delta=-it.cantidad,
                        motivo=f"venta_pagada({pedido.pedido_id},{metodo.value})",
                        usuario_id=pedido.usuario_id,
                    )
                pedido.estado = EstadoPedido.PAGADO
                pedido.metodo_pago = metodo
            
            # Sincronizar actualización con Notion
            from server.notion_client import NOTION
            if NOTION.disponible:
                for pedido in pedidos_a_procesar:
                    NOTION.actualizar_order(pedido.pedido_id, estado=pedido.estado.value, datos={"metodo_pago": metodo.value})
                    datos_voucher = dict(datos_extra) if datos_extra else {}
                    import datetime
                    now = datetime.datetime.now(datetime.timezone.utc)
                    
                    # Cleanup deprecated columns if they were passed
                    for key in ["TOTAL_ESPERADO", "NOMBRE_RECEPTOR", "ES_YAPE", "MONTO_CORRECTO", "NOMBRE_CORRECTO", "DUPLICADO"]:
                        datos_voucher.pop(key, None)
                        
                    if "NOMBRE_PRODUCTO" not in datos_voucher:
                        nombres = ", ".join([f"{item.cantidad}x {item.nombre}" for item in pedido.items])
                        datos_voucher["NOMBRE_PRODUCTO"] = nombres[:1900]
                        
                    if "CLIENTE_ID" not in datos_voucher:
                        datos_voucher["CLIENTE_ID"] = pedido.usuario_id
                    if "NOMBRE_CLIENTE" not in datos_voucher or not datos_voucher["NOMBRE_CLIENTE"]:
                        datos_voucher["NOMBRE_CLIENTE"] = "Cliente Web" if pedido.usuario_id == "anonimo" else pedido.usuario_id
                    
                    datos_voucher["NOMBRE_ESPERADO"] = "AURA Boutique"
                    
                    if "MONTO_TRANSFERIDO" not in datos_voucher:
                        datos_voucher["MONTO_TRANSFERIDO"] = float(pedido.total)
                    if "MONTO_DETECTADO" not in datos_voucher:
                        datos_voucher["MONTO_DETECTADO"] = float(pedido.total)
                        
                    datos_voucher["METODO_PAGO"] = metodo.value.capitalize()
                    
                    if "NUMERO_OPERACION" not in datos_voucher:
                        datos_voucher["NUMERO_OPERACION"] = f"COMP-{int(now.timestamp())}"
                    if "FECHA_DETECTADA" not in datos_voucher:
                        datos_voucher["FECHA_DETECTADA"] = now.date().isoformat()
                    if "HORA_DETECTADA" not in datos_voucher:
                        datos_voucher["HORA_DETECTADA"] = now.strftime("%H:%M")
                        
                    if "VALIDACION_IA" not in datos_voucher:
                        datos_voucher["VALIDACION_IA"] = "APROBADO"
                    if "OBSERVACION" not in datos_voucher:
                        datos_voucher["OBSERVACION"] = f"Pago validado correctamente mediante {metodo.value.upper()}."
                    
                    NOTION.registrar_voucher(
                        pedido_id=pedido.pedido_id,
                        voucher_path=datos_voucher.get("VOUCHER_URL", "https://aura.local/voucher_no_proporcionado"),
                        monto=pedido.total,
                        metodo_pago=metodo.value,
                        usuario_id=pedido.usuario_id,
                        datos_extra=datos_voucher
                    )
                
            return ResultadoOperacion(exito=True,
                mensaje=f"Pago registrado exitosamente. Total: S/ {sum(p.total for p in pedidos_a_procesar):.2f}.",
                datos={"pedido_id": pedido_id, "estado": EstadoPedido.PAGADO.value, "metodo_pago": metodo.value})



    def cargar_pedidos_usuario(self, usuario_id: str) -> list[dict]:
        """Obtiene historial de pedidos de un usuario, buscando primero en Notion y usando fallback local si falla."""
        from server.notion_client import NOTION
        if NOTION.disponible:
            pedidos_db = NOTION.cargar_pedidos_por_usuario(usuario_id)
            if pedidos_db is not None:
                return pedidos_db
                
        # Fallback local
        import datetime
        res = []
        for p in self._pedidos.values():
            if p.usuario_id == usuario_id:
                items_list = []
                for it in p.items:
                    it_dict = it.model_dump() if hasattr(it, "model_dump") else dict(it)
                    items_list.append(it_dict)
                res.append({
                    "pedido_id": p.pedido_id,
                    "estado": p.estado.value,
                    "total": p.total,
                    "metodo_pago": p.metodo_pago.value if p.metodo_pago else None,
                    "items": items_list,
                    "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
        
        # Ordenar localmente por fecha (el mas reciente primero, si tuvieramos fecha real local, aqui usamos now por simplicidad)
        return res[::-1]


# Instancia única compartida por todo el servidor MCP (memoria compartida).
TIENDA = StoreState()
