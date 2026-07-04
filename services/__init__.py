"""
services/
=========
Capa de Servicios de la Tienda Virtual (LangChain/LangGraph architecture).

Esta capa consolida todas las integraciones externas y la lógica de negocio pura.
Se actúa como una fachada (facade) sobre los módulos existentes para no romper
las integraciones del servidor MCP actual ("No cambiar rutas existentes").

Servicios expuestos:
- TIENDA: Lógica de negocio y estado del catálogo/carrito (store_logic)
- NOTION: Cliente de integración con Notion (notion_client)
- NIUBIZ: Cliente de integración con pasarela de pagos (niubiz_client)
- auth: Utilidades de validación de Firebase (web.auth)
"""

# Re-exportamos los servicios ya desacoplados para uso en LangChain
from server.store_logic import TIENDA
from server.notion_client import NOTION
from server.niubiz_client import NIUBIZ
from web import auth

__all__ = [
    "TIENDA",
    "NOTION",
    "NIUBIZ",
    "auth"
]
