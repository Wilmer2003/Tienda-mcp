"""
store_data.py
=============
Catalogo de prendas e inventario inicial de Tienda Solenne.

Son datos simulados pero con variabilidad realista (precios, stock, una
prenda agotada a proposito en P010 y otra con stock=1 en P009) para
demostrar los flujos condicionales que pide el Criterio 4 de la rubrica:
  - producto agotado    -> el agente busca alternativas
  - stock bajo (= 1)    -> conflicto si dos pedidos compiten por la pieza
"""

from server.models import Producto, Categoria

CATALOGO: list[Producto] = [
    # ---- POLOS ----
    Producto(id="P001", nombre="Polo Básico Algodón Blanco",
             categoria=Categoria.POLOS, precio=49.90, marca="Solenne Essentials",
             rating=4.5, descripcion="Algodón pima 100%, corte regular, blanco."),
    Producto(id="P002", nombre="Polo Premium Negro",
             categoria=Categoria.POLOS, precio=89.90, marca="Pima Co.",
             rating=4.7, descripcion="Pima peruano, costuras reforzadas, negro."),
    Producto(id="P013", nombre="Polo Deportivo Transpirable",
             categoria=Categoria.POLOS, precio=59.90, marca="Solenne Active",
             rating=4.6, descripcion="Tela dry-fit, ideal para entrenamientos, gris azulado."),
    Producto(id="P014", nombre="Polo Estampado Vintage",
             categoria=Categoria.POLOS, precio=69.90, marca="Urban Co.",
             rating=4.3, descripcion="Estampado retro frontal, algodón suave, amarillo mostaza."),
    Producto(id="P015", nombre="Polo Manga Larga Henley",
             categoria=Categoria.POLOS, precio=79.90, marca="Solenne Essentials",
             rating=4.8, descripcion="Cuello con botones, manga larga, azul marino."),
    Producto(id="P031", nombre="Polo Pique Cuello Camisero",
             categoria=Categoria.POLOS, precio=89.00, marca="Solenne Essentials",
             rating=4.5, descripcion="Tejido pique transpirable, cuello estructurado, verde oliva."),
    
    # ---- PANTALONES ----
    Producto(id="P003", nombre="Jeans Slim Fit Azul",
             categoria=Categoria.PANTALONES, precio=159.00, marca="Denim Lab",
             rating=4.6, descripcion="Denim 12oz, slim fit, lavado medio."),
    Producto(id="P004", nombre="Pantalón Chino Beige",
             categoria=Categoria.PANTALONES, precio=119.00, marca="Urban Co.",
             rating=4.4, descripcion="Algodón stretch, corte recto, beige cálido."),
    Producto(id="P016", nombre="Jeans Relaxed Fit Negro",
             categoria=Categoria.PANTALONES, precio=149.00, marca="Denim Lab",
             rating=4.7, descripcion="Corte holgado cómodo, denim negro resistente."),
    Producto(id="P017", nombre="Pantalón Cargo Verde Oliva",
             categoria=Categoria.PANTALONES, precio=139.00, marca="StreetWear",
             rating=4.5, descripcion="Múltiples bolsillos, tela ripstop ligera, verde oliva."),
    Producto(id="P018", nombre="Pantalón de Vestir Gris",
             categoria=Categoria.PANTALONES, precio=189.00, marca="Noir Studio",
             rating=4.8, descripcion="Corte sastre, mezcla de lana, ideal oficina."),
    Producto(id="P032", nombre="Jogger Deportivo Algodón",
             categoria=Categoria.PANTALONES, precio=99.00, marca="Solenne Active",
             rating=4.6, descripcion="Cintura elástica, puños ajustados, gris jaspeado."),

    # ---- VESTIDOS ----
    Producto(id="P005", nombre="Vestido Floral Verano",
             categoria=Categoria.VESTIDOS, precio=179.00, marca="Bloom",
             rating=4.9, descripcion="Viscosa fluida, estampado floral, midi."),
    Producto(id="P006", nombre="Vestido Negro Elegante",
             categoria=Categoria.VESTIDOS, precio=249.00, marca="Noir Studio",
             rating=4.6, descripcion="Crepe stretch, corte recto, largo midi."),
    Producto(id="P019", nombre="Vestido Largo Bohemio",
             categoria=Categoria.VESTIDOS, precio=210.00, marca="Bloom",
             rating=4.7, descripcion="Tela vaporosa, diseño largo con volantes, terracota."),
    Producto(id="P020", nombre="Vestido Corto Fiesta Brillante",
             categoria=Categoria.VESTIDOS, precio=199.00, marca="Noir Studio",
             rating=4.5, descripcion="Lentejuelas plateadas, ajuste al cuerpo, tirantes finos."),
    Producto(id="P021", nombre="Vestido Camisero Casual",
             categoria=Categoria.VESTIDOS, precio=159.00, marca="Solenne Essentials",
             rating=4.8, descripcion="Botones frontales, cinturón ajustable, azul claro."),
    Producto(id="P033", nombre="Vestido Midi de Lino",
             categoria=Categoria.VESTIDOS, precio=239.00, marca="Bloom",
             rating=4.9, descripcion="Lino natural 100%, fresco, tirantes anchos, beige."),

    # ---- CALZADO ----
    Producto(id="P007", nombre="Zapatillas Urban Sneakers",
             categoria=Categoria.CALZADO, precio=219.00, marca="Step",
             rating=4.5, descripcion="Cuero sintético, suela acolchada, blancas."),
    Producto(id="P008", nombre="Mocasines Cuero Marrón",
             categoria=Categoria.CALZADO, precio=289.00, marca="Lazaro",
             rating=4.7, descripcion="Cuero genuino, costura manual, marrón."),
    Producto(id="P022", nombre="Botines Chelsea Negros",
             categoria=Categoria.CALZADO, precio=320.00, marca="Lazaro",
             rating=4.9, descripcion="Cuero natural, elástico lateral, sin pasadores."),
    Producto(id="P023", nombre="Zapatillas Running Pro",
             categoria=Categoria.CALZADO, precio=259.00, marca="Step",
             rating=4.6, descripcion="Suela con alta amortiguación, malla transpirable, negro/verde."),
    Producto(id="P024", nombre="Sandalias de Cuero Plataforma",
             categoria=Categoria.CALZADO, precio=189.00, marca="Lazaro",
             rating=4.4, descripcion="Tiras cruzadas, plataforma ligera, camel."),
    Producto(id="P034", nombre="Oxfords Clásicos Negros",
             categoria=Categoria.CALZADO, precio=299.00, marca="Noir Studio",
             rating=4.8, descripcion="Cuero brillante, pasadores finos, suela de madera, formales."),

    # ---- CHAQUETAS ----
    Producto(id="P009", nombre="Chaqueta de Cuero Negra",
             categoria=Categoria.CHAQUETAS, precio=399.00, marca="Moto Lab",
             rating=4.8, descripcion="Cuero PU, forro acolchado, biker negro."),
    Producto(id="P010", nombre="Abrigo Lana Beige",
             categoria=Categoria.CHAQUETAS, precio=459.00, marca="Soft Wool",
             rating=4.6, descripcion="Lana mezcla, largo midi, beige cálido."),
    Producto(id="P025", nombre="Casaca Denim Clásica",
             categoria=Categoria.CHAQUETAS, precio=199.00, marca="Denim Lab",
             rating=4.7, descripcion="Lavado clásico, botones metálicos, estilo atemporal."),
    Producto(id="P026", nombre="Cortavientos Ligero",
             categoria=Categoria.CHAQUETAS, precio=149.00, marca="Solenne Active",
             rating=4.3, descripcion="Repelente al agua, capucha ajustable, bloque de colores."),
    Producto(id="P027", nombre="Blazer Casual Azul Marino",
             categoria=Categoria.CHAQUETAS, precio=289.00, marca="Noir Studio",
             rating=4.8, descripcion="Media estación, corte semi-formal, forro interior satinado."),
    Producto(id="P035", nombre="Bomber Jacket Verde",
             categoria=Categoria.CHAQUETAS, precio=179.00, marca="Urban Co.",
             rating=4.5, descripcion="Nylon impermeable, interior naranja, bolsillos laterales."),

    # ---- ACCESORIOS ----
    Producto(id="P011", nombre="Cinturón Cuero Trenzado",
             categoria=Categoria.ACCESORIOS, precio=79.00, marca="Cuir",
             rating=4.4, descripcion="Cuero genuino trenzado, hebilla metálica."),
    Producto(id="P012", nombre="Bufanda Lana Suave",
             categoria=Categoria.ACCESORIOS, precio=59.00, marca="Soft Wool",
             rating=4.5, descripcion="Lana merino, larga, color crema."),
    Producto(id="P028", nombre="Gafas de Sol Retro",
             categoria=Categoria.ACCESORIOS, precio=89.00, marca="Shades",
             rating=4.6, descripcion="Protección UV400, montura carey, diseño redondo."),
    Producto(id="P029", nombre="Mochila Urbana Lona",
             categoria=Categoria.ACCESORIOS, precio=129.00, marca="Urban Co.",
             rating=4.8, descripcion="Resistente al agua, compartimento para laptop, verde pino."),
    Producto(id="P030", nombre="Reloj Minimalista Cuero",
             categoria=Categoria.ACCESORIOS, precio=199.00, marca="Cuir",
             rating=4.7, descripcion="Esfera negra, correa de cuero marrón oscuro, analógico."),
    Producto(id="P036", nombre="Gorra Deportiva Logo",
             categoria=Categoria.ACCESORIOS, precio=49.00, marca="Solenne Active",
             rating=4.4, descripcion="Algodón transpirable, ajuste velcro, negro mate."),
]

# Inventario inicial: producto_id -> unidades disponibles.
# Dejamos P010 agotado y P009 con stock=1 a proposito (para demos).
INVENTARIO_INICIAL: dict[str, int] = {
    "P001": 30, "P002": 18, "P003": 22, "P004": 16,
    "P005": 12, "P006": 8,  "P007": 20, "P008": 14,
    "P009": 1,   # ULTIMA UNIDAD: ideal para demo de conflicto entre clientes
    "P010": 0,   # AGOTADO a proposito
    "P011": 25, "P012": 40,
    "P013": 20, "P014": 15, "P015": 10,
    "P016": 12, "P017": 24, "P018": 18,
    "P019": 10, "P020": 5,  "P021": 15,
    "P022": 8,  "P023": 25, "P024": 12,
    "P025": 30, "P026": 15, "P027": 10,
    "P028": 40, "P029": 18, "P030": 7,
    "P031": 25, "P032": 30, "P033": 12,
    "P034": 15, "P035": 20, "P036": 50,
}
