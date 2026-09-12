# -*- coding: utf-8 -*-
"""
Exporta el progreso (JSONL) a Excel y CSV listos para entregar.
"""
import os
import re
import unicodedata
from datetime import datetime

import pandas as pd
import phonenumbers
from openpyxl.utils import get_column_letter

import config
import galerias
from config import CARPETA_SALIDA

SIN_GALERIA = "(sin galeria)"


def _local(e164):
    """+51987654321 -> '987 654 321'; +5113370737 -> '(01) 3370737'."""
    if not e164:
        return None
    try:
        return phonenumbers.format_number(phonenumbers.parse(e164, "PE"), phonenumbers.PhoneNumberFormat.NATIONAL)
    except phonenumbers.NumberParseException:
        return e164

COLUMNAS = [
    ("galeria", "Galeria"), ("galeria_metodo", "Galeria (como se ubico)"),
    ("nombre", "Nombre"), ("categoria", "Rubro"), ("direccion", "Direccion"), ("calle", "Calle"),
    ("distancia_km", "Distancia (km)"), ("telefono", "Telefono"), ("telefono_e164", "Telefono +51"),
    ("posible_whatsapp", "Posible WhatsApp"), ("whatsapp_web", "WhatsApp (del sitio)"), ("telefonos_extra", "Otros telefonos"),
    ("correo", "Correo"), ("correos_extra", "Otros correos"), ("sitio_web", "Sitio web"),
    ("facebook", "Facebook"), ("instagram", "Instagram"), ("rating", "Rating"),
    ("url_maps", "Google Maps"), ("fuente", "Fuente"),
]


def exportar(tiendas, nombre="leads_malvinas", lote=None):
    """tiendas: dict id -> tienda. Escribe .xlsx y .csv; devuelve las rutas.
    Con `lote=N` ademas parte la tabla en archivos `<nombre>_loteK_<fecha>.xlsx` de N
    filas (mismo orden y hojas), que es como se entrega y cobra al cliente."""
    filas = []
    for t in tiendas.values():
        if t.get("ia_descartada"):
            continue
        # sin telefono, ni whatsapp, ni correo no le sirve al cliente
        if not (t.get("telefono_e164") or t.get("whatsapp_web") or t.get("correo")):
            continue
        if (t.get("categoria") or "") in config.EXCLUIR_CATEGORIAS:
            continue
        if any(n in (t.get("nombre") or "").lower() for n in config.EXCLUIR_NOMBRES):
            continue
        # vendedores de malvinas.pe cuyo local real quedo lejos del cluster
        if (t.get("distancia_km") or 0) > config.RADIO_KM:
            continue
        t = dict(t)
        # nombres con letras "decoradas" (𝐋𝐀 𝐂𝐀𝐒𝐀...) se pasan a letras normales
        t["nombre"] = unicodedata.normalize("NFKC", t.get("nombre") or "").strip()
        t["telefono"] = _local(t.get("telefono_e164")) or t.get("telefono")
        if not t.get("direccion") and "directorio" in (t.get("fuente") or ""):
            t["direccion"] = "Vende en malvinas.pe (sin local ubicado en Maps)"
        filas.append(t)
    # un numero que aparece como "extra" en dos o mas tiendas distintas suele ser del
    # diseñador web o de una plantilla, no de la tienda: fuera de "Otros telefonos"
    conteo = {}
    for t in filas:
        for n in set(x for x in (t.get("telefonos_extra") or "").split("; ") if x):
            conteo[n] = conteo.get(n, 0) + 1
    principales = {t.get("telefono_e164") for t in filas} | {t.get("whatsapp_web") for t in filas}
    repetidos = {n for n, k in conteo.items() if k > 1 or n in principales}
    for t in filas:
        if t.get("telefonos_extra"):
            limpios = [x for x in t["telefonos_extra"].split("; ") if x and x not in repetidos and x != t.get("telefono_e164")]
            t["telefonos_extra"] = "; ".join(limpios) or None
    # galeria de cada tienda (el cliente quiere el Excel separado por galerias)
    galerias.asignar_todas(filas)
    for t in filas:
        t["calle"] = galerias.calle_de(t.get("direccion"))
        t["galeria"] = t.get("galeria") or SIN_GALERIA
        t["galeria_metodo"] = {"direccion": "en la direccion", "numero": "misma direccion que la galeria",
                               "cercania": "por cercania (aprox.)"}.get(t.get("galeria_metodo"))
    df = pd.DataFrame(filas)
    for k, _ in COLUMNAS:
        if k not in df.columns:
            df[k] = None
    df = df[[k for k, _ in COLUMNAS]].rename(columns=dict(COLUMNAS))
    df["Posible WhatsApp"] = df["Posible WhatsApp"].map({True: "Si", False: "No"})
    # las mas completas primero
    df["_score"] = df["Telefono +51"].notna().astype(int) * 2 + df["Correo"].notna().astype(int) + \
                   df["WhatsApp (del sitio)"].notna().astype(int)
    # galerias con mas tiendas primero, "(sin galeria)" al final; dentro de cada una, las mas completas
    orden = df["Galeria"].value_counts().to_dict()
    df["_gal"] = df["Galeria"].map(lambda g: (1, 0) if g == SIN_GALERIA else (0, -orden.get(g, 0)))
    df = df.sort_values(["_gal", "Galeria", "_score", "Distancia (km)"],
                        ascending=[True, True, False, True]).drop(columns=["_score", "_gal"])

    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    xlsx = os.path.join(CARPETA_SALIDA, f"{nombre}_{stamp}.xlsx")
    csv = os.path.join(CARPETA_SALIDA, f"{nombre}_{stamp}.csv")
    resumen = _escribir(df, xlsx, csv)
    if lote:
        for k in range(0, len(df), lote):
            n = k // lote + 1
            _escribir(df.iloc[k:k + lote], os.path.join(CARPETA_SALIDA, f"{nombre}_lote{n}_{stamp}.xlsx"),
                      os.path.join(CARPETA_SALIDA, f"{nombre}_lote{n}_{stamp}.csv"))
    return xlsx, csv, resumen


_ANCHOS = {"Galeria": 26, "Galeria (como se ubico)": 22, "Nombre": 34, "Rubro": 22, "Direccion": 40, "Calle": 22,
           "Distancia (km)": 12, "Telefono": 16, "Telefono +51": 16, "Tipo": 9, "Posible WhatsApp": 14,
           "WhatsApp (del sitio)": 18, "Otros telefonos": 30, "Correo": 30, "Otros correos": 30, "Sitio web": 32,
           "Facebook": 32, "Instagram": 28, "Rating": 8, "Resenas": 9, "Google Maps": 40, "Busqueda": 20, "Fuente": 10}


def _hoja(w, df, nombre):
    df.to_excel(w, index=False, sheet_name=nombre)
    ws = w.sheets[nombre]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, col in enumerate(df.columns):
        ws.column_dimensions[get_column_letter(i + 1)].width = _ANCHOS.get(col, 16)


def _nombre_hoja(g, usados):
    n = re.sub(r"[\/*?:\[\]]", "", g)[:28] or "Galeria"
    base, k = n, 2
    while n in usados:
        n, k = f"{base[:25]} {k}", k + 1
    usados.add(n)
    return n


def _escribir(df, xlsx, csv):
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        _hoja(w, df, "Tiendas")
        # hoja resumen
        resumen = pd.DataFrame({
            "Metrica": ["Tiendas", "Con telefono", "Celular (posible WhatsApp)", "Con correo",
                        "Con telefono y correo", "Con sitio web", "Con Facebook"],
            "Cantidad": [len(df), df["Telefono +51"].notna().sum(), (df["Posible WhatsApp"] == "Si").sum(),
                         df["Correo"].notna().sum(), (df["Telefono +51"].notna() & df["Correo"].notna()).sum(),
                         df["Sitio web"].notna().sum(), df["Facebook"].notna().sum()],
        })
        resumen["%"] = (resumen["Cantidad"] / max(len(df), 1) * 100).round(1)
        resumen.to_excel(w, index=False, sheet_name="Resumen")
        w.sheets["Resumen"].column_dimensions["A"].width = 30
        # hoja de notas para quien recibe el archivo
        notas = pd.DataFrame({"Nota": [
            f"Generado el {datetime.now().strftime('%d/%m/%Y')}. Zona: {config.CENTRO_NOMBRE} "
            f"(Jr. Ascope 541), radio {config.RADIO_KM} km.",
            "Fuente 'gmaps' = ficha de Google Maps (telefono, direccion, web, rating). "
            "Fuente 'directorio' = vendedor registrado en malvinas.pe (celular y correo). "
            "Fuente 'web' = sitio o catalogo PDF de la tienda. "
            "Fuente 'amarillas' = ficha en Paginas Amarillas Peru (telefonos, WhatsApp, web, redes).",
            "Telefono +51 = numero en formato internacional listo para marcar o para WhatsApp.",
            "Posible WhatsApp = Si cuando el numero es celular peruano (empieza en 9). No se verifica contra WhatsApp.",
            "WhatsApp (del sitio) = numero que la tienda publica en su boton 'Chatea con nosotros' (wa.me). Es el mas seguro.",
            "Correo: solo aparece cuando la tienda lo publica en su web o en malvinas.pe. Google Maps no da correos.",
            "Distancia (km) = distancia en linea recta desde Jr. Ascope 541 (vacia si la tienda no tiene ficha en Maps).",
            "Fuente 'directorio+gmaps' = vendedor de malvinas.pe cuya ficha de Maps tambien se encontro (direccion y rating vienen de ahi).",
            "Galeria: se toma de la direccion cuando Maps la trae; si no, por la direccion de la galeria "
            "(misma calle y numero) o por cercania (menos de 60 m de la galeria; marcado como aprox.). "
            "Las que quedan en la calle van en la hoja 'Sin galeria (por calle)', agrupadas por avenida/jiron.",
            "Hay una hoja por galeria (mismas columnas) y la hoja 'Por galeria' con el conteo.",
            "Las filas estan ordenadas por galeria (las que tienen mas tiendas primero) y dentro de cada una, "
            "primero las que tienen telefono + correo + WhatsApp, luego por cercania.",
            "Se excluyeron galerias, mercados, parques, bancos, cadenas grandes y fichas sin ningun contacto.",
        ]})
        notas.to_excel(w, index=False, sheet_name="Notas")
        w.sheets["Notas"].column_dimensions["A"].width = 120
        # una hoja por galeria (en el orden de la tabla) y una final con las de calle
        usados = {"Tiendas", "Resumen", "Notas", "Por galeria"}
        por_gal = df.groupby("Galeria", sort=False).size()
        pd.DataFrame({"Galeria": por_gal.index, "Tiendas": por_gal.values}).to_excel(w, index=False, sheet_name="Por galeria")
        w.sheets["Por galeria"].column_dimensions["A"].width = 30
        for g, bloque in df.groupby("Galeria", sort=False):
            if g == SIN_GALERIA:
                continue
            _hoja(w, bloque.drop(columns=["Galeria", "Calle"]), _nombre_hoja(g, usados))
        resto = df[df["Galeria"] == SIN_GALERIA]
        if len(resto):
            resto = resto.sort_values(["Calle", "Distancia (km)"], na_position="last")
            _hoja(w, resto.drop(columns=["Galeria", "Galeria (como se ubico)"]), "Sin galeria (por calle)")
    df.to_csv(csv, index=False, encoding="utf-8-sig")
    return resumen
