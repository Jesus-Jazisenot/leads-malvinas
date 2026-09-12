# -*- coding: utf-8 -*-
"""
Fuente 4: gosom/google-maps-scraper (tools/gmaps.exe), el scraper de Google Maps
open source mas usado (Go). Se usa con `python run.py --fuente gmaps ...`.

Se usa en **fast mode**: pega al endpoint interno de busqueda de Maps sin abrir
navegador, ~2 s por consulta, hasta 21 resultados por consulta, con telefono, web,
direccion, coordenadas, horario y rating. (El modo con navegador del binario falla
hoy con "unexpected page type" — issue #322 abierto en el repo — y su modo
-grid-bbox depende de el; por eso la cuadricula se arma aqui: se reparten puntos
cada `celda_km` dentro del radio y se corre cada rubro en cada punto. Asi se rompe
el tope de ~20 resultados por busqueda y se cubre toda la zona.)

Lo que no da el fast mode (categoria, correos) lo completan las otras piezas:
web_enricher saca correos del sitio y `--ia` pone el rubro. Los ids son los mismos
`0x...:0x...` que usa maps_scraper.py, asi que no se duplican tiendas entre ambos.

El binario se baja de https://github.com/gosom/google-maps-scraper/releases
(windows-amd64) a tools/gmaps.exe.
"""
import json
import math
import os
import re
import subprocess
import tempfile
import urllib.parse

from config import CENTRO_LAT, CENTRO_LNG, CENTRO_NOMBRE, RADIO_KM
from utils import distancia_km, extraer_correos, normalizar_telefono, tienda_vacia

_AQUI = os.path.dirname(os.path.abspath(__file__))
GMAPS_EXE = os.path.join(_AQUI, "tools", "gmaps.exe")
CONCURRENCIA = 4
_RE_GALERIA = re.compile(r"^(c\.?\s?c\.?|centro comercial|galer[ií]as?|mercado|plaza)\b", re.I)


def puntos_cuadricula(celda_km, radio_km=RADIO_KM):
    """Centros de celda de `celda_km` que caen dentro del circulo de radio_km."""
    dlat = celda_km / 111.0
    dlng = celda_km / (111.0 * math.cos(math.radians(CENTRO_LAT)))
    n = int(math.ceil(radio_km / celda_km))
    puntos = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            lat, lng = CENTRO_LAT + i * dlat, CENTRO_LNG + j * dlng
            if distancia_km(lat, lng) <= radio_km:
                puntos.append((round(lat, 5), round(lng, 5)))
    # del centro hacia afuera, para que una corrida corta cubra primero lo mas cercano
    puntos.sort(key=lambda p: distancia_km(*p))
    return puntos


def _a_tienda(p, rubro):
    pid = p.get("data_id") or p.get("place_id") or p.get("cid") or ("gmaps:" + (p.get("title") or ""))
    t = tienda_vacia(pid, "gmaps")
    t["rubro_busqueda"] = rubro
    t["nombre"] = p.get("title")
    cats = p.get("categories") or []
    t["categoria"] = p.get("category") or (cats[0] if cats else None)
    if not t["categoria"] and t["nombre"] and _RE_GALERIA.match(t["nombre"].strip()):
        t["categoria"] = "Centro comercial"
    t["direccion"] = p.get("address")
    t["lat"], t["lng"] = p.get("latitude"), p.get("longitude")
    t["distancia_km"] = distancia_km(t["lat"], t["lng"])
    tel = p.get("phone")
    if tel:
        t["telefono"] = tel
        t["telefono_e164"], t["tipo_telefono"] = normalizar_telefono(tel)
        t["posible_whatsapp"] = t["tipo_telefono"] == "celular"
    web = p.get("website") or p.get("web_site")
    if web:
        low = web.lower()
        if "facebook.com" in low:
            t["facebook"] = web
        elif "instagram.com" in low:
            t["instagram"] = web
        else:
            t["sitio_web"] = web
    correos = p.get("emails") or []
    if isinstance(correos, str):
        correos = extraer_correos(correos)
    correos = [c for c in correos if c and "@" in c]
    if correos:
        t["correo"] = correos[0]
        if len(correos) > 1:
            t["correos_extra"] = "; ".join(correos[1:4])
    t["rating"] = p.get("review_rating") or None
    t["resenas"] = p.get("review_count") or None
    if p.get("link"):
        t["url_maps"] = p["link"]
    elif t["nombre"] and t["lat"] is not None:
        q = urllib.parse.quote(t["nombre"])
        t["url_maps"] = f"https://www.google.com/maps/place/{q}/@{t['lat']},{t['lng']},17z/data=!4m2!3m1!1s{pid}"
    return t


def _correr(entrada, salida, lat, lng, log):
    cmd = [GMAPS_EXE, "-fast-mode", "-input", entrada, "-results", salida, "-json", "-lang", "es",
           "-c", str(CONCURRENCIA), "-geo", f"{lat},{lng}", "-zoom", "16", "-exit-on-inactivity", "1m"]
    with open(salida + ".log", "w", encoding="utf-8") as lg:
        proc = subprocess.run(cmd, stdout=lg, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        log(f"   gmaps.exe termino con codigo {proc.returncode}; ver {salida}.log")
    return _leer(salida)


def _leer(salida):
    filas = []
    if os.path.exists(salida):
        with open(salida, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea:
                    try:
                        dato = json.loads(linea)
                    except json.JSONDecodeError:
                        continue
                    # en fast mode cada linea es la lista de resultados de una consulta
                    filas.extend(x for x in (dato if isinstance(dato, list) else [dato]) if x)
    return filas


def _procesar(filas, consultas, ya_vistos, limite, log, cada_tienda, nuevas=0):
    antes = nuevas
    for p in filas:
        if limite and nuevas >= limite:
            break
        rubro = (p.get("input_id") or "").strip()
        t = _a_tienda(p, rubro if rubro in consultas else None)
        if t["id"] in ya_vistos:
            continue
        ya_vistos.add(t["id"])
        if t["distancia_km"] is not None and t["distancia_km"] > RADIO_KM:
            continue
        if cada_tienda and cada_tienda(t) is False:
            continue
        nuevas += 1
        log(f"   [{nuevas}] {t['nombre']} | {t['telefono'] or 'sin tel'} | {t['sitio_web'] or ''} | {t['distancia_km']} km")
    return nuevas - antes


def reprocesar(ruta_json, ya_vistos, log=print, cada_tienda=None, limite=None):
    """Vuelve a pasar por `cada_tienda` un resultados.json ya generado (p. ej. tras
    ampliar RADIO_KM, sin gastar consultas nuevas)."""
    filas = _leer(ruta_json)
    log(f"> reprocesando {ruta_json}: {len(filas)} filas")
    return _procesar(filas, [], ya_vistos, limite, log, cada_tienda)


def scrapear(consultas, ya_vistos, limite=None, log=print, cada_tienda=None, grid=False, celda_km=0.7, **_):
    """Misma firma que maps_scraper.scrapear. grid=True recorre la cuadricula completa."""
    if not os.path.exists(GMAPS_EXE):
        raise RuntimeError(f"No esta {GMAPS_EXE}; bajarlo de github.com/gosom/google-maps-scraper/releases")
    tmp = tempfile.mkdtemp(prefix="gmaps_")
    entrada = os.path.join(tmp, "consultas.txt")
    with open(entrada, "w", encoding="utf-8") as f:
        for c in consultas:
            f.write(f"{c} {CENTRO_NOMBRE} #!#{c}\n")
    puntos = puntos_cuadricula(celda_km) if grid else [(CENTRO_LAT, CENTRO_LNG)]
    log(f"> gmaps.exe fast-mode: {len(consultas)} rubros x {len(puntos)} puntos "
        f"(~{len(consultas) * len(puntos) * 2.5 / 60:.0f} min). Temporales en {tmp}")

    nuevas = 0
    for k, (lat, lng) in enumerate(puntos, 1):
        if limite and nuevas >= limite:
            break
        filas = _correr(entrada, os.path.join(tmp, f"p{k}.json"), lat, lng, log)
        n = _procesar(filas, consultas, ya_vistos, limite, log, cada_tienda, nuevas)
        nuevas += n
        log(f"   punto {k}/{len(puntos)} ({lat},{lng}): {len(filas)} fichas, {n} nuevas")
    return nuevas
