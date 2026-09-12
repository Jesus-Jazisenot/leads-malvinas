# -*- coding: utf-8 -*-
"""
Paso opcional: limpieza con Claude (API de Anthropic).

La busqueda web deja fichas ruidosas: nombres tipo "Contacto" o "Inicio", paginas que
mencionan Las Malvinas pero son de una empresa en otro distrito, telefonos que son de
la agencia que hizo la web, etc. Este paso le pasa a Claude el texto de la pagina y le
pide un JSON con: si es un negocio real ubicado en el cluster, nombre limpio, direccion,
rubro, y cual telefono / whatsapp / correo es el del negocio.

Se activa con `python run.py --ia` y necesita ANTHROPIC_API_KEY en el entorno.
Solo toca las tiendas con fuente "web" (las de Maps ya vienen limpias).

Costo aproximado: ~4k tokens de entrada por pagina -> unos 2 centavos de dolar por
tienda con claude-opus-5. Cambiar MODELO si se quiere mas barato.
"""
import json
import re

import anthropic
from bs4 import BeautifulSoup

import fetch

MODELO = "claude-opus-5"
MAX_CHARS = 7000

_ESQUEMA = {
    "type": "object",
    "properties": {
        "es_negocio_del_cluster": {"type": "boolean",
                                    "description": "True solo si es un negocio (tienda, distribuidora, importadora) con local en Las Malvinas / Cercado de Lima"},
        "motivo": {"type": "string", "description": "Una frase: por que si o por que no"},
        "nombre": {"type": "string", "description": "Nombre comercial limpio, sin 'Contacto', 'Inicio' ni eslogans"},
        "direccion": {"type": "string", "description": "Direccion del local en Lima, con galeria/stand si aparece; vacio si no hay"},
        "rubro": {"type": "string", "description": "Que vende, en 2-5 palabras (ej. 'maquinas de soldar', 'calzado por mayor')"},
        "telefono": {"type": "string", "description": "Telefono principal del negocio en formato +51..., vacio si no hay"},
        "whatsapp": {"type": "string", "description": "Numero de WhatsApp del negocio (+51...), vacio si no hay"},
        "correo": {"type": "string", "description": "Correo del negocio, vacio si no hay"},
    },
    "required": ["es_negocio_del_cluster", "motivo", "nombre", "direccion", "rubro", "telefono", "whatsapp", "correo"],
    "additionalProperties": False,
}

_SISTEMA = (
    "Eres un asistente que limpia fichas de negocios del cluster comercial Las Malvinas "
    "(Cercado de Lima, Peru; ejes Av. Argentina, Av. Guillermo Dansey, Jr. Ascope; galerias como "
    "Malvitec, Nicolini, Udampe, Mesa Redonda, La Bellota, Plaza Ferretero, Malvinas Plaza). "
    "Recibes el texto de una pagina web y los datos de contacto que un script extrajo con regex. "
    "Responde solo con lo que diga la pagina; si un dato no aparece, dejalo vacio. "
    "Los numeros peruanos de celular tienen 9 digitos y empiezan con 9; los fijos de Lima tienen 7 "
    "y van con prefijo 01. Devuelvelos siempre como +51 seguido de los digitos. "
    "Ignora telefonos y correos de la agencia que hizo la web, de bancos o de Google."
)


def _texto_pagina(url):
    if url.lower().split("?")[0].endswith(".pdf"):
        return fetch.pdf_texto(url) or ""
    html = fetch.html(url) or ""
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "noscript", "svg"]):
        s.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" "))


def limpiar(tienda, cliente=None, log=print):
    """Modifica la tienda en sitio. Devuelve False si Claude dice que no es del cluster."""
    cliente = cliente or anthropic.Anthropic()
    texto = _texto_pagina(tienda["sitio_web"])[:MAX_CHARS]
    if not texto:
        return True   # sin texto no hay nada que juzgar; se deja como esta
    extraido = {k: tienda.get(k) for k in ("nombre", "direccion", "telefono_e164", "telefonos_extra",
                                          "whatsapp_web", "correo", "correos_extra")}
    r = cliente.messages.create(
        model=MODELO,
        max_tokens=1024,
        system=_SISTEMA,
        messages=[{"role": "user", "content":
                   f"URL: {tienda['sitio_web']}\n\nDatos extraidos por regex:\n{json.dumps(extraido, ensure_ascii=False)}"
                   f"\n\nTexto de la pagina:\n{texto}"}],
        output_config={"format": {"type": "json_schema", "schema": _ESQUEMA}},
    )
    if r.stop_reason == "refusal":
        return True
    datos = json.loads(next(b.text for b in r.content if b.type == "text"))
    tienda["ia_motivo"] = datos["motivo"]
    if not datos["es_negocio_del_cluster"]:
        tienda["ia_descartada"] = True
        log(f"   IA descarta '{tienda['nombre']}': {datos['motivo']}")
        return False
    from utils import normalizar_telefono
    if datos["nombre"]:
        tienda["nombre"] = datos["nombre"]
    if datos["direccion"]:
        tienda["direccion"] = datos["direccion"]
    if datos["rubro"]:
        tienda["categoria"] = datos["rubro"]
    if datos["telefono"]:
        e164, tipo = normalizar_telefono(datos["telefono"])
        if e164:
            tienda["telefono"], tienda["telefono_e164"], tienda["tipo_telefono"] = e164, e164, tipo
            tienda["posible_whatsapp"] = tipo == "celular"
    if datos["whatsapp"]:
        e164, _ = normalizar_telefono(datos["whatsapp"])
        if e164:
            tienda["whatsapp_web"], tienda["posible_whatsapp"] = e164, True
    if datos["correo"] and "@" in datos["correo"]:
        tienda["correo"] = datos["correo"].lower()
    tienda["ia_limpiada"] = True
    return True


def limpiar_todas(tiendas, log=print):
    """Pasa por todas las tiendas de fuente web que aun no se han limpiado."""
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("> IA: falta ANTHROPIC_API_KEY. Crear una key en console.anthropic.com y correr\n"
            "      setx ANTHROPIC_API_KEY \"sk-ant-...\"   (y abrir una terminal nueva)")
        return 0
    cliente = anthropic.Anthropic()
    hechas = descartadas = 0
    for t in list(tiendas.values()):
        if not (t.get("fuente") or "").startswith("web") or t.get("ia_limpiada") or t.get("ia_descartada"):
            continue
        if not t.get("sitio_web"):
            continue
        try:
            ok = limpiar(t, cliente, log)
        except anthropic.RateLimitError:
            log("   limite de la API, espera un momento y vuelve a correr")
            break
        except anthropic.APIStatusError as e:
            log(f"   error de la API ({e.status_code}): {e.message}")
            break
        except anthropic.APIConnectionError as e:
            log(f"   sin conexion con la API: {e}")
            break
        hechas += 1
        if not ok:
            descartadas += 1
        else:
            log(f"   IA ok: {t['nombre']} | {t.get('categoria') or ''} | {t.get('direccion') or ''}")
    log(f"> IA: {hechas} revisadas, {descartadas} descartadas")
    return hechas
