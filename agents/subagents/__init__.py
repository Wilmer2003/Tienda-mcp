"""Subagentes especializados del sistema multi-agente."""
from agents.subagents.catalogo import CatalogoAgent
from agents.subagents.inventario import InventarioAgent
from agents.subagents.ventas import VentasAgent
from agents.subagents.pagos import PagosAgent
from agents.subagents.soporte import SoporteAgent

__all__ = ["CatalogoAgent", "InventarioAgent", "VentasAgent",
           "PagosAgent", "SoporteAgent"]
