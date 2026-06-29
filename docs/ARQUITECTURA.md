# Arquitectura del sistema multi-agente — Tienda Virtual

## 1. Visión general

El sistema atiende a un cliente de una tienda virtual de electrónica a través
de un equipo de **agentes especializados** que se coordinan mediante un
**orquestador central** y comparten estado a través de tres mecanismos:

1. **MCP Server** (`server/`) — fuente única de verdad sobre catálogo, stock,
   carritos y pedidos. Toda mutación de datos pasa por aquí.
2. **Memoria compartida** (`agents/shared_state.py`) — historial de
   conversación, sesión por usuario y contexto que los agentes leen/escriben.
3. **Event bus** (`agents/event_bus.py`) — los agentes publican eventos
   ("producto_agotado", "pedido_creado") y otros se suscriben para reaccionar.

## 2. Topología: estrella con orquestador

Elegimos **topología en estrella** porque:

- El dominio "tienda" tiene un punto de entrada único (el cliente) y múltiples
  especialidades aisladas (catálogo, inventario, pagos…) que no necesitan
  hablar entre sí directamente.
- Concentrar el ruteo en un orquestador permite preservar el **historial de
  conversación** completo y resolver conflictos en un solo punto, no
  distribuidos por toda la malla.
- Es la topología que más se acerca al patrón "Swarms con coordinador" que
  menciona la rúbrica (Criterio 2).

```
                       ┌───────────────────┐
                       │   CLIENTE / user  │
                       └─────────┬─────────┘
                                 │ turno de conversación
                                 ▼
                       ┌───────────────────┐
                       │   ORQUESTADOR     │  ← clasifica intención,
                       │ (router central)  │    enruta al subagente,
                       └─┬───┬───┬───┬───┬─┘    agrega resultados.
            ┌────────────┘   │   │   │   └────────────┐
            ▼                ▼   ▼   ▼                ▼
       ┌─────────┐    ┌──────────┐ ┌────────┐  ┌──────────┐
       │CATÁLOGO │    │INVENTARIO│ │ VENTAS │  │ SOPORTE  │
       │ (busca, │    │ (stock,  │ │(carrito│  │(estados, │
       │ recomi- │    │alternat- │ │ upsell)│  │ FAQ)     │
       │ enda)   │    │ ivas)    │ │        │  │          │
       └────┬────┘    └────┬─────┘ └───┬────┘  └────┬─────┘
            │              │           │            │
            │              │      ┌────▼─────┐      │
            │              │      │  PAGOS   │      │
            │              │      │(checkout,│      │
            │              │      │ métodos) │      │
            │              │      └────┬─────┘      │
            │              │           │            │
            └──────────────┴───┬───────┴────────────┘
                               │ MCP tool calls (stdio + JSON schema)
                               ▼
                  ┌────────────────────────────┐
                  │   MCP SERVER (tienda)      │
                  │   9 tools + Pydantic       │
                  │   + StoreState con Lock    │
                  └────────────────────────────┘

   Memoria compartida y Event Bus son transversales:
   ┌────────────────────────────────────────────────────┐
   │  SHARED STATE   →  historial, sesión usuario,      │
   │                    último intent, carrito en vivo  │
   │  EVENT BUS      →  pedidos.creado, stock.agotado,  │
   │                    pago.aprobado, conflicto.stock  │
   └────────────────────────────────────────────────────┘
```

## 3. Roles y responsabilidades (sin solapamiento)

| Agente | Responsabilidad única | Herramientas MCP que usa |
|---|---|---|
| **Orquestador** | Recibe el turno del usuario, clasifica intención, decide qué subagente responde, mantiene historial y publica eventos de control. **No llama herramientas MCP directamente.** | — |
| **Catálogo** | Búsqueda de productos, recomendaciones por rating/precio, filtrado por categoría. | `buscar_productos`, `obtener_producto` |
| **Inventario** | Verifica stock, propone alternativas si algo está agotado, publica `stock.agotado`. | `verificar_inventario`, `buscar_productos` |
| **Ventas** | Gestiona carrito del usuario: agregar/quitar, ver total, sugerir upsell. | `agregar_al_carrito`, `ver_carrito`, `vaciar_carrito` |
| **Pagos** | Convierte carrito en pedido, procesa pago, valida método de pago. | `crear_pedido`, `procesar_pago` |
| **Soporte** | Consulta estado de pedidos, responde sobre devoluciones/garantía, escala al orquestador si no sabe. | `consultar_pedido` |

Cada agente tiene un **system prompt único** en `agents/prompts/`. La
diferenciación de prompts es lo que premia el Criterio 2 como "Excelente".

## 4. Estado compartido y resolución de conflictos

Tres niveles de coordinación:

1. **A nivel de datos (MCP)** — el `StoreState` usa `threading.Lock` para que
   `agregar_al_carrito`, `crear_pedido` y `procesar_pago` sean atómicos.
   Si dos agentes piden la última unidad de P009 al mismo tiempo, solo uno
   gana y el otro recibe `exito=False`.
2. **A nivel de sesión (shared_state)** — el orquestador anota el último
   intent y el agente que respondió, para que el siguiente turno tenga
   contexto ("el cliente acaba de pedir un Samsung, no preguntes de nuevo").
3. **A nivel de eventos (event_bus)** — cuando inventario detecta
   `stock.agotado`, catálogo se suscribe y propone alternativas
   automáticamente, sin pasar por el orquestador.

## 5. Flujos no triviales que demostramos (Criterio 4)

- **Feliz**: busca laptop → recomienda → agrega → paga → confirma.
- **Condicional (agotado)**: cliente pide P010 → inventario detecta stock=0 →
  publica `stock.agotado` → catálogo propone P011 (misma categoría).
- **Concurrente (conflicto)**: dos sesiones piden P009 (stock=1) en paralelo →
  el lock garantiza un único ganador → el perdedor recibe la alternativa.
- **Iterativo (carrito multi-turno)**: cliente agrega varios productos en
  turnos distintos → ventas preserva el carrito → pagos lo cierra al final.
- **Adversarial**: ID inexistente, cantidad negativa, método de pago inválido,
  pedido ya pagado — todos retornan `ResultadoOperacion(exito=False, ...)`.

## 6. Mapeo a la rúbrica

| Criterio | Cómo lo cubrimos |
|---|---|
| C1 (4 pts) Arquitectura | Topología estrella justificada + 6 roles sin solapamiento + este diagrama + implementación 1:1. |
| C2 (5 pts) Implementación | Prompts especializados por agente (`agents/prompts/`), memoria compartida (`shared_state.py`), event bus (`event_bus.py`), grafo de agentes en `orchestrator.py`. |
| C3 (4 pts) Comunicación | MCP con schemas Pydantic + `StoreState.lock` + historial preservado en `shared_state.history`. |
| C4 (2 pts) Complejidad | 5 flujos descritos en §5: condicional, paralelo, iterativo, adversarial. |
| C5 (2 pts) Pruebas/docs | Suite `tests/test_flujos.py` + métricas en `docs/METRICAS.md` + este README. |
| C6 (3 pts) Exposición | Guion en `docs/DEMO.md` con tiempos y comandos. |
