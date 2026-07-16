"""
graph/state.py
==============
Definición del State compartido para el ecosistema LangGraph de la tienda virtual.

Este estado reemplazará progresivamente al archivo shared_state.py.
Fue diseñado bajo un modelo minimalista, garantizando que solo la información
esencial de la sesión (contexto conversacional, contexto de compras y ruteo)
viaje a través del grafo.

Nota: No se almacenan datos permanentes aquí. La persistencia principal reside en
Notion/Firebase. Este estado sirve para el tracking contextual (thread_id)
utilizando el Checkpointer de LangGraph.
"""

import operator
from typing import Annotated, Any, TypedDict
from langchain_core.messages import BaseMessage


def add_messages(left: list[BaseMessage], right: list[BaseMessage]) -> list[BaseMessage]:
    """
    Combina los mensajes existentes con los nuevos.
    Se puede reemplazar con `from langgraph.graph.message import add_messages`
    una vez que se implemente LangGraph en el orquestador.
    """
    return left + right


class AgentState(TypedDict):
    """Estado compartido principal del Grafo conversacional."""
    
    # ----------------------------------------------------------------------
    # Historial y Sesión
    # ----------------------------------------------------------------------
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    
    # ----------------------------------------------------------------------
    # Enrutamiento e Intención
    # ----------------------------------------------------------------------
    current_agent: str
    current_intent: str
    next_action: str
    
    # ----------------------------------------------------------------------
    # Contexto de Negocio (Tienda Virtual)
    # ----------------------------------------------------------------------
    selected_product: str | None           # Producto en foco (ej: P001), reemplaza a producto_en_foco
    cart: dict[str, Any]                   # Resumen del carrito actual
    current_order: str | None              # ID del pedido en proceso, reemplaza a ultimo_pedido_id
    perfil_cliente: dict[str, Any] | None  # Perfil comercial desde Notion
    
    # ----------------------------------------------------------------------
    # Herramientas y Errores
    # ----------------------------------------------------------------------
    last_tool_used: str | None
    tool_result: dict[str, Any] | None
    error: str | None
    
    # ----------------------------------------------------------------------
    # Extensibilidad y Contexto Adicional
    # ----------------------------------------------------------------------
    metadata: dict[str, Any]               # Caché temporal (ej: alternativas_para_P001, candidatos_recientes)
