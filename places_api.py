# -*- coding: utf-8 -*-
"""
Fuente 2 (opcional): Google Places API (New). Mismo resultado que el scraper,
pero por la API oficial. Necesita GOOGLE_MAPS_API_KEY en el entorno.

Costo (sep-2026, revisar en la consola): Text Search "Pro" ~ 5,000 llamadas gratis
al mes; cada llamada trae hasta 20 tiendas y se puede paginar 3 veces (60 por
busqueda). Pedimos los campos de contacto en la misma llamada con el FieldMask,
asi no hace falta un Place Details aparte.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
"""
import time

import requests

from config import CENTRO_LAT, CENTRO_LNG, CENTRO_NOMBRE, GOOGLE_MAPS_API_KEY, RADIO_KM
from utils import distancia_km, normalizar_telefono, tienda_vacia

_URL = "https://places.googleapis.com/v1/places:searchText"
_CAMPOS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.nationalPhoneNumber", "places.internationalPhoneNumber", "places.websiteUri",
    "places.rating", "places.userRatingCount", "places.primaryTypeDisplayName",
    "places.googleMapsUri", "nextPageToken",
])


def _a_tienda(p, rubro):
    t = tienda_vacia(p["id"], "api")
    t["rubro_busqueda"] = rubro
    t["nombre"] = p.get("displayName", {}).get("text")
    t["categoria"] = p.get("primaryTypeDisplayName", {}).get("text")
    t["direccion"] = p.get("formattedAddress")
    loc = p.get("location", {})
    t["lat"], t["lng"] = loc.get("latitude"), loc.get("longitude")
    t["distancia_km"] = distancia_km(t["lat"], t["lng"])
    t["telefono"] = p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber")
    if t["telefono"]:
        t["telefono_e164"], t["tipo_telefono"] = normalizar_telefono(t["telefono"])
        t["posible_whatsapp"] = t["tipo_telefono"] == "celular"
    web = p.get("websiteUri")
    if web:
        low = web.lower()
        if "facebook.com" in low:
            t["facebook"] = web
        elif "instagram.com" in low:
            t["instagram"] = web
        else:
            t["sitio_web"] = web
    t["rating"] = p.get("rating")
    t["resenas"] = p.get("userRatingCount")
    t["url_maps"] = p.get("googleMapsUri")
    return t


def buscar(consulta, rubro, log=print):
    """Text Search paginado. Devuelve lista de tiendas dentro del radio."""
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError("Falta GOOGLE_MAPS_API_KEY en el entorno (ver config.py)")
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": _CAMPOS,
    }
    cuerpo = {
        "textQuery": consulta,
        "languageCode": "es",
        "regionCode": "PE",
        "locationBias": {"circle": {"center": {"latitude": CENTRO_LAT, "longitude": CENTRO_LNG},
                                    "radius": RADIO_KM * 1000}},
        "pageSize": 20,
    }
    tiendas = []
    token = None
    for _ in range(3):
        if token:
            cuerpo["pageToken"] = token
        r = requests.post(_URL, json=cuerpo, headers=headers, timeout=30)
        if r.status_code != 200:
            log(f"   API {r.status_code}: {r.text[:200]}")
            break
        datos = r.json()
        for p in datos.get("places", []):
            t = _a_tienda(p, rubro)
            if t["distancia_km"] is None or t["distancia_km"] <= RADIO_KM:
                tiendas.append(t)
        token = datos.get("nextPageToken")
        if not token:
            break
        time.sleep(1.5)
    log(f"   {len(tiendas)} tiendas dentro de {RADIO_KM} km")
    return tiendas


def scrapear(consultas, ya_vistos, limite=None, log=print, cada_tienda=None):
    """Misma firma que maps_scraper.scrapear para que run.py no distinga."""
    nuevas = 0
    for consulta in consultas:
        if limite and nuevas >= limite:
            break
        texto = f"{consulta} {CENTRO_NOMBRE}"
        log(f"> Buscando (API): {texto}")
        for t in buscar(texto, consulta, log):
            if limite and nuevas >= limite:
                break
            if t["id"] in ya_vistos:
                continue
            ya_vistos.add(t["id"])
            if cada_tienda and cada_tienda(t) is False:
                continue
            nuevas += 1
            log(f"   [{nuevas}] {t['nombre']} | {t['telefono'] or 'sin tel'} | {t['sitio_web'] or ''} | {t['distancia_km']} km")
    return nuevas
