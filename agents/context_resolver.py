"""
context_resolver.py
===================
Resolucion de contexto conversacional.

Es la capa que da fluidez al sistema multi-agente. Sin ella, "es la unica?",
"cuanto cuesta?" o "agregala" se clasifican como intent desconocido. Con ella,
el orquestador los interpreta en el contexto del ultimo turno: si Catalogo
acaba de recomendar P007, "agregala" se rutea a Ventas con producto_id=P007.

Mecanismos:
  - PATRONES_SEGUIMIENTO  : frases que indican que el turno actual depende
    del turno anterior (referencias implicitas).
  - resolver_referencia(mensaje, sesion) -> producto_id | None
    busca pronombres / demostrativos / "ese" / "esa" y los resuelve contra
    `producto_en_foco` o `candidatos_recientes` de la sesion.
  - inferir_intent_seguimiento(mensaje, sesion) -> (intent, params) | None
    cuando el mensaje es de seguimiento, retorna el intent que el sistema
    deberia ejecutar (ej. 'agregar_carrito' + producto_id resuelto).

Sin LLM: todo determinista. Si Gemini esta presente, esta capa se ejecuta
antes que Gemini para resolver referencias triviales sin gastar tokens.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _norm(t: str) -> str:
    """Normaliza: minusculas, sin tildes, sin signos."""
    nfkd = unicodedata.normalize("NFKD", t)
    sin = "".join(c for c in nfkd if not unicodedata.combining(c))
    sin = sin.replace("ñ", "n").replace("Ñ", "n").lower()
    return re.sub(r"[?!.,;:¿¡]+", " ", sin)


# ---------------------------------------------------------------------------
# Patrones que detectan "esto depende de lo que dijimos antes".
# Cada patron tiene un nombre/categoria y una funcion que produce
# (intent_sugerido, parametros_extra) cuando matchea.
# ---------------------------------------------------------------------------
PATRONES_SEGUIMIENTO: list[tuple[str, str]] = [
    # (categoria, patron_regex_sobre_texto_normalizado)
    ("agregar",   r"\b(agregalo|agregala|agrega esa|agrega ese|agregame|"
                  r"quiero esa|quiero ese|quiero esta|comprala|compralo|"
                  r"la quiero|lo quiero|me lo llevo|me la llevo|"
                  r"agrega al carrito|ponla en el carrito|"
                  r"ponlo en el carrito|al carrito|sumala|sumalo)\b"),
    ("precio",    r"\b(cuanto cuesta|cuanto vale|que precio tiene|"
                  r"cual es el precio|precio)\b"),
    ("stock",     r"\b(hay stock|tiene stock|cuantas hay|cuantos quedan|"
                  r"esta disponible|hay disponibles?|queda alguna|queda alguno)\b"),
    ("hay_mas",   r"\b(es la unica|es el unico|hay mas|tienes mas|"
                  r"que mas tienes|otras opciones|otras alternativas|"
                  r"mostrame mas|otro modelo)\b"),
    ("detalle",   r"\b(dame detalles|mas info|mas informacion|"
                  r"cuentame mas|caracteristicas)\b"),
    # Ordinales sobre precio: aplican a los candidatos_recientes.
    ("mas_barato", r"\b(el mas barato|mas barato|el mas economico|"
                   r"mas economico|menor precio|el mas barato porfa|"
                   r"el barato|el economico|el mas accesible)\b"),
    ("mas_caro",  r"\b(el mas caro|mas caro|mayor precio|el mas premium|"
                  r"el premium|el mejor)\b"),
    # Ordinal de calidad: el de mejor rating.
    ("mejor_rated", r"\b(el mejor rateado|mejor calificado|el de mejor "
                    r"rating|el de mejor calificacion)\b"),
    ("afirmacion",r"\b(si|claro|por supuesto|ok|okay|dale|listo|"
                  r"hagamoslo|adelante)\b"),
    ("negacion",  r"\b(no|nop|nope|tampoco|ninguno|no me convence|"
                  r"otra cosa|prefiero otra)\b"),
]


def detectar_seguimiento(mensaje: str) -> str | None:
    """Retorna la categoria de seguimiento detectada o None.

    Reglas:
      1) Patrones explicitos (agregar/precio/stock/hay_mas/...) ganan.
      2) Si el mensaje contiene una palabra-comando o nombre de categoria
         de producto, NO es seguimiento (es busqueda/accion nueva).
      3) Si es muy corto (1-2 palabras) y sin keywords -> "ambiguo".
    """
    m = " " + _norm(mensaje) + " "
    palabras = m.strip().split()
    for cat, pat in PATRONES_SEGUIMIENTO:
        if re.search(pat, m):
            return cat
    # Palabras-comando claras o nombres de categoria: no son seguimiento,
    # son una nueva accion/busqueda. Las dejamos al NLU normal.
    palabras_comando = (
        "carrito", "carro", "pago", "pagar", "pedido", "checkout",
        "comprar", "compra", "vaciar", "buscar", "busca", "busqueda",
        "buscame", "lista", "catalogo", "ver",
    )
    categorias_y_alias = (
        "polo", "camiseta", "remera", "jeans", "pantalon", "chino",
        "vestido", "zapatilla", "zapato", "mocasin", "sneakers",
        "chaqueta", "abrigo", "casaca", "blazer", "cinturon", "bufanda",
        "accesorio",
    )
    for kw in (*palabras_comando, *categorias_y_alias):
        if f" {kw} " in m or f" {kw}s " in m:
            return None
    # Mensaje muy corto (1 o 2 palabras) y sin keywords reconocidas:
    # lo tratamos como seguimiento ambiguo (apuntara al foco si hay).
    if 1 <= len(palabras) <= 2:
        return "ambiguo"
    return None


def resolver_referencia(mensaje: str, sesion: Any) -> str | None:
    """Si el mensaje contiene una referencia implicita ('esa', 'la', 'esta',
    'el negro', 'el segundo'), devuelve el producto_id en foco o el que
    matchee por palabra clave entre los candidatos recientes.
    """
    if sesion is None:
        return None
    contexto = getattr(sesion, "contexto", None) or {}
    m = _norm(mensaje)
    candidatos = contexto.get("candidatos_recientes") or []

    # 1) Si el mensaje contiene una palabra distintiva que solo aparece en
    #    UNO de los candidatos, ese gana ("el negro", "el floral").
    if candidatos:
        from server.store_logic import TIENDA
        tokens_msg = [w for w in re.findall(r"[a-z0-9]+", m)
                      if len(w) >= 3 and w not in (
                          "los", "las", "una", "uno", "esa", "ese", "esta",
                          "este", "que", "con", "por", "para", "del",
                          "quiero", "muestra", "muestrame", "agregar", "agrega",
                      )]
        matches = []
        for pid in candidatos:
            p = TIENDA.obtener_producto(pid)
            if not p:
                continue
            nombre_norm = _norm(p.nombre + " " + p.marca + " " + p.descripcion)
            score = sum(1 for t in tokens_msg if t in nombre_norm)
            if score > 0:
                matches.append((score, pid))
        if matches:
            matches.sort(key=lambda x: -x[0])
            # Si el mejor candidato tiene score estrictamente mayor a todos
            # los demas, es la mejor referencia. Si hay empate, no asumimos.
            if len(matches) == 1 or matches[0][0] > matches[1][0]:
                return matches[0][1]

    # 2) Foco directo si esta seteado.
    foco = contexto.get("producto_en_foco")
    if foco:
        return foco

    # 3) Ordinales numericos sobre la lista de candidatos.
    if candidatos:
        ordinales = {
            "primero": 0, "primer": 0, "uno": 0, "1": 0,
            "segundo": 1, "segunda": 1, "2": 1,
            "tercero": 2, "tercera": 2, "3": 2,
            "ultimo": -1, "ultima": -1,
        }
        for kw, idx in ordinales.items():
            if re.search(rf"\b{kw}\b", m):
                if -len(candidatos) <= idx < len(candidatos):
                    return candidatos[idx]
        if len(candidatos) == 1:
            return candidatos[0]
    return None


def inferir_intent_seguimiento(
    mensaje: str, sesion: Any
) -> tuple[str, dict[str, Any]] | None:
    """Si el mensaje es seguimiento, retorna (intent, params) inferido.
    Si no hay forma de inferir, retorna None.
    """
    cat = detectar_seguimiento(mensaje)
    if cat is None:
        return None
    pid = resolver_referencia(mensaje, sesion)
    contexto = getattr(sesion, "contexto", None) or {} if sesion else {}
    ultima_categoria = contexto.get("ultima_categoria_consultada")
    ultimo_precio_max = contexto.get("ultimo_precio_max")

    if cat == "agregar":
        if not pid:
            return None
        return ("agregar_carrito", {"producto_id": pid, "cantidad": 1})

    if cat == "precio" or cat == "detalle":
        if not pid:
            return None
        return ("ver_detalle", {"producto_id": pid})

    if cat == "stock":
        if not pid:
            return None
        return ("verificar_stock", {"producto_id": pid})

    if cat == "hay_mas":
        # Re-invocar Catalogo SIN el producto en foco (para mostrar otros).
        params: dict[str, Any] = {}
        if ultima_categoria:
            params["categoria"] = ultima_categoria
        if ultimo_precio_max:
            params["precio_max"] = ultimo_precio_max
        params["excluir"] = pid  # pista para el agente catalogo
        return ("buscar_producto", params)

    if cat == "afirmacion":
        # "Si" / "claro" tras una sugerencia de Ventas (upsell) o Pagos (metodo).
        ultima_sugerencia = contexto.get("ultima_sugerencia")
        if ultima_sugerencia:
            # Consumir: limpiar para que un segundo "si" no la vuelva a ejecutar.
            if hasattr(sesion, "contexto") and isinstance(sesion.contexto, dict):
                sesion.contexto["ultima_sugerencia"] = None
            return (ultima_sugerencia.get("intent", "desconocido"),
                    ultima_sugerencia.get("params", {}))
        # Sin sugerencia activa: no hacemos nada (evita "si"-repetitivos).
        return None

    if cat == "negacion":
        # Si rechaza un producto en foco, pedirle a Catalogo otra opcion.
        if ultima_categoria:
            return ("buscar_producto", {"categoria": ultima_categoria,
                                         "excluir": pid})
        return None

    if cat == "ambiguo":
        # Mensaje corto sin patron claro: si hay un foco, asumir que pregunta
        # por su detalle.
        if pid:
            return ("ver_detalle", {"producto_id": pid})
        return None

    if cat in ("mas_barato", "mas_caro", "mejor_rated"):
        # Buscar entre candidatos_recientes el que cumple el ordinal.
        candidatos = contexto.get("candidatos_recientes") or []
        if not candidatos:
            return None
        # Necesitamos acceder al precio/rating del catalogo.
        from server.store_logic import TIENDA
        productos = [TIENDA.obtener_producto(pid_c) for pid_c in candidatos]
        productos = [p for p in productos if p is not None]
        if not productos:
            return None
        if cat == "mas_barato":
            p_sel = min(productos, key=lambda x: x.precio)
        elif cat == "mas_caro":
            p_sel = max(productos, key=lambda x: x.precio)
        else:  # mejor_rated
            p_sel = max(productos, key=lambda x: x.rating)
        return ("ver_detalle", {"producto_id": p_sel.id})

    return None
