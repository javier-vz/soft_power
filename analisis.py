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


def t6_autorreferencia(B, ruta_unesco):
    """Tasa de autorreferencia patrimonial: cuanto estudia cada pais lo propio.

    Requiere un CSV de la Lista del Patrimonio Mundial con, al menos, una
    columna de nombre de sitio y una de pais (se detectan por heuristica).
    """
    u = pd.read_csv(ruta_unesco, encoding="utf-8-sig", low_memory=False)
    col_sitio = next((c for c in u.columns if re.search(r"name|site|nom", c, re.I)), None)
    col_pais = next((c for c in u.columns if re.search(r"states|country|pais|iso", c, re.I)), None)
    if not col_sitio or not col_pais:
        print(f"  aviso: no reconoci las columnas de {ruta_unesco}; columnas: {list(u.columns)[:12]}")
        return pd.DataFrame()

    sitios = []
    for _, r in u.iterrows():
        nombre = normalizar(r[col_sitio])
        if len(nombre) >= 6:
            sitios.append((nombre, normalizar(r[col_pais])))

    filas = []
    for pais, b in sorted(B.items()):
        if not len(b):
            continue
        nombre_pais = normalizar(NOMBRES.get(pais, pais))
        propios = ajenos = 0
        for _, r in b.iterrows():
            texto = normalizar(str(r.title) + " " + str(r.abstract))
            encontrados = [(s, p) for s, p in sitios if s in texto]
            if not encontrados:
                continue
            if any(nombre_pais in p or p in nombre_pais for _, p in encontrados):
                propios += 1
            else:
                ajenos += 1
        total = propios + ajenos
        filas.append({
            "pais": NOMBRES.get(pais, pais),
            "trabajos_con_sitio_identificado": total,
            "sitios_propios": propios,
            "sitios_ajenos": ajenos,
            "autorreferencia_pct": round(100 * propios / total, 1) if total else None,
            "cobertura_pct": round(100 * total / len(b), 1),
        })
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
        L.append("Proporcion de trabajos que estudian patrimonio del propio pais,")
        L.append("entre los que mencionan algun sitio de la Lista de UNESCO.")
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
