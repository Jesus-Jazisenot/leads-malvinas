# -*- coding: utf-8 -*-
"""
Descarga de paginas y PDFs con un solo punto de entrada.

Primero intenta con `requests` (rapido). Si el sitio responde 403/503 con la
pantalla "Just a moment..." de Cloudflare (p. ej. cfm.com.pe), lo vuelve a
pedir con un Chrome de Playwright, que si pasa ese filtro. El navegador se abre
una sola vez y se reutiliza.
"""
import atexit
import io

import threading

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import TIMEOUT_WEB, USER_AGENT

_HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "es-PE,es;q=0.9"}
_MAX_PDF = 15 * 1024 * 1024

_pw = _navegador = _pagina = None


def _con_navegador(url):
    global _pw, _navegador, _pagina
    # Playwright sync no se puede usar desde otro hilo (greenlet "cannot switch to a
    # different thread"); las descargas en paralelo del enricher se quedan sin fallback
    if threading.current_thread() is not threading.main_thread():
        return None
    if _pagina is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _navegador = _pw.chromium.launch(headless=True)
        _pagina = _navegador.new_context(locale="es-PE", user_agent=USER_AGENT).new_page()
        atexit.register(_cerrar)
    try:
        _pagina.goto(url, wait_until="domcontentloaded", timeout=25000)
        _pagina.wait_for_timeout(2500)   # deja pasar el reto de Cloudflare
        html = _pagina.content()
        return None if "Just a moment" in html[:3000] else html
    except Exception:
        return None


def _cerrar():
    try:
        _navegador.close()
        _pw.stop()
    except Exception:
        pass


def _get(url, timeout=TIMEOUT_WEB, **kw):
    """GET con reintento sin verificar certificado: muchas tiendas chicas tienen
    la cadena SSL rota y solo se lee HTML publico."""
    try:
        return requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True, **kw)
    except requests.exceptions.SSLError:
        return requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True, verify=False, **kw)


def html(url, navegador=True):
    """HTML de una pagina, o None. Cae a Playwright si Cloudflare bloquea (solo desde el hilo principal)."""
    try:
        r = _get(url)
    except requests.RequestException:
        return None
    tipo = r.headers.get("Content-Type", "")
    if r.status_code == 200 and "html" in tipo:
        if "Just a moment" in r.text[:3000]:
            return _con_navegador(url) if navegador else None
        return r.text
    if r.status_code in (403, 503, 429):
        return _con_navegador(url) if navegador else None
    return None


def pdf_texto(url):
    """Texto de un PDF en linea, o None."""
    try:
        r = _get(url, timeout=TIMEOUT_WEB * 2, stream=True)
        if r.status_code != 200:
            return None
        datos = b""
        for trozo in r.iter_content(65536):
            datos += trozo
            if len(datos) > _MAX_PDF:
                return None
        if not datos.startswith(b"%PDF"):
            return None
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(datos))
        return "\n".join((p.extract_text() or "") for p in lector.pages[:40])
    except Exception:
        return None
