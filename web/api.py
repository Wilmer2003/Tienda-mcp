"""
web/api.py
==========
Servidor FastAPI sobre el sistema multi-agente.

Expone:
  GET  /                        -> tienda (HTML estatico)
  GET  /api/productos           -> catalogo (con stock)
  GET  /api/productos/{id}      -> detalle de un producto
  GET  /api/carrito/{usuario}   -> contenido del carrito
  POST /api/chat                -> envia un mensaje al orquestador
  GET  /api/historial/{usuario} -> historial del usuario
  GET  /api/eventos             -> ultimos eventos del bus

Arrancar:
  py -m web.api
  -> abre http://localhost:8000
"""
from __future__ import annotations

from pathlib import Path
import html
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import uuid
from pathlib import Path as PathLib

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# server.config carga `.env` al importarse — IMPORTAR PRIMERO.
from server.config import SETTINGS
from agents.event_bus import BUS, Evento
from agents.shared_state import STATE
from web.lc_adapter import LC_ADAPTER
from server.notion_client import NOTION
from server.niubiz_client import NIUBIZ, NiubizApiError
from server.store_logic import TIENDA
from web.auth import (
    UserProfile,
    ensure_same_user,
    get_current_user,
    profile_from_decoded,
    upsert_user,
    verify_token,
)
from web.datos_pago import datos_para_metodo


# Buffer de eventos en memoria para el panel "Detras de escena".
EVENTOS_RECIENTES: list[dict[str, Any]] = []
MAX_EVENTOS = 100


def _on_any_event(evento: Evento) -> None:
    EVENTOS_RECIENTES.append({
        "tipo": evento.tipo.value,
        "publicado_por": evento.publicado_por,
        "datos": evento.datos,
        "timestamp": evento.timestamp.isoformat(),
    })
    if len(EVENTOS_RECIENTES) > MAX_EVENTOS:
        del EVENTOS_RECIENTES[:-MAX_EVENTOS]


# Suscribir a TODOS los tipos de evento al startup.
from agents.event_bus import EventType
for _t in EventType:
    BUS.subscribe(_t, _on_any_event)


NIUBIZ_SESSIONS: dict[str, dict[str, Any]] = {}


def _monto_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value.replace(",", "."))
        if match:
            return float(match.group(0))
    return float(default or 0)


def _niubiz_purchase_number(pedido_id: str) -> str:
    digits = re.sub(r"\D", "", pedido_id)[-2:].zfill(2)
    return datetime.now(timezone.utc).strftime("%m%d%H%M%S") + digits


def _registro_niubiz(pedido: Any, usuario_id: str, status: str,
                     response: dict[str, Any] | None = None,
                     error: dict[str, Any] | None = None,
                     http_status: int = 0,
                     request: Request | None = None) -> dict[str, Any]:
    response = response or {}
    error = error or {}
    data_map = response.get("dataMap") or error.get("data") or {}
    order = response.get("order") or {}
    header = response.get("header") or error.get("header") or {}
    fulfillment = response.get("fulfillment") or {}
    amount = _monto_float(order.get("amount") or data_map.get("AMOUNT"),
                          getattr(pedido, "total", 0.0))
    return {
        "pedido_id": pedido.pedido_id,
        "usuario_id": usuario_id,
        "status": status or data_map.get("STATUS") or "Error",
        "amount": amount,
        "currency": order.get("currency") or "PEN",
        "merchant_id": fulfillment.get("merchantId") or SETTINGS.niubiz.merchant_id,
        "ecore_transaction_uuid": header.get("ecoreTransactionUUID"),
        "ecore_transaction_date": header.get("ecoreTransactionDate"),
        "millis": header.get("millis"),
        "signature": fulfillment.get("signature"),
        "authorized_amount": order.get("authorizedAmount"),
        "authorization_code": order.get("authorizationCode"),
        "trace_number": order.get("traceNumber"),
        "transaction_date": order.get("transactionDate"),
        "transaction_id": order.get("transactionId"),
        "brand": data_map.get("BRAND"),
        "card": data_map.get("CARD"),
        "action_description": data_map.get("ACTION_DESCRIPTION"),
        "error_code": error.get("errorCode"),
        "error_message": error.get("errorMessage") or data_map.get("ACTION_DESCRIPTION"),
        "http_status": http_status,
        "ipv4": request.client.host if request and request.client else "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "raw_response": response or error,
    }


def _resultado_niubiz_html(titulo: str, mensaje: str, *,
                           aprobado: bool,
                           detalles: dict[str, Any] | None = None) -> HTMLResponse:
    color = "#256f4a" if aprobado else "#9b2f2f"
    bg = "#f7fbf8" if aprobado else "#fff7f7"
    detalles = detalles or {}
    rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in detalles.items() if v not in (None, "")
    )
    body = f"""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{html.escape(titulo)}</title>
      <style>
        body {{
          margin: 0; min-height: 100vh; display: grid; place-items: center;
          font-family: Arial, sans-serif; background: {bg}; color: #222;
        }}
        main {{
          width: min(560px, calc(100vw - 32px)); background: #fff;
          border: 1px solid #e5e1d8; border-radius: 8px; padding: 28px;
          box-shadow: 0 10px 30px rgba(0,0,0,.08);
        }}
        h1 {{ color: {color}; margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 18px 0; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #eee; }}
        th {{ width: 40%; color: #666; }}
        a {{
          display: inline-block; margin-top: 10px; padding: 10px 16px;
          background: {color}; color: white; text-decoration: none; border-radius: 6px;
        }}
      </style>
    </head>
    <body>
      <main>
        <h1>{html.escape(titulo)}</h1>
        <p>{html.escape(mensaje)}</p>
        <table>{rows}</table>
        <a href="/">Volver a la tienda</a>
      </main>
    </body>
    </html>
    """
    return HTMLResponse(body)


# -------------------------------------------------------------------------
# Schemas de request / response.
# -------------------------------------------------------------------------
class ChatRequest(BaseModel):
    usuario_id: str
    mensaje: str


class ChatResponse(BaseModel):
    agente: str
    intent: str
    mensaje: str
    datos: dict[str, Any] = {}
    tools_invocadas: list[str] = []
    latencia_ms: float = 0.0
    exito: bool = True


class NiubizSessionRequest(BaseModel):
    pedido_id: str
    usuario_id: str = "anonimo"
    email: str = ""
    nombres: str = ""
    apellidos: str = ""
    telefono: str = ""


# -------------------------------------------------------------------------
# App.
# -------------------------------------------------------------------------
app = FastAPI(title="Tienda Virtual con agentes MCP", version="1.0.0")

# CORS abierto: util en demo local.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await LC_ADAPTER.init()

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/register")
async def register_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "register.html")


# ----- API: auth -----
class AuthSyncRequest(BaseModel):
    """Payload que manda el frontend tras un login/registro exitoso en Firebase."""
    id_token: str
    display_name: Optional[str] = None  # se usa al registrar con email


class AuthSyncResponse(BaseModel):
    uid: str
    email: str
    display_name: str
    photo_url: Optional[str] = None
    provider: str


@app.post("/api/auth/sync", response_model=AuthSyncResponse)
async def auth_sync(req: AuthSyncRequest) -> AuthSyncResponse:
    """Verifica el ID token y guarda el perfil en el directorio local."""
    decoded = verify_token(req.id_token)
    profile = profile_from_decoded(decoded)
    if req.display_name and not profile.display_name.strip():
        profile.display_name = req.display_name
    elif req.display_name and profile.email == profile.display_name:
        # Si Firebase aun no tiene displayName, preferimos el que paso el frontend.
        profile.display_name = req.display_name
    upsert_user(profile)
    return AuthSyncResponse(**profile.model_dump())


@app.get("/api/auth/me", response_model=AuthSyncResponse)
async def auth_me(user: UserProfile = Depends(get_current_user)) -> AuthSyncResponse:
    return AuthSyncResponse(**user.model_dump())


# ----- API: productos -----
@app.get("/api/productos")
async def listar_productos() -> list[dict[str, Any]]:
    productos = TIENDA.buscar()
    out = []
    for p in productos:
        out.append({
            **p.model_dump(),
            "stock": TIENDA.stock(p.id),
        })
    return out


@app.get("/api/productos/{producto_id}")
async def obtener_producto(producto_id: str) -> dict[str, Any]:
    p = TIENDA.obtener_producto(producto_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"No existe {producto_id}")
    return {**p.model_dump(), "stock": TIENDA.stock(p.id)}


# ----- API: carrito -----
@app.get("/api/carrito/{usuario_id}")
async def ver_carrito(
    usuario_id: str,
    user: UserProfile = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_same_user(user, usuario_id)
    c = TIENDA.ver_carrito(usuario_id)
    return c.model_dump()


# ----- API: chat con el orquestador -----
@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: UserProfile = Depends(get_current_user),
) -> ChatResponse:
    usuario_id = user.uid

    # 1. Cargar sesión local y rehidratar desde Notion si corresponde.
    ses = STATE.sesion(usuario_id)

    # 2. Registrar turno del usuario.
    STATE.registrar_turno(
        rol="usuario",
        mensaje=req.mensaje,
        datos={"usuario_id": usuario_id},
    )

    # 3. Ejecutar grafo LangGraph multiagente.
    resp = await LC_ADAPTER.atender(req.mensaje, usuario_id=usuario_id)

    # 4. Registrar turno del agente/orquestador.
    STATE.registrar_turno(
        rol=resp.agente or "orquestador",
        mensaje=resp.mensaje,
        datos={
            "usuario_id": usuario_id,
            "intent": resp.intent,
            "tools_invocadas": resp.tools_invocadas,
            "latencia_ms": round(resp.latencia_ms, 2),
            "exito": resp.exito,
        },
    )

    # 5. Sincronizar variables críticas del blackboard hacia contexto.
    if u_ped := STATE.leer(f"ultimo_pedido_id_{usuario_id}"):
        ses.contexto["ultimo_pedido_id"] = u_ped
    if m_pag := STATE.leer(f"metodo_pago_{usuario_id}"):
        ses.contexto["metodo_pago"] = m_pag
    if u_vouch := STATE.leer(f"ultimo_voucher_{usuario_id}"):
        ses.contexto["ultimo_voucher"] = u_vouch

    ses.ultimo_intent = resp.intent or ""
    ses.ultimo_agente = resp.agente or ""

    # 6. Escribir en Notion de manera limpia (write-through)
    

    return ChatResponse(
        agente=resp.agente or "orquestador",
        intent=resp.intent or "",
        mensaje=resp.mensaje,
        datos=resp.datos,
        tools_invocadas=resp.tools_invocadas,
        latencia_ms=round(resp.latencia_ms, 2),
        exito=resp.exito,
    )


# ----- API: historial de conversacion -----
@app.get("/api/historial/{usuario_id}")
async def historial(
    usuario_id: str,
    limite: int = 40,
    user: UserProfile = Depends(get_current_user),
) -> list[dict[str, Any]]:
    ensure_same_user(user, usuario_id)
    turnos = STATE.historial(limite=limite)
    return [
        {
            "n": t.n, "rol": t.rol, "mensaje": t.mensaje,
            "datos": t.datos, "timestamp": t.timestamp.isoformat(),
        }
        for t in turnos
    ]


# ----- API: eventos del bus -----
@app.get("/api/eventos")
async def eventos(limite: int = 30) -> list[dict[str, Any]]:
    return EVENTOS_RECIENTES[-limite:]


# ----- API: historial de inventario (gestionado por agente Inventarios) -----
@app.get("/api/inventario/historial")
async def inventario_historial(producto_id: str = "",
                                limite: int = 50) -> dict[str, Any]:
    movs = TIENDA.historial_movimientos(
        producto_id=producto_id or None, limite=limite)
    return {"movimientos": movs, "total": len(movs)}


# ----- API: equipo de agentes (para el panel "Detras de escena") -----
@app.get("/api/equipo")
async def equipo() -> list[dict[str, Any]]:
    return [
        {"rol": "jefe", "titulo": "Agente Jefe",
         "descripcion": "Distribuye el trabajo al especialista correcto.",
         "tools": []},
        {"rol": "consultas", "titulo": "Agente Consultas",
         "descripcion": "Busca productos, recomienda y responde dudas.",
         "tools": ["buscar_productos", "obtener_producto"]},
        {"rol": "inventarios", "titulo": "Agente Inventarios",
         "descripcion": "Verifica stock y mantiene el historial de movimientos.",
         "tools": ["verificar_inventario", "consultar_historial_inventario"]},
        {"rol": "ventas", "titulo": "Agente Ventas",
         "descripcion": "Gestiona el carrito y crea el pedido (el mas hablador).",
         "tools": ["agregar_al_carrito", "ver_carrito",
                   "vaciar_carrito", "crear_pedido"]},
        {"rol": "finanzas", "titulo": "Agente Finanzas",
         "descripcion": "Procesa el pago y lo verifica.",
         "tools": ["procesar_pago", "consultar_pedido",
                   "consultar_transacciones_niubiz"]},
    ]


# ----- API: delegaciones del Jefe (resumen filtrado del bus) -----
@app.get("/api/delegaciones")
async def delegaciones(limite: int = 20) -> list[dict[str, Any]]:
    delegas = [e for e in EVENTOS_RECIENTES if e["tipo"] == "jefe.delega"]
    return delegas[-limite:]


# ----- API: estado de la integracion Notion -----
@app.get("/api/notion/status")
async def notion_status() -> dict[str, Any]:
    """Diagnostico: si Notion esta conectada, que DBs tiene configuradas,
    cual es la fuente actual del catalogo y el ultimo error visto."""
    estado = NOTION.estado()
    estado["fuente_catalogo"] = TIENDA.fuente_catalogo
    return estado


@app.post("/api/notion/refrescar")
async def notion_refrescar() -> dict[str, Any]:
    """Fuerza una recarga del catalogo desde Notion. Util si el admin
    actualizo la DB PRODUCTOS y quiere que el sistema lo refleje sin
    reiniciar el servidor."""
    if not NOTION.disponible:
        raise HTTPException(status_code=503,
                            detail="Notion no esta configurado o no disponible.")
    ok = TIENDA.hidratar_desde_notion()
    return {
        "exito": ok,
        "fuente_catalogo": TIENDA.fuente_catalogo,
        "total_productos": len(TIENDA._catalogo),
    }


# ----- API: datos de pago segun metodo -----
@app.get("/api/datos-pago")
async def datos_pago(metodo: str, pedido_id: str = "",
                     total: float = 0) -> dict[str, Any]:
    if not pedido_id:
        raise HTTPException(status_code=400, detail="pedido_id requerido")
    return datos_para_metodo(metodo, pedido_id, total)


# ----- API: Niubiz checkout -----
@app.post("/api/niubiz/session")
async def niubiz_crear_sesion(req: NiubizSessionRequest,
                              request: Request,
                              user: UserProfile = Depends(get_current_user)) -> dict[str, Any]:
    usuario_id = user.uid
    customer_email = req.email or user.email
    pedido = TIENDA.consultar_pedido(req.pedido_id)
    if not pedido:
        raise HTTPException(status_code=404,
                            detail=f"No existe el pedido {req.pedido_id}")
    if pedido.estado.value != "pendiente_pago":
        raise HTTPException(status_code=409,
                            detail=f"El pedido ya esta en estado {pedido.estado.value}")
    if not NIUBIZ.habilitado:
        raise HTTPException(status_code=503,
                            detail="Niubiz no esta configurado.")

    purchase_number = _niubiz_purchase_number(req.pedido_id)
    try:
        session = NIUBIZ.crear_sesion_checkout(
            amount=pedido.total,
            purchase_number=purchase_number,
            client_ip=request.client.host if request.client else "127.0.0.1",
            email=customer_email,
            phone=req.telefono,
        )
    except NiubizApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    NIUBIZ_SESSIONS[req.pedido_id] = {
        "security_token": session.security_token,
        "purchase_number": purchase_number,
        "usuario_id": usuario_id,
        "amount": pedido.total,
    }
    base_url = str(request.base_url).rstrip("/")
    action_query = urlencode({
        "security_token": session.security_token,
        "purchase_number": purchase_number,
        "usuario_id": usuario_id,
    })
    return {
        "exito": True,
        "merchant_id": session.merchant_id,
        "session_key": session.session_key,
        "purchase_number": purchase_number,
        "pedido_id": req.pedido_id,
        "amount": session.amount,
        "currency": session.currency,
        "checkout_js_url": session.checkout_js_url,
        "mode": session.mode,
        "action_url": f"{base_url}/api/niubiz/autorizar/{req.pedido_id}?{action_query}",
    }


@app.post("/api/niubiz/autorizar/{pedido_id}")
async def niubiz_autorizar(request: Request, pedido_id: str,
                           transactionToken: str = Form(""),
                           security_token: str = "",
                           purchase_number: str = "",
                           usuario_id: str = "anonimo") -> HTMLResponse:
    pedido = TIENDA.consultar_pedido(pedido_id)
    if not pedido:
        return _resultado_niubiz_html(
            "Pedido no encontrado",
            f"No existe el pedido {pedido_id}.",
            aprobado=False,
        )
    if pedido.estado.value == "pagado":
        return _resultado_niubiz_html(
            "Pago ya confirmado",
            f"El pedido {pedido_id} ya estaba pagado.",
            aprobado=True,
            detalles={"pedido": pedido_id, "estado": pedido.estado.value},
        )

    cached = NIUBIZ_SESSIONS.get(pedido_id, {})
    security_token = security_token or cached.get("security_token", "")
    purchase_number = purchase_number or cached.get("purchase_number", "")
    usuario_id = usuario_id or cached.get("usuario_id", "anonimo")
    if not security_token or not purchase_number:
        return _resultado_niubiz_html(
            "Sesion Niubiz expirada",
            "Vuelve a iniciar el checkout desde la tienda.",
            aprobado=False,
            detalles={"pedido": pedido_id},
        )

    try:
        response = NIUBIZ.autorizar(
            amount=pedido.total,
            purchase_number=purchase_number,
            transaction_token=transactionToken,
            security_token=security_token,
            store_url=str(request.base_url).rstrip("/"),
        )
        data_map = response.get("dataMap") or {}
        status = data_map.get("STATUS") or "Unknown"
        http_status = int(response.get("_http_status") or 0)
        registro = _registro_niubiz(
            pedido, usuario_id, status, response=response,
            http_status=http_status, request=request)
        aprobado = status == "Authorized" and http_status == 200
        if aprobado:
            pago = TIENDA.procesar_pago(pedido_id, "niubiz")
            registro["pedido_confirmado"] = pago.exito
            if pago.exito:
                BUS.publish(EventType.PAGO_APROBADO, publicado_por="niubiz",
                            datos={"pedido_id": pedido_id, "metodo": "niubiz"})
            else:
                registro["store_error"] = pago.mensaje
        else:
            BUS.publish(EventType.PAGO_RECHAZADO, publicado_por="niubiz",
                        datos={"pedido_id": pedido_id, "status": status})
        TIENDA.registrar_transaccion_niubiz(registro)
        if aprobado and registro.get("pedido_confirmado"):
            return _resultado_niubiz_html(
                "Pago aprobado",
                "Niubiz autorizo la transaccion y el pedido fue confirmado.",
                aprobado=True,
                detalles={
                    "pedido": pedido_id,
                    "monto": f"S/ {pedido.total:.2f}",
                    "estado_niubiz": status,
                    "autorizacion": registro.get("authorization_code"),
                    "tarjeta": registro.get("card"),
                    "marca": registro.get("brand"),
                },
            )
        return _resultado_niubiz_html(
            "Pago no aprobado",
            "Niubiz no autorizo la transaccion.",
            aprobado=False,
            detalles={
                "pedido": pedido_id,
                "estado_niubiz": status,
                "motivo": registro.get("action_description"),
            },
        )
    except NiubizApiError as exc:
        error_body = exc.body_json or {}
        data = error_body.get("data") or {}
        status = data.get("STATUS") or "Error"
        registro = _registro_niubiz(
            pedido, usuario_id, status, error=error_body,
            http_status=exc.status_code, request=request)
        TIENDA.registrar_transaccion_niubiz(registro)
        BUS.publish(EventType.PAGO_RECHAZADO, publicado_por="niubiz",
                    datos={"pedido_id": pedido_id, "status": status,
                           "error": registro.get("error_message")})
        return _resultado_niubiz_html(
            "Error al autorizar",
            "Niubiz rechazo o no pudo procesar la transaccion.",
            aprobado=False,
            detalles={
                "pedido": pedido_id,
                "estado_niubiz": status,
                "codigo": registro.get("error_code"),
                "motivo": registro.get("error_message"),
            },
        )


@app.get("/api/niubiz/transacciones")
async def niubiz_transacciones(pedido_id: str = "",
                               limite: int = 50) -> dict[str, Any]:
    txs = TIENDA.transacciones_niubiz(pedido_id=pedido_id or None,
                                      limite=limite)
    return {"transacciones": txs, "total": len(txs)}


# ----- API: subir voucher (imagen) y confirmar pago -----
UPLOADS_DIR = PathLib(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


@app.post("/api/voucher")
async def subir_voucher(pedido_id: str = Form(...),
                        usuario_id: str = Form("anonimo"),
                        voucher: UploadFile = File(...),
                        user: UserProfile = Depends(get_current_user)) -> dict[str, Any]:
    """Cliente sube imagen de voucher. El agente Finanzas verifica y
    cierra el pago. En la simulacion aceptamos cualquier imagen valida."""
    ensure_same_user(user, usuario_id)
    # Validar tipo MIME
    if not (voucher.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400,
                            detail="El voucher debe ser una imagen.")
    # Guardar el archivo con nombre unico
    ext = (voucher.filename or "voucher.png").split(".")[-1].lower()[:6]
    fname = f"{pedido_id}-{uuid.uuid4().hex[:8]}.{ext}"
    target = UPLOADS_DIR / fname
    contenido = await voucher.read()
    target.write_bytes(contenido)
    # Disparar al agente Finanzas para confirmar el pago.
    resp = await LC_ADAPTER.atender(
        f"confirmar voucher del pedido {pedido_id}, archivo: {fname}",
        usuario_id=usuario_id,
    )
    # Sincronización de memoria y Notion
    if resp.exito:
        voucher_relpath = f"web/uploads/{fname}"
        
        # 1. Actualizar memoria local de sesión
        STATE.actualizar_sesion(usuario_id, contexto={
            "ultimo_voucher": voucher_relpath,
            f"ultimo_voucher_{usuario_id}": voucher_relpath
        })
        
        # 2. Persistir en Notion si está activo y disponible
        import os
        if os.getenv("AURA_DISABLE_NOTION") != "1" and NOTION.disponible:
            try:
                # Evitar duplicar voucher
                existente = NOTION.buscar_voucher_por_pedido(pedido_id)
                if not existente:
                    monto = 0.0
                    metodo = "desconocido"
                    pedido = TIENDA.consultar_pedido(pedido_id)
                    if pedido:
                        monto = pedido.total
                        metodo = pedido.metodo_pago.value if pedido.metodo_pago else "desconocido"
                    
                    NOTION.registrar_voucher(
                        pedido_id=pedido_id,
                        voucher_path=voucher_relpath,
                        monto=monto,
                        metodo_pago=metodo,
                        usuario_id=usuario_id
                    )
                
                # Persistir sesión actual también en Notion
                STATE.persistir_sesion(usuario_id)
            except Exception:
                pass

    return {
        "exito": resp.exito,
        "mensaje": resp.mensaje,
        "agente": resp.agente,
        "datos": resp.datos,
        "voucher_guardado": fname,
        "tam_bytes": len(contenido),
    }


# ----- API: metricas en vivo -----
@app.get("/api/metricas")
async def metricas() -> dict[str, Any]:
    return {
        "turnos_totales": len(STATE.historial()),
        "eventos_publicados": len(EVENTOS_RECIENTES),
    }


# ----- Static files (al final para no shadowing del /) -----
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run("web.api:app", host="127.0.0.1", port=8000, reload=False)
