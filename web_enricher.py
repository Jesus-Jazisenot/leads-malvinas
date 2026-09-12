# -*- coding: utf-8 -*-
"""
Enriquecimiento: visita el sitio web de cada tienda (si tiene) y saca correos,
numero de WhatsApp (enlaces wa.me / api.whatsapp.com), telefonos extra y
enlaces a Facebook / Instagram.

No toca Facebook ni Instagram: solo guarda el enlace para que el cliente lo
abra a mano si quiere.
"""
import re
import urllib.parse

from bs4 import BeautifulSoup

from concurrent.futures import ThreadPoolExecutor

import fetch
from config import PAGINAS_CONTACTO
from utils import extraer_correos, extraer_telefonos, normalizar_telefono

_RE_WA = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send\?phone=)\+?(\d{9,15})")
_RE_FB = re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/[^\s\"'<>)]+")
_RE_IG = re.compile(r"https?://(?:www\.)?instagram\.com/[^\s\"'<>)]+")
_FB_BASURA = ("sharer", "share.php", "plugins", "dialog", "login", "/tr?", "policy", "privacy")


def _redes(html):
    fb = next((u for u in _RE_FB.findall(html) if not any(b in u for b in _FB_BASURA)), None)
    ig = next((u for u in _RE_IG.findall(html) if "/p/" not in u and "share" not in u), None)
    return fb, ig


def enriquecer(tienda, log=print):
    """Modifica la tienda en sitio. Devuelve True si encontro algo nuevo."""
    tienda["enriquecido"] = True
    web = tienda.get("sitio_web")
    if not web:
        return False
    base = web if web.startswith("http") else "http://" + web
    correos, whatsapps, telefonos = [], [], []
    fb, ig = None, None

    # portada primero; si no responde, el sitio esta muerto y no se insiste
    # con las demas rutas (antes eran 7 intentos de 12 s cada uno)
    portada = fetch.html(base)
    if not portada:
        return False
    rutas = [r for r in PAGINAS_CONTACTO if r]
    with ThreadPoolExecutor(max_workers=len(rutas)) as pool:
        otras = pool.map(lambda r: fetch.html(urllib.parse.urljoin(base.rstrip("/") + "/", r)), rutas)
    paginas = [("", portada)] + list(zip(rutas, otras))

    for ruta, html in paginas:
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        # mailto: y tel: en enlaces (lo mas confiable)
        for a in soup.select("a[href]"):
            h = a["href"]
            if h.startswith("mailto:"):
                correos += extraer_correos(h[7:])
            elif h.startswith("tel:"):
                telefonos += extraer_telefonos(h[4:])
        texto = soup.get_text(" ")
        correos += extraer_correos(texto) + extraer_correos(html)
        whatsapps += _RE_WA.findall(html)
        telefonos += extraer_telefonos(texto) + extraer_telefonos(html)
        f, i = _redes(html)
        fb, ig = fb or f, ig or i
        # con la portada + una pagina de contacto con datos ya es suficiente
        if ruta and (correos or whatsapps):
            break

    # dedup conservando orden; primero los del mismo dominio que el sitio
    dominio = re.sub(r"^www\.", "", urllib.parse.urlparse(base).netloc.lower())
    correos = list(dict.fromkeys(correos))
    if dominio:
        correos.sort(key=lambda c: 0 if c.endswith("@" + dominio) else 1)
    whatsapps = list(dict.fromkeys(whatsapps))
    telefonos = [t for t in dict.fromkeys(telefonos) if t != tienda.get("telefono_e164")]

    algo = False
    if correos and not tienda.get("correo"):
        tienda["correo"] = correos[0]
        if len(correos) > 1:
            tienda["correos_extra"] = "; ".join(correos[1:4])
        algo = True
    if whatsapps:
        num = whatsapps[0].lstrip("0")
        if len(num) == 9:
            num = "51" + num
        e164, _ = normalizar_telefono("+" + num)
        if e164 and e164.startswith("+51"):
            tienda["whatsapp_web"] = e164
            algo = True
    # si Maps no dio telefono pero el sitio si, usar el primero celular
    if not tienda.get("telefono_e164") and telefonos:
        cel = next((t for t in telefonos if normalizar_telefono(t)[1] == "celular"), telefonos[0])
        tienda["telefono"] = cel
        tienda["telefono_e164"], tienda["tipo_telefono"] = normalizar_telefono(cel)
        tienda["posible_whatsapp"] = tienda["tipo_telefono"] == "celular"
        algo = True
    telefonos = [t for t in telefonos if t != tienda.get("telefono_e164")]
    if telefonos:
        tienda["telefonos_extra"] = "; ".join(telefonos[:5])
        algo = True
    if fb and not tienda.get("facebook"):
        tienda["facebook"] = fb
        algo = True
    if ig and not tienda.get("instagram"):
        tienda["instagram"] = ig
        algo = True
    # si el whatsapp del sitio es celular y Maps solo dio fijo, marcar posible whatsapp
    if tienda.get("whatsapp_web"):
        tienda["posible_whatsapp"] = True
    return algo
