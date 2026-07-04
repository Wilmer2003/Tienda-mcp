"""
datos_pago.py
=============
Datos de cobro para AURA Boutique.

Niubiz es la pasarela real para pagos con tarjeta. Yape, Plin, PayPal y
contra entrega se mantienen como medios simulados de la demo.
"""
from __future__ import annotations

import base64
import io
from typing import Any

import qrcode


_TELEFONO_AURA = "999 888 777"


def _qr_base64_png(texto: str) -> str:
    """Genera un QR a partir de `texto` y retorna PNG base64 (data URI)."""
    img = qrcode.make(texto, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def datos_para_metodo(metodo: str, pedido_id: str, total: float) -> dict[str, Any]:
    """Devuelve el bloque estructurado de instrucciones de pago."""
    m = (metodo or "").lower().replace(" ", "_")
    base = {
        "metodo": m,
        "pedido_id": pedido_id,
        "total": total,
        "requiere_voucher": False,
    }

    if m in ("tarjeta", "niubiz"):
        base.update({
            "metodo": "niubiz",
            "instrucciones": (
                "Paga con tarjeta desde el checkout seguro de Niubiz. "
                "Al aprobarse la transaccion, el pedido se confirma automaticamente."
            ),
            "pasarela": "Niubiz",
            "moneda": "PEN",
            "requiere_voucher": False,
            "requiere_pasarela": True,
            "boton_texto": "Pagar con Niubiz",
        })
        return base

    if m in ("yape", "plin"):
        base.update({
            "instrucciones": (
                f"1. Abre tu app de {m.capitalize()}.\n"
                f"2. Escanea el QR o envía S/ {total:.2f} al número {_TELEFONO_AURA}.\n"
                f"3. En el mensaje pon tu número de pedido: {pedido_id}\n"
                "4. Sube la captura de pantalla (voucher) para confirmar tu compra."
            ),
            "requiere_voucher": True,
            "qr_data": _qr_base64_png(f"00020101021226500014*.pe.com.yape0224{_TELEFONO_AURA}5204000053036045404{total:.2f}5802PE5913AURA Boutique6004LIMA6304"),
        })
        return base

    if m == "contra_entrega":
        base.update({
            "instrucciones": (
                "Pagas en efectivo o tarjeta al momento de recibir tu pedido. "
                "No requiere enviar voucher previo."
            ),
            "requiere_voucher": False,
        })
        return base

    if m == "paypal":
        base.update({
            "instrucciones": (
                "Envía el pago a pagos@auraboutique.com y sube tu comprobante."
            ),
            "requiere_voucher": True,
        })
        return base

    base.update({
        "instrucciones": (
            f"No reconocemos el metodo '{metodo}'. "
            "Por favor, elige Yape, Plin, Tarjeta o Contra Entrega."
        ),
        "requiere_voucher": False,
        "invalido": True,
    })
    return base


METODOS_VALIDOS = {"tarjeta", "niubiz", "yape", "plin", "contra_entrega", "paypal"}
