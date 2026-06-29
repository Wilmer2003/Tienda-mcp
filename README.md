# Tienda Virtual con MCP + Sistema Multi-agente

Proyecto del curso **Automatización Inteligente de Procesos** (Ing. de
Sistemas e IA, 2026‑10). Construye un equipo de agentes especializados que
atienden a un cliente de una tienda de electrónica peruana, coordinándose a
través de un **servidor MCP** que expone la lógica de la tienda como tools
con schemas validados por Pydantic.

> **Stack**: Python 3.14 · MCP 1.27 · Pydantic 2 · pytest‑asyncio · arquitectura
> multi‑agente en topología **estrella** con orquestador central.

## 1. Arquitectura en una imagen

```
                       ┌───────────────────┐
                       │   CLIENTE / user  │
                       └─────────┬─────────┘
                                 │
                       ┌─────────▼─────────┐
                       │   ORQUESTADOR     │ ← clasifica intent, enruta,
                       │ (router central)  │   consolida respuesta final.
                       └─┬───┬───┬───┬───┬─┘
              ┌──────────┘   │   │   │   └──────────┐
              ▼              ▼   ▼   ▼              ▼
         ┌─────────┐  ┌──────────┐ ┌────────┐ ┌──────────┐
         │CATÁLOGO │  │INVENTARIO│ │ VENTAS │ │ SOPORTE  │
         └────┬────┘  └────┬─────┘ └───┬────┘ └────┬─────┘
              │            │      ┌────▼────┐     │
              │            │      │  PAGOS  │     │
              │            │      └────┬────┘     │
              └────────────┴───┬───────┴──────────┘
                               ▼  MCP tool calls (JSON schema validado)
                  ┌────────────────────────────┐
                  │  MCP SERVER (tienda)       │
                  │  9 tools · StoreState lock │
                  └────────────────────────────┘
        ┌────────────────────────────────────────────────────┐
        │ SHARED STATE → historial, sesiones, pizarra        │
        │ EVENT BUS    → stock.agotado, conflicto.stock, ... │
        └────────────────────────────────────────────────────┘
```

Detalle completo en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## 2. Estructura del repositorio

```
tienda-mcp/
├─ server/                    ← Servidor MCP (Paso 1)
│  ├─ mcp_server.py           ← 9 tools FastMCP
│  ├─ models.py               ← schemas Pydantic
│  ├─ store_logic.py          ← StoreState con threading.Lock
│  ├─ store_data.py           ← catálogo de 12 productos
│  └─ requirements.txt
├─ agents/                    ← Sistema multi-agente (Paso 2)
│  ├─ orchestrator.py         ← agente Orquestador
│  ├─ agent.py                ← clase base Agent
│  ├─ brain.py                ← motor híbrido (reglas + Claude opcional)
│  ├─ mcp_client.py           ← cliente in-process al MCP
│  ├─ shared_state.py         ← historial, sesiones, pizarra
│  ├─ event_bus.py            ← pub/sub para coordinar
│  ├─ metrics.py              ← latencia, tasa de éxito, tokens
│  ├─ subagents/              ← Catálogo, Inventario, Ventas, Pagos, Soporte
│  └─ prompts/                ← system prompts especializados (1 por agente)
├─ scripts/                   ← demos ejecutables
│  ├─ smoke_test.py           ← valida que el MCP carga
│  └─ run_escenarios.py       ← corre los 3 escenarios y genera métricas
├─ tests/                     ← suite con casos adversariales
├─ docs/
│  ├─ ARQUITECTURA.md         ← diagrama + decisiones + mapeo a rúbrica
│  ├─ METRICAS.md             ← reporte cuantitativo (autogenerado)
│  ├─ metricas.json
│  └─ DEMO.md                 ← guion para la exposición
└─ README.md
```

## 3. Instalación reproducible (Windows / PowerShell)

```powershell
# 1. Crear y activar entorno virtual
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
py -m pip install -r server\requirements.txt

# 3. Sanity check: el MCP carga sus 9 tools
$env:PYTHONIOENCODING = 'utf-8'
py -m scripts.smoke_test
```

En macOS/Linux:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
PYTHONIOENCODING=utf-8 python -m scripts.smoke_test
```

## 4. Cómo correr todo

```powershell
# (a) Tienda web con frontend visual — la demo "para personas normales"
py -m web.api
# luego abre http://localhost:8000 en el navegador

# (b) Servidor MCP standalone (stdio, para Antigravity / Claude Desktop)
py -m server.mcp_server

# (c) Los 3 escenarios del sistema multi-agente con metricas en consola
py -m scripts.run_escenarios

# (d) Suite de tests (10 casos, incluye adversariales)
py -m pytest -v
```

### Sobre la tienda web (`web/`)

`py -m web.api` levanta un servidor FastAPI en `http://localhost:8000` que sirve:

- `GET /` → tienda HTML (catálogo, carrito, chat)
- `GET /api/productos` → catálogo con stock en vivo
- `POST /api/chat` → envía un mensaje al orquestador; devuelve agente, intent, tools, latencia
- `GET /api/eventos` → últimos eventos del event bus (para el panel "Detrás de escena")
- `GET /api/carrito/{usuario_id}` → estado del carrito por usuario
- `GET /api/metricas` → resumen en vivo

El frontend (HTML/CSS/JS vanilla, sin Node) muestra:

- **Catálogo** con cards por producto, filtros por categoría, búsqueda y badge de stock.
- **Carrito** drawer lateral con total en vivo y botón Finalizar compra.
- **Asistente** con 3 pestañas:
  - *Chat* — habla en lenguaje natural con el orquestador; quick-actions con prompts pre-armados.
  - *Agentes* — resalta cuál de los 6 agentes está activo en el turno actual.
  - *Eventos* — timeline en tiempo real del event bus (stock.agotado, alternativa.sugerida, ...).
- **Botón "Detrás de escena"** que oculta/muestra el panel — ideal para alternar entre vista cliente y vista técnica durante la exposición.

## 5. Conectar el MCP a Antigravity / Claude Desktop

Añade este bloque al archivo de configuración MCP del cliente:

```json
{
  "mcpServers": {
    "tienda-virtual": {
      "command": "py",
      "args": ["-m", "server.mcp_server"],
      "cwd": "C:/Users/medin/Downloads/Corpus/tienda-mcp"
    }
  }
}
```

## 6. Tres escenarios que evidencian la rúbrica

### Escenario 1 — Camino feliz (Criterio 4: flujo iterativo)
```
[u1] Hola, quiero ver laptops menos de 4000 soles
   → catalogo: recomienda P001 Laptop UltraBook 14
[u1] Agrega 1 unidad de P001 al carrito
   → ventas: agrega + sugiere mouse P008 (upsell)
[u1] Muestra mi carrito
   → ventas: muestra carrito con total
[u1] Quiero pagar con yape
   → pagos: crea pedido ORD-XXXX + procesa pago → "aprobado vía yape"
```

### Escenario 2 — Producto agotado → alternativa (Criterio 4: condicional)
```
[u2] Verifica stock de P010 (Consola PlayBox X)
   → inventario: stock=0 → publica STOCK_AGOTADO
   → catalogo (suscrito al evento): propone P011 Volante Racing Pro
   → orquestador: consolida y agrega nota con alternativa
```

### Escenario 3 — Conflicto por stock = 1 (Criterio 3: resolución de conflictos)
```
[uA] Agrega P009 al carrito        (stock=1)
[uB] Agrega P009 al carrito        (en paralelo)
[uA] Crear pedido y pagar tarjeta  → OK
[uB] Crear pedido y pagar tarjeta  → FAIL: "Ya no hay stock suficiente"
```
El `threading.Lock` del StoreState garantiza un único ganador.

## 7. Métricas (autogeneradas por `scripts/run_escenarios.py`)

Última corrida — ver [docs/METRICAS.md](docs/METRICAS.md):

- Turnos atendidos: **11**
- Tasa de éxito: **81.8 %** (los 2 fallos son comportamiento correcto frente a stock agotado y conflicto).
- Latencia avg: **0.69 ms** · p95 **0.75 ms** · max **2.34 ms**.
- Tokens estimados totales: **364**.

## 8. Mapeo explícito a la rúbrica (20 pts)

| Criterio | Peso | Cómo lo cubre el proyecto |
|---|---:|---|
| **C1** Arquitectura multi-agente | 4 | Topología estrella justificada · orquestador + 5 subagentes con roles únicos sin solapamiento · diagrama en `docs/ARQUITECTURA.md` alineado 1:1 con la implementación. |
| **C2** Implementación Claude Code + Antigravity | 5 | Prompts especializados (`agents/prompts/*.md`) · grafo de agentes en `orchestrator.py` · memoria compartida (`shared_state.py`) · event bus (`event_bus.py`) · Brain híbrido (reglas + Claude opcional). |
| **C3** Comunicación y coordinación | 4 | MCP con schemas Pydantic en todas las tools · `StoreState.Lock` para concurrencia · historial preservado en `SharedState.historial()` · resolución de conflictos via event bus + lock. |
| **C4** Complejidad del caso | 2 | 5 flujos distintos: feliz, condicional (agotado→alternativa), paralelo (stock=1), iterativo (carrito multi-turno), adversarial (IDs malos, métodos inválidos). |
| **C5** Pruebas y documentación | 2 | 10 tests `pytest`, 6 adversariales · métricas cuantitativas autogeneradas · este README + `ARQUITECTURA.md` + `DEMO.md`. |
| **C6** Exposición y defensa | 3 | Guion paso a paso en `docs/DEMO.md` con tiempos y comandos exactos para correr en vivo. |

## 9. Cómo extender

- **Más agentes**: añade `agents/subagents/Xxx.py` heredando de `Agent`,
  registra en `orchestrator.INTENT_AGENTE` y crea su prompt en `prompts/`.
- **LLM real**: define `ANTHROPIC_API_KEY` y `pip install anthropic`.
  `agents/brain.py::crear_brain` detecta y conecta automáticamente.
- **Persistencia**: hoy el `StoreState` es in-memory. Para producción,
  sustituir por un repositorio SQL conservando la misma interfaz.
