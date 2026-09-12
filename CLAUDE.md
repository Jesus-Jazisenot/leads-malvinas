# leads_malvinas — guía para Claude Code

Scraper de tiendas del clúster Las Malvinas (Cercado de Lima, Perú) para un cliente
freelance de Jesús. Entrega Excel/CSV con teléfono, WhatsApp probable, correo, web y redes.
Lee `README.md` para el detalle de fuentes y flags.

## Cómo correrlo
- Muestra rápida (Maps con Playwright): `python run.py --muestra 50`
- Mejor fuente de correos: `python run.py --directorio` (marketplace malvinas.pe, ~52 vendedores)
- Sitios y catálogos PDF que mencionan el clúster: `python run.py --web`
- Cobertura masiva de Maps: `python run.py --completo` (109 rubros x 37 lugares, ~15 min).
  `--grid` NO sirve (el fast mode ignora la coordenada); la cobertura sale de variar el texto.
- Paginas Amarillas Peru por rubro: `python run.py --amarillas`
- Reprocesar un resultados.json de gmaps.exe sin volver a consultar: `--gmaps-json RUTA`
- Limpieza con Claude de lo que salió de la web: `python run.py --ia` (necesita `ANTHROPIC_API_KEY`)
- Rellenar huecos cruzando fuentes (Maps por nombre, web por nombre): `python run.py --completar`
- Regenerar el Excel (y partirlo en lotes): `python run.py --solo-exportar --nombre Base_Las_Malvinas --lote 500`

Todo se acumula en `salida/progreso.jsonl` (reanudable) y se exporta a `salida/*.xlsx`.
Para empezar de cero, borrar `salida/progreso.jsonl`.

## Reglas
- Antes de correr algo que tarde más de 10 min (`--completo`, `--amarillas`, `--web`, `--completar`),
  avisar cuánto va a tardar y lanzarlo en segundo plano.
- No inventar datos: si no hay tacómetro no hay RPM; si no hay correo, la celda va vacía.
- `--ia` cuesta dinero (~2 ¢ por ficha con claude-opus-5): decir cuántas fichas va a
  revisar antes de lanzarlo.
- Facebook/Instagram no se scrapean; solo se guarda el enlace.
- Si Google Maps deja de dar teléfonos, revisar los selectores `data-item-id` en
  `maps_scraper.leer_ficha()`; si `--web` trae basura, agregar el dominio a
  `web_discovery._DOMINIOS_FUERA`.

## Archivos
`config.py` centro/radio/rubros/galerías · `maps_scraper.py` Maps con Playwright ·
`gmaps_runner.py` envuelve `tools/gmaps.exe` (gosom/google-maps-scraper) · `amarillas.py` API de Paginas Amarillas ·
`places_api.py` Places API · `web_discovery.py` directorio + búsqueda web + PDF ·
`web_enricher.py` correos/wa.me desde el sitio · `completar.py` cruce de fuentes para huecos · `fetch.py` descarga con fallback a
Chrome para Cloudflare · `ia_limpieza.py` limpieza con Claude · `exportar.py` Excel/CSV ·
`run.py` orquestador.
