# -*- coding: utf-8 -*-
"""
Fuente 3: la web abierta.

a) Directorio malvinas.pe (marketplace del propio emporio): cada vendedor tiene
   pagina con telefono (enlace tel:) y correo (escondido por Cloudflare, se descifra).
b) Busqueda web (DuckDuckGo, sin key): rubros x "Las Malvinas" Lima, nombres de
   galerias, "catalogo pdf". De cada resultado se baja la pagina, se comprueba que
   de verdad mencione el cluster y se sacan telefonos, botones de WhatsApp
   ("Chatea con nosotros" -> wa.me / api.whatsapp.com), correos, redes; ademas se
   siguen la pagina de contacto y los PDF (catalogos) enlazados.

Cada hallazgo se convierte al mismo esquema de tienda (utils.tienda_vacia) con
fuente "directorio" o "web"; run.py lo fusiona con lo de Maps por telefono.
"""
import re
import time
import urllib.parse

from bs4 import BeautifulSoup

import fetch
from config import GALERIAS, RUBROS
from utils import (extraer_correos, extraer_telefonos, normalizar_telefono, tienda_vacia)

# --- que cuenta como "menciona el cluster" -----------------------------------
_ANCLAS = [r"malvinas", r"jr\.?\s*ascope", r"jir[oó]n\s+ascope", r"av\.?\s*argentina", r"guillermo\s+dansey",
           r"mesa\s+redonda", r"nicol+ini", r"udampe", r"acoprom?", r"malvitec", r"la\s+bellota",
           r"plaza\s+ferretero", r"calzamundo", r"unicentro", r"electro\s*ferretero"]
_RE_ANCLA = re.compile("|".join(_ANCLAS), re.I)

# dominios que nunca son una tienda (directorios, prensa, redes, academia)
_DOMINIOS_FUERA = ("facebook.com", "instagram.com", "tiktok.com", "youtube.com", "twitter.com", "x.com",
                   "linkedin.com", "wikipedia.org", "gob.pe", "edu.pe", "concytec", "repositorio", "tesis.",
                   "gestion.pe", "elcomercio.pe", "rpp.pe", "larepublica.pe", "andina.pe", "infobae",
                   "cityperu.com", "paginasamarillas", "cylex", "infoisinfo", "nadlan.com", "inmobiliaria",
                   "urbania", "adondevivir", "mercadolibre", "olx", "google.com", "scribd", "issuu",
                   "malvinas.pe", "amazon", "alibaba", "made-in-china", "pinterest", "tripadvisor", "waze",
                   "findglocal", "aiyellow", "americatv", "panamericana", "latina.pe", "canaln", "peru21",
                   "ojo.pe", "trome", "exitosa", "diariocorreo", "elpopular", "expreso", "libero.pe",
                   "yelp", "foursquare", "confiep", "claro.com.pe", "movistar", "entel", "todosnegocios", "deperu.com", "construyendo.pe", "dipromin", "sunat", "indecopi", "munlima", "bcp", "interbank", "bbva", "scotiabank", "maps.apple.com", "apple.com", "bing.com", "duckduckgo", ".mx", ".ar", ".cl", "yellowpages", "tupalo", "hotfrog", "cybo", "encuentra24",
                   "compuempresa", "indeed.com", "computrabajo", "bumeran", "enerplus.pe", "directorioempresasperu", "peruyello",
                   "universidadperu", "datosperu", "empresaperu", "infoempresa", "cuentaperu", "glassdoor", "linkedin",
                   "honda.com.pe", "argenper", "verificascore", "calzamundo.com.co", "unicentro.com", "unicentro.pe", "malvitec.pe", "malvitec.com")

_RE_WA = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=|web\.whatsapp\.com/send\?phone=|whatsapp://send\?phone=)\+?(\d{9,15})")
_RE_FB = re.compile(r"https?://(?:www\.|m\.)?facebook\.com/(?!sharer|share|plugins|dialog|login|tr\b)[^\s\"'<>)]+")
_RE_IG = re.compile(r"https?://(?:www\.)?instagram\.com/(?!p/|share)[^\s\"'<>)]+")
_RE_PDF = re.compile(r"\.pdf(?:$|\?)", re.I)
_RE_CONTACTO = re.compile(r"contact|nosotros|quienes|about|ubic", re.I)


def _dominio(url):
    return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")


def _fuera(url):
    d = _dominio(url)
    ruta = url.lower()
    return any(x in d for x in _DOMINIOS_FUERA) or         any(x in ruta for x in ("/wp-content/uploads/", "bitstream", "/noticia", "/news", "/blog/", "/articulo", "/nota/", "/prensa"))


_GENERICOS = {"contacto", "contactenos", "contáctenos", "inicio", "home", "nosotros", "productos", "catalogo",
              "catálogo", "tienda", "shop", "quienes somos", "quiénes somos", "about", "about us", "blog"}


def _nombre(soup, url):
    candidatos = []
    for sel, attr in (('meta[property="og:site_name"]', "content"), ('meta[property="og:title"]', "content")):
        el = soup.select_one(sel)
        if el and el.get(attr):
            candidatos.append(el[attr])
    if soup.title and soup.title.string:
        candidatos += re.split(r"\s[|\-–:]\s", soup.title.string.strip())
    h1 = soup.select_one("h1")
    if h1:
        candidatos.append(h1.get_text(" "))
    for c in candidatos:
        c = re.sub(r"\s+", " ", c).strip(" |-–")
        if c and c.lower() not in _GENERICOS and len(c) > 2:
            return c[:80]
    return _dominio(url)


def _extraer(html, texto):
    """Telefonos, whatsapps, correos y redes de un html + su texto plano."""
    soup_links = re.findall(r'href=["\']((?:tel|mailto):[^"\']+)', html, re.I)
    tels, mails = [], []
    for h in soup_links:
        if h.lower().startswith("tel:"):
            tels += extraer_telefonos(h[4:])
        else:
            mails += extraer_correos(h[7:])
    was = _RE_WA.findall(html)
    tels += extraer_telefonos(texto) + extraer_telefonos(html)
    mails += extraer_correos(texto) + extraer_correos(html)
    fb = next(iter(_RE_FB.findall(html)), None)
    ig = next(iter(_RE_IG.findall(html)), None)
    return (list(dict.fromkeys(tels)), list(dict.fromkeys(was)), list(dict.fromkeys(mails)), fb, ig)


def _armar(id_, fuente, nombre, url, tels, was, mails, fb, ig, direccion=None, rubro=None):
    t = tienda_vacia(id_, fuente)
    t["nombre"], t["sitio_web"], t["direccion"], t["rubro_busqueda"] = nombre, url, direccion, rubro
    t["facebook"], t["instagram"] = fb, ig
    if was:
        num = was[0].lstrip("0")
        if len(num) == 9:
            num = "51" + num
        e164, _ = normalizar_telefono("+" + num)
        if e164 and e164.startswith("+51"):
            t["whatsapp_web"] = e164
            t["posible_whatsapp"] = True
    principal = next((x for x in tels if normalizar_telefono(x)[1] == "celular"), None) or (tels[0] if tels else None)
    if not principal and t["whatsapp_web"]:
        principal = t["whatsapp_web"]
    if principal:
        t["telefono"] = principal
        t["telefono_e164"], t["tipo_telefono"] = normalizar_telefono(principal)
        t["posible_whatsapp"] = t["posible_whatsapp"] or t["tipo_telefono"] == "celular"
    extra = [x for x in tels if x != t["telefono_e164"]]
    if extra:
        t["telefonos_extra"] = "; ".join(extra[:5])
    if mails:
        t["correo"] = mails[0]
        if len(mails) > 1:
            t["correos_extra"] = "; ".join(mails[1:4])
    t["enriquecido"] = True
    return t


# =============================================================================
# a) Directorio malvinas.pe
# =============================================================================
_DIR_BASE = "https://malvinas.pe"


def productos_directorio(texto):
    """malvinas.pe no da rubro por vendedor; se resume con sus primeros productos."""
    prods = re.findall(r"Añadir lista de deseos (.+?) Valorado con", texto)
    prods = [p.strip().title()[:45] for p in prods if p.strip()]
    prods = list(dict.fromkeys(prods))[:3]
    return ("Vende: " + "; ".join(prods)) if prods else None


def directorio_malvinas(ya_vistos, log=print, cada_tienda=None, limite=None):
    nuevas = 0
    vendedores = []
    for pag in range(1, 30):
        url = f"{_DIR_BASE}/tiendas-comerciales/" + (f"page/{pag}/" if pag > 1 else "")
        html = fetch.html(url)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        antes = len(vendedores)
        for a in soup.select('a[href^="https://malvinas.pe/tienda/"]'):
            h = a["href"].rstrip("/")
            if "/tienda/" not in h:
                continue
            slug = h.split("/tienda/", 1)[1]
            # los vendedores tienen un solo tramo y no son categorias del catalogo
            if "/" not in slug and slug not in ("abrir-mi-tienda", "categorias", "super-ofertas") and h not in vendedores:
                vendedores.append(h)
        if len(vendedores) == antes:
            break
        time.sleep(0.8)
    log(f"> Directorio malvinas.pe: {len(vendedores)} vendedores")

    for url in vendedores:
        if limite and nuevas >= limite:
            break
        id_ = "dir:" + url.split("/tienda/", 1)[1]
        if id_ in ya_vistos:
            continue
        html = fetch.html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        texto = re.sub(r"\s+", " ", soup.get_text(" "))
        # el bloque del vendedor: "<n> de 5 NOMBRE DIRECCION telefono correo Chatear con Vendedor"
        m = re.search(r"\d de 5 (.{0,300}?)Chatear con Vendedor", texto)
        if not m:
            # sin bloque de vendedor: es una categoria del catalogo o un vendedor dado de baja
            # (malvinas.pe redirige al inicio); no es una tienda
            ya_vistos.add(id_)
            continue
        bloque = m.group(1)
        tels, was, mails, fb, ig = _extraer(html, bloque)
        mails = [x for x in mails if not x.endswith("@malvinas.pe")]
        tels = [x for x in tels if x not in ("+51937508325", "+51926719972")]   # telefonos del propio sitio
        if fb and "malvinas.pe" in fb:
            fb = None
        h1 = soup.select_one("h1")
        nombre = h1.get_text(" ").strip() if h1 else _nombre(soup, url)
        nombre = nombre.replace("Malvinas.pe", "").strip(" |-") or _nombre(soup, url)
        direccion = None
        resto = bloque.strip()
        if resto.lower().startswith(nombre.lower()):
            resto = resto[len(nombre):]
        md = re.match(r"\s*(.+?)\s*(?:\+?51\s?)?9\d{2}\s?\d{3}\s?\d{3}", resto) or re.match(r"\s*(.+?)\s*\[email", resto)
        if md and len(md.group(1)) > 5:
            direccion = md.group(1).strip(" ,")
        t = _armar(id_, "directorio", nombre, url, tels, was, mails, fb, ig, direccion)
        t["categoria"] = productos_directorio(texto)
        ya_vistos.add(id_)
        if cada_tienda and cada_tienda(t) is False:
            continue
        nuevas += 1
        log(f"   [{nuevas}] {nombre} | {t['telefono'] or 'sin tel'} | {t['correo'] or 'sin correo'}")
        time.sleep(0.8)
    return nuevas


# =============================================================================
# b) Busqueda web
# =============================================================================
def consultas_web(rubros=None, galerias=True, pdf=True):
    rubros = rubros or RUBROS
    c = [f'"Las Malvinas" Lima {r}' for r in rubros]
    if galerias:
        c += [f'"{g}" Lima contacto' for g in GALERIAS]
    if pdf:
        c += [f'"Las Malvinas" Lima {r} catalogo pdf' for r in rubros[:12]]
        c += ['"Las Malvinas" Lima catalogo filetype:pdf', '"Av. Argentina" Lima catalogo filetype:pdf']
    return c


def _buscar(consulta, max_results=20):
    from ddgs import DDGS
    try:
        with DDGS() as d:
            return [r["href"] for r in d.text(consulta, region="pe-es", max_results=max_results)]
    except Exception:
        return []


def _procesar_sitio(url, rubro, log):
    """Devuelve una tienda si la pagina menciona el cluster y tiene algun contacto."""
    if _RE_PDF.search(url):
        texto = fetch.pdf_texto(url)
        if not texto or not _RE_ANCLA.search(texto):
            return None
        tels, was, mails, fb, ig = _extraer("", texto)
        if not (tels or mails):
            return None
        nombre = (texto.strip().splitlines() or [_dominio(url)])[0][:80]
        return _armar("pdf:" + url, "web-pdf", nombre, url, tels, was, mails, fb, ig, rubro=rubro)

    html = fetch.html(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    texto = re.sub(r"\s+", " ", soup.get_text(" "))
    if not _RE_ANCLA.search(texto) and not _RE_ANCLA.search(html):
        return None
    tels, was, mails, fb, ig = _extraer(html, texto)

    base = url
    vistos = 0
    # pagina de contacto y PDFs enlazados desde la portada
    for a in soup.select("a[href]"):
        h = urllib.parse.urljoin(base, a["href"])
        if _dominio(h) != _dominio(base):
            continue
        es_pdf = bool(_RE_PDF.search(h))
        es_contacto = bool(_RE_CONTACTO.search(h)) and h != url
        if not (es_pdf or es_contacto) or vistos >= 4:
            continue
        vistos += 1
        if es_pdf:
            tx = fetch.pdf_texto(h)
            if tx:
                t2, w2, m2, _, _ = _extraer("", tx)
                tels, was, mails = tels + t2, was + w2, mails + m2
        else:
            h2 = fetch.html(h)
            if h2:
                s2 = BeautifulSoup(h2, "html.parser")
                for s in s2(["script", "style", "noscript"]):
                    s.decompose()
                t2, w2, m2, f2, i2 = _extraer(h2, re.sub(r"\s+", " ", s2.get_text(" ")))
                tels, was, mails = tels + t2, was + w2, mails + m2
                fb, ig = fb or f2, ig or i2
    tels, was, mails = list(dict.fromkeys(tels)), list(dict.fromkeys(was)), list(dict.fromkeys(mails))
    if not (tels or was):        # sin numero peruano no sirve como lead
        return None
    m = re.search(r"((?:Jr\.?|Jir[oó]n|Av\.?|Avenida|Pje\.?|Pasaje|Calle|Galer[ií]a|C\.?C\.?)[^.|]{5,90}?(?:Lima|Malvinas)[^.|]{0,30})", texto)
    direccion = m.group(1).strip() if m else None
    return _armar("web:" + _dominio(url), "web", _nombre(soup, url), url, tels, was, mails, fb, ig, direccion, rubro)


def busqueda_web(consultas, ya_vistos, log=print, cada_tienda=None, limite=None):
    nuevas = 0
    dominios_hechos = set()
    for consulta in consultas:
        if limite and nuevas >= limite:
            break
        log(f"> Web: {consulta}")
        urls = _buscar(consulta)
        time.sleep(1.5)
        for url in urls:
            if limite and nuevas >= limite:
                break
            if _fuera(url):
                continue
            clave = url if _RE_PDF.search(url) else _dominio(url)
            if clave in dominios_hechos or ("web:" + clave) in ya_vistos or ("pdf:" + clave) in ya_vistos:
                continue
            dominios_hechos.add(clave)
            try:
                t = _procesar_sitio(url, consulta, log)
            except Exception as e:
                log(f"   error en {url[:60]}: {e}")
                continue
            if not t:
                continue
            ya_vistos.add(t["id"])
            if cada_tienda and cada_tienda(t) is False:
                continue
            nuevas += 1
            log(f"   [{nuevas}] {t['nombre']} | {t['telefono'] or 'sin tel'} | wa:{t['whatsapp_web'] or '-'} | {t['correo'] or 'sin correo'} | {url[:50]}")
    return nuevas
