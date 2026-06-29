"""
notion_client.py
================
Cliente de Notion para AURA Boutique. Fuente de datos OPCIONAL.

Reglas duras:
  - Si NOTION_API_KEY no esta -> el sistema funciona igual con datos locales.
  - Si una DB ID falta o devuelve error -> fallback silencioso, publicamos
    evento en el bus para que el panel "Detras de escena" lo muestre.
  - Toda escritura es BEST-EFFORT: si Notion esta caido, la tx local se
    completa de todos modos. La idea es "espejo de auditoria", no source-of-truth.

Eventos que publica:
  - notion.consulta.iniciada      (datos: {operacion, db})
  - notion.consulta.exitosa       (datos: {operacion, db, items?})
  - notion.consulta.fallida       (datos: {operacion, db, error})
  - notion.fallback.local         (datos: {motivo})  -- una vez al startup
                                                       si no hay API key.

Parser tolerante:
  - Acepta varios nombres de propiedad (ej. "nombre" o "Name" o "Title").
  - Tolera tipos no esperados (string vs rich_text vs title): se intenta
    extraer el valor en orden de probabilidad.

Esquema esperado por DB (todos los campos opcionales; lo que no este se
toma del local). Documentado en README.md tambien:

  PRODUCTOS              ORDENES                 SESSIONS
  ---------              -------                 --------
  id        (title)      pedido_id  (title)      usuario_id (title)
  nombre    (rich_text)  usuario_id (rich_text)  iniciada   (date)
  categoria (select)     total      (number)     ultimo_intent (rich_text)
  precio    (number)     estado     (select)     ultimo_agente (rich_text)
  marca     (rich_text)  metodo_pago(select)
  descripcion (rich_text)items      (rich_text JSON)
  rating    (number)     creado_en  (date)
  stock     (number)

  PROMPTS                BASE_CONOCIMIENTO       VOUCHERS
  -------                -----------------       --------
  agente   (title)       titulo     (title)      pedido_id (title)
  contenido (rich_text)  cuerpo     (rich_text)  archivo   (rich_text)
                         tags       (multi_select)usuario_id (rich_text)
                                                  subido_en (date)

  TRANSACCIONES_NIUBIZ (opcional)
  --------------------
  transaccion_id (title), pedido_id (rich_text), usuario_id (rich_text),
  estado (select), monto (number), moneda (select), metodo (select),
  authorization_code / transaction_date / card / brand / raw (rich_text),
  creado_en (date). Si falta esta DB, se usa ORDENES como auditoria.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from agents.event_bus import BUS, EventType
from server.config import SETTINGS

logger = logging.getLogger("notion")


# -------------------------------------------------------------------------
# Helpers de parsing tolerante
# -------------------------------------------------------------------------
def _get_prop(props: dict, *nombres: str) -> Optional[dict]:
    """Devuelve la primera propiedad cuyo nombre matchee (case-insensitive)."""
    if not props:
        return None
    low = {k.lower(): v for k, v in props.items()}
    for n in nombres:
        if n.lower() in low:
            return low[n.lower()]
    return None


def _texto(prop: Optional[dict]) -> str:
    """Extrae texto de una propiedad title / rich_text / select / etc."""
    if not prop:
        return ""
    tipo = prop.get("type", "")
    if tipo == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    if tipo == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
    if tipo == "select":
        sel = prop.get("select") or {}
        return sel.get("name", "") if sel else ""
    if tipo == "multi_select":
        return ", ".join(s.get("name", "") for s in prop.get("multi_select", []))
    if tipo == "url":
        return prop.get("url", "") or ""
    if tipo == "email":
        return prop.get("email", "") or ""
    if tipo == "phone_number":
        return prop.get("phone_number", "") or ""
    if tipo == "checkbox":
        return "true" if prop.get("checkbox") else ""
    if tipo == "number":
        n = prop.get("number")
        return str(n) if n is not None else ""
    if tipo == "date":
        d = prop.get("date") or {}
        return d.get("start", "") if d else ""
    return ""


# Categorias validas del catalogo local (deben coincidir con Categoria enum).
_CATEGORIAS_VALIDAS = {
    "polos", "pantalones", "vestidos", "calzado", "chaquetas", "accesorios",
}


def _inferir_categoria(cat_raw: str, nombre: str) -> str:
    """Si la categoria de Notion es generica (ej. 'ROPA'), la inferimos del
    nombre del producto. Asi PRODUCTOS de Notion con categoria 'ROPA' se
    mapean a polos / pantalones / vestidos / etc para que el agente Consultas
    pueda filtrarlos."""
    c = (cat_raw or "").strip().lower()
    if c in _CATEGORIAS_VALIDAS:
        return c
    n = (nombre or "").lower()
    if any(x in n for x in ("polo", "polera", "camiseta", "remera", "t-shirt")):
        return "polos"
    if any(x in n for x in ("jean", "pantalon", "chino", "short")):
        return "pantalones"
    if "vestido" in n:
        return "vestidos"
    if any(x in n for x in ("zapatill", "zapato", "sneaker", "mocasin",
                            "bota")):
        return "calzado"
    if any(x in n for x in ("chaqueta", "casaca", "abrigo", "blazer",
                            "saco")):
        return "chaquetas"
    return "accesorios"


def _numero(prop: Optional[dict], default: float = 0.0) -> float:
    if not prop:
        return default
    if prop.get("type") == "number":
        v = prop.get("number")
        return float(v) if v is not None else default
    txt = _texto(prop)
    try:
        return float(txt) if txt else default
    except ValueError:
        return default


# -------------------------------------------------------------------------
# Cliente
# -------------------------------------------------------------------------
class NotionClient:
    """Cliente singleton de Notion para la boutique."""

    _instance: Optional["NotionClient"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self) -> None:
        self._fallback_publicado = False
        self.ultimo_error: Optional[str] = None
        self._client = None
        # Cache database_id -> data_source_id. La API nueva de Notion
        # (2025-09-03) separa "databases" de "data_sources". Las queries van
        # por data_source. Cada DB tiene 1+ data_sources; usamos el primero.
        self._ds_cache: dict[str, str] = {}
        cfg = SETTINGS.notion
        if not cfg.habilitado:
            self._anunciar_fallback("NOTION_API_KEY no configurada")
            return
        try:
            from notion_client import Client
            self._client = Client(auth=cfg.api_key)
            logger.info("[notion] cliente inicializado")
        except ImportError:
            self._anunciar_fallback("paquete notion-client no instalado")
        except Exception as e:
            self._anunciar_fallback(f"error al inicializar: {e}")

    def _data_source_id(self, database_id: str) -> Optional[str]:
        """Resuelve el data_source_id primario de un database_id, con cache."""
        if not database_id or not self._client:
            return None
        if database_id in self._ds_cache:
            return self._ds_cache[database_id]
        try:
            db = self._client.databases.retrieve(database_id=database_id)
            sources = db.get("data_sources") or []
            if not sources:
                # API antigua: el database_id mismo sirve como data_source_id.
                self._ds_cache[database_id] = database_id
                return database_id
            ds_id = sources[0].get("id") or database_id
            self._ds_cache[database_id] = ds_id
            return ds_id
        except Exception as e:
            logger.error(f"[notion] resolver data_source_id: {e}")
            self.ultimo_error = str(e)
            return None

    def _query(self, database_id: str, **params: Any) -> Optional[dict]:
        """Query unificada: usa data_sources.query si esta disponible;
        si no, cae a databases.query (compat con notion-client viejos)."""
        if not self._client:
            return None
        # Intento moderno (data_sources.query)
        ds_id = self._data_source_id(database_id)
        if ds_id and hasattr(self._client, "data_sources"):
            try:
                return self._client.data_sources.query(
                    data_source_id=ds_id, **params)
            except Exception as e:
                self.ultimo_error = str(e)
                # cae al intento antiguo
        # Fallback antiguo (databases.query) por si el SDK lo expone
        if hasattr(self._client.databases, "query"):
            try:
                return self._client.databases.query(
                    database_id=database_id, **params)
            except Exception as e:
                self.ultimo_error = str(e)
        return None

    def _obtener_esquema(self, database_id: str) -> dict[str, dict]:
        """Obtiene el esquema de propiedades de una base de datos de Notion.
        Si databases.retrieve devuelve un esquema vacio (por permisos o version API),
        realiza una query rapida de la primera fila para extraer las propiedades
        directamente del primer resultado.
        """
        schema = {}
        if not self._client:
            return schema
        try:
            db = self._client.databases.retrieve(database_id=database_id)
            schema = db.get("properties") or {}
        except Exception as e:
            logger.warning(f"[notion] _obtener_esquema databases.retrieve error: {e}")
            
        if not schema:
            # Fallback: query a la primera fila para inferir propiedades
            try:
                resp = self._query(database_id, page_size=1)
                if resp and resp.get("results"):
                    first_row = resp["results"][0]
                    row_props = first_row.get("properties", {})
                    # Mapeamos al formato de esquema {nombre: {type: tipo}}
                    for name, val in row_props.items():
                        schema[name] = {"type": val.get("type", "rich_text")}
            except Exception as e:
                logger.warning(f"[notion] _obtener_esquema query fallback error: {e}")
                
        return schema

    # ------------ infra de eventos --------------
    def _anunciar_fallback(self, motivo: str) -> None:
        if self._fallback_publicado:
            return
        self._fallback_publicado = True
        self.ultimo_error = motivo
        try:
            BUS.publish(EventType.NOTION_FALLBACK_LOCAL,
                        publicado_por="notion", datos={"motivo": motivo})
        except Exception:
            pass
        logger.warning(f"[notion] fallback local: {motivo}")

    def _evento(self, tipo: EventType, op: str, db: Optional[str] = None,
                **extras: Any) -> None:
        BUS.publish(tipo, publicado_por="notion",
                    datos={"operacion": op, "db": db or "", **extras})

    @property
    def disponible(self) -> bool:
        return self._client is not None

    def estado(self) -> dict[str, Any]:
        """Diagnostico para el endpoint /api/notion/status."""
        cfg = SETTINGS.notion
        return {
            "habilitado":       cfg.habilitado,
            "conectado":        self.disponible,
            "dbs_configuradas": cfg.dbs_disponibles,
            "ultimo_error":     self.ultimo_error,
        }

    # ============================================================
    # LECTURAS
    # ============================================================
    def cargar_productos(self) -> Optional[list[dict[str, Any]]]:
        """Lee la DB PRODUCTOS y devuelve lista de dicts con el esquema
        del modelo `Producto`. Retorna None si no esta disponible o falla.
        """
        if not self.disponible:
            return None
        cfg = SETTINGS.notion
        if not cfg.db_productos:
            return None
        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "cargar_productos", db="productos")
        try:
            resp = self._query(cfg.db_productos)
            if resp is None:
                raise RuntimeError(self.ultimo_error or "query devolvio None")
            productos: list[dict[str, Any]] = []
            inventario: dict[str, int] = {}
            for row in resp.get("results", []):
                props = row.get("properties", {})
                # ID: aceptamos "id", "ID", "codigo", "ID-Producto", "SKU", "item"...
                pid = (_texto(_get_prop(props, "id", "ID", "codigo",
                                        "id-producto", "ID-Producto",
                                        "sku", "SKU", "item", "ITEM"))
                       or row.get("id", "")[:8])
                if not pid:
                    continue
                pid = pid.strip().upper()
                # Nombre: "Producto" (su DB) o "nombre/name/title"
                nombre = _texto(_get_prop(props, "producto", "Producto",
                                          "nombre", "name", "title"))
                # Categoria: "CATEGORIA"/multi_select o "categoria"
                categoria = (_texto(_get_prop(props, "categoria", "CATEGORIA",
                                              "category"))
                             or "accesorios").lower().strip()
                # Si la categoria es generica ("ROPA"), inferir desde el nombre.
                categoria = _inferir_categoria(categoria, nombre)
                # Precio: "PRECIO_FINAL" o "precio" o "precio_venta"
                precio = _numero(_get_prop(props, "precio_final", "PRECIO_FINAL",
                                           "precio", "price", "precio_venta"), 0.0)
                marca = _texto(_get_prop(props, "marca", "brand", "MARCA"))
                # Si la DB no tiene marca, derivamos del nombre o categoria.
                if not marca:
                    marca = "AURA"
                descripcion = _texto(_get_prop(props, "descripcion",
                                               "Descripcion", "description",
                                               "DESCRIPCION", "descr"))
                rating = _numero(_get_prop(props, "rating", "RATING",
                                           "calificacion"), 4.5)
                stock = int(_numero(_get_prop(props, "stock", "STOCK",
                                              "inventario", "unidades"), 0))
                p = {
                    "id":          pid,
                    "nombre":      nombre or pid,
                    "categoria":   categoria,
                    "precio":      precio,
                    "marca":       marca,
                    "descripcion": descripcion or "—",
                    "rating":      rating,
                }
                productos.append(p)
                inventario[pid] = stock
            self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                         "cargar_productos", db="productos",
                         items=len(productos))
            return [{"producto": p, "stock": inventario[p["id"]]} for p in productos]
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "cargar_productos", db="productos", error=str(e))
            logger.error(f"[notion] cargar_productos: {e}")
            return None

    def cargar_prompt(self, agente: str) -> Optional[str]:
        """Devuelve el system prompt de un agente desde la DB PROMPTS, o
        None para que el agente caiga al .md local.
        """
        if not self.disponible:
            return None
        cfg = SETTINGS.notion
        if not cfg.db_prompts:
            return None
        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "cargar_prompt", db="prompts", agente=agente)
        try:
            resp = self._query(
                cfg.db_prompts,
                filter={"property": "agente", "title": {"equals": agente}},
            )
            if resp is None:
                raise RuntimeError(self.ultimo_error or "query devolvio None")
            results = resp.get("results", [])
            if not results:
                self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                             "cargar_prompt", db="prompts",
                             error=f"sin prompt para {agente}")
                return None
            props = results[0].get("properties", {})
            texto = _texto(_get_prop(props, "contenido", "prompt", "body"))
            self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                         "cargar_prompt", db="prompts", agente=agente)
            return texto or None
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "cargar_prompt", db="prompts", error=str(e))
            return None

    def consultar_kb(self, query: str, limite: int = 5) -> Optional[list[dict]]:
        """Busca articulos en BASE_DE_CONOCIMIENTO cuyo titulo o cuerpo
        contengan `query`. Util para preguntas de devoluciones/garantia/etc.
        """
        if not self.disponible:
            return None
        cfg = SETTINGS.notion
        if not cfg.db_base_conocimiento:
            return None
        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "consultar_kb", db="base_conocimiento", query=query)
        try:
            resp = self._query(
                cfg.db_base_conocimiento,
                page_size=max(1, min(limite, 25)),
            )
            if resp is None:
                raise RuntimeError(self.ultimo_error or "query devolvio None")
            articulos = []
            q = (query or "").lower().strip()
            for row in resp.get("results", []):
                props = row.get("properties", {})
                titulo = _texto(_get_prop(props, "titulo", "title", "name"))
                cuerpo = _texto(_get_prop(props, "cuerpo", "body", "contenido"))
                tags = _texto(_get_prop(props, "tags", "etiquetas"))
                if q and q not in (titulo + " " + cuerpo + " " + tags).lower():
                    continue
                articulos.append({"titulo": titulo, "cuerpo": cuerpo, "tags": tags})
                if len(articulos) >= limite:
                    break
            self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                         "consultar_kb", db="base_conocimiento",
                         items=len(articulos))
            return articulos
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "consultar_kb", db="base_conocimiento", error=str(e))
            return None

    # ============================================================
    # ESCRITURAS (best-effort)
    # ============================================================
    def crear_pedido(self, pedido_id: str, usuario_id: str, total: float,
                     estado: str, items: list[dict],
                     metodo_pago: Optional[str] = None) -> bool:
        """Espeja o actualiza un pedido en la DB ORDENES con tolerancia e idempotencia. No bloquea si falla."""
        if not self.disponible:
            return False
        cfg = SETTINGS.notion
        if not cfg.db_ordenes:
            return False
        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "crear_pedido", db="ordenes", pedido_id=pedido_id)
        try:
            # 1. Obtener schema para saber qué propiedades existen y cuál es el title
            db = self._client.databases.retrieve(database_id=cfg.db_ordenes)
            schema = db.get("properties", {})
            title_prop = next(
                (name for name, val in schema.items() if val.get("type") == "title"),
                "pedido_id",
            )
            
            # 2. Buscar si ya existe el pedido
            resp = self._query(
                cfg.db_ordenes,
                filter={"property": title_prop, "title": {"equals": pedido_id}},
                page_size=1
            )
            results = resp.get("results", []) if resp else []
            
            # 3. Preparar propiedades
            props: dict[str, dict] = {}
            
            # usuario_id
            for usr_name in ["usuario_id", "usuario", "user_id"]:
                if usr_name in schema:
                    props[usr_name] = {"rich_text": [{"text": {"content": usuario_id}}]}
                    break
                    
            # total
            for tot_name in ["total", "monto", "total_pago"]:
                if tot_name in schema:
                    props[tot_name] = {"number": float(total)}
                    break
                    
            # estado
            for est_name in ["estado", "status", "state"]:
                if est_name in schema:
                    props[est_name] = {"select": {"name": estado}}
                    break
                    
            # items
            for items_name in ["items", "productos", "pedido_items"]:
                if items_name in schema:
                    props[items_name] = {"rich_text": [{"text": {
                        "content": json.dumps(items, ensure_ascii=False)[:1900]
                    }}]}
                    break
                    
            # metodo_pago
            if metodo_pago:
                for met_name in ["metodo_pago", "metodo", "payment_method"]:
                    if met_name in schema:
                        props[met_name] = {"select": {"name": metodo_pago}}
                        break
                        
            # creado_en
            for date_name in ["creado_en", "fecha", "date", "created_at"]:
                if date_name in schema:
                    if not results:
                        props[date_name] = {"date": {"start": datetime.now(timezone.utc).isoformat()}}
                    break
            
            if results:
                page_id = results[0]["id"]
                self._client.pages.update(page_id=page_id, properties=props)
                self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                             "actualizar_pedido", db="ordenes", pedido_id=pedido_id)
            else:
                props[title_prop] = {"title": [{"text": {"content": pedido_id}}]}
                self._client.pages.create(
                    parent={"database_id": cfg.db_ordenes},
                    properties=props,
                )
                self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                             "crear_pedido", db="ordenes", pedido_id=pedido_id)
            return True
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "crear_pedido", db="ordenes", error=str(e))
            logger.error(f"[notion] crear_pedido error: {e}")
            return False

    def crear_sesion(self, usuario_id: str, ultimo_intent: str = "",
                      ultimo_agente: str = "", contexto: Optional[dict] = None) -> bool:
        """Registra o actualiza una sesion de cliente en la DB SESSIONS (Upsert)."""
        if not self.disponible:
            return False
        cfg = SETTINGS.notion
        if not cfg.db_sessions:
            return False
        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "crear_sesion", db="sessions", usuario=usuario_id)
        try:
            # 1. Obtener schema para saber qué propiedades existen y cuál es el title
            db = self._client.databases.retrieve(database_id=cfg.db_sessions)
            schema = db.get("properties", {})
            title_prop = next(
                (name for name, val in schema.items() if val.get("type") == "title"),
                "usuario_id",
            )
            
            # 2. Buscar si ya existe una página para este usuario
            resp = self._query(
                cfg.db_sessions,
                filter={"property": title_prop, "title": {"equals": usuario_id}},
                page_size=1
            )
            results = resp.get("results", []) if resp else []
            ctx_str = json.dumps(contexto, ensure_ascii=False) if contexto else "{}"
            
            # 3. Preparar propiedades deseadas tolerando el schema real
            props: dict[str, dict] = {}
            
            # iniciada / fecha
            for date_name in ["iniciada", "fecha", "date", "created_at"]:
                if date_name in schema:
                    props[date_name] = {"date": {"start": datetime.now(timezone.utc).isoformat()}}
                    break
                    
            # ultimo_intent
            for intent_name in ["ultimo_intent", "intent", "last_intent"]:
                if intent_name in schema:
                    props[intent_name] = {"rich_text": [{"text": {"content": ultimo_intent}}]}
                    break
                    
            # ultimo_agente
            for agent_name in ["ultimo_agente", "agente", "last_agent"]:
                if agent_name in schema:
                    props[agent_name] = {"rich_text": [{"text": {"content": ultimo_agente}}]}
                    break
                    
            # contexto
            for ctx_name in ["contexto", "context", "data"]:
                if ctx_name in schema:
                    props[ctx_name] = {"rich_text": [{"text": {"content": ctx_str[:1900]}}]}
                    break
            
            if results:
                page_id = results[0]["id"]
                self._client.pages.update(page_id=page_id, properties=props)
                self._evento(EventType.NOTION_CONSULTA_EXITOSA, "actualizar_sesion", db="sessions")
            else:
                props[title_prop] = {"title": [{"text": {"content": usuario_id}}]}
                self._client.pages.create(parent={"database_id": cfg.db_sessions}, properties=props)
                self._evento(EventType.NOTION_CONSULTA_EXITOSA, "crear_sesion", db="sessions")
            return True
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "crear_sesion", db="sessions", error=str(e))
            logger.error(f"[notion] crear_sesion error: {e}")
            return False

    def cargar_sesion_desde_notion(self, usuario_id: str) -> Optional[dict[str, Any]]:
        """Busca el ultimo registro de sesion del usuario en Notion."""
        if not self.disponible:
            return None
        cfg = SETTINGS.notion
        if not cfg.db_sessions:
            return None
        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "cargar_sesion", db="sessions", usuario=usuario_id)
        try:
            # 1. Obtener schema para saber qué propiedades existen y cuál es el title
            db = self._client.databases.retrieve(database_id=cfg.db_sessions)
            schema = db.get("properties", {})
            title_prop = next(
                (name for name, val in schema.items() if val.get("type") == "title"),
                "usuario_id",
            )
            
            # Intentar con sort
            resp = None
            try:
                resp = self._query(
                    cfg.db_sessions,
                    filter={"property": title_prop, "title": {"equals": usuario_id}},
                    sorts=[{"property": "iniciada", "direction": "descending"}],
                    page_size=5
                )
            except Exception:
                pass
            
            # Fallback sin sort
            if resp is None:
                resp = self._query(
                    cfg.db_sessions,
                    filter={"property": title_prop, "title": {"equals": usuario_id}},
                    page_size=20
                )
                
            if resp is None:
                raise RuntimeError(self.ultimo_error or "query devolvio None")
                
            results = resp.get("results", [])
            if not results:
                self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                             "cargar_sesion", db="sessions", items=0)
                return None
            
            # Si no se ordeno por la API, ordenamos por fecha localmente
            def get_iniciada(row):
                props = row.get("properties", {})
                d = _texto(_get_prop(props, "iniciada"))
                if d:
                    return d
                return row.get("created_time", "")
                
            results = sorted(results, key=get_iniciada, reverse=True)
            
            props = results[0].get("properties", {})
            ultimo_intent = _texto(_get_prop(props, "ultimo_intent", "intent", "last_intent"))
            ultimo_agente = _texto(_get_prop(props, "ultimo_agente", "agente", "last_agent"))
            ctx_str = _texto(_get_prop(props, "contexto", "context", "data"))
            
            contexto = {}
            if ctx_str:
                try:
                    contexto = json.loads(ctx_str)
                except Exception:
                    pass
            
            self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                         "cargar_sesion", db="sessions", items=1)
            return {
                "ultimo_intent": ultimo_intent,
                "ultimo_agente": ultimo_agente,
                "contexto": contexto
            }
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "cargar_sesion", db="sessions", error=str(e))
            logger.error(f"[notion] cargar_sesion_desde_notion: {e}")
            return None

    def guardar_sesion(self, usuario_id: str, contexto: dict) -> bool:
        """Espeja o registra el contexto de sesion del usuario en Notion."""
        ultimo_intent = contexto.get("ultimo_intent", "") if contexto else ""
        ultimo_agente = contexto.get("ultimo_agente", "") if contexto else ""
        return self.crear_sesion(
            usuario_id=usuario_id,
            ultimo_intent=ultimo_intent,
            ultimo_agente=ultimo_agente,
            contexto=contexto
        )

    def registrar_order(self, pedido: Any) -> bool:
        """Registra un pedido completo en la DB de Notion."""
        if not self.disponible:
            return False
        # Mapea los items del pedido a dict
        items_dict = []
        for i in pedido.items:
            if hasattr(i, "model_dump"):
                items_dict.append(i.model_dump())
            elif hasattr(i, "dict"):
                items_dict.append(i.dict())
            else:
                items_dict.append(dict(i))
                
        metodo_val = None
        if pedido.metodo_pago:
            metodo_val = pedido.metodo_pago.value if hasattr(pedido.metodo_pago, "value") else str(pedido.metodo_pago)
            
        estado_val = pedido.estado.value if hasattr(pedido.estado, "value") else str(pedido.estado)
        
        return self.crear_pedido(
            pedido_id=pedido.pedido_id,
            usuario_id=pedido.usuario_id,
            total=pedido.total,
            estado=estado_val,
            items=items_dict,
            metodo_pago=metodo_val
        )

    def actualizar_order(self, pedido_id: str, estado: str, datos: Optional[dict] = None) -> bool:
        """Actualiza el estado y datos de un pedido existente en Notion."""
        if not self.disponible:
            return False
        cfg = SETTINGS.notion
        if not cfg.db_ordenes:
            return False
        self._evento(EventType.NOTION_CONSULTA_INICIADA, "actualizar_order", db="ordenes", pedido_id=pedido_id)
        try:
            # 1. Obtener schema para saber qué propiedades existen y cuál es el title
            db = self._client.databases.retrieve(database_id=cfg.db_ordenes)
            schema = db.get("properties", {})
            title_prop = next(
                (name for name, val in schema.items() if val.get("type") == "title"),
                "pedido_id",
            )
            
            # Buscar la página por pedido_id
            resp = self._query(
                cfg.db_ordenes,
                filter={"property": title_prop, "title": {"equals": pedido_id}},
                page_size=1
            )
            if not resp or not resp.get("results"):
                logger.warning(f"[notion] actualizar_order: pedido {pedido_id} no encontrado para actualizar.")
                return False
            
            page_id = resp["results"][0]["id"]
            
            # 2. Preparar propiedades a actualizar
            properties = {}
            for est_name in ["estado", "status", "state"]:
                if est_name in schema:
                    properties[est_name] = {"select": {"name": estado}}
                    break
                    
            if datos:
                if "total" in datos:
                    for tot_name in ["total", "monto", "total_pago"]:
                        if tot_name in schema:
                            properties[tot_name] = {"number": float(datos["total"])}
                            break
                if "metodo_pago" in datos and datos["metodo_pago"]:
                    for met_name in ["metodo_pago", "metodo", "payment_method"]:
                        if met_name in schema:
                            properties[met_name] = {"select": {"name": str(datos["metodo_pago"])}}
                            break
                if "items" in datos and datos["items"]:
                    for items_name in ["items", "productos", "pedido_items"]:
                        if items_name in schema:
                            properties[items_name] = {"rich_text": [{"text": {
                                "content": json.dumps(datos["items"], ensure_ascii=False)[:1900]
                            }}]}
                            break
            
            self._client.pages.update(page_id=page_id, properties=properties)
            self._evento(EventType.NOTION_CONSULTA_EXITOSA, "actualizar_order", db="ordenes", pedido_id=pedido_id)
            return True
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA, "actualizar_order", db="ordenes", error=str(e))
            logger.error(f"[notion] actualizar_order error: {e}")
            return False

    def actualizar_stock_producto(self, producto_id: str, nuevo_stock: int) -> bool:
        """Actualiza el stock de un producto en la DB PRODUCTOS de Notion."""
        if not self.disponible:
            return False
        cfg = SETTINGS.notion
        if not cfg.db_productos:
            return False
        self._evento(EventType.NOTION_CONSULTA_INICIADA, "actualizar_stock_producto", db="productos", producto_id=producto_id)
        try:
            # 1. Obtener schema para saber qué propiedades existen y cuál es el title
            db = self._client.databases.retrieve(database_id=cfg.db_productos)
            schema = db.get("properties", {})
            
            # Buscamos el nombre de la propiedad ID (id, ID, codigo, SKU, etc)
            low_schema = {k.lower(): k for k in schema.keys()}
            id_prop = None
            for name in ["id", "ID", "codigo", "id-producto", "ID-Producto", "sku", "SKU", "item", "ITEM"]:
                if name.lower() in low_schema:
                    id_prop = low_schema[name.lower()]
                    break
            
            if not id_prop:
                # Si no encontramos propiedad id, buscamos la title
                id_prop = next(
                    (name for name, val in schema.items() if val.get("type") == "title"),
                    "id",
                )
            
            # 2. Buscar si existe el producto por su ID
            prop_type = schema.get(id_prop, {}).get("type", "")
            filter_query = {}
            if prop_type == "title":
                filter_query = {"property": id_prop, "title": {"equals": producto_id.upper()}}
            elif prop_type == "rich_text":
                filter_query = {"property": id_prop, "rich_text": {"equals": producto_id.upper()}}
            else:
                filter_query = {"property": id_prop, "title": {"equals": producto_id.upper()}}
                
            resp = self._query(
                cfg.db_productos,
                filter=filter_query,
                page_size=1
            )
            results = resp.get("results", []) if resp else []
            if not results and prop_type != "rich_text":
                # Intentar buscar por rich_text si fallo
                try:
                    resp = self._query(
                        cfg.db_productos,
                        filter={"property": id_prop, "rich_text": {"equals": producto_id.upper()}},
                        page_size=1
                    )
                    results = resp.get("results", []) if resp else []
                except Exception:
                    pass

            if not results:
                logger.warning(f"[notion] actualizar_stock_producto: producto {producto_id} no encontrado en Notion.")
                return False
                
            page_id = results[0]["id"]
            
            # 3. Encontrar la propiedad de stock
            stock_prop = None
            for name in ["stock", "STOCK", "inventario", "unidades"]:
                if name.lower() in low_schema:
                    stock_prop = low_schema[name.lower()]
                    break
            if not stock_prop:
                stock_prop = "stock"
                
            # 4. Actualizar la página con el nuevo stock
            props = {
                stock_prop: {"number": int(nuevo_stock)}
            }
            self._client.pages.update(page_id=page_id, properties=props)
            self._evento(EventType.NOTION_CONSULTA_EXITOSA, "actualizar_stock_producto", db="productos", producto_id=producto_id)
            return True
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA, "actualizar_stock_producto", db="productos", error=str(e))
            logger.error(f"[notion] actualizar_stock_producto error: {e}")
            return False

    def registrar_voucher(self, pedido_id: str, voucher_path: str, monto: float, metodo_pago: str, usuario_id: str = "") -> bool:
        """Registra un voucher de pago completo en Notion con soporte para múltiples esquemas e idempotencia."""
        if not self.disponible:
            return False
        cfg = SETTINGS.notion
        if not cfg.db_vouchers:
            return False
        self._evento(EventType.NOTION_CONSULTA_INICIADA, "registrar_voucher", db="vouchers", pedido=pedido_id)
        try:
            # Obtener el esquema para hacer un mapeo tolerante
            db = self._client.databases.retrieve(database_id=cfg.db_vouchers)
            schema = db.get("properties", {})
            
            title_prop = next(
                (name for name, val in schema.items() if val.get("type") == "title"),
                "pedido_id",
            )
            
            # Buscar existente para evitar duplicados
            existente = self.buscar_voucher_por_pedido(pedido_id)
            page_id = existente.get("page_id") if existente else None
            
            props: dict[str, dict] = {}
            
            # 1. Archivo / voucher_path
            for path_name in ["archivo", "voucher_path", "file", "path"]:
                if path_name in schema:
                    props[path_name] = {"rich_text": [{"text": {"content": voucher_path}}]}
                    break
            else:
                rt_prop = next(
                    (name for name, val in schema.items() if val.get("type") == "rich_text" and name not in (title_prop, "usuario_id", "metodo_pago")),
                    "archivo"
                )
                props[rt_prop] = {"rich_text": [{"text": {"content": voucher_path}}]}
                
            # 2. Usuario
            for usr_name in ["usuario_id", "usuario", "user_id"]:
                if usr_name in schema:
                    props[usr_name] = {"rich_text": [{"text": {"content": usuario_id}}]}
                    break
            
            # 3. Monto / Total
            for amt_name in ["monto", "monto_total", "total", "amount"]:
                if amt_name in schema:
                    props[amt_name] = {"number": float(monto)}
                    break
            
            # 4. Método Pago
            for pay_name in ["metodo_pago", "metodo", "payment_method"]:
                if pay_name in schema:
                    props[pay_name] = {"select": {"name": metodo_pago.lower()}}
                    break
            
            # 5. Fecha / Subido en
            for date_name in ["subido_en", "fecha", "date", "created_at"]:
                if date_name in schema:
                    if not page_id: # Solo setear si es nuevo
                        props[date_name] = {"date": {"start": datetime.now(timezone.utc).isoformat()}}
                    break
                    
            if page_id:
                self._client.pages.update(
                    page_id=page_id,
                    properties=props,
                )
                self._evento(EventType.NOTION_CONSULTA_EXITOSA, "actualizar_voucher", db="vouchers")
            else:
                props[title_prop] = {"title": [{"text": {"content": pedido_id}}]}
                self._client.pages.create(
                    parent={"database_id": cfg.db_vouchers},
                    properties=props,
                )
                self._evento(EventType.NOTION_CONSULTA_EXITOSA, "registrar_voucher", db="vouchers")
            return True
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA, "registrar_voucher", db="vouchers", error=str(e))
            logger.error(f"[notion] registrar_voucher error: {e}")
            return self.crear_voucher(pedido_id=pedido_id, archivo=voucher_path, usuario_id=usuario_id)

    def buscar_voucher_por_pedido(self, pedido_id: str) -> Optional[dict[str, Any]]:
        """Busca un voucher registrado en Notion para un pedido específico."""
        if not self.disponible:
            return None
        cfg = SETTINGS.notion
        if not cfg.db_vouchers:
            return None
        self._evento(EventType.NOTION_CONSULTA_INICIADA, "buscar_voucher", db="vouchers", pedido=pedido_id)
        try:
            db = self._client.databases.retrieve(database_id=cfg.db_vouchers)
            schema = db.get("properties", {})
            title_prop = next(
                (name for name, val in schema.items() if val.get("type") == "title"),
                "pedido_id",
            )
            
            resp = self._query(
                cfg.db_vouchers,
                filter={"property": title_prop, "title": {"equals": pedido_id}},
                page_size=1
            )
            if not resp or not resp.get("results"):
                self._evento(EventType.NOTION_CONSULTA_EXITOSA, "buscar_voucher", db="vouchers", items=0)
                return None
                
            page_id = resp["results"][0]["id"]
            props = resp["results"][0]["properties"]
            voucher_path = ""
            for path_name in ["archivo", "voucher_path", "file", "path"]:
                val = _texto(_get_prop(props, path_name))
                if val:
                    voucher_path = val
                    break
                    
            monto = 0.0
            for amt_name in ["monto", "monto_total", "total", "amount"]:
                val = _numero(_get_prop(props, amt_name))
                if val:
                    monto = val
                    break
                    
            metodo = ""
            for pay_name in ["metodo_pago", "metodo", "payment_method"]:
                val = _texto(_get_prop(props, pay_name))
                if val:
                    metodo = val
                    break
                    
            usr = _texto(_get_prop(props, "usuario_id", "usuario", "user_id"))
            
            self._evento(EventType.NOTION_CONSULTA_EXITOSA, "buscar_voucher", db="vouchers", items=1)
            return {
                "page_id": page_id,
                "pedido_id": pedido_id,
                "voucher_path": voucher_path,
                "monto": monto,
                "metodo_pago": metodo,
                "usuario_id": usr
            }
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA, "buscar_voucher", db="vouchers", error=str(e))
            logger.error(f"[notion] buscar_voucher_por_pedido error: {e}")
            return None

    def crear_voucher(self, pedido_id: str, archivo: str,
                      usuario_id: str = "") -> bool:
        """Registra un voucher subido en la DB VOUCHERS."""
        if not self.disponible:
            return False
        cfg = SETTINGS.notion
        if not cfg.db_vouchers:
            return False
        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "crear_voucher", db="vouchers", pedido=pedido_id)
        try:
            self._client.pages.create(
                parent={"database_id": cfg.db_vouchers},
                properties={
                    "pedido_id":  {"title": [{"text": {"content": pedido_id}}]},
                    "archivo":    {"rich_text": [{"text": {"content": archivo}}]},
                    "usuario_id": {"rich_text": [{"text": {"content": usuario_id}}]},
                    "subido_en":  {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                },
            )
            self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                         "crear_voucher", db="vouchers")
            return True
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "crear_voucher", db="vouchers", error=str(e))
            return False

    def crear_transaccion_niubiz(self, transaccion: dict[str, Any]) -> bool:
        """Registra una transaccion Niubiz en Notion.

        Usa NOTION_TRANSACCIONES_NIUBIZ_DB_ID si existe. Si no, cae a la DB
        ORDENES como fila de auditoria para aprovechar lo que ya esta creado.
        """
        if not self.disponible:
            return False
        cfg = SETTINGS.notion
        db_id = cfg.db_transacciones_niubiz or cfg.db_ordenes
        if not db_id:
            return False

        usa_db_dedicada = bool(cfg.db_transacciones_niubiz)
        db_name = "transacciones_niubiz" if usa_db_dedicada else "ordenes"
        pedido_id = str(transaccion.get("pedido_id") or "")
        status = str(transaccion.get("status") or "unknown")
        tx_id = (
            str(transaccion.get("transaction_id") or "")
            or str(transaccion.get("ecore_transaction_uuid") or "")
            or f"NIUBIZ-{pedido_id}-{status}"
        )
        raw = json.dumps(transaccion, ensure_ascii=False, default=str)[:1900]

        self._evento(EventType.NOTION_CONSULTA_INICIADA,
                     "crear_transaccion_niubiz", db=db_name,
                     pedido_id=pedido_id)
        try:
            if usa_db_dedicada:
                desired = {
                    "transaccion_id": {"title": [{"text": {"content": tx_id}}]},
                    "pedido_id": {"rich_text": [{"text": {"content": pedido_id}}]},
                    "usuario_id": {"rich_text": [{"text": {"content": str(transaccion.get("usuario_id") or "")}}]},
                    "estado": {"select": {"name": status}},
                    "monto": {"number": float(transaccion.get("amount") or 0)},
                    "moneda": {"select": {"name": str(transaccion.get("currency") or "PEN")}},
                    "metodo": {"select": {"name": "niubiz"}},
                    "merchant_id": {"rich_text": [{"text": {"content": str(transaccion.get("merchant_id") or "")}}]},
                    "authorization_code": {"rich_text": [{"text": {"content": str(transaccion.get("authorization_code") or "")}}]},
                    "trace_number": {"rich_text": [{"text": {"content": str(transaccion.get("trace_number") or "")}}]},
                    "transaction_date": {"rich_text": [{"text": {"content": str(transaccion.get("transaction_date") or "")}}]},
                    "card": {"rich_text": [{"text": {"content": str(transaccion.get("card") or "")}}]},
                    "brand": {"rich_text": [{"text": {"content": str(transaccion.get("brand") or "")}}]},
                    "raw": {"rich_text": [{"text": {"content": raw}}]},
                    "creado_en": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                }
                self._crear_pagina_tolerante(
                    db_id, desired, title_fallback=tx_id)
            else:
                audit_id = f"TX-NIUBIZ-{pedido_id}-{status}"
                self._client.pages.create(
                    parent={"database_id": db_id},
                    properties={
                        "pedido_id": {"title": [{"text": {"content": audit_id}}]},
                        "usuario_id": {"rich_text": [{"text": {"content": str(transaccion.get("usuario_id") or "")}}]},
                        "total": {"number": float(transaccion.get("amount") or 0)},
                        "estado": {"select": {"name": "pagado" if status == "Authorized" else "cancelado"}},
                        "metodo_pago": {"select": {"name": "niubiz"}},
                        "items": {"rich_text": [{"text": {"content": raw}}]},
                        "creado_en": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                    },
                )
            self._evento(EventType.NOTION_CONSULTA_EXITOSA,
                         "crear_transaccion_niubiz", db=db_name,
                         pedido_id=pedido_id)
            return True
        except Exception as e:
            self.ultimo_error = str(e)
            self._evento(EventType.NOTION_CONSULTA_FALLIDA,
                         "crear_transaccion_niubiz", db=db_name,
                         error=str(e))
            return False

    def _crear_pagina_tolerante(self, database_id: str,
                                desired: dict[str, dict],
                                title_fallback: str) -> None:
        """Crea una pagina usando solo propiedades existentes en la DB.

        Esto permite que la hoja de transacciones tenga nombres ligeramente
        distintos; siempre llenamos la propiedad title real de la DB.
        """
        db = self._client.databases.retrieve(database_id=database_id)
        schema = db.get("properties", {})
        title_prop = next(
            (name for name, val in schema.items() if val.get("type") == "title"),
            "transaccion_id",
        )
        props: dict[str, dict] = {}
        for name, value in desired.items():
            if name in schema and name != title_prop:
                props[name] = value
        props[title_prop] = {"title": [{"text": {"content": title_fallback}}]}
        self._client.pages.create(
            parent={"database_id": database_id},
            properties=props,
        )


# Instancia global. Si no hay key, queda en "no disponible" pero importable.
NOTION = NotionClient()
