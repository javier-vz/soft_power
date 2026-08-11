#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descarga de corpus OpenAlex para el estudio sobre IA, patrimonio cultural
y posicionamiento academico internacional.

ESTRATEGIA EN DOS PASOS
-----------------------
La API recupera por PATRIMONIO (termino raro, filtro liviano para el servidor)
y el cruce con INTELIGENCIA ARTIFICIAL se aplica localmente sobre titulo y
resumen. Esto tiene dos ventajas sobre meter todo en una sola query booleana:

  1. Evita la sintaxis anidada con parentesis, que es la parte mas fragil
     de la busqueda de OpenAlex y la causa habitual de errores 400.
  2. El criterio de inclusion queda como codigo versionado y auditable, no
     como una cadena opaca dentro de una URL. Mily puede revisarlo y ajustarlo
     sin volver a descargar nada.

De paso, produce los dos primeros niveles de corpus de la nota de trabajo:
  corpus A (amplio)   = todo lo recuperado por patrimonio
  corpus B (IA+patr.) = lo que ademas menciona IA en titulo o resumen

Uso
---
    pip install requests

    python descarga_openalex.py --diagnostico     # PRIMERO: ver que query funciona
    python descarga_openalex.py --paises cn
    python descarga_openalex.py --todos

Salida
------
    datos/openalex_A_<pais>_<version>.csv   corpus amplio (patrimonio)
    datos/openalex_B_<pais>_<version>.csv   corpus IA + patrimonio
    datos/log_descarga.csv                  registro de cada corrida
    QUERY.txt                               criterios congelados, para citar
"""

import argparse, csv, os, re, sys, time
from datetime import date
from urllib.parse import urlencode, quote

import requests

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

MAILTO = "jxvera@gmail.com"
VERSION_QUERY = "v1"
ANIO_INI, ANIO_FIN = 2015, 2026
DIR_SALIDA = "datos"
BASE = "https://api.openalex.org/works"
MAX_ESPERAS_429 = 20        # ~15 min de paciencia antes de rendirse
PAUSA_ENTRE_PAISES = 5      # respiro para que el limitador se recupere

# ── Terminos de PATRIMONIO: se envian a la API ───────────────────────────────
TERMINOS_PATRIMONIO = [
    "cultural heritage", "intangible heritage", "world heritage",
    "archaeology", "archaeological", "museum", "monument",
    "historic architecture", "cultural relic", "heritage site",
]

# ── Terminos de IA: se aplican localmente sobre titulo + resumen ─────────────
TERMINOS_IA = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "computer vision", "knowledge graph",
    "large language model", "natural language processing",
    "generative model", "convolutional", "transformer model",
]

# Excluidos a proposito, y por que:
#   "conservation" solo   -> arrastra ecologia y biodiversidad
#   "heritage" solo       -> arrastra genetica y herencia medica
#   "digital" / "3D"      -> tecnologia sin IA
#   "AI" (sigla suelta)   -> demasiados falsos positivos

PAISES = {
    "cn": "China", "it": "Italia", "gr": "Grecia", "eg": "Egipto",
    "gb": "Reino Unido", "us": "Estados Unidos", "fr": "Francia",
    "jp": "Japon", "in": "India", "pe": "Peru", "es": "Espana",
}

# OJO: "grants" existe en el registro pero NO es seleccionable. Para obtener
# financiamiento hay que descargar el registro completo: usar --completo.
CAMPOS = ("id,doi,title,publication_year,publication_date,type,cited_by_count,"
          "open_access,primary_location,authorships,topics,concepts,"
          "abstract_inverted_index,referenced_works_count,language")

COLUMNAS = [
    "openalex_id", "doi", "title", "abstract", "publication_year", "publication_date",
    "type", "language", "cited_by_count", "referenced_works_count",
    "is_oa", "oa_status", "source", "source_type",
    "authors", "institutions", "countries", "n_countries", "es_colaboracion_intl",
    "topics", "concepts", "grants", "funders",
    "terminos_ia_hallados", "n_terminos_ia",
    "pais_consulta", "version_query", "fecha_descarga",
]


def query_patrimonio():
    """OR simple, sin parentesis ni AND anidado: la forma mas estable."""
    return " OR ".join(f'"{t}"' for t in TERMINOS_PATRIMONIO)


def pedir(params, timeout=90):
    """GET con codificacion %20 en vez de +, que es lo que espera OpenAlex."""
    url = BASE + "?" + urlencode(params, quote_via=quote)
    return requests.get(url, timeout=timeout)


def depurar_select(params, max_intentos=6):
    """Si OpenAlex rechaza un campo de select, lo quita y reintenta.

    OpenAlex cambia de vez en cuando que campos admite en select (por ejemplo,
    "grants" dejo de ser seleccionable). En vez de fallar, el script descarta
    el campo problematico y avisa, para que la descarga no se detenga.
    """
    if "select" not in params:
        return params
    for _ in range(max_intentos):
        prueba = dict(params, **{"per-page": 1, "cursor": "*"})
        try:
            r = pedir(prueba, timeout=30)
        except requests.RequestException:
            return params
        if r.status_code != 400:
            return params
        try:
            msg = r.json().get("message", "")
        except Exception:
            return params
        m = re.search(r"([A-Za-z_\.]+) is not a valid select field", msg)
        if not m:
            return params
        malo = m.group(1)
        campos = [c for c in params["select"].split(",") if c != malo]
        print(f"    aviso: OpenAlex no admite el campo '{malo}' en select; se descarta")
        params = dict(params, select=",".join(campos))
    return params


# ─────────────────────────────────────────────────────────────────────────────
# DIAGNOSTICO
# ─────────────────────────────────────────────────────────────────────────────

def diagnostico():
    """Prueba variantes de query y reporta cual responde. Correr esto primero."""
    ia = " OR ".join(f'"{t}"' for t in TERMINOS_IA[:4])
    pat = " OR ".join(f'"{t}"' for t in TERMINOS_PATRIMONIO[:4])
    anios = f"{ANIO_INI}-{ANIO_FIN}"

    variantes = [
        ("1. patrimonio OR, codificacion %20  [la que usa el script]",
         {"filter": f"institutions.country_code:cn,publication_year:{anios},"
                    f"title_and_abstract.search:{pat}"}),
        ("2. patrimonio OR, una sola frase",
         {"filter": f"institutions.country_code:cn,publication_year:{anios},"
                    f'title_and_abstract.search:"cultural heritage"'}),
        ("3. patrimonio con pipes | en vez de OR",
         {"filter": f"institutions.country_code:cn,publication_year:{anios},"
                    f"title_and_abstract.search:" + "|".join(f'"{t}"' for t in TERMINOS_PATRIMONIO[:4])}),
        ("4. booleano completo con parentesis  [la que fallaba]",
         {"filter": f"institutions.country_code:cn,publication_year:{anios},"
                    f"title_and_abstract.search:({ia}) AND ({pat})"}),
        ("5. booleano sin comillas",
         {"filter": f"institutions.country_code:cn,publication_year:{anios},"
                    f"title_and_abstract.search:(heritage OR museum) AND (learning OR neural)"}),
        ("6. dos filtros search repetidos (AND implicito)",
         {"filter": f"institutions.country_code:cn,publication_year:{anios},"
                    f'title_and_abstract.search:"cultural heritage",'
                    f'title_and_abstract.search:"deep learning"'}),
        ("7. parametro search= en vez de filtro",
         {"search": "cultural heritage deep learning",
          "filter": f"institutions.country_code:cn,publication_year:{anios}"}),
        ("8. sin busqueda, solo pais y anio  [control]",
         {"filter": f"institutions.country_code:cn,publication_year:{anios}"}),
    ]

    print("DIAGNOSTICO DE QUERY  (una llamada por variante)\n" + "─" * 62)
    ok = []
    for nombre, params in variantes:
        params = dict(params, **{"per-page": 1, "mailto": MAILTO})
        try:
            r = pedir(params, timeout=30)
            if r.status_code == 200:
                n = r.json()["meta"]["count"]
                print(f"  OK   {nombre}\n         {n:,} registros")
                ok.append(nombre)
            else:
                msg = ""
                try:
                    msg = r.json().get("message", "")[:90]
                except Exception:
                    pass
                print(f"  {r.status_code}  {nombre}\n         {msg}")
        except Exception as e:
            print(f"  ERR  {nombre}\n         {str(e)[:80]}")
        time.sleep(1)
    print("─" * 62)
    print(f"Variantes que funcionan: {len(ok)} de {len(variantes)}")
    if ok:
        print("El script usa la variante 1. Si esa falla pero otra funciona, avisame cual.")


# ─────────────────────────────────────────────────────────────────────────────
# DESCARGA
# ─────────────────────────────────────────────────────────────────────────────

def reconstruir_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for palabra, idxs in inv.items():
        for i in idxs:
            pos[i] = palabra
    return " ".join(pos[i] for i in sorted(pos)) if pos else ""


def limpiar(t):
    return re.sub(r"\s+", " ", str(t)).strip() if t is not None else ""


def terminos_ia_en(texto):
    """Devuelve los terminos de IA presentes en el texto (minusculas)."""
    t = texto.lower()
    return [x for x in TERMINOS_IA if x in t]


def aplanar(w, pais, hoy):
    oa = w.get("open_access") or {}
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}

    autores, insts, paises = [], [], []
    for a in w.get("authorships") or []:
        nom = (a.get("author") or {}).get("display_name")
        if nom:
            autores.append(nom)
        for i in a.get("institutions") or []:
            if i.get("display_name"):
                insts.append(i["display_name"])
            if i.get("country_code"):
                paises.append(i["country_code"].lower())

    pu = sorted(set(paises))
    grants = w.get("grants") or []
    titulo = limpiar(w.get("title"))
    resumen = limpiar(reconstruir_abstract(w.get("abstract_inverted_index")))
    hallados = terminos_ia_en(titulo + " " + resumen)

    return {
        "openalex_id": limpiar(w.get("id")),
        "doi": limpiar(w.get("doi")),
        "title": titulo,
        "abstract": resumen,
        "publication_year": w.get("publication_year") or "",
        "publication_date": limpiar(w.get("publication_date")),
        "type": limpiar(w.get("type")),
        "language": limpiar(w.get("language")),
        "cited_by_count": w.get("cited_by_count") or 0,
        "referenced_works_count": w.get("referenced_works_count") or 0,
        "is_oa": oa.get("is_oa", ""),
        "oa_status": limpiar(oa.get("oa_status")),
        "source": limpiar(src.get("display_name")),
        "source_type": limpiar(src.get("type")),
        "authors": "; ".join(autores),
        "institutions": "; ".join(sorted(set(insts))),
        "countries": "; ".join(pu),
        "n_countries": len(pu),
        "es_colaboracion_intl": int(len(pu) > 1),
        "topics": "; ".join(limpiar(t.get("display_name")) for t in (w.get("topics") or [])),
        "concepts": "; ".join(limpiar(c.get("display_name")) for c in (w.get("concepts") or [])),
        "grants": "; ".join(limpiar(g.get("award_id")) for g in grants if g.get("award_id")),
        "funders": "; ".join(limpiar(g.get("funder_display_name")) for g in grants if g.get("funder_display_name")),
        "terminos_ia_hallados": "; ".join(hallados),
        "n_terminos_ia": len(hallados),
        "pais_consulta": pais,
        "version_query": VERSION_QUERY,
        "fecha_descarga": hoy,
    }


def descargar_pais(codigo, incluir_regiones=False, pausa=0.6, reintentos=5, completo=False):
    filtro_pais = "cn|hk|mo|tw" if (codigo == "cn" and incluir_regiones) else codigo
    params = {
        "filter": (f"institutions.country_code:{filtro_pais},"
                   f"publication_year:{ANIO_INI}-{ANIO_FIN},"
                   f"title_and_abstract.search:{query_patrimonio()}"),
        "per-page": 200,
        "cursor": "*",
        "mailto": MAILTO,
    }
    if not completo:
        params["select"] = CAMPOS

    params = depurar_select(params)

    filas, total, hoy, pagina = [], None, date.today().isoformat(), 0
    esperas_429 = 0          # presupuesto propio, no consume los reintentos de red
    while True:
        for intento in range(reintentos):
            try:
                r = pedir(params)
                if r.status_code == 429:
                    esperas_429 += 1
                    if esperas_429 > MAX_ESPERAS_429:
                        raise RuntimeError(
                            "OpenAlex mantiene el limite de tasa. Probable cuota diaria "
                            "agotada: reintenta en unas horas, o baja de a pocos paises.")
                    espera = min(15 * esperas_429, 90)
                    print(f"    limite de tasa ({esperas_429}), esperando {espera}s" + " " * 12)
                    time.sleep(espera)
                    continue
                if r.status_code == 400:
                    try:
                        msg = r.json().get("message", "")
                    except Exception:
                        msg = r.text[:200]
                    raise RuntimeError(f"400 de OpenAlex: {msg[:160]}\n"
                                       f"    Corre  python descarga_openalex.py --diagnostico")
                r.raise_for_status()
                datos = r.json()
                break
            except RuntimeError:
                raise
            except requests.RequestException as e:
                if intento == reintentos - 1:
                    raise
                print(f"    error de red ({str(e)[:50]}), reintento {intento + 1}")
                time.sleep(5 * (intento + 1))
        else:
            raise RuntimeError("agotados los reintentos")

        if total is None:
            total = datos["meta"]["count"]
            print(f"    corpus A declarado por la API: {total:,}")

        for w in datos["results"]:
            filas.append(aplanar(w, codigo, hoy))

        pagina += 1
        esperas_429 = 0
        print(f"    pagina {pagina}: {len(filas):,}/{total:,}", end="\r")

        cur = datos["meta"].get("next_cursor")
        if not cur or not datos["results"]:
            break
        params["cursor"] = cur
        time.sleep(pausa)

    print(" " * 50, end="\r")

    # El cursor puede repetir registros entre paginas: deduplicar por id.
    vistos, unicas = set(), []
    for f in filas:
        if f["openalex_id"] and f["openalex_id"] not in vistos:
            vistos.add(f["openalex_id"])
            unicas.append(f)
    if len(unicas) != len(filas):
        print(f"    deduplicados: {len(filas):,} -> {len(unicas):,}")
    return unicas, total


def guardar(filas, ruta):
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnostico", action="store_true",
                    help="prueba variantes de query y reporta cual responde")
    ap.add_argument("--paises", nargs="+")
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--incluir-hk-mo-tw", action="store_true",
                    help="agrupa Hong Kong, Macao y Taiwan con China (DECLARARLO en el paper)")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--pausa", type=float, default=0.6)
    ap.add_argument("--completo", action="store_true",
                    help="descarga el registro entero (mas lento, pero incluye financiamiento)")
    args = ap.parse_args()

    if args.diagnostico:
        diagnostico()
        return

    codigos = list(PAISES) if args.todos else (args.paises or ["cn"])
    os.makedirs(DIR_SALIDA, exist_ok=True)

    with open("QUERY.txt", "w", encoding="utf-8") as fh:
        fh.write(f"Version: {VERSION_QUERY}\n")
        fh.write(f"Congelada el: {date.today().isoformat()}\n")
        fh.write(f"Anios: {ANIO_INI}-{ANIO_FIN}\n")
        fh.write(f"hk/mo/tw agrupados con cn: {'si' if args.incluir_hk_mo_tw else 'no'}\n\n")
        fh.write("PASO 1 - recuperacion en la API (title_and_abstract.search):\n")
        fh.write(query_patrimonio() + "\n\n")
        fh.write("PASO 2 - filtro local de IA sobre titulo + resumen (basta un termino):\n")
        fh.write(" | ".join(TERMINOS_IA) + "\n")
    print(f"Criterios congelados en QUERY.txt ({VERSION_QUERY})\n")

    log = os.path.join(DIR_SALIDA, "log_descarga.csv")
    nuevo_log = not os.path.exists(log)
    for cod in codigos:
        nombre = PAISES.get(cod, cod)
        ruta_a = os.path.join(DIR_SALIDA, f"openalex_A_{cod}_{VERSION_QUERY}.csv")
        ruta_b = os.path.join(DIR_SALIDA, f"openalex_B_{cod}_{VERSION_QUERY}.csv")
        if os.path.exists(ruta_a) and not args.forzar:
            print(f"[{cod}] {nombre}: ya existe, se omite")
            continue
        print(f"[{cod}] {nombre}: descargando...")
        try:
            filas, total = descargar_pais(cod, args.incluir_hk_mo_tw, args.pausa,
                                          completo=args.completo)
        except Exception as e:
            print(f"    FALLO: {e}")
            print(f"    (vuelve a correr con --paises {cod} cuando se libere la cuota)\n")
            time.sleep(PAUSA_ENTRE_PAISES)
            continue

        filas_b = [f for f in filas if f["n_terminos_ia"] > 0]
        guardar(filas, ruta_a)
        guardar(filas_b, ruta_b)
        pct = 100 * len(filas_b) / len(filas) if filas else 0
        print(f"    corpus A (patrimonio):     {len(filas):,}")
        print(f"    corpus B (IA+patrimonio):  {len(filas_b):,}  ({pct:.1f}%)")
        print(f"    -> {ruta_a}\n       {ruta_b}\n")

        time.sleep(PAUSA_ENTRE_PAISES)

        with open(log, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if nuevo_log:
                w.writerow(["fecha", "pais", "version", "corpus_A", "corpus_B",
                            "total_api", "anio_ini", "anio_fin"])
                nuevo_log = False
            w.writerow([date.today().isoformat(), cod, VERSION_QUERY,
                        len(filas), len(filas_b), total, ANIO_INI, ANIO_FIN])

    print("Listo. Registro en datos/log_descarga.csv")


if __name__ == "__main__":
    main()
