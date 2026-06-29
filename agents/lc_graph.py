"""
agents/lc_graph.py
==================
Grafo LangGraph con supervisor simple compatible con Groq.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv
load_dotenv()
import re
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import create_react_agent

from agents.lc_tools import get_mcp_tools, split_tools

PROMPTS_DIR = Path(__file__).parent / "prompts"

MEMBERS = ["catalogo", "inventario", "ventas", "finanzas", "soporte"]

# ---------------------------------------------------------------------------
# LLM compartido
# ---------------------------------------------------------------------------
def _llm() -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
    )


# ---------------------------------------------------------------------------
# Supervisor simple — sin structured_output, usa texto plano
# ---------------------------------------------------------------------------
SUPERVISOR_SYSTEM = """Eres el supervisor de un sistema multiagente de tienda virtual.
Tu única tarea es decidir qué agente debe atender el mensaje del usuario.

Agentes disponibles:
- catalogo: buscar productos, recomendaciones, información de productos
- inventario: verificar stock, historial de inventario
- ventas: agregar al carrito, ver carrito, crear pedido
- finanzas: procesar pago, consultar pedido, transacciones
- soporte: ayuda general, preguntas frecuentes

Responde SOLO con el nombre del agente (una sola palabra, en minúsculas).
Si ya hay una respuesta completa del agente en el historial, responde: __end__
"""

def make_supervisor_node(llm):
    def supervisor_node(state: MessagesState):
        messages = [SystemMessage(content=SUPERVISOR_SYSTEM)] + state["messages"]
        response = llm.invoke(messages)
        text = response.content.strip().lower()

        # Extraer el agente del texto
        next_agent = "__end__"
        for member in MEMBERS:
            if member in text:
                next_agent = member
                break

        return {"next_agent": next_agent, "messages": state["messages"]}

    return supervisor_node


# ---------------------------------------------------------------------------
# Nodos de subagentes
# ---------------------------------------------------------------------------
def make_agent_node(nombre: str, tools: list, llm):
    prompt_file = PROMPTS_DIR / f"{nombre}.md"
    system_prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else ""

    agent = create_react_agent(
        llm,
        tools=tools,
        prompt=system_prompt,
    )

    async def agent_node(state: MessagesState):
        result = await agent.ainvoke(state)
        return {"messages": result["messages"], "next_agent": "__end__"}

    return agent_node


# ---------------------------------------------------------------------------
# Router condicional
# ---------------------------------------------------------------------------
def route_to_agent(state: dict) -> str:
    return state.get("next_agent", "__end__")


# ---------------------------------------------------------------------------
# State con campo extra
# ---------------------------------------------------------------------------
from typing import Annotated
from langgraph.graph.message import add_messages

class AgentState(MessagesState):
    next_agent: str = ""


# ---------------------------------------------------------------------------
# Builder principal
# ---------------------------------------------------------------------------
async def build_graph(checkpointer=None):
    all_tools = await get_mcp_tools()
    tools_by_agent = split_tools(all_tools)

    llm = _llm()

    builder = StateGraph(AgentState)

    supervisor = make_supervisor_node(llm)
    builder.add_node("supervisor", supervisor)

    for nombre in MEMBERS:
        tools = tools_by_agent.get(nombre, [])
        node_fn = make_agent_node(nombre, tools, llm)
        builder.add_node(nombre, node_fn)
        builder.add_edge(nombre, "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        route_to_agent,
        {**{m: m for m in MEMBERS}, "__end__": END},
    )

    builder.add_edge(START, "supervisor")

    cp = checkpointer or MemorySaver()
    return builder.compile(checkpointer=cp)
