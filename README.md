# AURA Boutique - Tienda Virtual Multi-Agente con Memoria Evolutiva

Bienvenido al repositorio principal de **AURA Boutique**, un sistema de tienda virtual impulsado por una arquitectura Multi-Agente avanzada (LangGraph), memoria a corto plazo (SQLite), memoria semántica a largo plazo (Notion CRM) y un Profiler Agent impulsado por LLM.

Este proyecto ha superado con éxito sus 3 fases arquitectónicas, consolidando una inteligencia artificial proactiva, asíncrona y segura.

---

## 🏗️ 1. Arquitectura Técnica (Fase 3 Completa)

Para conocer en detalle cómo funciona el motor bajo el capó, incluyendo:
- El flujo completo de **LangGraph**.
- El Checkpointer SQLite.
- La arquitectura asíncrona del **Profiler Agent**.
- El funcionamiento del **EventBus**.
- Mecanismos de seguridad como **Delta, Read-Modify-Write, Partial Update y Locks**.

📖 **Por favor lee nuestra documentación arquitectónica detallada aquí:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 🚀 2. Instalación y Despliegue Local (Quickstart)

Cualquier desarrollador puede levantar el proyecto desde cero siguiendo estos pasos. El backend (FastAPI) y el frontend (Archivos estáticos servidos por FastAPI) se ejecutan unificados en un solo puerto.

### Prerequisitos
- Python 3.11 o superior.
- Cuentas activas y credenciales (API Keys) de: **Groq**, **Notion**, y **Firebase**.

### Paso a paso

1. **Clonar el repositorio y entrar a la carpeta:**
   ```bash
   git clone <URL_DEL_REPO>
   cd tienda-mcp
   ```

2. **Crear y activar el entorno virtual:**
   ```powershell
   # En Windows
   python -m venv .venv
   .\.venv\Scripts\activate
   
   # En macOS/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Instalar dependencias:**
   Todas las dependencias (FastAPI, LangGraph, Notion, Firebase, Groq, Pydantic, etc.) están listadas en el requirements.
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar las variables de entorno:**
   Copia el archivo `.env.example` a `.env` o crea uno nuevo en la raíz del proyecto. **Debes** configurar las siguientes variables:

   ```env
   # API Keys de LLM
   GROQ_API_KEY="gsk_..."

   # Integración con Notion (CRM)
   NOTION_TOKEN="ntn_..."
   NOTION_CLIENTES_DB_ID="921a10870eb542ec8f9904653fd64233" # ID real de la base de datos (NO de la página)
   NOTION_ORDENES_DB_ID="3121746bc439802c9337eca5f43fef78"

   # Configuración de Firebase (Auth)
   FIREBASE_API_KEY="AIza..."
   FIREBASE_AUTH_DOMAIN="tu-proyecto.firebaseapp.com"
   FIREBASE_PROJECT_ID="tu-proyecto"
   ```

5. **Iniciar el servidor:**
   ```bash
   python -m web.api
   ```
   *(También puedes usar `uvicorn web.api:app --reload` para modo desarrollo).*

6. **Abrir la Tienda:**
   Entra en tu navegador a 👉 `http://localhost:8000`

---

## 📂 3. Estructura de Carpetas

```text
tienda-mcp/
├── agents/                 # Lógica de Inteligencia Artificial
│   ├── event_bus.py        # Patrón Pub/Sub para comunicación asíncrona
│   ├── agent.py            # Tools base y utilidades
│   └── profiler_agent.py   # Agente de Memoria Evolutiva (Fase 3)
├── docs/                   # Documentación del proyecto
│   └── ARCHITECTURE.md     # Detalle profundo del sistema E2E
├── graph/                  # LangGraph multi-agente
│   ├── builder.py          # Grafo, Nodos, Aristas e inyección de contexto
│   └── state.py            # AgentState y partición por hilos
├── scripts/                # Scripts utilitarios (diagnóstico y tests E2E)
├── server/                 # Lógica del servidor y clientes externos
│   ├── config.py           # Configuración tipada (Pydantic Settings)
│   └── notion_client.py    # Integración con la API de Notion (CRM)
├── web/                    # Capa de presentación y red
│   ├── api.py              # Endpoints FastAPI y Montaje del Frontend estático
│   ├── lc_adapter.py       # Puente LangGraph-FastAPI (Checkpointer SQLite)
│   └── static/             # Frontend (HTML, CSS, JS Vainilla)
├── .env                    # Configuración sensible local (Oculto en git)
└── requirements.txt        # Dependencias del proyecto Python
```

---

## 🛠️ 4. Dependencias Principales

Este proyecto aprovecha herramientas estado del arte para IA y web:
*   `fastapi` & `uvicorn`: Framework web de alto rendimiento.
*   `langgraph` & `langchain-groq`: Motor multi-agente y comunicación con LLMs rápidos.
*   `notion-client`: Manejo del estado permanente del negocio.
*   `firebase-admin`: Capa de seguridad y autenticación inmutable de identidad.
*   `pydantic`: Validación estricta de esquemas y herramientas.

*(Para más información de extensión y contribución, revisa `docs/ARCHITECTURE.md`)*
