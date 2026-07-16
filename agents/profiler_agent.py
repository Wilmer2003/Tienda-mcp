"""
profiler_agent.py
=================
Agente asíncrono en segundo plano responsable de la Memoria Evolutiva (Fase 3).
"""
import asyncio
import logging
import json
from typing import Any

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agents.event_bus import BUS, EventType, Evento
from web.lc_adapter import LC_ADAPTER
from server.notion_client import NOTION

logger = logging.getLogger("profiler")

class PerfilDelta(BaseModel):
    hubo_cambios_relevantes: bool = Field(description="True si se descubrio nueva informacion comercial (gustos, tallas, comportamiento). False si fue irrelevante.")
    preferencias: list[str] = Field(description="Lista FUSIONADA final de preferencias. NUNCA eliminar las que ya existian.", default_factory=list)
    tallas_habituales: list[str] = Field(description="Lista FUSIONADA final de tallas.", default_factory=list)
    resumen_evolutivo: str = Field(description="El resumen historico actualizado con las nuevas observaciones.", default="")

PROMPT_PROFILER = """Eres el Analista Profiler de AURA Boutique.
Tu tarea es aplicar Memoria Evolutiva al perfil del cliente basandote en su ultima interaccion.

REGLAS DE MEMORIA ACUMULATIVA:
1. FUSIÓN (MERGE): Las 'preferencias' y 'tallas' que generes deben INCLUIR las actuales. Nunca elimines una preferencia previa a menos que el cliente la rechace explícitamente.
2. ENRIQUECIMIENTO: Tu 'resumen_evolutivo' no debe ser un relato del chat actual. Toma el 'Resumen Historico' actual y añadale o modificale el nuevo comportamiento descubierto.
3. EFICIENCIA (DELTA): Si el chat fue trivial (saludos, consultas vagas sin conclusion), devuelve hubo_cambios_relevantes = False.

--- PERFIL ACTUAL DEL CLIENTE ---
Preferencias actuales: {preferencias_actuales}
Tallas actuales: {tallas_actuales}
Resumen Historico: {resumen_actual}

--- INTERACCION RECIENTE ---
Trigger de Analisis: {trigger_evento}
Datos del evento: {datos_evento}

Historial Filtrado:
{historial_texto}

IMPORTANTE: Responde ÚNICAMENTE con un objeto en formato json con esta estructura exacta:
{{
  "hubo_cambios_relevantes": boolean,
  "preferencias": ["lista", "de", "strings"],
  "tallas_habituales": ["lista", "de", "strings"],
  "resumen_evolutivo": "string con el resumen fusionado"
}}
Usa estrictamente 'true' o 'false' en minúsculas para los booleanos.
"""

class ProfilerAgent:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        # Timers para debouncing: usuario_id -> asyncio.Task
        self._debounce_timers: dict[str, asyncio.Task] = {}
        self._subscribe()

    def _subscribe(self):
        # Escuchar eventos relevantes (Triggers)
        BUS.subscribe(EventType.PAGO_APROBADO, self._on_evento)
        # Preparación para futuros eventos:
        # BUS.subscribe(EventType.CARRITO_ABANDONADO, self._on_evento)
        # BUS.subscribe(EventType.INACTIVIDAD_DETECTADA, self._on_evento)
        
    def _on_evento(self, evento: Evento):
        """Callback síncrono disparado por el EventBus."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._manejar_evento_async(evento))
        except RuntimeError:
            logger.error("[profiler] No se pudo obtener el event loop para ejecutar la tarea asíncrona.")

    def _get_lock(self, usuario_id: str) -> asyncio.Lock:
        if usuario_id not in self._locks:
            self._locks[usuario_id] = asyncio.Lock()
        return self._locks[usuario_id]

    async def _manejar_evento_async(self, evento: Evento):
        usuario_id = evento.datos.get("usuario_id")
        
        if not usuario_id:
            logger.warning(f"[profiler] Evento {evento.tipo.value} ignorado: falta usuario_id.")
            return

        logger.info(f"[profiler] Trigger recibido: {evento.tipo.value} para usuario: {usuario_id}")
        
        # Debouncing (espera 2 segundos para agrupar eventos rápidos)
        if usuario_id in self._debounce_timers:
            self._debounce_timers[usuario_id].cancel()
            logger.info(f"[profiler] Debouncing: cancelando ejecución previa para {usuario_id}")
            
        task = asyncio.create_task(self._procesar_perfil_con_lock(usuario_id, evento))
        self._debounce_timers[usuario_id] = task

    async def _procesar_perfil_con_lock(self, usuario_id: str, evento: Evento):
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            return

        lock = self._get_lock(usuario_id)
        async with lock:
            logger.info(f"[profiler] Lock adquirido para {usuario_id}. Iniciando análisis...")
            
            # Paso 1: Leer historial reciente (filtrado para ahorrar tokens)
            historial_crudo = await LC_ADAPTER.get_raw_history(usuario_id)
            mensajes_filtrados = []
            for m in historial_crudo[-20:]:  # Limitar contexto
                if isinstance(m, HumanMessage):
                    mensajes_filtrados.append(f"Cliente: {m.content}")
                elif isinstance(m, ToolMessage):
                    mensajes_filtrados.append(f"Herramienta Ejecutada: {m.name} -> {str(m.content)[:100]}...")
                elif isinstance(m, AIMessage) and m.tool_calls:
                    tools = ", ".join([t['name'] for t in m.tool_calls])
                    mensajes_filtrados.append(f"Agente decidio usar herramientas: {tools}")
            
            historial_texto = "\n".join(mensajes_filtrados) if mensajes_filtrados else "No hay conversacion reciente."
            
            # Paso 2: Leer el perfil actual de Notion (Read-Modify-Write)
            perfil_actual = NOTION.cargar_perfil_cliente(usuario_id) or {}
            
            # Paso 3: Evaluar Delta con LLM
            prompt = PROMPT_PROFILER.format(
                preferencias_actuales=perfil_actual.get("preferencias", "Ninguna registrada"),
                tallas_actuales=perfil_actual.get("tallas_habituales", "Ninguna registrada"),
                resumen_actual=perfil_actual.get("resumen_evolutivo", "Cliente nuevo sin resumen."),
                trigger_evento=evento.tipo.value,
                datos_evento=json.dumps(evento.datos),
                historial_texto=historial_texto
            )
            
            llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.1).bind(response_format={"type": "json_object"})
            
            try:
                logger.info("[profiler] Invocando LLM para analisis de perfil...")
                resp = await llm.ainvoke(prompt)
                
                # Paso 4: Validar Delta y Escribir en Notion
                datos = json.loads(resp.content)
                resultado = PerfilDelta(**datos)
                
                logger.info(f"[profiler] Analisis finalizado. Hubo cambios: {resultado.hubo_cambios_relevantes}")
                if resultado.hubo_cambios_relevantes:
                    logger.info(f"[profiler] JSON RESULTANTE:\n{resultado.model_dump_json(indent=2)}")
                    
                    # Calcular Delta
                    delta = {}
                    
                    # Comparar Preferencias
                    pref_actuales = set([p.strip().lower() for p in perfil_actual.get("preferencias", "").split(",") if p.strip()])
                    pref_nuevas = set([p.strip().lower() for p in resultado.preferencias if p.strip()])
                    if pref_actuales != pref_nuevas:
                        delta["preferencias"] = resultado.preferencias
                        
                    # Comparar Tallas
                    tallas_actuales = set([t.strip().lower() for t in perfil_actual.get("tallas_habituales", "").split(",") if t.strip()])
                    tallas_nuevas = set([t.strip().lower() for t in resultado.tallas_habituales if t.strip()])
                    if tallas_actuales != tallas_nuevas:
                        delta["tallas_habituales"] = resultado.tallas_habituales
                        
                    # Comparar Resumen
                    if perfil_actual.get("resumen_evolutivo", "") != resultado.resumen_evolutivo:
                        delta["resumen_evolutivo"] = resultado.resumen_evolutivo
                        
                    # Aplicar Partial Update solo si hay cambios
                    if delta:
                        logger.info(f"[profiler] Ejecutando Partial Update en Notion. Delta: {delta}")
                        exito = NOTION.actualizar_perfil_cliente(usuario_id, delta)
                        if exito:
                            logger.info("[profiler] Perfil actualizado exitosamente en Notion.")
                        else:
                            logger.warning("[profiler] Error al intentar actualizar Notion (ver logs de Notion).")
                    else:
                        logger.info("[profiler] No se encontraron diferencias reales respecto a Notion. Omitiendo escritura.")
                        
                else:
                    logger.info("[profiler] El LLM decidio que no hay informacion nueva de valor. Omitiendo escritura.")
                    
            except Exception as e:
                logger.error(f"[profiler] Error durante la evaluacion del LLM: {e}")
            
            logger.info(f"[profiler] Analisis concluido para {usuario_id}. Lock liberado.")

# Inicialización Singleton para que se suscriba automáticamente al importar
PROFILER = ProfilerAgent()
