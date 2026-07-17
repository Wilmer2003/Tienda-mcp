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
        model="llama-3.3-70b-versatile",
        temperature=0.2,
    )

# -----------------------------------------------------------------------------
# NODOS
# -----------------------------------------------------------------------------

def filter_chat_history(messages, limit=10):
    filtered = []
    for m in messages:
        if m.type == "human":
            filtered.append(m)
        elif m.type == "ai" and not getattr(m, "tool_calls", None) and m.content:
            filtered.append(m)
    return filtered[-limit:] if len(filtered) > limit else filtered

async def supervisor_node(state: AgentState) -> dict:
    from server.notion_client import NOTION
    
    perfil = state.get("perfil_cliente")
    if perfil is None and NOTION.disponible:
        perfil = NOTION.cargar_perfil_cliente(state["user_id"])
        if perfil is None:
            perfil = {}  # Evitar consultas repetidas si no existe
            
    system_prompt = supervisor_prompt.SYSTEM_PROMPT
    if perfil and perfil.get("resumen_evolutivo"):
        system_prompt += f"\n\nContexto Evolutivo del Cliente:\n{perfil['resumen_evolutivo']}"

    llm = _get_llm()
    mensajes_recientes = filter_chat_history(state["messages"], limit=6)
    messages = [SystemMessage(content=system_prompt)] + mensajes_recientes
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
        
    # Buscar exactamente qué agentes se mencionan
    import re
    encontrados = re.findall(r'\b(?:catalogo|inventario|ventas|pagos|soporte)\b', text)
    if encontrados:
        # Tomar el ÚLTIMO agente mencionado por el LLM (suele ser su conclusión final)
        next_action = encontrados[-1]
        
    return {"next_action": next_action, "perfil_cliente": perfil}


def make_agent_node(agent_name: str, system_prompt: str, tools: list):
    """
    Crea un nodo envolviendo un create_react_agent.
    Se compila el agente una sola vez para mejorar el rendimiento.
    """
    llm = _get_llm()
    react_agent = create_react_agent(llm, tools=tools)
    
    from langchain_core.runnables import RunnableConfig
    
    async def node(state: AgentState, config: RunnableConfig) -> dict:
        prompt_dinamico = system_prompt
        
        perfil = state.get("perfil_cliente")
        if perfil and any(perfil.values()):
            prompt_dinamico += "\n\n--- PERFIL COMERCIAL DEL CLIENTE ---"
            if perfil.get("resumen_evolutivo"):
                prompt_dinamico += f"\nResumen: {perfil['resumen_evolutivo']}"
            if perfil.get("preferencias"):
                prompt_dinamico += f"\nPreferencias: {perfil['preferencias']}"
            if perfil.get("tallas_habituales"):
                prompt_dinamico += f"\nTallas Habituales: {perfil['tallas_habituales']}"
            if perfil.get("fidelizacion"):
                prompt_dinamico += f"\nNivel de Fidelización: {perfil['fidelizacion']}"
        
        # Truncar historial a los últimos 10 mensajes para evitar Rate Limits y crashes por mensajes huérfanos
        mensajes_recientes = filter_chat_history(state["messages"], limit=10)
        
        # Añadir el prompt dinámico como SystemMessage al inicio de este turno
        from langchain_core.messages import SystemMessage
        messages_to_pass = [SystemMessage(content=prompt_dinamico)] + mensajes_recientes
        
        # Pasar el config al react_agent para que las herramientas tengan acceso al thread_id (usuario_id)
        result = await react_agent.ainvoke({"messages": messages_to_pass}, config)
        
        # El react_agent devuelve TODOS los mensajes (los que le pasamos + los nuevos).
        # Para no duplicar el historial global, solo devolvemos los NUEVOS mensajes generados en este turno.
        num_input_messages = len(messages_to_pass)
        new_messages = result["messages"][num_input_messages:]
        
        # Limpiar cualquier SystemMessage residual por si acaso
        out_messages = [m for m in new_messages if not isinstance(m, SystemMessage)]
        
        return {
            "messages": out_messages, 
            "current_agent": agent_name
        }
    return node


# -----------------------------------------------------------------------------
# DICCIONARIO DE HERRAMIENTAS POR AGENTE
# -----------------------------------------------------------------------------
AGENT_TOOLS = {
    "catalogo": [store_tools.buscar_productos, store_tools.obtener_producto],
    "inventario": [store_tools.verificar_inventario, store_tools.consultar_historial_inventario],
    "ventas": [store_tools.buscar_productos, store_tools.agregar_al_carrito, store_tools.eliminar_del_carrito, store_tools.ver_carrito, store_tools.vaciar_carrito, store_tools.crear_pedido],
    "pagos": [store_tools.crear_pedido, store_tools.procesar_pago, store_tools.consultar_pedido, store_tools.consultar_transacciones_niubiz],
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
