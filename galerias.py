# -*- coding: utf-8 -*-
"""
Asigna cada tienda a una galeria del cluster (el cliente pidio el Excel separado
por galerias, 12-sep-2026). Tres metodos, del mas seguro al menos:

  1. "direccion": el nombre de la galeria (o un alias) aparece en la direccion o
     en el nombre de la tienda. Solo ~1 de cada 4 fichas de Maps lo trae.
  2. "numero": la direccion es la misma que la de la galeria (calle + numero),
     p. ej. "Av. Argentina 608" es Malvinas Plaza.
  3. "cercania": la ficha esta a menos de RADIO_GALERIA_M metros de la galeria
     (Maps suele poner a las tiendas de una galeria en el mismo punto).

Las coordenadas y direcciones salieron de las fichas de Maps de cada galeria
(consulta "<galeria> Las Malvinas Lima" con gmaps.exe). Las galerias sin ficha en
Maps (Acopro, Loreto, El Progreso...) solo se detectan por texto; si en la corrida
aparecen tiendas con esa galeria en la direccion, su centroide se usa para el metodo 3.
"""
import re
import unicodedata

from utils import distancia_km

RADIO_GALERIA_M = 60

# Orden en el Excel: primero las que el cliente marco como prioritarias (12-sep-2026)
PRIORIDAD = ["Nicolini", "La Bellota", "La Bellota 2", "La Bellota 3", "Plaza Ferretero", "Malvitec"]

# nombre canonico -> (aliases regex, direcciones (calle regex, numero), lat, lng)
GALERIAS = {
    "Malvitec":                     (r"malvitec",                                   [(r"argentina", "460")], -12.0428996, -77.0480596),
    "Mesa Redonda (Las Malvinas)":  (r"me[sz]a\s*redonda",                          [(r"argentina", "428")], -12.0428454, -77.047512),
    "Malvinas Plaza":               (r"malvinas\s*plaza",                           [(r"argentina", "608")], -12.0432203, -77.0500864),
    "La Bellota":                   (r"bellota(?!\s*(?:2|ii|3|iii))",               [(r"argentina", "725")], -12.0447483, -77.0511572),
    "La Bellota 2":                 (r"bellota\s*(?:2|ii)\b",                       [(r"argentina", "308")], -12.0432901, -77.0460013),
    "La Bellota 3":                 (r"bellota\s*(?:3|iii)\b",                      [], None, None),
    "Acopro":                       (r"\bacopro\b",                                 [], None, None),
    "Acoprom":                      (r"\bacoprom\b",                                [], None, None),
    "Udampe":                       (r"udampe",                                     [(r"argentina", "639"), (r"c[aá]rcamo", "453")], -12.0444523, -77.0500692),
    "Nicolini":                     (r"nicol+ini",                                  [(r"argentina", "215"), (r"huarochir", "18")], -12.0443497, -77.0445988),
    "Plaza Ferretero":              (r"plaza\s*ferretero",                          [(r"dansey", "405")], -12.0458292, -77.044455),
    "La Cachina Fashion":           (r"cachina",                                    [(r"argentina", "801")], -12.0444948, -77.0525964),
    "Loreto":                       (r"(?:c\.?\s?c\.?|galer[ií]a|centro comercial)\s*loreto", [], None, None),
    "Calzamundo":                   (r"calzamundo",                                 [(r"dansey", "351")], -12.0453415, -77.0435116),
    "Calza Centro":                 (r"calza\s*centro",                             [], None, None),
    "Unicentro":                    (r"unicentro",                                  [(r"alfonso ugarte", "028"), (r"alfonso ugarte", "28")], -12.0425927, -77.0436912),
    "Boulevard Electro Ferretero":  (r"boulevard|electro\s*ferretero",              [(r"dansey", "354")], -12.0449885, -77.0435502),
    "El Progreso":                  (r"(?:c\.?\s?c\.?|galer[ií]a|centro comercial)\s*el\s*progreso", [], None, None),
    "El Reloj":                     (r"(?:c\.?\s?c\.?|galer[ií]a|centro comercial)\s*el\s*reloj", [], None, None),
    "Viamix":                       (r"v[ií]a\s*mix",                               [(r"benavides", "687")], -12.0473452, -77.0504993),
    "La Chimenea":                  (r"chimenea",                                   [], None, None),
    "Centro Comercial Las Malvinas": (r"(?:c\.?\s?c\.?|galer[ií]a|centro comercial)\s*(?:las\s*)?malvinas\b(?!\s*plaza)", [(r"dansey", "440")], -12.0449008, -77.0449576),
    "Grupo Malvinas 33":            (r"malvinas\s*33",                              [(r"dansey", "401")], -12.0452338, -77.0446736),
    "Top Center":                   (r"top\s*center",                               [], None, None),
    "Multicenter":                  (r"multicenter",                                [], None, None),
    "Acero Center":                 (r"acero\s*center",                             [], None, None),
}

_ALIAS = {g: re.compile(v[0], re.I) for g, v in GALERIAS.items()}
_GENERICA = re.compile(r"(?:c\.?\s?c\.?|centro\s+comercial|galer[ií]as?)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ0-9&'\. ]{3,35}?)(?=,|\s+(?:av|jr|jir[oó]n|calle|tienda|local|stand|puesto|int|piso|nro|n°|#|\d)|$)", re.I)
_CALLE = re.compile(r"((?:av(?:enida)?|jr|jir[oó]n|calle|ca|psje|pasaje|prolongaci[oó]n)\.?\s+[A-Za-zÁÉÍÓÚÑáéíóúñ\. ]{3,40}?)(?=\s+\d|,|$)", re.I)
_NUM = re.compile(r"\b(\d{2,4})\b")


def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _por_texto(texto):
    if not texto:
        return None
    for g, rx in _ALIAS.items():
        if rx.search(texto):
            return g
    return None


def _por_numero(direccion):
    if not direccion:
        return None
    d = _sin_acentos(direccion).lower()
    for g, (_, dirs, _, _) in GALERIAS.items():
        for calle, numero in dirs:
            m = re.search(calle + r"[^,]{0,25}?\b" + numero + r"\b", d)
            if m:
                return g
    return None


def _por_cercania(lat, lng, centros):
    if lat is None or lng is None:
        return None
    mejor, dist = None, RADIO_GALERIA_M / 1000.0
    for g, (glat, glng) in centros.items():
        d = distancia_km(lat, lng, glat, glng)
        if d <= dist:
            mejor, dist = g, d
    return mejor


def calle_de(direccion):
    """'Av. Argentina', 'Jr. Ascope'... para agrupar las que no tienen galeria."""
    m = _CALLE.search(direccion or "")
    if not m:
        return None
    c = re.sub(r"\s+", " ", m.group(1)).strip(" .")
    c = re.sub(r"^(av|avenida)\b\.?", "Av.", c, flags=re.I)
    c = re.sub(r"^(jr|jiron|jirón)\b\.?", "Jr.", c, flags=re.I)
    return c[:40].title().replace("Av.", "Av.").replace("Jr.", "Jr.")


def asignar_todas(tiendas):
    """tiendas: iterable de dicts. Escribe `galeria` y `galeria_metodo` en cada una.
    Devuelve un conteo por galeria."""
    tiendas = list(tiendas)
    centros = {g: (lat, lng) for g, (_, _, lat, lng) in GALERIAS.items() if lat is not None}

    # 1 y 2: texto y numero; de paso, centroides para las galerias sin coordenadas
    suma = {}
    for t in tiendas:
        texto = f"{t.get('direccion') or ''} | {t.get('nombre') or ''}"
        g = _por_texto(texto)
        metodo = "direccion" if g else None
        if not g:
            g = _por_numero(t.get("direccion"))
            metodo = "numero" if g else None
        if not g:
            m = _GENERICA.search(t.get("direccion") or "")
            if m:
                g = "Galería " + m.group(1).strip(" .").title()
                metodo = "direccion"
        t["galeria"], t["galeria_metodo"] = g, metodo
        if g and t.get("lat") is not None and g in GALERIAS:
            s = suma.setdefault(g, [0.0, 0.0, 0])
            s[0] += t["lat"]; s[1] += t["lng"]; s[2] += 1
    for g, (la, ln, n) in suma.items():
        if g not in centros and n >= 2:
            centros[g] = (la / n, ln / n)

    # 3: cercania
    for t in tiendas:
        if t.get("galeria"):
            continue
        g = _por_cercania(t.get("lat"), t.get("lng"), centros)
        if g:
            t["galeria"], t["galeria_metodo"] = g, "cercania"
    conteo = {}
    for t in tiendas:
        conteo[t.get("galeria") or "(sin galería)"] = conteo.get(t.get("galeria") or "(sin galería)", 0) + 1
    return conteo
