"""
config.py
=========
Carga centralizada de variables de entorno (.env) y settings tipados.

Cualquier modulo que necesite leer credenciales (NotionClient, gemini_nlu,
etc.) debe importar `SETTINGS` desde aqui, no leer `os.getenv` directo.
Asi tenemos un solo punto donde se decide que existe y que no.

Uso:
    from server.config import SETTINGS
    if SETTINGS.notion.habilitado:
        ...
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    # Cargar .env desde la raiz del proyecto. Idempotente: llamar varias veces
    # no rompe nada y respeta variables ya definidas en el entorno real.
    _ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_ROOT / ".env", override=True)
except ImportError:
    pass  # sin dotenv el sistema sigue funcionando con env del SO


@dataclass(frozen=True)
class NotionConfig:
    """Configuracion de la integracion con Notion."""
    api_key: Optional[str] = None
    db_productos: Optional[str] = None
    db_ordenes: Optional[str] = None
    db_sessions: Optional[str] = None
    db_prompts: Optional[str] = None
    db_base_conocimiento: Optional[str] = None
    db_vouchers: Optional[str] = None
    db_transacciones_niubiz: Optional[str] = None

    @property
    def habilitado(self) -> bool:
        """True si la API key esta configurada (minimo para intentar)."""
        return bool(self.api_key)

    @property
    def dbs_disponibles(self) -> dict[str, bool]:
        """Cada DB es opcional; reportamos cuales tienen ID configurado."""
        return {
            "productos":           bool(self.db_productos),
            "ordenes":             bool(self.db_ordenes),
            "sessions":            bool(self.db_sessions),
            "prompts":             bool(self.db_prompts),
            "base_conocimiento":   bool(self.db_base_conocimiento),
            "vouchers":            bool(self.db_vouchers),
            "transacciones_niubiz": bool(self.db_transacciones_niubiz),
        }


@dataclass(frozen=True)
class NiubizConfig:
    """Configuracion single-merchant para Niubiz."""
    username: Optional[str] = None
    password: Optional[str] = None
    merchant_id: Optional[str] = None
    url: str = "https://apisandbox.vnforappstest.com/api"
    mode: str = "sandbox"
    timeout_seconds: float = 20.0

    @property
    def habilitado(self) -> bool:
        return bool(self.username and self.password and self.merchant_id)

    @property
    def checkout_js_url(self) -> str:
        if self.mode.lower() in {"prod", "production", "produccion"}:
            return "https://static-content.vnforapps.com/v2/js/checkout.js"
        return "https://static-content-qas.vnforapps.com/env/sandbox/js/checkout.js"


@dataclass(frozen=True)
class Settings:
    notion: NotionConfig = field(default_factory=NotionConfig)
    niubiz: NiubizConfig = field(default_factory=NiubizConfig)
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    @classmethod
    def cargar(cls) -> "Settings":
        def _get_env(key: str) -> Optional[str]:
            val = os.getenv(key)
            if val and "REEMPLAZA_CON" in val:
                return None
            return val

        return cls(
            notion=NotionConfig(
                api_key=_get_env("NOTION_API_KEY") or _get_env("NOTION_TOKEN") or None,
                db_productos=_get_env("NOTION_PRODUCTOS_DB_ID") or _get_env("NOTION_DATABASE_ID") or None,
                db_ordenes=_get_env("NOTION_ORDENES_DB_ID") or None,
                db_sessions=_get_env("NOTION_SESSIONS_DB_ID") or None,
                db_prompts=_get_env("NOTION_PROMPTS_DB_ID") or None,
                db_base_conocimiento=_get_env("NOTION_BASE_CONOCIMIENTO_DB_ID") or None,
                db_vouchers=_get_env("NOTION_VOUCHERS_DB_ID") or None,
                db_transacciones_niubiz=_get_env("NOTION_TRANSACCIONES_NIUBIZ_DB_ID") or None,
            ),
            niubiz=NiubizConfig(
                username=os.getenv("NIUBIZ_USERNAME") or None,
                password=os.getenv("NIUBIZ_PASSWORD") or None,
                merchant_id=os.getenv("NIUBIZ_MERCHANT_ID") or None,
                url=(os.getenv("NIUBIZ_URL") or "https://apisandbox.vnforappstest.com/api").rstrip("/"),
                mode=os.getenv("NIUBIZ_MODE") or "sandbox",
                timeout_seconds=float(os.getenv("NIUBIZ_TIMEOUT_SECONDS") or "20"),
            ),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        )


# Instancia unica importable desde cualquier modulo.
SETTINGS = Settings.cargar()
