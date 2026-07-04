"""
graph/builder.py
================
Constructor del StateGraph (Orquestador LangGraph) de la Tienda Virtual.

Reemplaza progresivamente al orquestador actual. 
Flujo: START -> Supervisor -> [Agente] -> END
"""
from __future__ import annotations

import os
from typing import Literal

# -----------------------------------------------------------------------------
# OBSERVABILIDAD LANGSMITH (Capa 11)
# -----------------------------------------------------------------------------
if "LANGSMITH_API_KEY" in os.environ and "LANGCHAIN_API_KEY" not in os.environ:
    os.environ["LANGCHAIN_API_KEY"] = os.environ["LANGSMITH_API_KEY"]

# Solo forzar tracing si hay una API key disponible
if os.getenv("LANGCHAIN_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "true")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "AURA_Boutique_LangGraph")
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from graph.state import AgentState
from tools import store_tools
from prompts import (
    supervisor_prompt,
    catalogo_prompt,
    inventario_prompt,
    ventas_prompt,
    pagos_prompt,
    soporte_prompt
)

def _get_llm() -> ChatGroq:
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.2,
    )

# -----------------------------------------------------------------------------
# NODOS
# -----------------------------------------------------------------------------

async def supervisor_node(state: AgentState) -> dict:
    llm = _get_llm()
    mensajes_recientes = state["messages"][-6:] if len(state["messages"]) > 6 else state["messages"]
    messages = [SystemMessage(content=supervisor_prompt.SYSTEM_PROMPT)] + mensajes_recientes
    response = await llm.ainvoke(messages)
    text = str(response.content).strip().lower()
    
    # Extraer el agente destino de la respuesta
    next_action = END
    agentes = ["catalogo", "inventario", "ventas", "pagos", "soporte"]
    
    # Manejar sinónimos de prompts antiguos
    if "finanzas" in text:
        text += " pagos"
    if "consultas" in text:
        text += " catalogo"
        
    for agent in agentes:
        if agent in text:
            next_action = agent
            break
            
    return {"next_action": next_action}


def make_agent_node(agent_name: str, system_prompt: str, tools: list):
    """
    Crea un nodo envolviendo un create_react_agent.
    Se inyecta el user_id y session_id en el prompt si es necesario.
    """
    async def node(state: AgentState) -> dict:
        llm = _get_llm()
        
        # Inyectar el user_id al prompt para que el LLM sepa qué id usar en las tools
        uid = state.get("user_id", "anonimo")
        prompt_dinamico = system_prompt + f"\n\n[INFO DEL SISTEMA] El usuario actual tiene ID: {uid}. Usa este ID al invocar herramientas que lo requieran."
        
        react_agent = create_react_agent(llm, tools=tools, prompt=prompt_dinamico)
        
        # Truncar historial a los últimos 10 mensajes para evitar Rate Limits de Groq
        mensajes_recientes = state["messages"][-10:] if len(state["messages"]) > 10 else state["messages"]
        result = await react_agent.ainvoke({"messages": mensajes_recientes})
        
        # Guardar el estado
        return {
            "messages": result["messages"], 
            "current_agent": agent_name
        }
    return node


# -----------------------------------------------------------------------------
# DICCIONARIO DE HERRAMIENTAS POR AGENTE
# -----------------------------------------------------------------------------
AGENT_TOOLS = {
    "catalogo": [store_tools.buscar_productos, store_tools.obtener_producto],
    "inventario": [store_tools.verificar_inventario, store_tools.consultar_historial_inventario],
    "ventas": [store_tools.agregar_al_carrito, store_tools.eliminar_del_carrito, store_tools.ver_carrito, store_tools.vaciar_carrito, store_tools.crear_pedido],
    "pagos": [store_tools.crear_pedido, store_tools.consultar_pedido, store_tools.consultar_transacciones_niubiz],
    "soporte": [store_tools.consultar_pedido]
}

AGENT_PROMPTS = {
    "catalogo": catalogo_prompt.SYSTEM_PROMPT,
    "inventario": inventario_prompt.SYSTEM_PROMPT,
    "ventas": ventas_prompt.SYSTEM_PROMPT,
    "pagos": pagos_prompt.SYSTEM_PROMPT,
    "soporte": soporte_prompt.SYSTEM_PROMPT
}

# -----------------------------------------------------------------------------
# EDGES CONDICIONALES
# -----------------------------------------------------------------------------
def route_after_supervisor(state: AgentState) -> str:
    """Enruta basándose en la decisión del supervisor guardada en next_action."""
    return state.get("next_action", END)

# -----------------------------------------------------------------------------
# CONSTRUCTOR DEL GRAFO
# -----------------------------------------------------------------------------
def build_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    
    # 1. Agregar nodos
    builder.add_node("supervisor", supervisor_node)
    
    for agent_name in AGENT_TOOLS.keys():
        node_func = make_agent_node(
            agent_name=agent_name,
            system_prompt=AGENT_PROMPTS[agent_name],
            tools=AGENT_TOOLS[agent_name]
        )
        builder.add_node(agent_name, node_func)
        
    # 2. Agregar edges
    builder.add_edge(START, "supervisor")
    
    # 3. Conditional edges desde supervisor
    destinations = {agent: agent for agent in AGENT_TOOLS.keys()}
    destinations[END] = END
    
    builder.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        destinations
    )
    
    # 4. Finalizar
    for agent_name in AGENT_TOOLS.keys():
        builder.add_edge(agent_name, END)
        
    cp = checkpointer or MemorySaver()
    return builder.compile(checkpointer=cp)
