# Metricas del sistema multi-agente

Reporte generado tras correr los escenarios de prueba.

## Resumen global

- Turnos atendidos: **11**
- Tasa de exito: **81.8%**
- Latencia (ms): avg **0.69** · p50 **0.52** · p95 **0.75** · max **2.34**
- Tokens estimados totales: **364**

## Latencia promedio por agente (ms)

| Agente | Latencia avg |
|---|---|
| catalogo | 1.49 |
| ventas | 0.54 |
| pagos | 0.49 |
| inventario | 0.5 |

## Detalle por turno

| # | Usuario | Mensaje | Agente | Intent | Tools | Lat. ms | Exito |
|---|---|---|---|---|---|---|---|
| 1 | u1 | Hola, quiero ver laptops menos de 4000 soles | catalogo | buscar_producto | buscar_productos | 2.3 | OK |
| 2 | u1 | Agrega 1 unidad de P001 al carrito | ventas | agregar_carrito | agregar_al_carrito, ver_carrito | 0.7 | OK |
| 3 | u1 | Muestra mi carrito | ventas | ver_carrito | ver_carrito | 0.4 | OK |
| 4 | u1 | Quiero pagar con yape | pagos | procesar_pago | crear_pedido, procesar_pago | 0.5 | OK |
| 1 | u2 | Tienes la Consola PlayBox X? | catalogo | buscar_producto | buscar_productos | 0.6 | OK |
| 2 | u2 | Verifica stock de P010 | inventario | verificar_stock | verificar_inventario | 0.5 | OK |
| 3 | u2 | Agrega P010 al carrito | ventas | agregar_carrito | agregar_al_carrito | 0.5 | FAIL |
| 1 | uA | Agrega P009 al carrito | ventas | agregar_carrito | agregar_al_carrito, ver_carrito | 0.6 | OK |
| 2 | uB | Agrega P009 al carrito | ventas | agregar_carrito | agregar_al_carrito, ver_carrito | 0.5 | OK |
| 3 | uA | Quiero crear pedido y pagar con tarjeta | pagos | procesar_pago | crear_pedido, procesar_pago | 0.5 | OK |
| 4 | uB | Quiero crear pedido y pagar con tarjeta | pagos | procesar_pago | crear_pedido | 0.4 | FAIL |
