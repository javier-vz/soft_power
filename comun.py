#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Funciones compartidas por analisis.py, agenda.py y validacion.py.

Contiene cuatro cosas:

  1. La carga de los corpus, con deduplicacion y filtro de anios.
  2. Estadistica minima: intervalos de confianza de Wilson para proporciones.
  3. El buscador de toponimos (Gazetteer), que reemplaza al cotejo regex
     variante por variante de la version 1.0. Busca por n-gramas de palabras
     completas, de modo que "berat" nunca coincide dentro de "deliberate".
  4. Los diccionarios de paises, regiones y sitios de la Lista del Patrimonio
     Mundial de la UNESCO.

Todo criterio de clasificacion vive aqui y en agenda.py como codigo versionado:
nada esta escondido en datos.
"""

import glob
import html
import math
import os
import re
import unicodedata
from collections import Counter

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION GENERAL
# ─────────────────────────────────────────────────────────────────────────────

DIR_DATOS = "datos"
DIR_SALIDA = "resultados"

ANIO_MIN = 2015
# 2026 es un anio parcial (la descarga es de agosto de 2026): se excluye por
# defecto de todo calculo de tasas. Se puede incluir con --anio-max 2026.
ANIO_MAX_DEFECTO = 2025

NOMBRES = {
    "cn": "China", "it": "Italia", "gr": "Grecia", "eg": "Egipto",
    "gb": "Reino Unido", "us": "Estados Unidos", "fr": "Francia",
    "jp": "Japón", "in": "India", "pe": "Perú", "es": "España",
}

# Terminos del filtro de IA de la consulta v1 (identicos a descarga_openalex.py).
TERMINOS_IA = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "computer vision", "knowledge graph",
    "large language model", "natural language processing",
    "generative model", "convolutional", "transformer model",
]

# Fuentes que son repositorios o archivos de datos, no revistas ni actas.
# Se usan solo en el analisis de sensibilidad de la tasa de IA.
REGEX_REPOSITORIO = re.compile(
    r"zenodo|research square|ssrn|arxiv|preprints|archaeology data service|"
    r"figshare|dryad|open science framework|osf preprints", re.I)


# Tema principal (primer topico de OpenAlex) propio de las ciencias de la vida.
# El termino "museum" de la consulta atrae tambien la taxonomia de especimenes
# de museo, que no es patrimonio cultural. Es una heuristica por palabras clave
# sobre el nombre del topico; se usa SOLO en el analisis de sensibilidad. Se
# excluyen a proposito los topicos de isotopos, etnobotanica e indigenas, que
# son ciencia arqueologica o patrimonio inmaterial.
REGEX_CIENCIAS_VIDA = re.compile(
    r"taxonom|insect|orthopter|coleopter|lepidopter|hymenopter|hemipter|dipter|arthropod|"
    r"entomolog|species|phylogen|ornitholog|\bbird|\bfish|ichthy|mammal|reptile|amphibian|"
    r"parasit|fung|\bplant|botan|ecolog|biodiversity|marine biology|zoolog|palaeont|paleont|"
    r"dinosaur|fossil|spider|mollus|coral|astrophys|particle physics|quantum", re.I)
REGEX_CIENCIAS_VIDA_EXCEPCION = re.compile(r"isotope|ethnobot|indigenous|astronomy", re.I)


def es_ciencias_vida(topicos):
    """True si el primer topico de la lista es de ciencias de la vida."""
    primero = str(topicos).split("; ")[0] if isinstance(topicos, str) else ""
    return bool(REGEX_CIENCIAS_VIDA.search(primero)
                and not REGEX_CIENCIAS_VIDA_EXCEPCION.search(primero))


def limpiar_html(texto):
    """Quita etiquetas y entidades HTML/XML que OpenAlex deja en titulos y resumenes."""
    t = re.sub(r"<[^>]+>", " ", str(texto))
    return re.sub(r"\s+", " ", html.unescape(html.unescape(t))).strip()


# ─────────────────────────────────────────────────────────────────────────────
# TEXTO
# ─────────────────────────────────────────────────────────────────────────────

def normalizar(texto):
    """Minusculas, sin acentos y sin puntuacion: solo palabras separadas por
    un espacio. "Xi'an" -> "xi an"; "Hegra (Al-Hijr)" -> "hegra al hijr".
    Aplicar la MISMA funcion a los textos y a los nombres del gazetteer es lo
    que garantiza que coincidan."""
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def separar(serie, sep="; "):
    """Aplana una columna de listas separadas por punto y coma."""
    c = Counter()
    for v in serie.dropna():
        for x in str(v).split(sep):
            x = x.strip()
            if x:
                c[x] += 1
    return c


# ─────────────────────────────────────────────────────────────────────────────
# ESTADISTICA
# ─────────────────────────────────────────────────────────────────────────────

def wilson(k, n, z=1.96):
    """Intervalo de Wilson al 95 % para una proporcion k/n, en porcentaje.

    Se usa en lugar del intervalo normal porque funciona bien con n pequeno y
    con proporciones cercanas a 0 o 100, que es exactamente nuestro caso
    (Peru tiene decenas de trabajos de IA, no miles)."""
    if not n:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    mitad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * max(0.0, centro - mitad), 100 * min(1.0, centro + mitad))


def pct(k, n, nd=1):
    return round(100 * k / n, nd) if n else float("nan")


def fila_proporcion(prefijo, k, n):
    """Devuelve {prefijo_pct, prefijo_ic_inf, prefijo_ic_sup} para una columna."""
    lo, hi = wilson(k, n)
    return {f"{prefijo}_pct": pct(k, n), f"{prefijo}_ic_inf": round(lo, 1),
            f"{prefijo}_ic_sup": round(hi, 1)}


# ─────────────────────────────────────────────────────────────────────────────
# CARGA DE CORPUS
# ─────────────────────────────────────────────────────────────────────────────

def cargar_corpus(anio_min=ANIO_MIN, anio_max=ANIO_MAX_DEFECTO,
                  dir_datos=DIR_DATOS, verbose=True):
    """Carga los corpus A de cada pais. Devuelve (A, info).

    - Elimina duplicados por identificador de OpenAlex (el cursor de la API
      puede repetir registros; la descarga de China los conserva).
    - Restringe a [anio_min, anio_max].
    - Limpia etiquetas y entidades HTML de titulos y resumenes.
    - Agrega las columnas auxiliares tiene_resumen, es_repositorio y ciencias_vida.

    El corpus B (IA + patrimonio) NO se lee de los archivos openalex_B_*.csv:
    se deriva como A[n_terminos_ia > 0], que es exactamente como lo construye
    descarga_openalex.py. Asi A y B pasan siempre por el mismo filtrado.
    """
    A, info = {}, []
    for ruta in sorted(glob.glob(os.path.join(dir_datos, "openalex_A_*_*.csv"))):
        m = re.match(r"openalex_A_([a-z]{2})_", os.path.basename(ruta))
        if not m:
            continue
        pais = m.group(1)
        df = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)
        n0 = len(df)
        df = df.drop_duplicates("openalex_id")
        n1 = len(df)
        df = df[(df.publication_year >= anio_min) & (df.publication_year <= anio_max)].copy()
        df["pais"] = pais
        df["abstract"] = df["abstract"].fillna("").map(limpiar_html)
        df["title"] = df["title"].fillna("").map(limpiar_html)
        df["ciencias_vida"] = df["topics"].map(es_ciencias_vida)
        df["tiene_resumen"] = df["abstract"].str.strip().ne("")
        df["es_repositorio"] = df["source"].fillna("").map(lambda s: bool(REGEX_REPOSITORIO.search(s)))
        A[pais] = df.reset_index(drop=True)
        info.append({"pais": pais, "filas_archivo": n0, "duplicados": n0 - n1,
                     "fuera_de_anios": n1 - len(df), "filas_analizadas": len(df)})
    if not A:
        raise SystemExit(f"No se encontraron archivos en {dir_datos}/. "
                         f"Corre primero descarga_openalex.py")
    info = pd.DataFrame(info)
    if verbose:
        print(f"Corpus cargados: {', '.join(NOMBRES.get(p, p) for p in sorted(A))}")
        print(f"  periodo {anio_min}-{anio_max}; duplicados eliminados: "
              f"{int(info.duplicados.sum())}; filas fuera de periodo: {int(info.fuera_de_anios.sum())}\n")
    return A, info


def derivar_B(A, minimo_terminos=1):
    """Corpus B: trabajos de A con al menos `minimo_terminos` terminos de IA."""
    return {p: d[d.n_terminos_ia >= minimo_terminos] for p, d in A.items()}


# ─────────────────────────────────────────────────────────────────────────────
# GAZETTEER: BUSQUEDA POR N-GRAMAS DE PALABRAS COMPLETAS
# ─────────────────────────────────────────────────────────────────────────────

class Gazetteer:
    """Diccionario nombre -> valor con busqueda de coincidencia mas larga.

    `buscar` recorre una lista de palabras y devuelve las coincidencias que no
    se solapan, prefiriendo siempre la mas larga: asi "south korea" gana a
    "korea", "inner mongolia" a "mongolia" y "north africa" a "africa".

    Es mucho mas rapido que probar una expresion regular por cada nombre, y por
    construccion solo reconoce palabras completas.
    """

    def __init__(self, entradas):
        self.d = dict(entradas)
        largos = {}
        for nombre in self.d:
            t = nombre.split()
            largos.setdefault(t[0], set()).add(len(t))
        self.largos = {k: sorted(v, reverse=True) for k, v in largos.items()}

    def buscar(self, palabras):
        salida, i, n = [], 0, len(palabras)
        while i < n:
            avance = 1
            for k in self.largos.get(palabras[i], ()):
                if i + k <= n:
                    cand = " ".join(palabras[i:i + k])
                    if cand in self.d:
                        salida.append((cand, self.d[cand]))
                        avance = k
                        break
            i += avance
        return salida


# ── Paises ───────────────────────────────────────────────────────────────────

# Homonimos con palabras comunes del ingles cientifico: no se buscan.
_PAISES_EXCLUIDOS = {"georgia", "chad", "guinea", "niger", "jersey", "guernsey"}

_ALIAS_PAIS = {
    "gb": ["united kingdom", "uk", "great britain", "britain", "england",
           "scotland", "wales", "northern ireland"],
    "us": ["united states", "united states of america", "usa"],
    "ru": ["russia"], "ir": ["iran"], "kr": ["south korea", "korea"],
    "kp": ["north korea"], "tr": ["turkey", "turkiye"], "vn": ["vietnam"],
    "sy": ["syria"], "cz": ["czech republic", "czechia"],
    "mm": ["myanmar", "burma"], "la": ["laos"], "mo": ["macao", "macau"],
    "hk": ["hong kong"], "tw": ["taiwan"],
    "va": ["vatican", "vatican city", "holy see"], "ps": ["palestine"],
    "cd": ["democratic republic of the congo", "dr congo"],
    "cg": ["republic of the congo"], "mk": ["north macedonia", "macedonia"],
    "sz": ["eswatini", "swaziland"], "cv": ["cape verde", "cabo verde"],
    "bn": ["brunei"], "ae": ["united arab emirates", "uae"],
    "ci": ["ivory coast", "cote d ivoire"], "tz": ["tanzania"],
    "bo": ["bolivia"], "ve": ["venezuela"], "md": ["moldova"],
    # "Inner Mongolia" es una provincia china, no el pais Mongolia. La
    # coincidencia mas larga la asigna a China en lugar de a Mongolia.
    "cn": ["china", "inner mongolia"],
}


def construir_paises():
    """Devuelve dict nombre_normalizado -> codigo ISO (minusculas)."""
    import pycountry
    out = {}
    for cc, nombres in _ALIAS_PAIS.items():           # los alias tienen prioridad
        for n in nombres:
            out[normalizar(n)] = cc
    for c in pycountry.countries:
        cc = c.alpha_2.lower()
        for atributo in ("name", "common_name"):
            v = getattr(c, atributo, None)
            if not v:
                continue
            v = re.sub(r",.*", "", v)                  # "Korea, Republic of" -> "Korea"
            n = normalizar(v)
            if len(n) >= 4 and n not in _PAISES_EXCLUIDOS:
                out.setdefault(n, cc)
    return out


# Gentilicios de los nueve paises focales. Solo se usan en el analisis de
# sensibilidad: algunos son ambiguos ("Indian" tambien designa pueblos
# originarios de America) y por eso no forman parte de la definicion principal.
GENTILICIOS = {
    "chinese": "cn", "italian": "it", "greek": "gr", "egyptian": "eg",
    "british": "gb", "french": "fr", "japanese": "jp", "indian": "in",
    "peruvian": "pe",
}

# ── Regiones ─────────────────────────────────────────────────────────────────
# Cada codigo ISO pertenece a una sola region. Las asignaciones discutibles
# estan documentadas: Egipto, Turquia y el Caucaso van en Oriente Medio y Norte
# de Africa; Sudan y Sudan del Sur en Africa subsahariana; Chipre en Europa.

REGIONES_ISO = {
    "africa_subsahariana": "ao bj bw bf bi cm cv cf td km cg cd ci dj gq er sz et ga gm gh gn gw ke ls lr mg mw ml mu mz na ne ng rw st sn sc sl so za ss sd tz tg ug zm zw",
    "oriente_medio_n_africa": "dz eg ly ma tn mr eh ae bh ir iq il jo kw lb om ps qa sa sy tr ye ge am az",
    "asia_central": "kz kg tj tm uz",
    "asia_sur": "af bd bt in lk mv np pk",
    "sudeste_asiatico": "bn kh id la my mm ph sg th tl vn",
    "asia_oriental": "cn hk jp kp kr mn mo tw",
    "europa": "al ad at by ba be bg hr cz dk ee fi fr de gr hu is ie it xk lv li lt lu mt md mc me nl mk no pl pt ro ru sm rs sk si es se ch ua gb va gi cy",
    "america_latina_caribe": "ag ar bs bb bz bo br cl co cr cu dm do ec sv gd gt gy ht hn jm mx ni pa py pe kn lc vc sr tt uy ve pr",
    "norteamerica_oceania": "us ca au nz fj pg ws to vu sb ki fm mh nr pw tv gu",
}

# Palabras que nombran una region sin nombrar un pais. "ruta_seda" no es una
# region sino un marcador de discurso (Ruta de la Seda / Franja y la Ruta).
REGIONES_PALABRAS = {
    "ruta_seda": ["silk road", "silk roads", "silk route", "silk routes",
                  "maritime silk road", "new silk road", "belt and road",
                  "belt road", "one belt one road"],
    "africa_subsahariana": ["africa", "african", "sub saharan africa", "west africa",
                            "east africa", "southern africa", "central africa",
                            "horn of africa", "sahel"],
    "oriente_medio_n_africa": ["middle east", "near east", "north africa", "levant",
                               "maghreb", "arabian peninsula", "mesopotamia"],
    "asia_central": ["central asia"],
    "asia_sur": ["south asia", "indian subcontinent"],
    "sudeste_asiatico": ["southeast asia", "south east asia", "indochina"],
    "asia_oriental": ["east asia", "eastern asia"],
    "europa": ["europe"],
    "america_latina_caribe": ["latin america", "caribbean", "andean", "mesoamerica",
                              "central america", "south america"],
    "norteamerica_oceania": ["north america", "oceania", "australasia", "pacific islands"],
}

ETIQUETAS_REGION = {
    "ruta_seda": "Ruta de la Seda / Franja y la Ruta",
    "africa_subsahariana": "África subsahariana",
    "oriente_medio_n_africa": "Oriente Medio y Norte de África",
    "asia_central": "Asia Central",
    "asia_sur": "Asia meridional",
    "sudeste_asiatico": "Sudeste asiático",
    "asia_oriental": "Asia oriental",
    "europa": "Europa",
    "america_latina_caribe": "América Latina y Caribe",
    "norteamerica_oceania": "Norteamérica y Oceanía",
}

REGION_DE_ISO = {iso: reg for reg, codigos in REGIONES_ISO.items() for iso in codigos.split()}


def construir_regiones():
    """Gazetteer nombre -> region, solo para las palabras de region."""
    out = {}
    for reg, palabras in REGIONES_PALABRAS.items():
        for p in palabras:
            out[normalizar(p)] = reg
    return out


# ── Sitios de la Lista del Patrimonio Mundial ────────────────────────────────

# Palabras genericas que encabezan los nombres oficiales de UNESCO y que los
# trabajos academicos casi nunca usan. Se recortan para generar la forma corta.
_PREFIJOS = re.compile(
    r"^(the |los |las |el |la )?"
    r"(historic(al)? (centre|center|sanctuary|town|city|monuments?|village|area)s?|"
    r"archaeological (site|area|zone|ensemble|remains|park|landscape)s?|"
    r"cultural (landscape|site|heritage)s?|"
    r"natural (park|reserve|monument)s?|"
    r"national park|old (town|city|quarter)|"
    r"ruins|city|town|monastery|cathedral|church|fortress|palace|temple|"
    r"centro historico|santuario historico|zona arqueologica|sitio arqueologico|"
    r"paisaje cultural|parque nacional|ciudad|centre historique|"
    r"ensemble|complex|group of monuments)"
    r"\s+(of|de|del|des|du|d|and)?\s*", re.I)

# Descriptores que aparecen al final: "Chan Chan Archaeological Zone".
_SUFIJOS = re.compile(
    r"\s+(archaeological (zone|site|area|park|ensemble)s?|national park|"
    r"historic(al)? (centre|center|site|town|city)|cultural landscape|"
    r"nature reserve|biosphere reserve|and its (lagoon|environs|surroundings))\s*$", re.I)

# Formas cortas demasiado ambiguas para usarse como nombre de sitio. Se
# normalizan al comparar. La lista crece por revision manual de las
# detecciones (resultados/t6b_detecciones.csv y t7e_muestra_validacion.csv).
_PELIGROSAS = {
    # adjetivos y sustantivos genericos que sobreviven al recorte
    "historic", "historical", "ancient", "modern", "cultural", "natural",
    "national", "monuments", "monument", "ensemble", "complex", "sanctuary",
    "architectural", "archaeological", "primeval", "antiguos", "historico",
    "historique", "naturel", "cultural landscape", "world heritage",
    "bath", "wall", "centre", "center", "city", "old town", "park", "ruins",
    "temple", "palace", "island", "islands", "lagoon", "valley", "caves",
    "gardens", "cathedral", "church", "monastery", "fortress", "castle",
    "bridge", "canal", "delta", "coast", "forest", "lake", "river",
    "mountain", "desert", "reef",
    # observados como ruido en las pruebas de la v1.0
    "coastal", "villages", "village", "houses", "house", "walls",
    "residential", "surroundings", "settlement", "settlements", "landscapes",
    "landscape", "ancient city", "natural environment", "multi layered",
    "inaccessible", "funerary", "biodiversity", "ecosystem", "ecosystems",
    "reflection", "related", "central", "convent", "studio", "sciences",
    "university", "lines", "forts", "steel", "cultura", "culture",
    "historica", "museo", "terres", "genes", "prehistoric sites",
    "residential ensemble", "lakes", "basilica", "universidad", "volcanoes",
    "grottoes", "mountains", "old city",
    # agregados en la v1.1 tras revisar las detecciones
    "ayuntamiento", "human rights", "town hall", "iglesia", "catedral",
    "abbey", "abbeys", "monasterio", "castillo", "puente", "ciudad vieja", "palacio", "templo",
    "jardines", "murallas", "casco antiguo", "heritage", "sites", "site",
}

_PREPOSICIONES_INICIALES = re.compile(r"^\s*(the|los|las|el|la|its|su|of|de)\s+", re.I)


def variantes_nombre(bruto):
    """Genera formas buscables de un nombre de sitio de la Lista de UNESCO.

    Los nombres oficiales son largos y compuestos ("Archaeological Areas of
    Pompei, Herculaneum and Torre Annunziata") mientras que los articulos usan
    la forma breve ("Pompei"). La separacion se hace sobre el texto crudo,
    porque la normalizacion elimina la puntuacion que marca las partes.
    """
    if not isinstance(bruto, str) or not bruto.strip():
        return []
    completo = normalizar(bruto)
    if len(completo) < 6:
        return []
    out = [completo] if len(completo) >= 8 else []

    cuerpo = _PREFIJOS.sub("", bruto.strip())
    cuerpo = _SUFIJOS.sub("", cuerpo).strip()
    partes = re.split(r"[,;]| \band\b | \by\b | \bet\b | \bund\b ", cuerpo, flags=re.I)

    for parte in partes:
        parte = _PREPOSICIONES_INICIALES.sub("", parte.strip())
        if len(parte.split()) > 5:      # descarta subordinadas largas
            continue
        n = normalizar(parte)
        if 5 <= len(n) < len(completo) and n not in _PELIGROSAS and n not in out:
            out.append(n)
    return out


def cargar_unesco(ruta, paises=None, verbose=True):
    """Lee la Lista del Patrimonio Mundial y devuelve (dict variante -> {iso}, n_sitios).

    Solo se usan los nombres en ingles y espanol: el corpus de OpenAlex esta
    indexado en ingles, de modo que los nombres en otros idiomas no aportan
    recuperacion y si colisiones (el frances "Genes", Genova, coincide con la
    palabra inglesa "genes").

    Dos filtros contra el ruido:
      - se descartan las palabras sueltas asociadas a mas de 3 paises;
      - se descartan las variantes que son el nombre de un pais. Aparecen al
        separar nombres transfronterizos ("... in Poland and Ukraine" produce
        "ukraine"), y una mencion de pais no es una mencion de sitio.
    """
    ext = os.path.splitext(ruta)[1].lower()
    u = pd.read_excel(ruta) if ext in (".xls", ".xlsx") else pd.read_csv(
        ruta, encoding="utf-8-sig", low_memory=False)

    col_iso = next((c for c in u.columns if c.lower() in ("iso_code", "iso", "country_code")), None)
    cols_nombre = [c for c in u.columns if c.lower() in ("name_en", "name_es")]
    if not col_iso or not cols_nombre:
        raise ValueError(f"No reconoci las columnas. Disponibles: {list(u.columns)[:15]}")

    sitios = {}
    for _, r in u.iterrows():
        isos = {x.strip().lower() for x in str(r[col_iso]).split(",") if x.strip()}
        if not isos:
            continue
        for c in cols_nombre:
            for v in variantes_nombre(r[c]):
                sitios.setdefault(v, set()).update(isos)

    genericas = [v for v, isos in sitios.items() if len(isos) > 3 and len(v.split()) == 1]
    paises = paises if paises is not None else construir_paises()
    como_pais = [v for v in sitios if v in paises]
    for v in set(genericas) | set(como_pais):
        del sitios[v]
    if verbose:
        print(f"  Lista de UNESCO: {len(u)} sitios, {len(sitios)} variantes de nombre "
              f"(descartadas {len(genericas)} genericas y {len(como_pais)} que son nombres de pais)")
    return sitios, len(u)


# Exonimos y grafias frecuentes que el nomenclator no trae bajo ese nombre.
_EXONIMOS_CIUDAD = {"peking": "cn", "canton": "cn", "nanking": "cn", "xian": "cn",
                    "marrakesh": "ma", "marrakech": "ma", "constantinople": "tr",
                    "byzantium": "tr", "angkor": "kh", "cuzco": "pe", "cusco": "pe",
                    "machu picchu": "pe", "teotihuacan": "mx", "petra": "jo"}


def construir_ciudades(excluir=(), pob_min=50000):
    """Gazetteer de ciudades: nombre normalizado -> codigo ISO, desde el paquete
    geonamescache (GeoNames, ciudades de mas de `pob_min` habitantes).

    Es una capa para el analisis de sensibilidad: recupera los referentes que
    nombran una ciudad sin nombrar el pais ("Dalian", "Turin"). Reglas contra
    la ambiguedad, tras revisar los falsos positivos de una primera version
    que usaba tambien grafias alternativas (generaban "from", "time", "most"):
      - solo el nombre principal de cada ciudad, mas unos pocos exonimos;
      - un nombre con varias ciudades en paises distintos se asigna al pais de
        la mas poblada, salvo que esa tenga menos de 200.000 habitantes: ahi
        la ambiguedad es real ("Orange", "Venice") y se descarta;
      - se excluyen nombres que son paises o regiones (parametro `excluir`),
        y los de la lista _CIUDADES_RUIDOSAS (nombres de persona o palabras
        comunes que tambien son ciudades: "Raman", "Victoria", "Union").
    Las palabras comunes que son ciudades ("Reading", "Nice", "Bath") se filtran
    despues con la regla de mayuscula de agenda.py."""
    import geonamescache
    cand = {}
    for v in geonamescache.GeonamesCache().get_cities().values():
        if v["population"] < pob_min:
            continue
        n = normalizar(v["name"])
        if len(n) >= 4 and n not in excluir and n not in _CIUDADES_RUIDOSAS:
            cand.setdefault(n, []).append((v["population"], v["countrycode"].lower()))
    out = {}
    for n, lst in cand.items():
        lst.sort(reverse=True)
        if len({cc for _, cc in lst}) > 1 and lst[0][0] < 200000:
            continue
        out[n] = lst[0][1]
    for n, cc in _EXONIMOS_CIUDAD.items():
        if n not in excluir:
            out[n] = cc
    return out


# Nombres de ciudad que en un corpus cientifico casi siempre son otra cosa.
# Lista construida por revision manual de las variantes mas frecuentes.
_CIUDADES_RUIDOSAS = {
    "raman", "roman", "union", "republic", "march", "delta", "george", "victoria", "david",
    "martin", "mark", "paul", "peter", "john", "james", "mary", "elizabeth", "charles",
    "sample", "model", "sound", "energy", "center", "central", "general", "national",
    "spring", "river", "bridge", "garden", "mission", "liberty", "freedom", "success",
    "industry", "progress", "reform", "culture", "science", "church", "castle", "tower",
    "plain", "rock", "stone", "wood", "forest", "valley", "island", "lake", "mount",
}


def tokenizar(titulo, resumen):
    """Titulo y resumen normalizados, como lista de palabras."""
    return normalizar(f"{titulo} {resumen}").split()


# ─────────────────────────────────────────────────────────────────────────────
# ESTILO DE FIGURAS (compartido por analisis.py y agenda.py)
#   Estilo de "enfasis": China en el color de acento y el resto en gris neutro,
#   porque la historia es China frente al conjunto y no nueve categorias.
# ─────────────────────────────────────────────────────────────────────────────

ACENTO = "#2a78d6"
GRIS = "#a3a29c"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
SUPERFICIE = "#fcfcfb"
REJILLA = "#e4e3df"
SECUENCIAL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
              "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]


def importar_matplotlib():
    """Devuelve pyplot con el estilo base aplicado, o None si no esta instalado."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib no instalado: se omiten las figuras)")
        return None
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SUPERFICIE})
    return plt


def estilo_ejes(ax, rejilla="x"):
    ax.set_facecolor(SUPERFICIE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(REJILLA)
    ax.tick_params(colors=TINTA_2, labelsize=9, length=0)
    ax.grid(visible=False)
    if rejilla:
        ax.grid(axis=rejilla, color=REJILLA, linewidth=.8)
    ax.set_axisbelow(True)


def etiquetas_finales(ax, puntos, separacion):
    """Etiquetas directas al final de cada linea sin que se superpongan.
    `puntos`: lista de (y, x, nombre, es_china)."""
    puntos = sorted(puntos)
    y_prev = -1e9
    for y, x, nombre, china in puntos:
        y_lab = max(y, y_prev + separacion)
        ax.text(x + .15, y_lab, nombre, fontsize=9, va="center",
                color=ACENTO if china else TINTA_2, fontweight="bold" if china else "normal")
        y_prev = y_lab
