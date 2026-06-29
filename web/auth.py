"""
web/auth.py
===========
Integracion con Firebase Authentication.

- Inicializa firebase-admin una sola vez al importar.
- Verifica ID tokens emitidos por Firebase desde el frontend.
- Mantiene un "directorio" en memoria de usuarios sincronizados,
  util para mostrar perfil sin tocar Firebase en cada request.

El frontend hace el login/registro con el SDK JS de Firebase (email o
Google), obtiene un ID Token y se lo manda al backend. El backend lo
verifica con `auth.verify_id_token()` y devuelve el perfil.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

try:
    import firebase_admin
    from firebase_admin import auth as fb_auth
    from firebase_admin import credentials
except ModuleNotFoundError:
    firebase_admin = None
    fb_auth = None
    credentials = None


# -------------------------------------------------------------------------
# Inicializacion del SDK admin.
# -------------------------------------------------------------------------
_CREDENTIALS_PATH = Path(__file__).resolve().parent.parent / "server" / "firebase-credentials.json"


def _init_firebase() -> bool:
    if firebase_admin is None:
        return False
    if firebase_admin._apps:  # ya inicializado
        return True
    if not _CREDENTIALS_PATH.exists():
        return False
    cred = credentials.Certificate(str(_CREDENTIALS_PATH))
    firebase_admin.initialize_app(cred)
    return True


FIREBASE_READY = _init_firebase()


# -------------------------------------------------------------------------
# Perfil de usuario (in-memory; pasa a DB cuando quieras persistir).
# -------------------------------------------------------------------------
class UserProfile(BaseModel):
    uid: str
    email: str
    display_name: str
    photo_url: Optional[str] = None
    provider: str = "password"  # "password" | "google" | "unknown"


_USERS: dict[str, UserProfile] = {}


def upsert_user(profile: UserProfile) -> UserProfile:
    """Inserta o actualiza el usuario en el directorio en memoria."""
    _USERS[profile.uid] = profile
    return profile


def get_user(uid: str) -> Optional[UserProfile]:
    return _USERS.get(uid)


def ensure_same_user(profile: UserProfile, requested_uid: str) -> None:
    """Evita que un token valido opere sobre el carrito/pedido de otro uid."""
    if profile.uid != requested_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario autenticado no coincide con el recurso solicitado.",
        )


# -------------------------------------------------------------------------
# Verificacion de ID Token.
# -------------------------------------------------------------------------
def verify_token(id_token: str) -> dict[str, Any]:
    """Verifica un ID token de Firebase. Lanza HTTPException si es invalido."""
    if not FIREBASE_READY or fb_auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Firebase Admin no esta configurado en este entorno local. "
                "La tienda puede operar como invitado."
            ),
        )
    try:
        decoded = fb_auth.verify_id_token(id_token)
        return decoded
    except Exception as exc:  # InvalidIdTokenError, ExpiredIdTokenError, ...
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token Firebase invalido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _provider_from_decoded(decoded: dict[str, Any]) -> str:
    firebase_info = decoded.get("firebase", {}) or {}
    sign_in = firebase_info.get("sign_in_provider", "")
    if sign_in == "google.com":
        return "google"
    if sign_in == "password":
        return "password"
    return sign_in or "unknown"


def profile_from_decoded(decoded: dict[str, Any]) -> UserProfile:
    return UserProfile(
        uid=decoded["uid"],
        email=decoded.get("email") or "",
        display_name=decoded.get("name") or decoded.get("email") or decoded["uid"],
        photo_url=decoded.get("picture"),
        provider=_provider_from_decoded(decoded),
    )


# -------------------------------------------------------------------------
# Dependencia FastAPI para rutas protegidas.
# -------------------------------------------------------------------------
async def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> UserProfile:
    """Modo invitado si Firebase no está listo."""
    if not FIREBASE_READY or not authorization or not authorization.lower().startswith("bearer "):
        return UserProfile(
            uid="cliente-01",
            email="invitado@tienda.com",
            display_name="Invitado",
            provider="guest",
        )
    token = authorization.split(" ", 1)[1].strip()
    decoded = verify_token(token)
    profile = profile_from_decoded(decoded)
    return upsert_user(profile)


# Variante opcional (no obliga): util para endpoints que aceptan invitados.
async def get_optional_user(    authorization: Optional[str] = Header(default=None),
) -> Optional[UserProfile]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return await get_current_user(authorization=authorization)
    except HTTPException:
        return None
