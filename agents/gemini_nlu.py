"""
gemini_nlu.py
=============
Módulo NLU que utiliza la API de Gemini para interpretar intenciones y extraer variables.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Optional, Literal
from pydantic import BaseModel, Field
# pyrefly: ignore [missing-import]
from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types

logger = logging.getLogger("gemini_nlu")


class NLUResponse(BaseModel):
    intent: Literal["buscar_producto", "agregar_carrito", "ver_carrito", "pagar", "consultar_pedido", "fallback"]
    producto: Optional[str] = Field(default=None, description="Nombre o ID del producto mencionado. O null si no hay.")
    categoria: Optional[str] = Field(default=None, description="Categoría de producto (polos, pantalones, vestidos, calzado, chaquetas, accesorios). O null.")
    precio_max: Optional[float] = Field(default=None, description="Precio máximo en soles (número). O null.")
    metodo_pago: Optional[str] = Field(default=None, description="Método de pago (tarjeta, yape, paypal, contra_entrega). O null.")
    cantidad: int = Field(default=1, description="Cantidad de productos. Por defecto 1.")


async def interpretar_intencion(mensaje: str) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[GeminiNLU] Variable GEMINI_API_KEY no definida. Se usará fallback local.")
        return None

    try:
        client = genai.Client(api_key=api_key)

        system_instruction = (
            "Eres el módulo NLU de una boutique de ropa peruana llamada 'Tienda Solenne'. "
            "Tu tarea es clasificar la intención del usuario y extraer las variables clave en formato JSON. "
            "El catálogo contiene las siguientes prendas:\n"
            "- P001: Polo Básico Algodón Blanco Solenne Essentials (S/ 49.90)\n"
            "- P002: Polo Premium Negro Pima Co. (S/ 89.90)\n"
            "- P003: Jeans Slim Fit Azul Denim Lab (S/ 159)\n"
            "- P004: Pantalón Chino Beige Urban Co. (S/ 119)\n"
            "- P005: Vestido Floral Verano Bloom (S/ 179)\n"
            "- P006: Vestido Negro Elegante Noir Studio (S/ 249)\n"
            "- P007: Zapatillas Urban Sneakers Step (S/ 219)\n"
            "- P008: Mocasines Cuero Marrón Lazaro (S/ 289)\n"
            "- P009: Chaqueta de Cuero Negra Moto Lab (S/ 399)\n"
            "- P010: Abrigo Lana Beige Soft Wool (S/ 459)\n"
            "- P011: Cinturón Cuero Trenzado Cuir (S/ 79)\n"
            "- P012: Bufanda Lana Suave Soft Wool (S/ 59)\n\n"
            "Categorías permitidas: polos, pantalones, vestidos, calzado, chaquetas, accesorios.\n"
            "Métodos de pago permitidos: tarjeta, yape, paypal, contra_entrega.\n"
            "Si la consulta no encaja en las intenciones específicas, usa 'fallback'."
        )

        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=mensaje,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=NLUResponse,
                system_instruction=system_instruction,
                temperature=0.1,
            )
        )

        res_text = response.text
        if not res_text:
            return None

        return json.loads(res_text)

    except Exception as e:
        logger.error(f"[GeminiNLU] Error al llamar a Gemini: {e}. Se usará fallback local.")
        return None
