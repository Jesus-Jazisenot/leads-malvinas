# -*- coding: utf-8 -*-
"""
Fuente 5: Paginas Amarillas Peru (paginasamarillas.com.pe).

La pagina es Next.js y las fichas se cargan desde un API JSON publico:
    /api/advertisements?searchWord=<rubro>&locationWord=lima-lima&page=N&size=50
`lima-lima` = distrito Cercado de Lima (ubigeo 150101). Cada ficha trae nombre,
telefonos ya en E.164 (`allPhones`), WhatsApp/web/Facebook/Instagram (`contactMap`),
direccion y coordenadas. Se filtra por distancia al centro del cluster.

Probado el 12-sep-2026: "ferreteria" en Cercado da 772 fichas, 720 con telefono,
128 dentro de 3.2 km. No trae correos.
"""
import re
import time
import urllib.parse

import requests

from config import RADIO_KM, RUBROS, USER_AGENT
from utils import distancia_km, normalizar_telefono, tienda_vacia

API = "https://www.paginasamarillas.com.pe/api/advertisements"
LOCALIDAD = "lima-lima"          # Cercado de Lima
TAMANO = 50
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Language": "es-PE,es;q=0.9"}


def _pagina(rubro, pagina):
    params = {"searchWord": rubro, "locationWord": LOCALIDAD, "page": pagina, "size": TAMANO}
    r = requests.get(API, params=params, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d.get("results") or [], d.get("total") or 0


def _link(cm, clave):
    v = (cm or {}).get(clave) or []
    return v[0] if v else None


def _a_tienda(f, rubro):
    ma = f.get("mainAddress") or {}
    t = tienda_vacia("pa:" + str(f["id"]), "amarillas")
    t["nombre"] = (f.get("name") or "").strip() or None
    t["rubro_busqueda"] = rubro
    t["categoria"] = None
    calle = " ".join(x for x in (ma.get("streetName"), ma.get("streetNumber")) if x)
    acceso = ma.get("access")
    t["direccion"] = ", ".join(x for x in (calle, acceso, ma.get("localityToShow")) if x) or None
    try:
        t["lat"], t["lng"] = float(ma["latitude"]), float(ma["longitude"])
        t["distancia_km"] = round(distancia_km(t["lat"], t["lng"]), 2)
    except (KeyError, TypeError, ValueError):
        pass

    tels = []
    for p in ma.get("allPhones") or []:
        e164, _ = normalizar_telefono(p.get("freeCallNumber") or p.get("number"))
        if e164 and e164 not in tels:
            tels.append(e164)
    cm = f.get("contactMap") or ma.get("contactMap") or {}
    wa = _link(cm, "WHATSAPP")
    if wa:
        m = re.search(r"(\d{9,12})", wa)
        if m:
            num = m.group(1)
            e164, _ = normalizar_telefono("+" + (num if num.startswith("51") else "51" + num))
            if e164:
                t["whatsapp_web"] = e164
                t["posible_whatsapp"] = True
                if e164 not in tels:
                    tels.append(e164)
    principal = next((x for x in tels if normalizar_telefono(x)[1] == "celular"), None) or (tels[0] if tels else None)
    if principal:
        t["telefono"] = principal
        t["telefono_e164"], t["tipo_telefono"] = normalizar_telefono(principal)
        t["posible_whatsapp"] = t["posible_whatsapp"] or t["tipo_telefono"] == "celular"
    extra = [x for x in tels if x != t["telefono_e164"]]
    if extra:
        t["telefonos_extra"] = "; ".join(extra[:5])

    web = _link(cm, "WEB")
    if web and "paginasamarillas" not in web:
        t["sitio_web"] = web
    t["facebook"] = _link(cm, "FACEBOOK")
    t["instagram"] = _link(cm, "INSTAGRAM")
    correo = _link(cm, "EMAIL")
    if correo and "@" in correo:
        t["correo"] = correo.replace("mailto:", "")
    return t


def scrapear(consultas=None, ya_vistos=None, limite=None, log=print, cada_tienda=None, pausa=0.4, **_):
    """Recorre cada rubro en Paginas Amarillas (Cercado de Lima) y guarda las fichas dentro del radio."""
    consultas = consultas or RUBROS
    ya_vistos = ya_vistos if ya_vistos is not None else set()
    nuevas = 0
    fuera = 0
    for rubro in consultas:
        if limite and nuevas >= limite:
            break
        pagina, total, vistas = 0, None, 0
        while True:
            try:
                fichas, total = _pagina(rubro, pagina)
            except Exception as e:
                log(f"   (amarillas '{rubro}' pag {pagina}: {e})")
                break
            if not fichas:
                break
            vistas += len(fichas)
            for f in fichas:
                if limite and nuevas >= limite:
                    break
                t = _a_tienda(f, rubro)
                if t["id"] in ya_vistos:
                    continue
                ya_vistos.add(t["id"])
                if t["distancia_km"] is None or t["distancia_km"] > RADIO_KM:
                    fuera += 1
                    continue
                if cada_tienda and cada_tienda(t) is False:
                    continue
                nuevas += 1
                log(f"   [{nuevas}] {t['nombre']} | {t['telefono'] or 'sin tel'} | {t['sitio_web'] or ''} | {t['distancia_km']} km")
            if vistas >= total or len(fichas) < TAMANO:
                break
            pagina += 1
            time.sleep(pausa)
        log(f"   amarillas '{rubro}': {vistas}/{total} fichas revisadas, {nuevas} nuevas acumuladas ({fuera} fuera del radio)")
    return nuevas
