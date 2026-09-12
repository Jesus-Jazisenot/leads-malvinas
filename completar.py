# -*- coding: utf-8 -*-
"""
Rellena huecos cruzando fuentes (`python run.py --completar`):

  a) Tiendas sin coordenadas/direccion (directorio, web): se buscan por nombre en
     Google Maps con gmaps.exe y, si el telefono o el nombre coinciden, se copian
     direccion, coordenadas, distancia, rating, resenas, enlace a Maps, rubro y web.
  b) Tiendas sin sitio web ni correo (la mayoria de Maps): se buscan por nombre en
     DuckDuckGo; si un resultado es claramente de la tienda (el dominio o la pagina
     de Facebook/Instagram lleva el nombre) se guarda y se enriquece con web_enricher.

Solo escribe en campos vacios; nunca pisa lo que ya habia.
"""
import difflib
import os
import re
import tempfile
import time
import unicodedata

from config import RADIO_KM
from gmaps_runner import GMAPS_EXE, _a_tienda, _correr
from utils import distancia_km
from web_discovery import _buscar, _dominio, _fuera
from web_enricher import enriquecer

_GENERICAS = {"sac", "srl", "eirl", "sa", "s.a.c", "e.i.r.l", "s.r.l", "s.a", "de", "del", "la", "las", "el", "los",
              "y", "e", "en", "lima", "peru", "perú", "malvinas", "import", "importaciones", "importadora",
              "distribuidora", "comercial", "corporacion", "corporación", "grupo", "inversiones", "servicios",
              "tienda", "empresa", "industrial", "industriales", "general", "generales", "centro", "cc", "c.c"}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def _tokens(nombre):
    return [t for t in _norm(nombre).split() if len(t) >= 4 and t not in _GENERICAS]


def _parecidos(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    corto, largo = sorted((a, b), key=len)
    # "valvulas lima" dentro de un nombre SEO kilometrico no es la misma tienda
    if corto in largo and len(corto) >= 0.6 * len(largo):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


# ---------------------------------------------------------------------------
# a) Ficha de Maps para tiendas del directorio / web
# ---------------------------------------------------------------------------
_CAMPOS_MAPS = ("direccion", "lat", "lng", "distancia_km", "rating", "resenas", "url_maps",
                "categoria", "sitio_web", "facebook", "instagram")


def completar_desde_maps(tiendas, log=print):
    pendientes = [t for t in tiendas.values() if t.get("lat") is None and t.get("nombre")]
    if not pendientes or not os.path.exists(GMAPS_EXE):
        return 0
    tmp = tempfile.mkdtemp(prefix="gmaps_completar_")
    entrada = os.path.join(tmp, "consultas.txt")
    with open(entrada, "w", encoding="utf-8") as f:
        for t in pendientes:
            nombre = re.sub(r"\(.*?\)", "", t["nombre"]).strip()
            f.write(f"{nombre} Las Malvinas Lima\n")
    log(f"> Maps por nombre: {len(pendientes)} tiendas sin coordenadas (~{len(pendientes) * 2.5 / 60:.0f} min)")
    from config import CENTRO_LAT, CENTRO_LNG
    filas = _correr(entrada, os.path.join(tmp, "r.json"), CENTRO_LAT, CENTRO_LNG, log)
    fichas = [_a_tienda(p, None) for p in filas if isinstance(p, dict)]
    fichas = [f for f in fichas if f.get("nombre")]
    por_tel = {f["telefono_e164"]: f for f in fichas if f.get("telefono_e164")}
    ids_conocidos = set(tiendas)

    n = 0
    for t in pendientes:
        f = por_tel.get(t.get("telefono_e164"))
        como = "telefono"
        if not f:
            cands = [c for c in fichas if _parecidos(t["nombre"], c["nombre"])
                     and (c.get("distancia_km") is None or c["distancia_km"] <= RADIO_KM)]
            f = cands[0] if cands else None
            como = "nombre"
        if not f:
            continue
        if f["id"] in ids_conocidos and f["id"] != t["id"]:
            # la ficha de Maps ya esta como otra tienda: se fusiona hacia la de Maps
            otra = tiendas[f["id"]]
            for k, v in t.items():
                if v not in (None, "", False) and otra.get(k) in (None, "", False):
                    otra[k] = v
            if t.get("telefono_e164") and t["telefono_e164"] != otra.get("telefono_e164"):
                extra = [x for x in (otra.get("telefonos_extra") or "").split("; ") if x] + [t["telefono_e164"]]
                otra["telefonos_extra"] = "; ".join(dict.fromkeys(extra))
            otra["fuente"] = "+".join(dict.fromkeys((otra["fuente"] + "+" + t["fuente"]).split("+")))
            del tiendas[t["id"]]
            log(f"   {t['nombre'][:40]} -> ya estaba en Maps como '{otra['nombre'][:40]}' (fusionada)")
            n += 1
            continue
        for k in _CAMPOS_MAPS:
            if t.get(k) in (None, "", False) and f.get(k) not in (None, "", False):
                t[k] = f[k]
        if f.get("telefono_e164") and f["telefono_e164"] != t.get("telefono_e164"):
            if not t.get("telefono_e164"):
                for k in ("telefono", "telefono_e164", "tipo_telefono", "posible_whatsapp"):
                    t[k] = f.get(k)
            else:
                extra = [x for x in (t.get("telefonos_extra") or "").split("; ") if x] + [f["telefono_e164"]]
                t["telefonos_extra"] = "; ".join(dict.fromkeys(extra))
        if t.get("lat") is not None and t.get("distancia_km") is None:
            t["distancia_km"] = distancia_km(t["lat"], t["lng"])
        t["fuente"] = "+".join(dict.fromkeys((t["fuente"] + "+gmaps").split("+")))
        log(f"   {t['nombre'][:40]} <- Maps por {como}: {f.get('direccion') or ''}")
        n += 1
    return n


# ---------------------------------------------------------------------------
# b) Sitio web / redes por nombre (DuckDuckGo)
# ---------------------------------------------------------------------------
def _resultado_de_la_tienda(url, nombre):
    toks = _tokens(nombre)
    if not toks:
        return None
    dom = _dominio(url)
    ruta = url.lower()
    if "facebook.com" in dom or "instagram.com" in dom:
        slug = _norm(ruta.split(dom, 1)[1])
        if any(tk in slug.replace(" ", "") for tk in toks) or any(tk in slug for tk in toks):
            return "facebook" if "facebook" in dom else "instagram"
        return None
    if _fuera(url):
        return None
    base = dom.split(".")[0]
    if any(tk in base for tk in toks) or any(tk in base for tk in ("".join(toks),)):
        return "sitio_web"
    return None


def completar_desde_web(tiendas, log=print, pausa=1.5):
    pendientes = [t for t in tiendas.values()
                  if not t.get("sitio_web") and not t.get("correo") and t.get("nombre") and not t.get("buscado_web")]
    if not pendientes:
        return 0
    log(f"> DuckDuckGo por nombre: {len(pendientes)} tiendas sin web ni correo (~{len(pendientes) * (pausa + 1.5) / 60:.0f} min)")
    n = 0
    for t in pendientes:
        t["buscado_web"] = True
        nombre = re.sub(r"\(.*?\)", "", t["nombre"]).strip()
        urls = _buscar(f'"{nombre}" Lima', max_results=8)
        hallado = []
        for u in urls:
            tipo = _resultado_de_la_tienda(u, nombre)
            if tipo and not t.get(tipo):
                if tipo == "sitio_web":
                    t["sitio_web"] = u.split("?")[0]
                else:
                    t[tipo] = u.split("?")[0]
                hallado.append(tipo)
        if "sitio_web" in hallado:
            try:
                enriquecer(t)
            except Exception as e:
                log(f"   (no se pudo leer {t['sitio_web']}: {e})")
        if hallado:
            n += 1
            log(f"   {t['nombre'][:40]}: {', '.join(hallado)} | correo: {t.get('correo') or '-'}")
        time.sleep(pausa)
    return n


def completar(tiendas, log=print):
    return completar_desde_maps(tiendas, log) + completar_desde_web(tiendas, log)
