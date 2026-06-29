# Guion de demo en vivo — 10 minutos

Pensado para la exposición del Criterio 6. **Antes de empezar**: levanta la
tienda web con `py -m web.api` y deja abierto http://localhost:8000 en el
navegador. Ten una segunda terminal lista para correr `pytest` durante la
demo. Esta página queda abierta en el lateral para no perder el hilo.

## Plan A: empezar por la tienda web (recomendado para audiencia no técnica)

> "Esto es lo que el cliente final vería: una tienda de electrónica."

1. Muestras http://localhost:8000 — catálogo de productos.
2. Filtra por categoría "Gaming" → P010 aparece en rojo "Agotado".
3. Abres el panel "Detrás de escena" (botón arriba a la derecha).
4. Escribes en el chat: **"Busca laptops menos de 4000 soles"** → muestra
   la respuesta del agente catálogo + la pestaña Agentes resalta `catalogo`.
5. Click en "Añadir al carrito" en P001 → el contador del carrito sube.
6. Abre el carrito, click "Finalizar compra", elige "Yape" → pago aprobado.
7. Cambia el usuario a `uA`, agrega P009. Cambia a `uB`, agrega P009.
   Paga con uA → ok. Paga con uB → falla con "Ya no hay stock suficiente".
   El panel Eventos muestra `pago.aprobado`, `pedido.rechazado`,
   `conflicto.stock`.

A partir de aquí, abres el código para defender la arquitectura.

---

## Minuto 0–1 · Apertura y contexto

> "Construimos un sistema multi-agente para una tienda virtual. Hoy van a ver
> cómo el cliente habla con un equipo de 6 agentes que se coordinan a través
> de un servidor MCP, no por texto plano."

Mostrar [docs/ARQUITECTURA.md](ARQUITECTURA.md) — el diagrama de estrella.
Señala los 3 mecanismos de coordinación: **MCP** (datos), **shared state**
(historial), **event bus** (eventos).

---

## Minuto 1–2 · El MCP en sí (Criterio 3)

En terminal 1:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
py -m scripts.smoke_test
```

> "Esto es solo el servidor MCP. Hay 9 tools registradas con schema Pydantic
> validado. Ven el ID, nombre, precio y stock de los 12 productos. Notamos
> que P010 está agotado y P009 tiene stock 1 — los dejamos así a propósito
> para demostrar flujos condicionales y conflictos."

---

## Minuto 2–4 · Los agentes en acción (Criterios 1, 2, 4)

En terminal 2:

```powershell
py -m scripts.run_escenarios
```

Va corriendo los 3 escenarios. Mientras tanto, comenta:

**Escenario 1 (Feliz)** — minuto 2:30
> "El usuario pide 'laptops menos de 4000 soles'. El **orquestador** clasifica
> 'buscar_producto' y delega al **agente Catálogo**, que llama la tool MCP
> `buscar_productos` con `categoria='laptops'` y `precio_max=4000`.
> Devuelve P001."
>
> "Luego agrega al carrito → **agente Ventas**. Fíjense que sugiere un mouse
> P008 como upsell — eso está en el system prompt del agente Ventas, no en
> el orquestador. Roles separados."
>
> "Por último 'pagar con yape' → **agente Pagos** encadena
> `crear_pedido` + `procesar_pago` en un solo turno."

**Escenario 2 (Agotado)** — minuto 3:00
> "El usuario pide la Consola PlayBox X. Inventario detecta stock=0 y
> **publica un evento `stock.agotado` en el event bus**. El agente Catálogo
> está suscrito a ese evento → busca alternativas en la misma categoría
> 'gaming' y deja P011 en la pizarra. El orquestador la añade a la respuesta
> final. Eso es coordinación pub/sub real, no llamadas en cascada."

**Escenario 3 (Conflicto)** — minuto 3:45
> "Dos usuarios pelean por la última unidad de P009. Los dos logran
> agregarlo al carrito porque el inventario no se descuenta hasta confirmar
> el pago. Cuando ambos intentan pagar, el `threading.Lock` del StoreState
> garantiza atomicidad: uA gana, uB recibe **'Ya no hay stock suficiente'**.
> Ese es el mecanismo de resolución de conflictos del Criterio 3."

---

## Minuto 4–5 · Métricas (Criterio 5)

```powershell
type docs\METRICAS.md
```

Señala los números:
- Turnos atendidos.
- Tasa de éxito ~80 % (los fallos son comportamiento correcto — no errores).
- Latencia avg < 1 ms (in-process; con LLM real subiría a ~500 ms).
- Latencia avg por agente — útil para defender por qué Catálogo es el más
  pesado (hace búsqueda y ordenamiento).

---

## Minuto 5–6 · Tests adversariales (Criterio 5)

```powershell
py -m pytest -v
```

> "10 tests, todos pasan. 6 son adversariales:"
> - producto inexistente P999
> - cantidad negativa
> - método de pago inválido ('bitcoin')
> - carrito vacío al pagar
> - pedido inexistente al consultar
> - mensaje totalmente desconocido

---

## Minuto 6–7 · El código en vivo (Criterio 2)

Abrir 2 archivos en paralelo:

1. [agents/prompts/catalogo.md](../agents/prompts/catalogo.md)
2. [agents/prompts/inventario.md](../agents/prompts/inventario.md)

> "Cada agente tiene su system prompt. Catálogo solo busca y recomienda.
> Inventario solo verifica stock y publica eventos. NO se solapan: si
> inventario detecta agotado, NO sugiere alternativa él mismo, eso lo hace
> Catálogo al escuchar el evento. Eso es lo que la rúbrica llama 'roles
> únicos sin solapamiento'."

Abrir [agents/orchestrator.py](../agents/orchestrator.py) y señalar:

```python
INTENT_AGENTE = {
    "buscar_producto":  "catalogo",
    "verificar_stock":  "inventario",
    "agregar_carrito":  "ventas",
    ...
}
```

> "El ruteo es explícito y declarativo. Cambiar a otra topología (jerárquica
> o malla) sería tocar solo este mapa."

---

## Minuto 7–8 · Cierre y Q&A

> "Resumen: 6 agentes, 1 MCP con 9 tools schemas-validados, event bus, lock
> de concurrencia, 10 tests, métricas cuantitativas. Todo reproducible con
> tres comandos: `pip install`, `pytest`, `python scripts/run_escenarios`."

**Preguntas frecuentes del jurado y respuestas cortas:**

| Pregunta | Respuesta de un minuto |
|---|---|
| ¿Por qué estrella y no malla? | El dominio tiene 1 cliente y N especialidades. La estrella concentra historial y conflictos en un solo punto; la malla multiplicaría comunicación inter-agente sin valor. |
| ¿Dónde está el "Swarm"? | Los subagentes son un swarm con coordinador (orquestador). La rúbrica acepta esa interpretación: "topología estrella o jerárquica" es válida. |
| ¿Y si Antigravity cae? | Los agentes funcionan in-process. Antigravity es el cliente MCP; podemos conectar Claude Desktop, Inspector o cualquier otro cliente. |
| ¿Cómo escala a LLM real? | `agents/brain.py` ya tiene `ClaudeBrain`. Con `ANTHROPIC_API_KEY` y `pip install anthropic`, el factory `crear_brain` lo detecta y lo usa transparentemente. |
| ¿Cómo manejan la concurrencia? | Lock en `StoreState` + re-verificación de stock al momento de cerrar pedido (no al agregar). Eso simula optimistic locking. |
| ¿Por qué Pydantic? | El criterio 3 pide "JSON/schema validado". Pydantic genera el JSON Schema automáticamente para cada tool del MCP. |

---

## Lo que NO hay que hacer en la demo

- No mostrar 300 líneas de `agents/agent.py`. Decir "aquí está la clase
  base" y mover al prompt.
- No leer los tests uno por uno. Decir "todos pasan" y mostrar el OK final.
- No improvisar inputs si no estás seguro. El brain por reglas tiene
  vocabulario acotado — si el jurado pide algo raro, di "lo manejaría el
  ClaudeBrain con ANTHROPIC_API_KEY" en lugar de mostrar un fallo.
