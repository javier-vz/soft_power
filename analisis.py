#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analisis comparativo de los corpus OpenAlex sobre IA y patrimonio cultural.

Lee todos los archivos datos/openalex_A_*.csv y datos/openalex_B_*.csv que
existan y produce tablas y figuras. Funciona con un solo pais, pero el
argumento del estudio solo se sostiene con corpus espejo: las tablas se
llenan solas a medida que se agregan paises.

Uso
---
    pip install pandas matplotlib
    python analisis.py
    python analisis.py --unesco whc_sites.csv    # activa la autorreferencia

Salida
------
    resultados/t1_panorama.csv          volumen, tasa de IA, colaboracion, citas
    resultados/t2_evolucion.csv         serie anual de la tasa de IA por pais
    resultados/t3_tecnicas.csv          que tecnicas de IA usa cada pais
    resultados/t4_venues.csv            donde publica cada pais
    resultados/t5_instituciones.csv     instituciones mas productivas
    resultados/t6_autorreferencia.csv   (requiere --unesco)
    resultados/f1_evolucion.png         curvas de tasa de IA por pais
    resultados/f2_colaboracion.png      colaboracion internacional por pais
    resultados/informe.txt              resumen legible de todo lo anterior

Nota sobre la tasa de IA
------------------------
Se define como corpus B / corpus A: la proporcion de la produccion sobre
patrimonio de un pais que ademas involucra inteligencia artificial. Es la
metrica central del estudio porque es directamente comparable entre paises
y no depende del tamano del sistema cientifico de cada uno.
"""

import argparse
import glob
import os
import re
import sys
import unicodedata
from collections import Counter

import pandas as pd

DIR_DATOS = "datos"
DIR_SALIDA = "resultados"

NOMBRES = {
    "cn": "China", "it": "Italia", "gr": "Grecia", "eg": "Egipto",
    "gb": "Reino Unido", "us": "Estados Unidos", "fr": "Francia",
    "jp": "Japon", "in": "India", "pe": "Peru", "es": "Espana",
}

TERMINOS_IA = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "computer vision", "knowledge graph",
    "large language model", "natural language processing",
    "generative model", "convolutional", "transformer model",
]


# ─────────────────────────────────────────────────────────────────────────────
# CARGA
# ─────────────────────────────────────────────────────────────────────────────

def cargar():
    """Devuelve dos diccionarios pais -> DataFrame, para corpus A y B."""
    A, B = {}, {}
    for ruta in sorted(glob.glob(os.path.join(DIR_DATOS, "openalex_*_*.csv"))):
        nombre = os.path.basename(ruta)
        m = re.match(r"openalex_([AB])_([a-z]{2})_", nombre)
        if not m:
            continue
        nivel, pais = m.groups()
        df = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)
        df["pais"] = pais
        (A if nivel == "A" else B)[pais] = df
    if not A:
        sys.exit(f"No se encontraron archivos en {DIR_DATOS}/. "
                 f"Corre primero descarga_openalex.py")
    return A, B


def normalizar(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


_CACHE_PATRON = {}


def aparece(variante, texto):
    """Comprueba si la variante esta en el texto como palabra completa.

    La comparacion por subcadena produce falsos positivos graves: "berat"
    (ciudad albanesa inscrita por UNESCO) coincide dentro de "deliberate" y
    "liberated". Se hace primero una prueba rapida de subcadena y solo cuando
    esta da positivo se verifica el limite de palabra, que es mas costoso.
    """
    if variante not in texto:
        return False
    pat = _CACHE_PATRON.get(variante)
    if pat is None:
        pat = re.compile(r"(?<!\w)" + re.escape(variante) + r"(?!\w)")
        _CACHE_PATRON[variante] = pat
    return bool(pat.search(texto))


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
# TABLAS
# ─────────────────────────────────────────────────────────────────────────────

def t1_panorama(A, B):
    """Volumen, tasa de IA, colaboracion y citas por pais."""
    filas = []
    for pais in sorted(A):
        a, b = A[pais], B.get(pais, A[pais].iloc[0:0])
        n_a, n_b = len(a), len(b)
        filas.append({
            "pais": NOMBRES.get(pais, pais),
            "codigo": pais,
            "corpus_A_patrimonio": n_a,
            "corpus_B_IA_patrimonio": n_b,
            "tasa_IA_pct": round(100 * n_b / n_a, 2) if n_a else 0,
            "colab_intl_pct": round(100 * b.es_colaboracion_intl.mean(), 1) if n_b else 0,
            "citas_medianas": int(b.cited_by_count.median()) if n_b else 0,
            "citas_medias": round(b.cited_by_count.mean(), 1) if n_b else 0,
            "acceso_abierto_pct": round(100 * b.is_oa.astype(str).str.lower().eq("true").mean(), 1) if n_b else 0,
            "articulos_pct": round(100 * b.type.eq("article").mean(), 1) if n_b else 0,
            "congresos_pct": round(100 * b.type.eq("conference-paper").mean(), 1) if n_b else 0,
        })
    return pd.DataFrame(filas).sort_values("tasa_IA_pct", ascending=False)


def t2_evolucion(A, B):
    """Serie anual: cuantos trabajos y que proporcion involucra IA."""
    filas = []
    for pais in sorted(A):
        a, b = A[pais], B.get(pais, A[pais].iloc[0:0])
        ca = a.publication_year.value_counts()
        cb = b.publication_year.value_counts() if len(b) else pd.Series(dtype=int)
        for anio in sorted(x for x in ca.index if pd.notna(x)):
            na = int(ca[anio])
            nb = int(cb.get(anio, 0))
            filas.append({
                "pais": NOMBRES.get(pais, pais), "anio": int(anio),
                "n_A": na, "n_B": nb,
                "tasa_IA_pct": round(100 * nb / na, 2) if na else 0,
            })
    return pd.DataFrame(filas)


def t3_tecnicas(B):
    """Que tecnicas de IA predominan en cada pais (perfil tecnologico)."""
    filas = []
    for pais, b in sorted(B.items()):
        if not len(b):
            continue
        c = separar(b.terminos_ia_hallados)
        fila = {"pais": NOMBRES.get(pais, pais), "n": len(b)}
        for t in TERMINOS_IA:
            fila[t] = round(100 * c.get(t, 0) / len(b), 1)
        filas.append(fila)
    return pd.DataFrame(filas)


def t4_venues(B, top=15):
    """Donde circula la investigacion de cada pais."""
    filas = []
    for pais, b in sorted(B.items()):
        if not len(b):
            continue
        for fuente, n in separar(b.source).most_common(top):
            sub = b[b.source == fuente]
            filas.append({
                "pais": NOMBRES.get(pais, pais), "fuente": fuente, "n": n,
                "pct_del_corpus": round(100 * n / len(b), 1),
                "citas_medianas": int(sub.cited_by_count.median()) if len(sub) else 0,
                "tipo": sub.source_type.mode().iloc[0] if len(sub) and sub.source_type.notna().any() else "",
            })
    return pd.DataFrame(filas)


def t5_instituciones(B, top=20):
    """Instituciones mas productivas, con su tasa de colaboracion internacional."""
    filas = []
    for pais, b in sorted(B.items()):
        if not len(b):
            continue
        for inst, n in separar(b.institutions).most_common(top):
            sub = b[b.institutions.fillna("").str.contains(re.escape(inst))]
            filas.append({
                "pais": NOMBRES.get(pais, pais), "institucion": inst, "n": n,
                "pct_del_corpus": round(100 * n / len(b), 1),
                "colab_intl_pct": round(100 * sub.es_colaboracion_intl.mean(), 1) if len(sub) else 0,
                "citas_medianas": int(sub.cited_by_count.median()) if len(sub) else 0,
            })
    return pd.DataFrame(filas)


def cargar_unesco(ruta):
    """Lee la Lista del Patrimonio Mundial en xls, xlsx o csv.

    El archivo oficial de whc.unesco.org trae los nombres de cada sitio en
    seis idiomas y el codigo ISO del pais, lo que permite un emparejamiento
    mucho mas fiable que el cotejo por nombre de pais.
    """
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".xls", ".xlsx"):
        u = pd.read_excel(ruta)
    else:
        u = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)

    col_iso = next((c for c in u.columns if c.lower() in ("iso_code", "iso", "country_code")), None)
    # Solo ingles y espanol: el corpus de OpenAlex esta indexado en ingles, de
    # modo que los nombres en frances, ruso, arabe o chino no aportan
    # recuperacion y si producen colisiones graves. El caso mas claro es
    # "Genes", nombre frances de Genova, que coincide con la palabra inglesa
    # "genes" en un corpus cientifico.
    cols_nombre = [c for c in u.columns if c.lower() in ("name_en", "name_es")] \
                  or [c for c in u.columns if c.lower().startswith("name_")] \
                  or [c for c in u.columns if re.search(r"name|site|nom", c, re.I)]
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
    # Una variante corta que apunta a muchos paises suele ser una palabra
    # generica que sobrevivio al recorte ("historic", "ensemble"). Se descarta.
    # El limite se aplica solo a palabras sueltas: un nombre de dos o mas
    # palabras presente en varios paises suele ser un sitio transfronterizo
    # legitimo, como el Qhapaq Nan o el Arco Geodesico de Struve. El filtro
    # por frecuencia sobre el corpus se encarga del resto.
    genericas = [v for v, isos in sitios.items()
                 if len(isos) > 3 and len(v.split()) == 1]
    for v in genericas:
        del sitios[v]
    if genericas:
        print(f"  descartadas {len(genericas)} variantes genericas: "
              f"{', '.join(sorted(genericas)[:6])}{'...' if len(genericas) > 6 else ''}")

    lista = sorted(sitios.items(), key=lambda x: -len(x[0]))
    return lista, len(u)


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

# Terminos demasiado ambiguos para usarse como forma corta.
_PELIGROSAS = {
               # adjetivos y sustantivos genericos que sobreviven al recorte
               "historic", "historical", "ancient", "modern", "cultural",
               "natural", "national", "monuments", "monument", "ensemble",
               "complex", "sanctuary", "architectural", "archaeological",
               "primeval", "antiguos", "historico", "historique", "naturel",
               "cultural landscape", "world heritage",
               "bath", "wall", "centre", "center", "city", "old town", "park",
               "ruins", "temple", "palace", "island", "islands", "lagoon",
               "valley", "caves", "gardens", "cathedral", "church", "monastery",
               "fortress", "castle", "bridge", "canal", "delta", "coast",
               "forest", "lake", "river", "mountain", "desert", "reef",
               # sustantivos y adjetivos observados como ruido en las pruebas
               "coastal", "villages", "village", "houses", "house", "walls",
               "residential", "surroundings", "settlement", "settlements",
               "landscapes", "landscape", "ancient city", "natural environment",
               "multi-layered", "inaccessible", "funerary", "biodiversity",
               "ecosystem", "ecosystems", "reflection", "related", "central",
               "convent", "studio", "sciences", "university", "lines", "forts",
               "steel", "cultura", "culture", "historica", "museo", "terres",
               "genes", "prehistoric sites", "residential ensemble",
               "lakes", "basilica", "universidad", "volcanoes", "grottoes",
               "caves", "islands", "mountains", "old city"}


def variantes_nombre(bruto):
    """Genera formas buscables de un nombre de sitio de la Lista de UNESCO.

    Los nombres oficiales son largos y compuestos ("Archaeological Areas of
    Pompei, Herculaneum and Torre Annunziata") mientras que los articulos usan
    la forma breve ("Pompei"). Sin esta reduccion la deteccion queda muy por
    debajo de lo real. La separacion se hace sobre el texto crudo, porque la
    normalizacion elimina la puntuacion que marca las partes.
    """
    if not isinstance(bruto, str) or not bruto.strip():
        return []

    completo = normalizar(bruto)
    if len(completo) < 6:
        return []
    out = [completo] if len(completo) >= 8 else []

    # 1. Quitar el descriptor generico, al inicio o al final del nombre.
    cuerpo = _PREFIJOS.sub("", bruto.strip())
    cuerpo = _SUFIJOS.sub("", cuerpo).strip()

    # 2. Separar en partes por coma, punto y coma o conector.
    partes = re.split(r"[,;]| \band\b | \by\b | \bet\b | \bund\b ", cuerpo, flags=re.I)

    for parte in partes:
        parte = re.sub(r"^\s*(the|los|las|el|la|its|su|of|de)\s+", "", parte.strip(), flags=re.I)
        # descarta subordinadas: "the properties of the holy see in that city..."
        if len(parte.split()) > 5:
            continue
        n = normalizar(parte)
        if 5 <= len(n) < len(completo) and n not in _PELIGROSAS and n not in out:
            out.append(n)
    return out


# Un nombre de sitio genuino no puede aparecer en una fraccion grande del
# corpus. Las variantes que superan este umbral se descartan como genericas.
UMBRAL_GENERICA = 0.005    # 0,5 % de los trabajos analizados


def t6_autorreferencia(B, ruta_unesco):
    """Tasa de autorreferencia patrimonial: cuanto estudia cada pais lo propio.

    Procede en dos pasadas. La primera registra todas las coincidencias entre
    los textos y las variantes de nombre de la Lista del Patrimonio Mundial.
    La segunda descarta las variantes que aparecen en demasiados trabajos,
    porque un toponimo real no puede estar en una fraccion grande del corpus,
    y recien entonces clasifica cada trabajo como propio o ajeno.

    Este filtro por frecuencia es necesario: los nombres oficiales son largos
    y compuestos, y al reducirlos a formas breves aparecen fragmentos genericos
    ("cultura", "university") que de otro modo dominarian la deteccion.
    """
    sitios, n_sitios = cargar_unesco(ruta_unesco)
    print(f"  Lista de UNESCO: {n_sitios} sitios, {len(sitios)} variantes de nombre")

    # ── Pasada 1: registrar coincidencias ───────────────────────────────────
    coincidencias = {}          # (pais, indice de fila) -> lista de variantes
    frecuencia = Counter()      # variante -> numero de trabajos en que aparece
    n_total = 0
    for pais, b in sorted(B.items()):
        for idx, r in b.iterrows():
            n_total += 1
            texto = normalizar(f"{r.title} {r.abstract}")
            hallados = [(v, isos) for v, isos in sitios if aparece(v, texto)]
            if hallados:
                coincidencias[(pais, idx)] = hallados
                for v, _ in hallados:
                    frecuencia[v] += 1

    # ── Pasada 2: descartar variantes demasiado frecuentes ──────────────────
    tope = max(3, int(UMBRAL_GENERICA * n_total))
    genericas = {v for v, n in frecuencia.items() if n > tope}
    if genericas:
        muestra = ", ".join(v for v, _ in
                            sorted(((v, frecuencia[v]) for v in genericas),
                                   key=lambda x: -x[1])[:8])
        print(f"  descartadas {len(genericas)} variantes por frecuencia "
              f"(mas de {tope} trabajos): {muestra}")

    filas, detalle = [], []
    for pais, b in sorted(B.items()):
        if not len(b):
            continue
        propios = ajenos = 0
        cuenta = Counter()
        for idx, r in b.iterrows():
            hallados = [(v, isos) for v, isos in coincidencias.get((pais, idx), [])
                        if v not in genericas]
            if not hallados:
                continue
            # la coincidencia mas larga es la mas especifica
            hallados.sort(key=lambda x: -len(x[0]))
            propio = any(pais in isos for _, isos in hallados)
            if propio:
                propios += 1
                cuenta[next(v for v, isos in hallados if pais in isos)] += 1
            else:
                ajenos += 1
            detalle.append({
                "pais_autor": pais,
                "titulo": str(r.title)[:180],
                "sitio_detectado": hallados[0][0],
                "paises_del_sitio": ";".join(sorted(hallados[0][1])),
                "clasificacion": "propio" if propio else "ajeno",
            })
        total = propios + ajenos
        filas.append({
            "pais": NOMBRES.get(pais, pais),
            "codigo": pais,
            "trabajos_con_sitio": total,
            "sitios_propios": propios,
            "sitios_ajenos": ajenos,
            "autorreferencia_pct": round(100 * propios / total, 1) if total else None,
            "cobertura_pct": round(100 * total / len(b), 1),
            "sitios_propios_mas_estudiados": "; ".join(f"{s} ({n})" for s, n in cuenta.most_common(5)),
        })

    if detalle:
        pd.DataFrame(detalle).to_csv(f"{DIR_SALIDA}/t6b_detecciones.csv",
                                     index=False, encoding="utf-8-sig")
        print(f"  detalle de cada deteccion -> {DIR_SALIDA}/t6b_detecciones.csv")
        print("  revisar a mano una muestra: el emparejamiento es heuristico")
    return pd.DataFrame(filas).sort_values("autorreferencia_pct", ascending=False)


# ─────────────────────────────────────────────────────────────────────────────
# FIGURAS
# ─────────────────────────────────────────────────────────────────────────────

def figuras(t2, t1):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib no instalado: se omiten las figuras)")
        return

    # f1: evolucion de la tasa de IA
    fig, ax = plt.subplots(figsize=(8, 5))
    for pais, sub in t2.groupby("pais"):
        sub = sub[(sub.anio >= 2015) & (sub.n_A >= 20)].sort_values("anio")
        if len(sub) >= 3:
            ax.plot(sub.anio, sub.tasa_IA_pct, marker="o", markersize=4, label=pais)
    ax.set_xlabel("Año")
    ax.set_ylabel("Trabajos de patrimonio que involucran IA (%)")
    ax.set_title("Penetración de la IA en la investigación patrimonial")
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(DIR_SALIDA, "f1_evolucion.png"), dpi=200)
    plt.close(fig)

    # f2: colaboracion internacional
    if len(t1) >= 2:
        fig, ax = plt.subplots(figsize=(7, 4))
        d = t1.sort_values("colab_intl_pct")
        ax.barh(d.pais, d.colab_intl_pct)
        ax.set_xlabel("Trabajos con coautoría internacional (%)")
        ax.set_title("Estructura de colaboración en IA + patrimonio")
        ax.grid(axis="x", alpha=.3)
        fig.tight_layout()
        fig.savefig(os.path.join(DIR_SALIDA, "f2_colaboracion.png"), dpi=200)
        plt.close(fig)
    print("  figuras guardadas")


# ─────────────────────────────────────────────────────────────────────────────

def informe(t1, t2, t3, t6):
    L = []
    L.append("INFORME DE ANALISIS - IA y patrimonio cultural")
    L.append("=" * 62)
    L.append("")
    L.append("PANORAMA POR PAIS")
    L.append(t1.to_string(index=False))
    L.append("")

    if len(t1) == 1:
        L.append("ADVERTENCIA METODOLOGICA")
        L.append("Solo hay un pais descargado. Ninguna afirmacion comparativa es")
        L.append("posible todavia: sin corpus espejo, cualquier cifra sobre este")
        L.append("pais es descriptiva y no permite decir si es o no distintiva.")
        L.append("")

    L.append("EVOLUCION DE LA TASA DE IA (ultimos anios)")
    piv = t2[t2.anio >= 2019].pivot_table(index="anio", columns="pais",
                                          values="tasa_IA_pct", aggfunc="first")
    L.append(piv.round(1).to_string())
    L.append("")

    if len(t3):
        L.append("PERFIL TECNOLOGICO (% del corpus B que menciona cada tecnica)")
        cols = ["pais", "n"] + [c for c in TERMINOS_IA if c in t3.columns]
        L.append(t3[cols].to_string(index=False))
        L.append("")

    if len(t6):
        L.append("AUTORREFERENCIA PATRIMONIAL")
        L.append("De los trabajos que mencionan algun sitio de la Lista del Patrimonio")
        L.append("Mundial, que proporcion estudia patrimonio del propio pais. La columna")
        L.append("de cobertura indica cuantos trabajos del corpus fue posible clasificar.")
        L.append(t6.to_string(index=False))
        L.append("")

    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unesco", help="CSV de la Lista del Patrimonio Mundial")
    args = ap.parse_args()

    os.makedirs(DIR_SALIDA, exist_ok=True)
    A, B = cargar()
    print(f"Cargados {len(A)} paises: {', '.join(NOMBRES.get(p, p) for p in sorted(A))}\n")

    t1 = t1_panorama(A, B);            t1.to_csv(f"{DIR_SALIDA}/t1_panorama.csv", index=False, encoding="utf-8-sig")
    t2 = t2_evolucion(A, B);           t2.to_csv(f"{DIR_SALIDA}/t2_evolucion.csv", index=False, encoding="utf-8-sig")
    t3 = t3_tecnicas(B);               t3.to_csv(f"{DIR_SALIDA}/t3_tecnicas.csv", index=False, encoding="utf-8-sig")
    t4 = t4_venues(B);                 t4.to_csv(f"{DIR_SALIDA}/t4_venues.csv", index=False, encoding="utf-8-sig")
    t5 = t5_instituciones(B);          t5.to_csv(f"{DIR_SALIDA}/t5_instituciones.csv", index=False, encoding="utf-8-sig")

    t6 = pd.DataFrame()
    if args.unesco and os.path.exists(args.unesco):
        print("Calculando autorreferencia patrimonial (puede tardar)...")
        t6 = t6_autorreferencia(B, args.unesco)
        if len(t6):
            t6.to_csv(f"{DIR_SALIDA}/t6_autorreferencia.csv", index=False, encoding="utf-8-sig")

    figuras(t2, t1)

    texto = informe(t1, t2, t3, t6)
    with open(f"{DIR_SALIDA}/informe.txt", "w", encoding="utf-8") as fh:
        fh.write(texto)
    print("\n" + texto)
    print(f"\nTodo guardado en {DIR_SALIDA}/")


if __name__ == "__main__":
    main()
