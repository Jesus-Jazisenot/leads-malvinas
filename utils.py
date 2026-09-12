# -*- coding: utf-8 -*-
"""
Funciones compartidas: distancia, telefonos peruanos, lectura/escritura del progreso.
"""
import json
import math
import os
import re

import phonenumbers

from config import ARCHIVO_PROGRESO, CENTRO_LAT, CENTRO_LNG


# ---- Distancia --------------------------------------------------------------
def distancia_km(lat, lng, lat0=CENTRO_LAT, lng0=CENTRO_LNG):
    """Distancia en linea recta (haversine) entre dos puntos, en km."""
    if lat is None or lng is None:
        return None
    r = 6371.0
    p1, p2 = math.radians(lat0), math.radians(lat)
    dp = math.radians(lat - lat0)
    dl = math.radians(lng - lng0)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


# ---- Telefonos --------------------------------------------------------------
def normalizar_telefono(texto):
    """
    Devuelve (telefono_e164, tipo) para un numero peruano, o (None, None).
    tipo: 'celular' (empieza con 9, 9 digitos -> casi seguro tiene WhatsApp)
          'fijo'    (Lima: 7 digitos con prefijo 01)
    """
    if not texto:
        return None, None
    try:
        num = phonenumbers.parse(texto, "PE")
    except phonenumbers.NumberParseException:
        return None, None
    if not phonenumbers.is_valid_number(num):
        return None, None
    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    t = phonenumbers.number_type(num)
    if t in (phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE):
        tipo = "celular"
    else:
        tipo = "fijo"
    return e164, tipo


def extraer_telefonos(texto):
    """Todos los numeros peruanos validos que aparezcan en un texto."""
    encontrados = []
    for m in phonenumbers.PhoneNumberMatcher(texto or "", "PE"):
        if phonenumbers.region_code_for_number(m.number) != "PE":
            continue
        e164 = phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)
        if e164 not in encontrados:
            encontrados.append(e164)
    return encontrados


# ---- Correos ----------------------------------------------------------------
_RE_CORREO = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_EXT_BASURA = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
_CORREOS_BASURA = ("example", "ejemplo", "@test.", "prueba@", "sentry", "wixpress", "tu@", "email@", "correo@", "@email.", "@domain", "@dominio",
                   "usuario@", "nombre@", "user@", "name@", "noreply", "no-reply", "@2x", "@3x",
                   # correos de plantillas y proveedores de software que se cuelan en el HTML
                   "prestashop", "azameo", "micahrich", "wordpress", "wpengine", "themeforest", "elementor",
                   "godaddy", "jquery", "schema.org", "w3.org", "cloudflare", "@google.com", "gstatic",
                   "@facebook.com", "@instagram.com", "wix.com", "squarespace", "shopify", "odoo.com",
                   "weebly", "jimdo", "hostinger", "namecheap", "@apple.com", "@microsoft.com", "@adobe.com",
                   "envato", "@gravatar", "@youtube.com", "@twitter.com", "@x.com", "@whatsapp.com")


_RE_CF = re.compile(r'data-cfemail="([0-9a-f]+)"|/cdn-cgi/l/email-protection#([0-9a-f]+)')


def descifrar_correos_cloudflare(html):
    """Cloudflare esconde los correos como hex XOR; muchos sitios peruanos lo usan."""
    correos = []
    for a, b in _RE_CF.findall(html or ""):
        h = a or b
        try:
            clave = int(h[:2], 16)
            correos.append("".join(chr(int(h[i:i + 2], 16) ^ clave) for i in range(2, len(h), 2)))
        except ValueError:
            pass
    return correos


def extraer_correos(texto):
    vistos = []
    for c in _RE_CORREO.findall(texto or "") + descifrar_correos_cloudflare(texto):
        c = c.lower().strip(".")
        if c.endswith(_EXT_BASURA) or any(b in c for b in _CORREOS_BASURA):
            continue
        if c not in vistos:
            vistos.append(c)
    return vistos


# ---- Progreso (JSONL) -------------------------------------------------------
def cargar_progreso():
    """Tiendas ya procesadas, indexadas por url_maps (o place_id)."""
    tiendas = {}
    if os.path.exists(ARCHIVO_PROGRESO):
        with open(ARCHIVO_PROGRESO, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea:
                    t = json.loads(linea)
                    tiendas[t["id"]] = t
    return tiendas


def reescribir_progreso(tiendas):
    """Vuelve a escribir todo el archivo (se usa cuando se fusiona una tienda ya guardada)."""
    os.makedirs(os.path.dirname(ARCHIVO_PROGRESO), exist_ok=True)
    with open(ARCHIVO_PROGRESO, "w", encoding="utf-8") as f:
        for t in tiendas.values():
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def fusionar(destino, nueva):
    """Copia a `destino` los campos que tenga `nueva` y a el le falten."""
    for k, v in nueva.items():
        if v not in (None, "", False) and destino.get(k) in (None, "", False) and k not in ("id", "fuente"):
            destino[k] = v
    if nueva.get("fuente") and nueva["fuente"] not in (destino.get("fuente") or ""):
        destino["fuente"] = f"{destino.get('fuente')}+{nueva['fuente']}"
    return destino


def guardar_tienda(tienda):
    os.makedirs(os.path.dirname(ARCHIVO_PROGRESO), exist_ok=True)
    with open(ARCHIVO_PROGRESO, "a", encoding="utf-8") as f:
        f.write(json.dumps(tienda, ensure_ascii=False) + "\n")


def tienda_vacia(id_, fuente):
    """Esquema unico de una tienda; todas las fuentes llenan estos campos."""
    return {
        "id": id_,
        "fuente": fuente,
        "nombre": None,
        "categoria": None,
        "direccion": None,
        "lat": None,
        "lng": None,
        "distancia_km": None,
        "telefono": None,             # como lo muestra Maps
        "telefono_e164": None,        # +51...
        "tipo_telefono": None,        # celular / fijo
        "posible_whatsapp": None,     # True si es celular
        "whatsapp_web": None,         # numero sacado de un enlace wa.me en su sitio
        "telefonos_extra": None,      # otros numeros que aparecen en su sitio
        "correo": None,
        "correos_extra": None,
        "sitio_web": None,
        "facebook": None,
        "instagram": None,
        "rating": None,
        "resenas": None,
        "url_maps": None,
        "rubro_busqueda": None,
        "enriquecido": False,
    }
