"""Agente Catalogo: busqueda y recomendacion de productos."""
from __future__ import annotations

from typing import Any

from agents.agent import Agent, AgentResponse
from agents.brain import Decision
from agents.event_bus import EventType


class CatalogoAgent(Agent):
    def __init__(self, mcp_client, state, bus) -> None:
        super().__init__("consultas", "consultas.md", mcp_client, state, bus)
        # Suscribimos este agente al evento de stock agotado para que
        # pueda proponer alternativas automaticamente.
        bus.subscribe(EventType.STOCK_AGOTADO, self._on_stock_agotado)

    async def _ejecutar(self, decision: Decision,
                        contexto: dict[str, Any]) -> AgentResponse:
        params = decision.parametros
        usuario_id = contexto.get("usuario_id", "anonimo")

        # Si el usuario menciono un producto concreto por nombre/ID, mostrar
        # el detalle directamente (no malgastar una busqueda generica).
        if "producto_id" in params and decision.intent in (
            "ver_detalle", "buscar_producto"
        ):
            r = await self.mcp.call("obtener_producto",
                                    producto_id=params["producto_id"])
            datos = r.datos
            if isinstance(datos, dict) and "exito" in datos and not datos["exito"]:
                return AgentResponse(agente=self.nombre,
                                     mensaje=datos.get("mensaje", "No encontrado."),
                                     datos=datos)
            # Anotar producto en foco para que el siguiente turno tenga contexto.
            self._anotar_foco(usuario_id, datos["id"])
            import random
            cupones = ["SOLENNE10 para 10% de descuento", "ENVIOFREE para envío gratis", "SOLENNEVIP para un regalo sorpresa"]
            cupon = random.choice(cupones)
            return AgentResponse(
                agente=self.nombre,
                mensaje=f"{datos['nombre']} ({datos['marca']}): {datos['descripcion']} "
                        f"S/ {datos['precio']:.0f}, rating {datos['rating']}. "
                        f"¿Quieres agregarlo al carrito? ¡Aprovecha el cupón {cupon} en tu compra!",
                datos={"producto": datos},
            )

        # Busqueda general (intent buscar_producto o desconocido pero con keywords).
        excluir = params.get("excluir")  # del context_resolver: "hay mas?"
        r = await self.mcp.call(
            "buscar_productos",
            query=params.get("query", ""),
            categoria=params.get("categoria", ""),
            precio_max=params.get("precio_max", 0.0),
        )
        productos = r.datos if isinstance(r.datos, list) else []
        if excluir:
            productos = [p for p in productos if p.get("id") != excluir]
        if not productos:
            # Mensaje contextualizado si el usuario pidio "hay mas" tras un resultado.
            msg = ("No tengo mas opciones en esa categoria por ahora."
                   if excluir
                   else "No encontre productos con esos criterios. Quieres ampliar la busqueda?")
            return AgentResponse(agente=self.nombre, mensaje=msg,
                                 datos={"resultados": []})

        # Ordenar por rating desc para que el más de moda esté primero.
        top = sorted(productos, key=lambda p: -p["rating"])
        
        # Anotar contexto
        self._anotar_candidatos(usuario_id, [p["id"] for p in top],
                                 categoria=params.get("categoria"),
                                 precio_max=params.get("precio_max"))
                                 
        import random
        cupon = random.choice(["SOLENNE10", "ENVIOFREE", "SOLENNEVIP"])
        
        # Sugerencias de combinación
        cat = str(params.get("categoria", "")).lower()
        combinar = "¿Te gustaría ver algo más para armar el look completo?"
        if "vestido" in cat:
            combinar = "Para lucir perfecta, ¿te gustaría combinarlo con un calzado elegante o algún accesorio?"
        elif "polo" in cat:
            combinar = "¿Qué te parece si lo combinamos con unos pantalones en tendencia o una chaqueta?"
        elif "pantalon" in cat:
            combinar = "Un buen pantalón resalta más con el polo correcto o una buena chaqueta. ¿Te busco opciones?"
        elif "calzado" in cat:
            combinar = "¡Zapatos increíbles! ¿Buscamos un vestido o pantalón a juego?"

        if len(top) == 1:
            p = top[0]
            mensaje = (f"Te recomiendo: {self._descripcion_corta(p)}. "
                       f"Es la única opción que encaja con tu filtro. "
                       f"¿Quieres agregarla al carrito?\n\n{combinar} Recuerda aplicar el cupón {cupon}.")
        else:
            mejor = top[0]
            resto = top[1:]
            lineas_resto = [self._descripcion_corta(p) for p in resto]
            
            mensaje = (f"¡Excelente elección! Tengo {len(top)} opciones para ti.\n"
                       f"El que está más de moda y destaca por su elegancia es:\n"
                       f"✨ {self._descripcion_corta(mejor)}\n\n"
                       f"También te puedo ofrecer estos otros:\n  " + "\n  ".join(lineas_resto) + "\n\n"
                       f"Dime cuál te interesa agregar al carrito. {combinar} ¡Aprovecha el cupón de descuento {cupon} al pagar!")

        return AgentResponse(
            agente=self.nombre,
            mensaje=mensaje,
            datos={"resultados": top, "total_encontrados": len(productos)},
        )

    # --------- Helpers de contexto ---------
    def _anotar_foco(self, usuario_id: str, producto_id: str,
                     categoria: str | None = None,
                     precio_max: float | None = None) -> None:
        # NO sobreescribimos candidatos_recientes aqui: el usuario podria
        # estar pidiendo el detalle de uno entre varios candidatos, y queremos
        # conservar la lista para que "y el otro?" o "el mas caro" funcionen.
        ctx = {"producto_en_foco": producto_id}
        sesion = self.state.sesion(usuario_id)
        if not sesion.contexto.get("candidatos_recientes"):
            ctx["candidatos_recientes"] = [producto_id]
        if categoria:
            ctx["ultima_categoria_consultada"] = categoria
        if precio_max:
            ctx["ultimo_precio_max"] = precio_max
        self.state.actualizar_sesion(usuario_id, contexto=ctx,
                                     producto_visto=producto_id)

    def _anotar_candidatos(self, usuario_id: str, ids: list[str],
                            categoria: str | None = None,
                            precio_max: float | None = None) -> None:
        ctx = {"candidatos_recientes": ids,
               "producto_en_foco": ids[0] if len(ids) == 1 else None}
        if categoria:
            ctx["ultima_categoria_consultada"] = categoria
        if precio_max:
            ctx["ultimo_precio_max"] = precio_max
        self.state.actualizar_sesion(usuario_id, contexto=ctx)

    # Callback: cuando inventario reporta stock agotado, este agente busca
    # alternativas en la misma categoria y las deja en la pizarra para que
    # el Orquestador las pueda mostrar.
    def _on_stock_agotado(self, evento) -> None:
        categoria = evento.datos.get("categoria", "")
        producto_id = evento.datos.get("producto_id", "")
        if not categoria:
            return
        # Llamada sincrona simulada: como buscar_productos es asincrona en MCP
        # pero el bus es sincrono, hacemos una busqueda directa al store.
        from server.store_logic import TIENDA
        alternativas = [p for p in TIENDA.buscar(categoria=categoria)
                        if p.id != producto_id and TIENDA.stock(p.id) > 0]
        # Ordenar por rating y dejar 2.
        alternativas.sort(key=lambda p: -p.rating)
        sugeridos = [{"id": p.id, "nombre": p.nombre, "precio": p.precio,
                      "rating": p.rating} for p in alternativas[:2]]
        if sugeridos:
            self.state.anotar(f"alternativas_para_{producto_id}", sugeridos)
            self.bus.publish(EventType.ALTERNATIVA_SUGERIDA,
                             publicado_por=self.nombre,
                             datos={"producto_id": producto_id,
                                    "sugeridos": sugeridos})
