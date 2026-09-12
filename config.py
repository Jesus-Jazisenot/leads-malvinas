# -*- coding: utf-8 -*-
"""
Configuracion del proyecto. Todo lo que se ajusta entre corridas esta aqui.
"""
import os

# ---- Zona de busqueda -------------------------------------------------------
# Jiron Ascope 541, Cercado de Lima (cluster comercial Las Malvinas)
CENTRO_LAT = -12.0446
CENTRO_LNG = -77.0457
CENTRO_NOMBRE = "Las Malvinas, Cercado de Lima"

# El cliente pidio 2 millas (3.2 km). El 12-sep-2026 Jesus decidio ampliar a 5 km para
# juntar mas tiendas (Wilson, Mesa Redonda, Paruro, Breña quedan dentro); la columna
# "Distancia (km)" del Excel permite filtrar al radio original si hace falta.
RADIO_KM = 5.0
ZOOM_MAPS = 16          # zoom con el que se abre Google Maps (16 ~ 1 km de ancho)

# ---- Que buscar -------------------------------------------------------------
# Cada rubro se convierte en una busqueda "<rubro> Las Malvinas Lima".
# Google Maps devuelve como maximo ~120 resultados por busqueda, por eso
# se busca por rubro y no una sola vez.
RUBROS = [
    "ferreteria", "equipos de mineria", "soldadura", "maquinas de soldar",
    "productos de limpieza", "zapatos", "calzado", "ropa", "motores electricos",
    "valvulas", "luminarias", "iluminacion led", "herramientas", "bombas de agua",
    "compresoras", "generadores electricos", "equipos de seguridad industrial",
    "epp", "cables electricos", "tuberias", "rodamientos", "repuestos",
    "pinturas", "plasticos", "articulos de limpieza", "electricidad",
    "importadora", "distribuidora", "tienda", "galeria comercial",
]

# Rubros adicionales para la corrida completa (`--completo`). El fast mode de
# gmaps.exe da como mucho 20 fichas por consulta y casi no le hace caso a la
# coordenada (probado el 12-sep: 18 puntos de cuadricula dieron 148 fichas
# distintas), asi que la forma de sacar miles es VARIAR EL TEXTO: mas rubros y
# cruzarlos con galerias y calles.
RUBROS_EXTRA = [
    "ferreteria industrial", "herramientas electricas", "pernos y tuercas", "tornillos",
    "abrasivos", "discos de corte", "mangueras", "cerrajeria", "candados y cerraduras",
    "escaleras y andamios", "extintores", "uniformes de trabajo", "guantes de seguridad",
    "botas de seguridad", "cascos de seguridad", "maquinaria", "equipos industriales",
    "motosierras", "motobombas", "hidrolavadoras", "grupos electrogenos", "esmeriles",
    "taladros", "amoladoras", "cocinas industriales", "refrigeracion", "aire acondicionado",
    "balanzas", "transformadores", "tableros electricos", "llaves termicas", "focos led",
    "reflectores", "paneles solares", "baterias", "conectores electricos", "tuberias pvc",
    "griferia", "sanitarios", "gasfiteria", "tanques de agua", "bombas sumergibles",
    "pinturas industriales", "adhesivos y siliconas", "lubricantes", "aceites y filtros",
    "fajas y rodajes", "empaquetaduras", "acero inoxidable", "aluminio y vidrio",
    "maderas", "envases plasticos", "bolsas plasticas", "descartables", "detergentes",
    "productos quimicos", "insumos industriales", "zapatillas", "ropa de trabajo",
    "textiles", "mochilas", "juguetes", "celulares", "accesorios de celular", "computadoras",
    "audio", "electrodomesticos", "motos repuestos", "autopartes", "llantas",
    "equipos de bombeo", "compresoras de aire", "soldadura mig", "electrodos",
    "equipos de proteccion personal", "señalizacion", "mallas", "alambres", "clavos",
]

# Calles del cluster para cruzar con los rubros (`--completo`).
CALLES = [
    "Av. Argentina", "Jr. Ascope", "Jr. Zorritos", "Jr. Loreto", "Av. Alfonso Ugarte",
    "Av. Colonial", "Av. Oscar R. Benavides", "Jr. Ramon Carcamo", "Av. Nicolas Dueñas",
    "Av. Tingo Maria", "Jr. Pacasmayo", "Av. Enrique Meiggs", "Jr. Huarochiri",
]

# Galerias prioritarias (el cliente, 12-sep-2026: "el corazon del cluster"). Van
# primero en el Excel y `--foco` les dedica una pasada extra de consultas.
GALERIAS_FOCO = {
    "Nicolini": ["Nicolini", "C.C. Nicolini", "Centro Comercial Nicolini", "galeria Nicolini",
                 "Av. Argentina 215", "Jr. Huarochiri 18"],
    "La Bellota": ["La Bellota", "C.C. La Bellota", "Centro Comercial La Bellota", "Bellota 2", "Bellota 3",
                   "Av. Argentina 725", "Av. Argentina 308"],
    "Plaza Ferretero": ["Plaza Ferretero", "C.C. Plaza Ferretero", "Centro Comercial Plaza Ferretero",
                        "Av. Guillermo Dansey 405", "Jr. Huarochiri 620"],
    "Malvitec": ["Malvitec", "C.C. Malvitec", "Centro Comercial Malvitec", "galeria Malvitec", "Av. Argentina 460"],
}
# Palabras genericas que se cruzan con cada variante en `--foco` (ademas de los rubros)
PALABRAS_FOCO = ["tienda", "tiendas", "stand", "local", "puesto", "importaciones", "importadora", "distribuidora",
                 "comercial", "inversiones", "corporacion", "grupo", "SAC", "EIRL", "SRL", "ventas", "mayorista",
                 "representaciones", "negocios", "multiservicios"]

# ---- Galerias del cluster (lista que mando el cliente, 11-sep-2026) -----------
# Se buscan tal cual en Maps; Google devuelve las tiendas que estan "dentro" de
# cada galeria cuando la busqueda es "tiendas en <galeria>".
GALERIAS = [
    "Centro Comercial Malvitec", "CC Mesa Redonda Las Malvinas", "Centro Comercial Malvinas Plaza",
    "CC Comercial La Bellota", "Centro Comercial La Bellota 2", "Centro Comercial La Bellota 3",
    "CC Acopro", "CC Udampe", "CC Nicollini", "Plaza Ferretero", "CC Acoprom",
    "CC La Cachina Fashion", "CC Loreto", "CC Calzamundo", "CC Calza Centro", "CC Unicentro",
    "CC Boulevard Electro Ferretero", "Malvitec", "CC Meza Redonda", "El Progreso",
    "El Reloj Galeria", "Viamix Malvinas", "CC Chimenea",
]

# Fichas que NO son tiendas (la galeria misma, mercados). Se saltan al guardar.
EXCLUIR_CATEGORIAS = ["Centro comercial", "Galería comercial", "Mercado", "Estacionamiento", "Parque",
                      "Banco", "Cajero automático", "Comisaría", "Iglesia", "Hospital", "Escuela", "Colegio"]

# Cadenas grandes que no son tiendas del cluster (el cliente quiere comerciantes de galeria)
EXCLUIR_NOMBRES = ["sodimac", "promart", "maestro ", "plaza vea", "tottus", "metro ", "wong ", "makro",
                   "ripley", "saga falabella", "oechsle", "bcp", "interbank", "scotiabank", "bbva"]

# ---- Muestra ----------------------------------------------------------------
# Para la muestra inicial: cuantas tiendas entregar y con que rubros.
MUESTRA_RUBROS = ["ferreteria", "soldadura", "equipos de mineria", "productos de limpieza", "zapatos"]

# ---- Google Places API (opcional) -------------------------------------------
# Solo se usa con `python run.py --fuente api`. Crear la key en Google Cloud,
# habilitar "Places API (New)" y ponerla en la variable de entorno:
#   setx GOOGLE_MAPS_API_KEY "AIza..."
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# ---- Scraper (Playwright) ---------------------------------------------------
HEADLESS = False            # True = sin ventana. False deja ver que hace.
PAUSA_ENTRE_FICHAS = 1.5    # segundos entre una tienda y otra (no acelerar mucho)
MAX_SCROLLS = 40            # cuantas veces bajar la lista de resultados por busqueda

# ---- Enriquecimiento web ----------------------------------------------------
TIMEOUT_WEB = 12
PAGINAS_CONTACTO = ["", "contacto", "contactenos", "contact", "nosotros", "quienes-somos", "about"]
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# ---- Salida -----------------------------------------------------------------
CARPETA_SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "salida")
ARCHIVO_PROGRESO = os.path.join(CARPETA_SALIDA, "progreso.jsonl")   # se va guardando tienda por tienda
