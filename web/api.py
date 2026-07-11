"""
web/api.py
==========
Servidor FastAPI sobre el sistema multi-agente.
"""
from __future__ import annotations

from pathlib import Path
import html
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode
from contextlib import asynccontextmanager

import uuid
from pathlib import Path as PathLib

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.config import SETTINGS
from agents.event_bus import BUS, Evento
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
        body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
          font-family: Arial, sans-serif; background: {bg}; color: #222; }}
        main {{ width: min(560px, calc(100vw - 32px)); background: #fff;
          border: 1px solid #e5e1d8; border-radius: 8px; padding: 28px;
          box-shadow: 0 10px 30px rgba(0,0,0,.08); }}
        h1 {{ color: {color}; margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 18px 0; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #eee; }}
        th {{ width: 40%; color: #666; }}
        a {{ display: inline-block; margin-top: 10px; padding: 10px 16px;
          background: {color}; color: white; text-decoration: none; border-radius: 6px; }}
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


class SimularPagoReq(BaseModel):
    pedido_id: str
    metodo: str
    datos_extra: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app):
    await LC_ADAPTER.init()
    yield

app = FastAPI(title="Tienda Virtual con LangGraph", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

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


class AuthSyncRequest(BaseModel):
    id_token: str
    display_name: Optional[str] = None


class AuthSyncResponse(BaseModel):
    uid: str
    email: str
    display_name: str
    photo_url: Optional[str] = None
    provider: str


@app.post("/api/auth/sync", response_model=AuthSyncResponse)
async def auth_sync(req: AuthSyncRequest) -> AuthSyncResponse:
    decoded = verify_token(req.id_token)
    profile = profile_from_decoded(decoded)
    if req.display_name and not profile.display_name.strip():
        profile.display_name = req.display_name
    elif req.display_name and profile.email == profile.display_name:
        profile.display_name = req.display_name
    upsert_user(profile)
    return AuthSyncResponse(**profile.model_dump())


@app.get("/api/auth/me", response_model=AuthSyncResponse)
async def auth_me(user: UserProfile = Depends(get_current_user)) -> AuthSyncResponse:
    return AuthSyncResponse(**user.model_dump())


@app.get("/api/productos")
async def listar_productos() -> list[dict[str, Any]]:
    productos = TIENDA.buscar()
    out = []
    for p in productos:
        out.append({**p.model_dump(), "stock": TIENDA.stock(p.id)})
    return out


@app.get("/api/productos/{producto_id}")
async def obtener_producto(producto_id: str) -> dict[str, Any]:
    p = TIENDA.obtener_producto(producto_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"No existe {producto_id}")
    return {**p.model_dump(), "stock": TIENDA.stock(p.id)}


@app.get("/api/carrito/{usuario_id}")
async def ver_carrito(
    usuario_id: str,
    user: UserProfile = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_same_user(user, usuario_id)
    carrito = TIENDA.ver_carrito(usuario_id)
    # Formateo compatible con el antiguo MCP:
    return carrito.model_dump() if hasattr(carrito, "model_dump") else carrito

class ModificarCarritoReq(BaseModel):
    producto_id: str
    cantidad: int
    accion: str = "agregar"  # "agregar" o "eliminar"

@app.post("/api/carrito/{usuario_id}/modificar")
async def modificar_carrito(
    usuario_id: str,
    req: ModificarCarritoReq,
    user: UserProfile = Depends(get_current_user)
) -> dict[str, Any]:
    ensure_same_user(user, usuario_id)
    if req.accion == "agregar":
        res = TIENDA.agregar_al_carrito(usuario_id, req.producto_id, req.cantidad)
    else:
        res = TIENDA.eliminar_del_carrito(usuario_id, req.producto_id, req.cantidad)
    
    if not res.exito:
        raise HTTPException(status_code=400, detail=res.mensaje)
    return {"exito": True, "carrito": TIENDA.ver_carrito(usuario_id).model_dump()}

@app.post("/api/pedido/crear")
async def crear_pedido_directo(
    user: UserProfile = Depends(get_current_user)
) -> dict[str, Any]:
    # Crear el pedido directamente usando la logica de la tienda
    res = TIENDA.crear_pedido(user.uid)
    if not res.exito:
        raise HTTPException(status_code=400, detail=res.mensaje)
    return {
        "exito": True, 
        "pedido_id": res.datos["pedido_id"], 
        "total": res.datos["total"],
        "mensaje": res.mensaje
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: UserProfile = Depends(get_current_user),
) -> ChatResponse:
    # Si el usuario está logueado, usar su UID real. Si es anónimo, usar el guest_id del frontend.
    usuario_id = user.uid if user.uid != "anonimo" else req.usuario_id
    resp = await LC_ADAPTER.atender(req.mensaje, usuario_id=usuario_id)
    
    agente = resp.agente or "agente"
    datos = {}
    
    # Inyectar pago_info si es el agente de pagos y detectamos intención de pago
    if agente in ["pagos", "finanzas"]:
        # Buscar ID de pedido (ej. ORD-0001)
        match_ord = re.search(r'ORD-\d+', resp.mensaje.upper())
        if match_ord:
            pedido_id = match_ord.group(0)
            pedido = TIENDA.consultar_pedido(pedido_id)
            if pedido and pedido.estado.value == "pendiente_pago":
                # Detectar método de pago en el texto
                txt = resp.mensaje.lower()
                metodo = None
                if "yape" in txt: metodo = "yape"
                elif "plin" in txt: metodo = "plin"
                elif "niubiz" in txt or "tarjeta" in txt: metodo = "niubiz"
                
                if metodo:
                    datos["pago_info"] = datos_para_metodo(metodo, pedido_id, pedido.total)

    return ChatResponse(
        agente=agente,
        intent="",
        mensaje=resp.mensaje,
        datos=datos,
        tools_invocadas=resp.tools_invocadas,
        latencia_ms=round(resp.latencia_ms, 2),
        exito=resp.exito,
    )


@app.get("/api/historial/{usuario_id}")
async def historial(
    usuario_id: str,
    limite: int = 40,
    user: UserProfile = Depends(get_current_user),
) -> list[dict[str, Any]]:
    ensure_same_user(user, usuario_id)
    h = await LC_ADAPTER.get_history(usuario_id)
    return h[-limite:]


@app.get("/api/eventos")
async def eventos(limite: int = 30) -> list[dict[str, Any]]:
    return EVENTOS_RECIENTES[-limite:]


@app.get("/api/inventario/historial")
async def inventario_historial(producto_id: str = "", limite: int = 50) -> dict[str, Any]:
    movs = TIENDA.historial_movimientos(producto_id=producto_id or None, limite=limite)
    return {"movimientos": movs, "total": len(movs)}


@app.get("/api/equipo")
async def equipo() -> list[dict[str, Any]]:
    return [
        {"rol": "supervisor", "titulo": "Supervisor",
         "descripcion": "Distribuye el trabajo al especialista correcto.", "tools": []},
        {"rol": "catalogo", "titulo": "Agente Catalogo",
         "descripcion": "Busca productos, recomienda y responde dudas.",
         "tools": ["buscar_productos", "obtener_producto"]},
        {"rol": "inventario", "titulo": "Agente Inventario",
         "descripcion": "Verifica stock y mantiene el historial de movimientos.",
         "tools": ["verificar_inventario", "consultar_historial_inventario"]},
        {"rol": "ventas", "titulo": "Agente Ventas",
         "descripcion": "Gestiona el carrito y crea el pedido.",
         "tools": ["agregar_al_carrito", "ver_carrito", "vaciar_carrito", "crear_pedido"]},
        {"rol": "finanzas", "titulo": "Agente Finanzas",
         "descripcion": "Procesa el pago y lo verifica.",
         "tools": ["procesar_pago", "consultar_pedido", "consultar_transacciones_niubiz"]},
    ]


@app.get("/api/delegaciones")
async def delegaciones(limite: int = 20) -> list[dict[str, Any]]:
    delegas = [e for e in EVENTOS_RECIENTES if e["tipo"] == "jefe.delega"]
    return delegas[-limite:]


@app.get("/api/notion/status")
async def notion_status() -> dict[str, Any]:
    return NOTION.estado()


@app.post("/api/notion/refrescar")
async def notion_refrescar() -> dict[str, Any]:
    if not NOTION.disponible:
        raise HTTPException(status_code=503, detail="Notion no esta configurado.")
    return {"exito": False, "mensaje": "Recarga manual no disponible en esta version."}


@app.get("/api/datos-pago")
async def datos_pago(metodo: str, pedido_id: str = "", total: float = 0) -> dict[str, Any]:
    if not pedido_id:
        raise HTTPException(status_code=400, detail="pedido_id requerido")
    return datos_para_metodo(metodo, pedido_id, total)


@app.post("/api/niubiz/session")
async def niubiz_crear_sesion(req: NiubizSessionRequest,
                              request: Request,
                              user: UserProfile = Depends(get_current_user)) -> dict[str, Any]:
    usuario_id = user.uid
    customer_email = req.email or user.email
    pedido = TIENDA.consultar_pedido(req.pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail=f"No existe el pedido {req.pedido_id}")
    if pedido.estado.value != "pendiente_pago":
        raise HTTPException(status_code=409,
                            detail=f"El pedido ya esta en estado {pedido.estado.value}")
    if not NIUBIZ.habilitado:
        raise HTTPException(status_code=503, detail="Niubiz no esta configurado.")
    purchase_number = _niubiz_purchase_number(req.pedido_id)
    try:
        session = NIUBIZ.crear_sesion_checkout(
            amount=pedido.total, purchase_number=purchase_number,
            client_ip=request.client.host if request.client else "127.0.0.1",
            email=customer_email, phone=req.telefono,
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

@app.post("/api/pago/simular")
async def simular_pago(
    req: SimularPagoReq,
    user: UserProfile = Depends(get_current_user)
) -> dict[str, Any]:
    # Siempre validamos usuario
    if user.uid != "anonimo":
        pass  # O podriamos requerir que coincida, pero para simulacion bastara esto
    
    pedido = TIENDA.consultar_pedido(req.pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    import datetime
    now = datetime.datetime.now()
    datos_extra = {
        "CLIENTE_ID": user.uid,
        "NOMBRE_CLIENTE": user.display_name or user.email or "Cliente Web",
        "NOMBRE_ESPERADO": "AURA Boutique",
        "MONTO_TRANSFERIDO": pedido.total,
        "MONTO_DETECTADO": pedido.total,
        "METODO_PAGO": req.metodo.lower(),
        "NUMERO_OPERACION": f"SIM-{int(now.timestamp())}",
        "FECHA_DETECTADA": now.date().isoformat(),
        "HORA_DETECTADA": now.strftime("%H:%M"),
        "VOUCHER_URL": "https://aura.local/simulado_por_interfaz",
        "VALIDACION_IA": "APROBADO",
        "OBSERVACION": f"Pago confirmado exitosamente mediante {req.metodo}."
    }
    
    # Fusionar cualquier dato extra que venga del frontend (ej. numeros de tarjeta enmascarados, si quisieramos)
    datos_extra.update(req.datos_extra)
    
    res = TIENDA.procesar_pago(req.pedido_id, req.metodo, datos_extra=datos_extra)
    
    if not res.exito:
        return {"exito": False, "mensaje": res.mensaje}
        
    msg = f"El pago con {req.metodo.upper()} ha sido procesado exitosamente. Tu compra esta confirmada."
    return {"exito": True, "mensaje": msg}


@app.post("/api/niubiz/autorizar/{pedido_id}")
async def niubiz_autorizar(request: Request, pedido_id: str,
                           transactionToken: str = Form(""),
                           security_token: str = "",
                           purchase_number: str = "",
                           usuario_id: str = "anonimo") -> HTMLResponse:
    pedido = TIENDA.consultar_pedido(pedido_id)
    if not pedido:
        return _resultado_niubiz_html("Pedido no encontrado",
                                      f"No existe el pedido {pedido_id}.", aprobado=False)
    if pedido.estado.value == "pagado":
        return _resultado_niubiz_html("Pago ya confirmado",
                                      f"El pedido {pedido_id} ya estaba pagado.", aprobado=True,
                                      detalles={"pedido": pedido_id, "estado": pedido.estado.value})
    cached = NIUBIZ_SESSIONS.get(pedido_id, {})
    security_token = security_token or cached.get("security_token", "")
    purchase_number = purchase_number or cached.get("purchase_number", "")
    usuario_id = usuario_id or cached.get("usuario_id", "anonimo")
    if not security_token or not purchase_number:
        return _resultado_niubiz_html("Sesion Niubiz expirada",
                                      "Vuelve a iniciar el checkout desde la tienda.",
                                      aprobado=False, detalles={"pedido": pedido_id})
    try:
        response = NIUBIZ.autorizar(
            amount=pedido.total, purchase_number=purchase_number,
            transaction_token=transactionToken, security_token=security_token,
            store_url=str(request.base_url).rstrip("/"),
        )
        data_map = response.get("dataMap") or {}
        status = data_map.get("STATUS") or "Unknown"
        http_status = int(response.get("_http_status") or 0)
        registro = _registro_niubiz(pedido, usuario_id, status, response=response,
                                    http_status=http_status, request=request)
        aprobado = status == "Authorized" and http_status == 200
        if aprobado:
            import datetime
            now = datetime.datetime.now()
            datos_extra = {
                "CLIENTE_ID": usuario_id,
                "NOMBRE_CLIENTE": "Cliente Niubiz" if usuario_id == "anonimo" else usuario_id,
                "NOMBRE_ESPERADO": "AURA Boutique",
                "MONTO_TRANSFERIDO": float(registro.get("amount") or pedido.total),
                "MONTO_DETECTADO": float(registro.get("amount") or pedido.total),
                "METODO_PAGO": "niubiz",
                "NUMERO_OPERACION": registro.get("transaction_id") or f"NIUBIZ-{int(now.timestamp())}",
                "FECHA_DETECTADA": now.date().isoformat(),
                "HORA_DETECTADA": now.strftime("%H:%M"),
                "VOUCHER_URL": "https://aura.local/pago_niubiz_nativo",
                "VALIDACION_IA": "APROBADO",
                "OBSERVACION": f"Pago procesado mediante Niubiz. Auth: {registro.get('authorization_code', 'N/A')}"
            }
            pago = TIENDA.procesar_pago(pedido_id, "niubiz", datos_extra=datos_extra)
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
                "Pago aprobado", "Niubiz autorizo la transaccion y el pedido fue confirmado.",
                aprobado=True,
                detalles={"pedido": pedido_id, "monto": f"S/ {pedido.total:.2f}",
                          "estado_niubiz": status,
                          "autorizacion": registro.get("authorization_code"),
                          "tarjeta": registro.get("card"), "marca": registro.get("brand")})
        return _resultado_niubiz_html("Pago no aprobado", "Niubiz no autorizo la transaccion.",
                                      aprobado=False,
                                      detalles={"pedido": pedido_id, "estado_niubiz": status,
                                                "motivo": registro.get("action_description")})
    except NiubizApiError as exc:
        error_body = exc.body_json or {}
        data = error_body.get("data") or {}
        status = data.get("STATUS") or "Error"
        registro = _registro_niubiz(pedido, usuario_id, status, error=error_body,
                                    http_status=exc.status_code, request=request)
        TIENDA.registrar_transaccion_niubiz(registro)
        BUS.publish(EventType.PAGO_RECHAZADO, publicado_por="niubiz",
                    datos={"pedido_id": pedido_id, "status": status,
                           "error": registro.get("error_message")})
        return _resultado_niubiz_html("Error al autorizar",
                                      "Niubiz rechazo o no pudo procesar la transaccion.",
                                      aprobado=False,
                                      detalles={"pedido": pedido_id, "estado_niubiz": status,
                                                "codigo": registro.get("error_code"),
                                                "motivo": registro.get("error_message")})


@app.get("/api/pedidos")
async def obtener_pedidos(user: UserProfile = Depends(get_current_user)) -> dict[str, Any]:
    if user.uid == "anonimo":
        return {"exito": False, "mensaje": "Usuario no autenticado", "pedidos": []}
    pedidos = TIENDA.cargar_pedidos_usuario(user.uid)
    return {"exito": True, "pedidos": pedidos}


@app.get("/api/niubiz/transacciones")
async def niubiz_transacciones(pedido_id: str = "", limite: int = 50) -> dict[str, Any]:
    txs = TIENDA.transacciones_niubiz(pedido_id=pedido_id or None, limite=limite)
    return {"transacciones": txs, "total": len(txs)}


UPLOADS_DIR = PathLib(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


@app.post("/api/voucher")
async def subir_voucher(pedido_id: str = Form(...),
                        usuario_id: str = Form("anonimo"),
                        voucher: UploadFile = File(...),
                        user: UserProfile = Depends(get_current_user)) -> dict[str, Any]:
    ensure_same_user(user, usuario_id)
    if not (voucher.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="El voucher debe ser una imagen.")
    ext = (voucher.filename or "voucher.png").split(".")[-1].lower()[:6]
    fname = f"{pedido_id}-{uuid.uuid4().hex[:8]}.{ext}"
    target = UPLOADS_DIR / fname
    contenido = await voucher.read()
    target.write_bytes(contenido)
    resp = await LC_ADAPTER.atender(
        f"confirmar voucher del pedido {pedido_id}, archivo: {fname}",
        usuario_id=usuario_id,
    )
    return {
        "exito": resp.exito,
        "mensaje": resp.mensaje,
        "agente": resp.agente,
        "datos": {},
        "voucher_guardado": fname,
        "tam_bytes": len(contenido),
    }


@app.get("/api/metricas")
async def metricas() -> dict[str, Any]:
    return {"eventos_publicados": len(EVENTOS_RECIENTES)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    uvicorn.run("web.api:app", host="127.0.0.1", port=8000, reload=False)
