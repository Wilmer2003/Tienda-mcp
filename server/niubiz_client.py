"""
Cliente Niubiz para el checkout web.

Flujo implementado (single merchant):
  1. GET  {NIUBIZ_URL}.security/v1/security
  2. POST {NIUBIZ_URL}.ecommerce/v2/ecommerce/token/session/{merchant_id}
  3. POST {NIUBIZ_URL}.authorization/v3/authorization/ecommerce/{merchant_id}

No incluye reversas, reembolsos ni configuracion por vendor.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from server.config import SETTINGS, NiubizConfig


class NiubizApiError(RuntimeError):
    """Error controlado al llamar a Niubiz."""

    def __init__(self, message: str, *, status_code: int = 0,
                 body_text: str = "", body_json: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body_text = body_text
        self.body_json = body_json or {}


@dataclass(frozen=True)
class NiubizCheckoutSession:
    merchant_id: str
    purchase_number: str
    amount: float
    currency: str
    security_token: str
    session_key: str
    checkout_js_url: str
    mode: str


class NiubizClient:
    """Wrapper minimo sobre la API REST de Niubiz."""

    def __init__(self, config: NiubizConfig | None = None) -> None:
        self.config = config or SETTINGS.niubiz
        self.base_url = self.config.url.rstrip("/")

    @property
    def habilitado(self) -> bool:
        return self.config.habilitado

    def _require_config(self) -> None:
        if not self.habilitado:
            raise NiubizApiError(
                "Configuracion de Niubiz incompleta. Revisa NIUBIZ_USERNAME, "
                "NIUBIZ_PASSWORD y NIUBIZ_MERCHANT_ID."
            )

    def _url(self, suffix: str) -> str:
        return f"{self.base_url}{suffix}"

    def _request(self, method: str, url: str, *,
                 headers: dict[str, str] | None = None,
                 payload: dict[str, Any] | None = None) -> tuple[int, str, Any]:
        data = None
        req_headers = dict(headers or {})
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(
            url, data=data, headers=req_headers, method=method.upper()
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = self._parse_json(body)
                return response.status, body, parsed
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = self._parse_json(body)
            raise NiubizApiError(
                f"Niubiz respondio HTTP {exc.code}",
                status_code=exc.code,
                body_text=body,
                body_json=parsed if isinstance(parsed, dict) else {},
            ) from exc
        except urllib.error.URLError as exc:
            raise NiubizApiError(f"No se pudo conectar con Niubiz: {exc}") from exc

    @staticmethod
    def _parse_json(body: str) -> Any:
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def crear_token_seguridad(self) -> str:
        self._require_config()
        raw = f"{self.config.username}:{self.config.password}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        _, body, _ = self._request(
            "GET",
            self._url(".security/v1/security"),
            headers={
                "accept": "text/plain",
                "authorization": f"Basic {encoded}",
            },
        )
        token = body.strip()
        if not token:
            raise NiubizApiError("Niubiz no devolvio token de seguridad.")
        return token

    def crear_sesion_checkout(self, *, amount: float, purchase_number: str,
                              client_ip: str, email: str = "",
                              phone: str = "") -> NiubizCheckoutSession:
        self._require_config()
        security_token = self.crear_token_seguridad()
        payload = {
            "channel": "web",
            "amount": round(float(amount), 2),
            "antifraud": {
                "clientIp": client_ip or "127.0.0.1",
                "merchantDefineData": {
                    "MDD4": email or "cliente@tienda-mcp.local",
                    "MDD32": email or "cliente@tienda-mcp.local",
                    "MDD75": "Registrado",
                    "MDD77": 0,
                },
            },
            "dataMap": {
                "cardholderCity": "Lima",
                "cardholderCountry": "PE",
                "cardholderAddress": "Lima",
                "cardholderPostalCode": "15001",
                "cardholderState": "LIM",
                "cardholderPhoneNumber": phone or "999999999",
            },
        }
        _, body, parsed = self._request(
            "POST",
            self._url(
                f".ecommerce/v2/ecommerce/token/session/{self.config.merchant_id}"
            ),
            headers={
                "Authorization": security_token,
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        if not isinstance(parsed, dict):
            parsed = self._parse_json(body)
        session_key = (parsed or {}).get("sessionKey")
        if not session_key:
            raise NiubizApiError(
                "Niubiz no devolvio sessionKey.",
                body_text=body,
                body_json=parsed if isinstance(parsed, dict) else {},
            )
        return NiubizCheckoutSession(
            merchant_id=str(self.config.merchant_id),
            purchase_number=str(purchase_number),
            amount=round(float(amount), 2),
            currency="PEN",
            security_token=security_token,
            session_key=str(session_key),
            checkout_js_url=self.config.checkout_js_url,
            mode=self.config.mode,
        )

    def autorizar(self, *, amount: float, purchase_number: str,
                  transaction_token: str, security_token: str,
                  store_url: str = "http://localhost:8000") -> dict[str, Any]:
        self._require_config()
        if not transaction_token:
            raise NiubizApiError("transactionToken requerido para autorizar.")
        payload = {
            "captureType": "manual",
            "channel": "web",
            "countable": True,
            "order": {
                "amount": round(float(amount), 2),
                "currency": "PEN",
                "purchaseNumber": str(purchase_number),
                "tokenId": transaction_token,
            },
            "dataMap": {
                "urlAddress": store_url,
                "serviceLocationCityName": "Lima",
                "serviceLocationCountrySubdivisionCode": "LIM",
                "serviceLocationCountryCode": "PER",
                "serviceLocationPostalCode": "15001",
            },
        }
        status, body, parsed = self._request(
            "POST",
            self._url(
                f".authorization/v3/authorization/ecommerce/{self.config.merchant_id}"
            ),
            headers={
                "Authorization": security_token,
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        if not isinstance(parsed, dict):
            raise NiubizApiError(
                "Niubiz devolvio una respuesta no JSON al autorizar.",
                status_code=status,
                body_text=body,
            )
        parsed["_http_status"] = status
        return parsed


NIUBIZ = NiubizClient()
