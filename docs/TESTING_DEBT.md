# Deuda Técnica de Testing (Testing Debt)

## Contexto
Durante la auditoría y migración hacia la arquitectura basada en **LangGraph + Groq (LLM)**, se detectó que la suite de pruebas automatizadas (ubicada en `tests/`) generaba falsos negativos.

## ¿Qué Pruebas Quedaron Obsoletas?
1. **Tests de Aserción Literal:** Pruebas como `test_flujo_conversacional_vestido` esperaban que el sistema respondiera estrictamente con IDs crudos (ej. `"P005"`).
2. **Tests de Enrutamiento Estricto:** Pruebas que validaban qué subagente exacto debía ejecutarse (`assert r.agente == "consultas"`). 

## ¿Por Qué Fallan Ahora?
El sistema antiguo era **determinístico** (basado en reglas o NLP básico). El sistema actual utiliza un modelo generativo dinámico que:
* Habla de forma natural y conversacional ("Tenemos varios vestidos, ¿cuál prefieres?" en lugar de escupir "P005").
* Enruta basándose en un razonamiento lógico interno del LLM Supervisor. El Supervisor podría considerar que "Buscar" es una tarea de "Ventas" si el contexto implica intención de compra.

## Estrategia de Testing para el Futuro
Para sistemas Stateful AI Agents, la metodología clásica de Pytest con aserciones literales (`==`) es frágil e inservible. En el futuro, se debe implementar una de las siguientes estrategias:

### 1. LLM-as-a-Judge (Evaluación Semántica)
En lugar de aserciones literales, se utiliza otro LLM (usualmente un modelo más pequeño y barato, o un prompt de evaluación estricto) que recibe la respuesta del bot y determina si cumplió el objetivo.
* *Test antiguo:* `assert "P005" in respuesta`
* *Test futuro:* `assert evaluador_llm(respuesta, "El bot debe mencionar que hay vestidos disponibles").exito == True`

### 2. Pruebas por Comportamiento y Estado (LangSmith)
En lugar de probar qué dice el bot, probar qué estado deja en la base de datos o en el Checkpointer.
* *Ejemplo:* Enviar "Quiero comprar la laptop". En lugar de verificar si responde "Ok, agregada", consultar directamente la API del `Carrito` y hacer el assert sobre el estado real de los datos transaccionales (`len(carrito.items) > 0`).

*Nota registrada durante la migración a Memoria Persistente. No borrar hasta que se rediseñe la suite.*
