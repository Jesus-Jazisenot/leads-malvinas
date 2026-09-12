# -*- coding: utf-8 -*-
"""
Punto de entrada. Ejemplos:

  python run.py --muestra 50                # 50 tiendas con los rubros de muestra (scraper)
  python run.py --galerias                  # busca "tiendas <galeria>" por cada galeria del cliente
  python run.py --rubros                    # busca por todos los rubros de config.RUBROS
  python run.py --cruzado                   # cada rubro x cada galeria (cientos de busquedas, para escalar)
  python run.py --consulta "valvulas" "motores"   # busquedas sueltas
  python run.py --fuente api --muestra 50   # lo mismo pero con Google Places API
  python run.py --fuente gmaps --rubros     # gosom/google-maps-scraper (rapido, saca correos)
  python run.py --fuente gmaps --rubros --grid   # cuadricula: cubre TODA la zona (horas; miles)
  python run.py --ia                        # limpia con Claude las fichas que salieron de la web
  python run.py --directorio                # vendedores del marketplace malvinas.pe
  python run.py --web                       # busqueda web: sitios y PDF que mencionen Las Malvinas
  python run.py --web --consulta "valvulas" # busqueda web solo con esos rubros
  python run.py --completar                 # rellena huecos: Maps por nombre + web por nombre
  python run.py --solo-exportar             # no busca nada, solo regenera el Excel

Todo lo que se va sacando se guarda en salida/progreso.jsonl; si se corta, al
volver a correr sigue donde iba. Al final siempre exporta Excel + CSV.
"""
import argparse
import sys

# La consola de Windows (cp1252) no aguanta emojis en nombres de tiendas
for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(errors="replace")
    except Exception:
        pass

import config
from exportar import exportar
from utils import cargar_progreso, fusionar, guardar_tienda, reescribir_progreso
from web_enricher import enriquecer


def main():
    ap = argparse.ArgumentParser(description="Leads de tiendas alrededor de Las Malvinas")
    import os
    ap.add_argument("--fuente", choices=["scraper", "api", "gmaps"],
                    default="gmaps" if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "gmaps.exe")) else "scraper",
                    help="gmaps (por defecto si esta tools/gmaps.exe), scraper (Playwright propio) o api (Places)")
    ap.add_argument("--grid", action="store_true", help="con --fuente gmaps: cuadricula sobre toda la zona")
    ap.add_argument("--ia", action="store_true", help="limpiar con Claude las tiendas de fuente web (ANTHROPIC_API_KEY)")
    ap.add_argument("--muestra", type=int, metavar="N", help="parar al juntar N tiendas nuevas")
    ap.add_argument("--galerias", action="store_true", help="buscar 'tiendas en <galeria>' por cada galeria")
    ap.add_argument("--rubros", action="store_true", help="buscar por todos los rubros")
    ap.add_argument("--cruzado", action="store_true", help="cada rubro x cada galeria")
    ap.add_argument("--completo", action="store_true",
                    help="(rubros + RUBROS_EXTRA) x (centro + galerias + CALLES); miles de consultas, para gmaps fast-mode")
    ap.add_argument("--consulta", nargs="+", metavar="TEXTO", help="busquedas sueltas")
    ap.add_argument("--directorio", action="store_true", help="vendedores de malvinas.pe")
    ap.add_argument("--amarillas", action="store_true",
                    help="Paginas Amarillas Peru (Cercado de Lima) por rubro; usa RUBROS + RUBROS_EXTRA")
    ap.add_argument("--gmaps-json", metavar="RUTA",
                    help="reprocesar un resultados.json que ya genero gmaps.exe (sin volver a consultar)")
    ap.add_argument("--web", action="store_true", help="busqueda web (DuckDuckGo) de sitios y PDF")
    ap.add_argument("--completar", action="store_true", help="rellenar huecos cruzando Maps y busqueda por nombre")
    ap.add_argument("--sin-enriquecer", action="store_true", help="no visitar los sitios web")
    ap.add_argument("--solo-exportar", action="store_true")
    ap.add_argument("--nombre", default="leads_malvinas", help="nombre base del archivo de salida")
    ap.add_argument("--lote", type=int, metavar="N", help="ademas exporta archivos por lotes de N filas")
    args = ap.parse_args()

    tiendas = cargar_progreso()
    print(f"Tiendas ya guardadas: {len(tiendas)}")

    if not args.solo_exportar:
        por_telefono = {t["telefono_e164"]: t for t in tiendas.values() if t.get("telefono_e164")}

        def guardar(t):
            if (t.get("categoria") or "") in config.EXCLUIR_CATEGORIAS:
                print(f"   (se salta, es {t['categoria']})")
                return False
            if any(n in (t.get("nombre") or "").lower() for n in config.EXCLUIR_NOMBRES):
                print(f"   (se salta, es cadena grande: {t['nombre']})")
                return False
            if not args.sin_enriquecer and t.get("sitio_web") and not t.get("enriquecido"):
                try:
                    enriquecer(t)
                except Exception as e:
                    print(f"   (no se pudo leer el sitio: {e})")
            # misma tienda vista por otra fuente: se fusiona por telefono
            previa = por_telefono.get(t.get("telefono_e164"))
            if previa and previa["id"] != t["id"]:
                fusionar(previa, t)
                reescribir_progreso(tiendas)
                print(f"   (fusionada con '{previa['nombre']}')")
                return False
            tiendas[t["id"]] = t
            if t.get("telefono_e164"):
                por_telefono[t["telefono_e164"]] = t
            guardar_tienda(t)
            return True

        total = 0
        try:
            if args.directorio:
                from web_discovery import directorio_malvinas
                total += directorio_malvinas(set(tiendas), log=print, cada_tienda=guardar, limite=args.muestra)
            if args.amarillas:
                from amarillas import scrapear as scrapear_amarillas
                total += scrapear_amarillas(config.RUBROS + config.RUBROS_EXTRA, set(tiendas), limite=args.muestra,
                                            log=print, cada_tienda=guardar)
            if args.gmaps_json:
                from gmaps_runner import reprocesar
                total += reprocesar(args.gmaps_json, set(tiendas), log=print, cada_tienda=guardar)
            if args.web:
                from web_discovery import busqueda_web, consultas_web
                cons = consultas_web(rubros=args.consulta) if args.consulta else consultas_web()
                total += busqueda_web(cons, set(tiendas), log=print, cada_tienda=guardar, limite=args.muestra)
            if not (args.directorio or args.web or args.ia or args.completar or args.amarillas or args.gmaps_json) or args.galerias or args.rubros or args.cruzado or args.completo:
                consultas = []
                if args.consulta and not args.web:
                    consultas += args.consulta
                if args.galerias:
                    consultas += [f"tiendas {g}" for g in config.GALERIAS]
                if args.rubros:
                    consultas += config.RUBROS
                if args.cruzado:
                    consultas += [f"{r} {g}" for g in config.GALERIAS for r in config.RUBROS]
                if args.completo:
                    todos = config.RUBROS + config.RUBROS_EXTRA
                    lugares = [""] + config.GALERIAS + config.CALLES
                    consultas += [f"{r} {l}".strip() for l in lugares for r in todos]
                consultas = list(dict.fromkeys(consultas))
                if not consultas and not (args.directorio or args.web or args.ia or args.completar or args.amarillas or args.gmaps_json):
                    consultas = config.MUESTRA_RUBROS
                    if not args.muestra:
                        args.muestra = 50
                if consultas:
                    if args.fuente == "api":
                        from places_api import scrapear
                        total += scrapear(consultas, set(tiendas), limite=args.muestra, cada_tienda=guardar)
                    elif args.fuente == "gmaps":
                        from gmaps_runner import scrapear
                        total += scrapear(consultas, set(tiendas), limite=args.muestra, cada_tienda=guardar,
                                          grid=args.grid, email=not args.sin_enriquecer)
                    else:
                        from maps_scraper import scrapear
                        total += scrapear(consultas, set(tiendas), limite=args.muestra, cada_tienda=guardar)
            if args.completar:
                from completar import completar
                n = completar(tiendas, log=print)
                reescribir_progreso(tiendas)
                print(f"   Fichas completadas: {n}")
            if args.ia:
                from ia_limpieza import limpiar_todas
                if limpiar_todas(tiendas, log=print):
                    reescribir_progreso(tiendas)
            print(f"\nTiendas nuevas en esta corrida: {total}")
        except KeyboardInterrupt:
            print("\nInterrumpido; lo que ya se saco quedo guardado.")

    if not tiendas:
        print("No hay nada que exportar.")
        sys.exit(1)
    xlsx, csv, resumen = exportar(tiendas, args.nombre, lote=args.lote)
    print("\n" + resumen.to_string(index=False))
    print(f"\nExcel: {xlsx}\nCSV:   {csv}")


if __name__ == "__main__":
    main()
