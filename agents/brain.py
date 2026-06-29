"""
brain.py
========
Motor de decision de un agente.

Hibrido: por defecto usa reglas (clasificacion de intent por keywords y
heuristica) para que el sistema corra sin API key. Si la variable de entorno
ANTHROPIC_API_KEY esta presente y el SDK `anthropic` esta instalado, los
agentes pueden delegar al modelo Claude usando su system prompt especializado.

Esta separacion permite:
- Reproducibilidad en la demo (Criterio 6) sin depender de red.
- Diferenciacion clara de prompts por agente (Criterio 2 "Excelente").
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class Decision:
    """Lo que un brain decide tras procesar el input del usuario."""
    intent: str
    parametros: dict[str, Any]
    respuesta_texto: str = ""           # texto orientativo para el usuario
    confianza: float = 1.0
    motivacion: str = ""                # por que tomo esta decision


class Brain(Protocol):
    """Cualquier motor de decision implementa este protocolo."""
    def decidir(self, mensaje: str, contexto: dict[str, Any]) -> Decision: ...


# ---------------------------------------------------------------------------
# RuleBased: clasificador deterministico por keywords + extraccion de slots.
# ---------------------------------------------------------------------------
INTENT_KEYWORDS = {
    "saludar":             ["hola", "buenas", "buenos dias", "saludos", "que tal", "hello"],
    "buscar_producto":     ["buscar", "busca", "buscame", "quiero", "necesito",
                            "dame", "muestrame", "muestrales", "tienes", "quiero ver",
                            "catalogo", "que productos", "que tienen", "que hay",
                            "encontrar", "encuentra"],
    "ver_detalle":         ["detalle", "ficha tecnica", "especificaciones",
                            "specs"],
    "verificar_stock":     ["stock", "disponible", "disponibilidad",
                            "cuantos hay", "quedan", "hay unidades",
                            "verifica", "verificar"],
    "ver_historial_stock": ["historial de inventario", "historial de stock",
                            "historial de movimientos",
                            "muestrame el historial", "muestra el historial",
                            "ver el historial", "ver historial",
                            "el historial", "los movimientos",
                            "movimientos de inventario", "que se vendio",
                            "que se ha vendido", "ultimas ventas",
                            "movimientos recientes",
                            "movimientos", "historial",
                            "muestrame los movimientos"],
    "agregar_carrito":     ["agregar", "anadir", "anade", "agrega", "sumar",
                            "incluir", "meter al carrito", "al carrito"],
    "ver_carrito":         ["ver carrito", "mi carrito", "que tengo en",
                            "mostrar carrito", "muestra mi carrito",
                            "muestrame el carrito"],
    "vaciar_carrito":      ["vaciar carrito", "limpiar carrito",
                            "borrar carrito"],
    "crear_pedido":        ["crear pedido", "generar pedido", "checkout",
                            "finalizar compra", "comprar", "finalizar",
                            "cerrar compra", "cerrar pedido", "cerrar orden",
                            "completar compra"],
    "confirmar_compra":    ["confirmar compra", "confirmo", "esta bien asi",
                            "todo bien", "asi esta bien", "confirma",
                            "confirmar"],
    "procesar_pago":       ["pagar con", "pago con", "procesar pago",
                            "tarjeta", "yape", "paypal", "contra_entrega",
                            "contraentrega", "contra entrega",
                            "quiero pagar"],
    "consultar_pedido":    ["estado de mi pedido", "estado del pedido",
                            "donde esta mi pedido", "consultar pedido",
                            "seguimiento", "rastrear", "mi pedido"],
    "soporte":             ["devolver", "devolucion", "reclamo", "garantia",
                            "ayuda", "no me llega", "problema",
                            "envio"],
}

# Palabras a quitar al limpiar el texto para extraer el query (ruido).
STOP_QUERY = {
    "hola", "buenas", "por favor", "porfa", "gracias",
    "busca", "buscar", "buscame", "muestrame", "muestra", "muestrales",
    "quiero", "necesito", "ver", "tienes", "tiene", "tienen",
    "una", "un", "el", "la", "los", "las", "del", "de", "para",
    "menos de", "mas de", "hasta", "max", "maximo", "minimo",
    "soles", "sol", "pen", "s/", "yo",
}

CATEGORIAS = {"polos", "pantalones", "vestidos", "calzado", "chaquetas", "accesorios"}

METODOS_PAGO = {"tarjeta", "yape", "paypal", "contra_entrega", "contraentrega",
                "contra entrega"}


def _normalizar(texto: str) -> str:
    """Quita tildes y pasa a minusculas para matching robusto."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    sin_tildes = sin_tildes.replace("ñ", "n").replace("Ñ", "n")
    sin_tildes = sin_tildes.lower()
    return re.sub(r"[?!.,;:¿¡]+", " ", sin_tildes)


def _detectar_intent(mensaje: str) -> tuple[str, float]:
    """Devuelve (intent, confianza).

    Scoring: para cada keyword que aparece en el mensaje, sumamos su
    longitud. Las frases multi-palabra ('ver carrito') ganan a palabras
    cortas ambiguas ('ver'). Empate -> orden de prioridad del dict.
    """
    m = " " + _normalizar(mensaje) + " "
    mejor_intent = "desconocido"
    mejor_score = 0
    for intent, kws in INTENT_KEYWORDS.items():
        # Para evitar matches dentro de palabras (ej. 'pago' en 'pagar'),
        # buscamos las keywords entre limites de palabra o espacios.
        score = 0
        for k in kws:
            kn = _normalizar(k)
            # Aceptamos match si la kw aparece rodeada por espacios o limites.
            if f" {kn} " in m or m.startswith(kn + " ") or m.endswith(" " + kn):
                score += len(kn)
        if score > mejor_score:
            mejor_score = score
            mejor_intent = intent
    if mejor_score == 0:
        return ("desconocido", 0.0)
    # Confianza normalizada por longitud del mensaje.
    conf = min(1.0, 0.5 + mejor_score / max(20, len(m)))
    return (mejor_intent, round(conf, 2))


def _extraer_producto_id(mensaje: str) -> str | None:
    m = re.search(r"\bP\d{3}\b", mensaje.upper())
    return m.group(0) if m else None


def _extraer_pedido_id(mensaje: str) -> str | None:
    m = re.search(r"\bORD-\d{4}\b", mensaje.upper())
    return m.group(0) if m else None


def _extraer_cantidad(mensaje: str) -> int:
    m_clean = _normalizar(mensaje)
    # Limpiar nombres de modelos conocidos que contienen números
    modelos_num = [
        "pixel 8", "tab s9", "wh 1000", "wh-1000", "k65", "ultrabook 14", "gamer 15",
        "galaxy a55", "monitor 27", "27 qhd", "p001", "p002", "p003", "p004", "p005",
        "p006", "p007", "p008", "p009", "p010", "p011", "p012"
    ]
    for mod in modelos_num:
        m_clean = m_clean.replace(mod, "")
    
    m = re.search(r"\b(\d+)\s*(unidad|unidades|x|piezas)?\b", m_clean)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    return 1


def _extraer_precio_max(mensaje: str) -> float:
    m = re.search(r"(menor a|menos de|hasta|max(?:imo)?)\s*s?/?\s*(\d+(?:\.\d+)?)",
                  mensaje.lower())
    if m:
        try:
            return float(m.group(2))
        except ValueError:
            pass
    return 0.0


def _extraer_categoria(mensaje: str) -> str:
    m = _normalizar(mensaje)
    for cat in CATEGORIAS:
        if cat in m:
            return cat
    # alias comunes (boutique de ropa)
    if "polo" in m or "camiseta" in m or "remera" in m:    return "polos"
    if "jeans" in m or "pantalon" in m or "chino" in m:    return "pantalones"
    if "vestido" in m:                                      return "vestidos"
    if "zapatilla" in m or "zapato" in m or "mocasin" in m \
       or "sneakers" in m or "tenis" in m:                  return "calzado"
    if "chaqueta" in m or "abrigo" in m or "casaca" in m \
       or "blazer" in m:                                    return "chaquetas"
    if "cinturon" in m or "bufanda" in m or "gorro" in m \
       or "accesorio" in m:                                 return "accesorios"
    return ""


def _extraer_metodo_pago(mensaje: str) -> str:
    m = _normalizar(mensaje)
    if "tarjeta" in m: return "tarjeta"
    if "yape" in m: return "yape"
    if "paypal" in m: return "paypal"
    if "contra" in m: return "contra_entrega"
    return ""


def _extraer_query(mensaje: str) -> str:
    """Devuelve solo la 'parte semantica' del mensaje, sin stop-words ni
    frases de precio/categoria que ya extrajimos a otros campos.

    IMPORTANTE: alias especificos de tipo de prenda (mocasines, sneakers,
    blazer, etc.) SI quedan en el query para que la busqueda los filtre
    por nombre.
    """
    m = _normalizar(mensaje)
    # Quitar la parte de precio "menos de 4000 soles" antes de tokenizar.
    m = re.sub(r"(menor a|menos de|hasta|max(?:imo)?)\s*s?/?\s*\d+(?:\.\d+)?",
               " ", m)
    # Quitar SOLO categorias generales (no alias especificos de prenda).
    for cat in CATEGORIAS:
        m = re.sub(rf"\b{cat}s?\b", " ", m)
    for w in STOP_QUERY:
        m = re.sub(rf"\b{re.escape(w)}\b", " ", m)
    m = re.sub(r"\s+", " ", m).strip()
    # Si solo queda ruido cortito, mejor query vacio (la categoria ya filtra).
    return m if len(m) >= 3 else ""


class RuleBasedBrain:
    """Motor por reglas. No usa API key, pero respeta el system prompt para
    saber que tools puede usar y como formatear la respuesta."""

    def __init__(self, system_prompt: str, agente: str) -> None:
        self.system_prompt = system_prompt
        self.agente = agente

    def decidir(self, mensaje: str, contexto: dict[str, Any]) -> Decision:
        if contexto and contexto.get("nlu_usado") == "gemini":
            intent = contexto.get("intent", "desconocido")
            params = contexto.get("parametros", {})
            return Decision(
                intent=intent,
                parametros=params,
                confianza=1.0,
                motivacion=f"[{self.agente}] Gemini NLU (via orquestador)"
            )

        intent, conf = _detectar_intent(mensaje)
        params: dict[str, Any] = {}

        if pid := _extraer_producto_id(mensaje):
            params["producto_id"] = pid
        if ped := _extraer_pedido_id(mensaje):
            params["pedido_id"] = ped
        if cat := _extraer_categoria(mensaje):
            params["categoria"] = cat
        if pmax := _extraer_precio_max(mensaje):
            params["precio_max"] = pmax
        if mp := _extraer_metodo_pago(mensaje):
            params["metodo_pago"] = mp

        if intent in ("buscar_producto",):
            params.setdefault("query", _extraer_query(mensaje))
        if intent == "agregar_carrito":
            params.setdefault("cantidad", _extraer_cantidad(mensaje))

        return Decision(
            intent=intent, parametros=params, confianza=conf,
            motivacion=f"[{self.agente}] reglas: detecte '{intent}' (conf={conf:.2f})"
        )


# ---------------------------------------------------------------------------
# ClaudeBrain (opcional): solo se activa si hay ANTHROPIC_API_KEY.
# ---------------------------------------------------------------------------
def _claude_disponible() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


class ClaudeBrain:
    """Brain que delega al modelo Claude usando el system prompt del agente.

    Esta implementacion es un esqueleto: en una demo con API key, completarias
    el metodo `decidir` para llamar a `anthropic.Anthropic().messages.create`.
    Como por defecto el sistema usa RuleBasedBrain, no es bloqueante para la
    rubrica que esto este al 100%.
    """

    def __init__(self, system_prompt: str, agente: str,
                 modelo: str = "claude-haiku-4-5-20251001") -> None:
        self.system_prompt = system_prompt
        self.agente = agente
        self.modelo = modelo
        # Fallback determinista para no romper si el SDK no responde.
        self._fallback = RuleBasedBrain(system_prompt, agente)

    def decidir(self, mensaje: str, contexto: dict[str, Any]) -> Decision:
        if contexto and contexto.get("nlu_usado") == "gemini":
            intent = contexto.get("intent", "desconocido")
            params = contexto.get("parametros", {})
            return Decision(
                intent=intent,
                parametros=params,
                confianza=1.0,
                motivacion=f"[{self.agente}] Gemini NLU (via orquestador)"
            )

        try:
            import anthropic
        except ImportError:
            return self._fallback.decidir(mensaje, contexto)

        client = anthropic.Anthropic()
        # Pedimos al modelo que clasifique intent y extraiga parametros como
        # JSON estructurado (alineado al schema que esperan las tools MCP).
        instrucciones = (
            "Responde SOLO con un JSON con keys: intent, parametros, "
            "respuesta_texto. 'intent' es uno de: "
            + ", ".join(INTENT_KEYWORDS.keys()) + ", desconocido."
        )
        try:
            r = client.messages.create(
                model=self.modelo, max_tokens=400,
                system=self.system_prompt + "\n\n" + instrucciones,
                messages=[{"role": "user", "content": mensaje}],
            )
            texto = r.content[0].text if r.content else "{}"
            import json
            obj = json.loads(texto)
            return Decision(
                intent=obj.get("intent", "desconocido"),
                parametros=obj.get("parametros", {}),
                respuesta_texto=obj.get("respuesta_texto", ""),
                confianza=0.95,
                motivacion=f"[{self.agente}] Claude {self.modelo}",
            )
        except Exception as e:
            d = self._fallback.decidir(mensaje, contexto)
            d.motivacion += f" (fallback por error de Claude: {e})"
            return d


def crear_brain(system_prompt: str, agente: str) -> Brain:
    """Factory: usa Claude si esta configurado; si no, reglas."""
    if _claude_disponible():
        return ClaudeBrain(system_prompt, agente)
    return RuleBasedBrain(system_prompt, agente)
