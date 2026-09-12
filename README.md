# Leads Las Malvinas

Extractor de contactos comerciales del clúster **Las Malvinas** (Cercado de Lima, Perú):
junta tiendas de varias fuentes públicas, las fusiona por teléfono y entrega un Excel/CSV
con **teléfono, WhatsApp probable, correo, sitio web, redes, dirección y distancia** al
centro del emporio. Hecho en Python para un encargo freelance real (una agencia de envíos
que quería contactar a los comerciantes de la zona).

```
python run.py --completo --amarillas --web --completar --lote 500
```

## Qué hace

```
                 ┌────────────────────────┐
  Google Maps ──▶│                        │
  (gmaps.exe)    │                        │      salida/progreso.jsonl
  Páginas ──────▶│  guardar()             │──▶   (una tienda por línea,
  Amarillas      │  · filtra por radio    │       reanudable)
  malvinas.pe ──▶│  · descarta galerías,  │              │
  DuckDuckGo ───▶│    bancos, cadenas     │              ▼
  (sitios + PDF) │  · fusiona por teléfono│      exportar.py ──▶ Excel + CSV
                 │  · enriquece con la    │      (hojas Tiendas / Resumen / Notas,
                 │    web de la tienda    │       y archivos por lotes)
                 └────────────────────────┘
```

| Fuente | Flag | Qué aporta | Notas |
|---|---|---|---|
| **Google Maps** vía [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper) | `--rubros`, `--galerias`, `--cruzado`, `--completo` | Nombre, teléfono, dirección, coordenadas, rating, web | *Fast mode*: sin navegador, ~6 consultas/s, máx. 20 fichas por consulta. Casi no obedece la coordenada, así que la cobertura se logra **variando el texto** (rubro × galería × calle). |
| **Páginas Amarillas Perú** | `--amarillas` | Teléfonos en E.164, WhatsApp, web, Facebook/Instagram, coordenadas | API JSON pública de su front Next.js (`/api/advertisements`). Se filtra por distancia. |
| **malvinas.pe** (marketplace del emporio) | `--directorio` | Celular **y correo** de ~50 vendedores | El correo viene ofuscado por Cloudflare; se descifra. |
| **Búsqueda web** (DuckDuckGo) | `--web` | Sitios y catálogos PDF que mencionan el clúster: botones `wa.me`, `tel:`, correos | Ruidosa (~1 de 3 útil); lista negra de dominios en `web_discovery._DOMINIOS_FUERA`. |
| **Sitio de cada tienda** | automático | Correos, WhatsApp, redes | `web_enricher.py`: portada + páginas de contacto en paralelo; reintenta sin verificar SSL (muchas tiendas chicas tienen la cadena rota). |
| **Google Maps con Playwright** | `--fuente scraper` | Lo mismo que gmaps.exe, hasta ~120 fichas por consulta | Más lento (abre cada ficha); útil si el binario deja de funcionar. |
| **Google Places API (New)** | `--fuente api` | Igual que Maps, oficial | Requiere `GOOGLE_MAPS_API_KEY`. |
| **Cruce de fuentes** | `--completar` | Rellena huecos: busca por nombre en Maps las tiendas del directorio/web, y en DuckDuckGo las que no tienen web | Solo escribe en campos vacíos. |
| **Limpieza con Claude** | `--ia` | Decide si una página de la búsqueda web es un negocio real del clúster y extrae sus datos en JSON | Requiere `ANTHROPIC_API_KEY` (~2 ¢ por ficha). |

Facebook e Instagram **no se scrapean**: solo se guarda el enlace. Los sitios detrás de
Cloudflare ("Just a moment…") se bajan con Chromium (`fetch.py`).

## Instalación

```
pip install -r requirements.txt
playwright install chromium
```

Bajar `google-maps-scraper` para Windows desde sus
[releases](https://github.com/gosom/google-maps-scraper/releases) y dejarlo en
`tools/gmaps.exe` (es la fuente por defecto cuando existe; si no, se usa Playwright).

## Uso

```
python run.py --muestra 50             # muestra rápida con config.MUESTRA_RUBROS
python run.py --rubros                 # los 30 rubros base desde el centro (~1 min)
python run.py --completo               # (rubros + extra) x (centro + galerías + calles): ~4,000 consultas, ~15 min
python run.py --amarillas              # Páginas Amarillas, todos los rubros (Cercado de Lima)
python run.py --directorio             # vendedores de malvinas.pe
python run.py --web                    # búsqueda web + PDF
python run.py --completar              # cruzar fuentes para rellenar huecos
python run.py --ia                     # limpiar con Claude lo que salió de --web
python run.py --gmaps-json RUTA.json   # reprocesar un resultados.json de gmaps.exe (p. ej. tras ampliar el radio)
python run.py --solo-exportar --nombre Base --lote 500   # regenerar Excel y partirlo en lotes de 500
```

- Todo se acumula en `salida/progreso.jsonl` **tienda por tienda**; si se corta, al volver a
  correr continúa sin repetir. Para empezar de cero, borrar ese archivo.
- Al terminar genera `salida/<nombre>_<fecha>.xlsx` (hojas *Tiendas*, *Resumen* con
  porcentajes y *Notas* que explica cada columna) y el mismo `.csv`. Con `--lote N`
  además escribe `<nombre>_loteK_<fecha>.xlsx`.
- Las filas van ordenadas: primero las que tienen teléfono + correo + WhatsApp, luego por cercanía.

## Columnas del Excel

Nombre · Rubro · Dirección · Distancia (km) · Teléfono · Teléfono +51 · Tipo (celular/fijo) ·
Posible WhatsApp · WhatsApp (del sitio) · Otros teléfonos · Correo · Otros correos ·
Sitio web · Facebook · Instagram · Rating · Reseñas · Google Maps · Búsqueda · Fuente

**Posible WhatsApp = Sí** cuando el número es celular peruano (empieza con 9). No se
verifica contra WhatsApp. **WhatsApp (del sitio)** es el número del botón "Chatea con
nosotros" de la propia web: ese sí es seguro.

## Qué esperar (medido)

- Una muestra de 97 tiendas (directorio + 30 rubros + web + cruce): 98 % con teléfono,
  95 % celular, 68 % con correo.
- `--completo` (4,033 consultas a Maps): ~2,400 fichas únicas, de las cuales ~1,700 dentro
  de 3.2 km y ~2,000 dentro de 5 km; ~90 % con teléfono.
- Google Maps **casi nunca da correo**; los correos salen del sitio web de la tienda,
  del directorio y de Páginas Amarillas. La mayoría de puestos de galería no tienen web.
- La cuadrícula geográfica (`--grid`) **no sirve** con el fast mode: 18 puntos separados
  0.7 km devolvieron 148 fichas distintas. Se dejó el flag por si el modo navegador del
  binario vuelve a funcionar (issue #322).

## Limpieza que se aplica al exportar

- Fuera: galerías, mercados, bancos, parques (`EXCLUIR_CATEGORIAS`), cadenas grandes
  (`EXCLUIR_NOMBRES`), fichas sin ningún contacto y las que quedan a más de `RADIO_KM`.
- Correos de plantillas web (`utils._CORREOS_BASURA`) y números que se repiten como
  "extra" en varias tiendas (suelen ser del diseñador web) se quitan.
- Nombres con letras decoradas (𝐋𝐀 𝐂𝐀𝐒𝐀…) se normalizan.
- Lo que sale de `--web` conviene revisarlo a mano o con `--ia`: ~1 de cada 2 no es del clúster.

## Ajustes (`config.py`)

`CENTRO_LAT/LNG` y `RADIO_KM` (zona), `RUBROS`, `RUBROS_EXTRA`, `CALLES`, `GALERIAS`
(qué buscar), `MUESTRA_RUBROS`, `EXCLUIR_CATEGORIAS`, `EXCLUIR_NOMBRES`, `PAGINAS_CONTACTO`,
`TIMEOUT_WEB`, `HEADLESS`.

## Herramientas evaluadas

| Herramienta | Decisión |
|---|---|
| **gosom/google-maps-scraper** | Integrado (`tools/gmaps.exe`). Su modo con navegador falla hoy ("unexpected page type"); se usa el fast mode y la variedad de consultas la arma este proyecto. |
| **Páginas Amarillas Perú** | Integrado: su front Next.js expone un API JSON limpio, con teléfonos ya normalizados. |
| **Crawl4AI** | No hacía falta: regex + Claude con JSON schema cubren la extracción de contactos. |
| **Scrapling** | No se instaló; el fallback a Chromium de `fetch.py` cubre el reto de Cloudflare. |
| **Firecrawl** | De pago; la parte útil (anti-bot, proxies) está solo en la nube. |
| **Google Places API** | Integrado como opción; no da correos y cuesta a escala. |
| **Padrón RUC de SUNAT** | Pendiente: 390 MB públicos con razón social y domicilio fiscal (sin teléfono). Serviría para llegar a *todos* los locales de la zona y luego cruzarlos por nombre. |

## Nota sobre datos

Solo se recogen datos que los propios negocios publican (fichas de Maps, directorios,
su sitio web). No se accede a Facebook/Instagram ni se verifica WhatsApp. Respetar los
términos de cada fuente y la normativa de protección de datos del país donde se use.
