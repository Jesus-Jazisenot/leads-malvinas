# -*- coding: utf-8 -*-
"""
Fuente 1: Google Maps con Playwright (sin API key).

Para cada busqueda abre Google Maps, baja la lista de resultados hasta el final,
junta los enlaces de cada ficha, filtra por distancia al centro y luego abre cada
ficha para leer nombre, telefono, sitio web, direccion, rating.

Selectores: se apoya sobre todo en los atributos `data-item-id` de la ficha
(phone:tel:, authority, address), que son los que menos cambia Google. Si algun
dia deja de sacar telefonos, revisar esos selectores primero.
"""
import re
import time
import urllib.parse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import (CENTRO_LAT, CENTRO_LNG, CENTRO_NOMBRE, HEADLESS, MAX_SCROLLS,
                    PAUSA_ENTRE_FICHAS, RADIO_KM, ZOOM_MAPS)
from utils import distancia_km, normalizar_telefono, tienda_vacia

_RE_COORDS = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
_RE_PLACE_ID = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")


def _coords_de_url(url):
    m = _RE_COORDS.search(url or "")
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def _id_de_url(url):
    m = _RE_PLACE_ID.search(url or "")
    if m:
        return m.group(1)
    # sin id hexadecimal: usa la parte /place/<nombre>/ como id
    m = re.search(r"/place/([^/]+)/", url or "")
    return "nombre:" + urllib.parse.unquote(m.group(1)) if m else url


def _url_busqueda(consulta):
    q = urllib.parse.quote(consulta)
    return f"https://www.google.com/maps/search/{q}/@{CENTRO_LAT},{CENTRO_LNG},{ZOOM_MAPS}z?hl=es"


def _aceptar_consentimiento(page):
    for texto in ("Aceptar todo", "Accept all", "Acepto"):
        try:
            page.get_by_role("button", name=texto).click(timeout=1500)
            return
        except PWTimeout:
            pass
        except Exception:
            pass


def listar_resultados(page, consulta, log=print):
    """Devuelve lista de (id, url, lat, lng, distancia) de una busqueda, ya filtrada por radio."""
    page.goto(_url_busqueda(consulta), wait_until="domcontentloaded")
    _aceptar_consentimiento(page)
    try:
        feed = page.wait_for_selector('div[role="feed"]', timeout=15000)
    except PWTimeout:
        # Puede ser que la busqueda abrio directo UNA ficha (un solo resultado)
        if "/maps/place/" in page.url:
            lat, lng = _coords_de_url(page.url)
            return [(_id_de_url(page.url), page.url, lat, lng, distancia_km(lat, lng))]
        log(f"   sin resultados para '{consulta}'")
        return []

    vistos = {}
    sin_cambio = 0
    for _ in range(MAX_SCROLLS):
        for a in page.query_selector_all('div[role="feed"] a[href*="/maps/place/"]'):
            href = a.get_attribute("href")
            pid = _id_de_url(href)
            if pid not in vistos:
                vistos[pid] = href
        antes = len(vistos)
        feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        time.sleep(1.5)
        if page.locator("text=Has llegado al final de la lista").count() or \
           page.locator("text=You've reached the end of the list").count():
            break
        sin_cambio = sin_cambio + 1 if len(vistos) == antes else 0
        if sin_cambio >= 6:
            break

    resultados = []
    for pid, href in vistos.items():
        lat, lng = _coords_de_url(href)
        d = distancia_km(lat, lng)
        if d is None or d <= RADIO_KM:
            resultados.append((pid, href, lat, lng, d))
    log(f"   {len(vistos)} fichas en la lista, {len(resultados)} dentro de {RADIO_KM} km")
    return resultados


def _texto(page, selector):
    el = page.query_selector(selector)
    return el.inner_text().strip() if el else None


def _attr(page, selector, attr):
    el = page.query_selector(selector)
    return el.get_attribute(attr) if el else None


def leer_ficha(page, pid, url, rubro):
    """Abre una ficha de Google Maps y regresa el dict de la tienda."""
    t = tienda_vacia(pid, "maps")
    t["url_maps"] = url
    t["rubro_busqueda"] = rubro
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector("h1", timeout=15000)
    except PWTimeout:
        return t
    time.sleep(0.8)

    t["nombre"] = _texto(page, "h1")
    t["categoria"] = _texto(page, "button.DkEaL") or _texto(page, 'button[jsaction*="category"]')

    # Coordenadas: la URL final trae !3d..!4d.. con la posicion exacta del pin
    lat, lng = _coords_de_url(page.url)
    if lat is None:
        lat, lng = _coords_de_url(url)
    t["lat"], t["lng"] = lat, lng
    t["distancia_km"] = distancia_km(lat, lng)

    # Direccion
    dir_ = _attr(page, 'button[data-item-id="address"]', "aria-label")
    t["direccion"] = dir_.split(":", 1)[-1].strip() if dir_ else None

    # Telefono: data-item-id="phone:tel:+51987654321"
    tel_item = _attr(page, 'button[data-item-id^="phone:tel:"]', "data-item-id")
    if tel_item:
        t["telefono"] = tel_item.replace("phone:tel:", "")
    else:
        lbl = _attr(page, 'button[aria-label^="Teléfono"], button[aria-label^="Phone"]', "aria-label")
        if lbl:
            t["telefono"] = lbl.split(":", 1)[-1].strip()
    if t["telefono"]:
        t["telefono_e164"], t["tipo_telefono"] = normalizar_telefono(t["telefono"])
        t["posible_whatsapp"] = t["tipo_telefono"] == "celular"

    # Sitio web
    web = _attr(page, 'a[data-item-id="authority"]', "href")
    if web:
        t["sitio_web"] = web
        low = web.lower()
        if "facebook.com" in low:
            t["facebook"], t["sitio_web"] = web, None
        elif "instagram.com" in low:
            t["instagram"], t["sitio_web"] = web, None

    # Rating y resenas: "4.3" y "(120)"
    rating = _texto(page, 'div.F7nice span[aria-hidden="true"]')
    if rating:
        try:
            t["rating"] = float(rating.replace(",", "."))
        except ValueError:
            pass
    res = _attr(page, 'div.F7nice span[aria-label*="reseñas"], div.F7nice span[aria-label*="reviews"]', "aria-label")
    if res:
        m = re.search(r"\d[\d.,]*", res)
        if m:
            t["resenas"] = int(m.group().replace(".", "").replace(",", ""))
    return t


def scrapear(consultas, ya_vistos, limite=None, log=print, cada_tienda=None):
    """
    consultas: lista de textos de busqueda (rubros o nombres de galerias).
    ya_vistos: set de ids ya procesados (para reanudar).
    limite: parar al juntar N tiendas nuevas (para la muestra).
    cada_tienda: callback(tienda); si devuelve False la ficha no cuenta (p. ej. era una galeria).
    """
    nuevas = 0
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=HEADLESS, args=["--lang=es-419"])
        ctx = navegador.new_context(locale="es-419", viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        for consulta in consultas:
            if limite and nuevas >= limite:
                break
            texto = f"{consulta} {CENTRO_NOMBRE}"
            log(f"> Buscando: {texto}")
            try:
                lista = listar_resultados(page, texto, log)
            except Exception as e:
                log(f"   error en la busqueda: {e}")
                continue
            for pid, url, lat, lng, d in lista:
                if limite and nuevas >= limite:
                    break
                if pid in ya_vistos:
                    continue
                try:
                    t = leer_ficha(page, pid, url, consulta)
                except Exception as e:
                    log(f"   error leyendo ficha: {e}")
                    continue
                ya_vistos.add(pid)
                if t["distancia_km"] is not None and t["distancia_km"] > RADIO_KM:
                    continue
                if cada_tienda and cada_tienda(t) is False:
                    continue
                nuevas += 1
                log(f"   [{nuevas}] {t['nombre']} | {t['telefono'] or 'sin tel'} | {t['sitio_web'] or ''} | {t['distancia_km']} km")
                time.sleep(PAUSA_ENTRE_FICHAS)
        navegador.close()
    return nuevas
