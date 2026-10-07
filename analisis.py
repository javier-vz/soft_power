#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analisis comparativo de los corpus OpenAlex sobre IA y patrimonio cultural.

Lee los archivos datos/openalex_A_<pais>_v1.csv y produce el panorama por pais:
volumen, penetracion de la IA, evolucion, tecnicas, venues, instituciones y
colaboracion internacional. La pregunta de AGENDA (patrimonio propio frente a
ajeno) esta en agenda.py.

Uso
---
    python analisis.py                      # periodo 2015-2025
    python analisis.py --anio-max 2026      # incluye 2026 (anio parcial)

Que cambia respecto de la version 1.0 (ver CHANGELOG.md)
--------------------------------------------------------
  - Elimina duplicados por identificador (la descarga de China tenia 195).
  - Excluye 2026 por defecto: es un anio parcial y deprime las tasas recientes.
  - Todas las proporciones llevan intervalo de confianza de Wilson al 95 %.
  - El corpus B se deriva de A (n_terminos_ia >= 1), no se lee aparte.
  - Agrega t1b_sensibilidad.csv: la tasa de IA bajo definiciones alternativas.
  - La autorreferencia por sitios UNESCO (t6) se retira: la reemplaza agenda.py.

Salida (resultados/)
--------------------
    t1_panorama.csv        volumen, tasa de IA, colaboracion, citas, con IC
    t1b_sensibilidad.csv   la tasa de IA bajo siete definiciones
    t2_evolucion.csv       serie anual de la tasa de IA
    t3_tecnicas.csv        que tecnicas de IA aparecen en cada pais
    t4_venues.csv          donde publica cada pais
    t5_instituciones.csv   instituciones mas productivas
    f1_evolucion.png, f2_colaboracion.png
    informe.txt            resumen legible

La tasa de IA
-------------
Es corpus B / corpus A: la proporcion de la produccion patrimonial de un pais
que menciona IA en titulo o resumen. Es comparable entre paises porque no
depende del tamano del sistema cientifico. Pero depende de QUE hay en el
denominador (un pais con muchos informes y datasets arqueologicos tiene una
tasa menor) y de la definicion de "menciona IA"; por eso t1b la prueba bajo
siete definiciones.
"""

import argparse
import os
import re

import pandas as pd

from comun import (ACENTO, ANIO_MAX_DEFECTO, ANIO_MIN, DIR_SALIDA, GRIS, NOMBRES,
                   SUPERFICIE, TERMINOS_IA, TINTA, TINTA_2, cargar_corpus, derivar_B,
                   estilo_ejes, etiquetas_finales, fila_proporcion, importar_matplotlib,
                   pct, separar, wilson)


# ─────────────────────────────────────────────────────────────────────────────
# TABLAS
# ─────────────────────────────────────────────────────────────────────────────

def t1_panorama(A, B):
    """Volumen, tasa de IA, colaboracion y citas por pais."""
    filas = []
    for p in sorted(A):
        a, b = A[p], B[p]
        n_a, n_b = len(a), len(b)
        con_pais = b[b.n_countries >= 1]          # colaboracion solo donde hay afiliacion con pais
        f = {"pais": NOMBRES.get(p, p), "codigo": p,
             "corpus_A_patrimonio": n_a, "corpus_B_IA_patrimonio": n_b,
             **fila_proporcion("tasa_IA", n_b, n_a),
             "colab_intl_n": int(con_pais.es_colaboracion_intl.sum()),
             "colab_intl_base": len(con_pais),
             **fila_proporcion("colab_intl", int(con_pais.es_colaboracion_intl.sum()), len(con_pais)),
             "sin_afiliacion_pais_pct": pct(len(b) - len(con_pais), len(b)),
             "citas_medianas": int(b.cited_by_count.median()) if n_b else 0,
             "citas_medias": round(b.cited_by_count.mean(), 1) if n_b else 0,
             "acceso_abierto_pct": pct(b.is_oa.astype(str).str.lower().eq("true").sum(), n_b),
             "articulos_pct": pct(b.type.eq("article").sum(), n_b),
             "congresos_pct": pct(b.type.eq("conference-paper").sum(), n_b),
             "A_sin_resumen_pct": pct((~a.tiene_resumen).sum(), n_a)}
        filas.append(f)
    return pd.DataFrame(filas).sort_values("tasa_IA_pct", ascending=False)


def t1b_sensibilidad(A_pri, A_full):
    """La tasa de IA bajo definiciones alternativas.

    Cada definicion cambia el numerador, el denominador o ambos. Si el puesto de
    China cambia segun la definicion, la conclusion no es robusta.
    """
    ARTICULOS = {"article", "conference-paper"}
    defs = {
        "1. principal (2015-2025, 1 o mas terminos de IA)":
            lambda d, full: (d, d[d.n_terminos_ia >= 1]),
        "2. incluyendo 2026 (anio parcial)":
            lambda d, full: (full, full[full.n_terminos_ia >= 1]),
        "3. solo trabajos con resumen":
            lambda d, full: (d[d.tiene_resumen], d[d.tiene_resumen & (d.n_terminos_ia >= 1)]),
        "4. sin repositorios (Zenodo, Research Square, ADS...)":
            lambda d, full: (d[~d.es_repositorio], d[~d.es_repositorio & (d.n_terminos_ia >= 1)]),
        "5. solo articulos y actas de congreso":
            lambda d, full: (d[d.type.isin(ARTICULOS)], d[d.type.isin(ARTICULOS) & (d.n_terminos_ia >= 1)]),
        "6. dos o mas terminos distintos de IA":
            lambda d, full: (d, d[d.n_terminos_ia >= 2]),
        "7. solo articulos y actas, con resumen, 2 o mas terminos":
            lambda d, full: (d[d.type.isin(ARTICULOS) & d.tiene_resumen],
                             d[d.type.isin(ARTICULOS) & d.tiene_resumen & (d.n_terminos_ia >= 2)]),
    }
    filas = []
    for nombre, f in defs.items():
        for p in sorted(A_pri):
            a, b = f(A_pri[p], A_full[p])
            lo, hi = wilson(len(b), len(a))
            filas.append({"definicion": nombre, "pais": NOMBRES.get(p, p), "codigo": p,
                          "n_A": len(a), "n_B": len(b), "tasa_IA_pct": pct(len(b), len(a), 2),
                          "tasa_ic_inf": round(lo, 2), "tasa_ic_sup": round(hi, 2)})
    S = pd.DataFrame(filas)
    S["puesto"] = S.groupby("definicion").tasa_IA_pct.rank(ascending=False, method="min")
    return S


def t2_evolucion(A, B):
    """Serie anual: cuantos trabajos y que proporcion involucra IA."""
    filas = []
    for p in sorted(A):
        a, b = A[p], B[p]
        ca = a.publication_year.value_counts()
        cb = b.publication_year.value_counts()
        for anio in sorted(ca.index):
            na, nb = int(ca[anio]), int(cb.get(anio, 0))
            filas.append({"pais": NOMBRES.get(p, p), "codigo": p, "anio": int(anio),
                          "n_A": na, "n_B": nb, **fila_proporcion("tasa_IA", nb, na)})
    return pd.DataFrame(filas)


def t3_tecnicas(B):
    """Que tecnicas de IA aparecen en cada pais (perfil tecnologico)."""
    filas = []
    for p, b in sorted(B.items()):
        if not len(b):
            continue
        c = separar(b.terminos_ia_hallados)
        fila = {"pais": NOMBRES.get(p, p), "n": len(b)}
        for t in TERMINOS_IA:
            fila[t] = round(100 * c.get(t, 0) / len(b), 1)
        filas.append(fila)
    return pd.DataFrame(filas)


def t4_venues(B, top=15):
    """Donde circula la investigacion de cada pais."""
    filas = []
    for p, b in sorted(B.items()):
        if not len(b):
            continue
        for fuente, n in separar(b.source).most_common(top):
            sub = b[b.source == fuente]
            filas.append({"pais": NOMBRES.get(p, p), "fuente": fuente, "n": n,
                          "pct_del_corpus": round(100 * n / len(b), 1),
                          "citas_medianas": int(sub.cited_by_count.median()) if len(sub) else 0,
                          "tipo": sub.source_type.mode().iloc[0]
                                  if len(sub) and sub.source_type.notna().any() else ""})
    return pd.DataFrame(filas)


def t5_instituciones(B, top=20):
    """Instituciones mas productivas, con su tasa de colaboracion internacional."""
    filas = []
    for p, b in sorted(B.items()):
        if not len(b):
            continue
        for inst, n in separar(b.institutions).most_common(top):
            sub = b[b.institutions.fillna("").str.contains(re.escape(inst))]
            con_pais = sub[sub.n_countries >= 1]
            filas.append({"pais": NOMBRES.get(p, p), "institucion": inst, "n": n,
                          "pct_del_corpus": round(100 * n / len(b), 1),
                          "colab_intl_pct": pct(con_pais.es_colaboracion_intl.sum(), len(con_pais)),
                          "citas_medianas": int(sub.cited_by_count.median()) if len(sub) else 0})
    return pd.DataFrame(filas)


def solape_entre_paises(B):
    """Trabajos que aparecen en el corpus B de mas de un pais.

    El filtro de la API es por afiliacion de CUALQUIER autor, de modo que un
    articulo coescrito por China y el Reino Unido esta en ambos corpus. Los
    corpus nacionales no son independientes; se informa cuanto se solapan."""
    ids = {p: set(b.openalex_id) for p, b in B.items()}
    todos = pd.Series([i for s in ids.values() for i in s]).value_counts()
    multi = set(todos[todos > 1].index)
    filas = [{"pais": NOMBRES.get(p, p), "codigo": p, "n_B": len(s),
              "en_otro_corpus": len(s & multi),
              "pct_en_otro_corpus": pct(len(s & multi), len(s))} for p, s in sorted(ids.items())]
    return pd.DataFrame(filas)


# ─────────────────────────────────────────────────────────────────────────────
# FIGURAS
# ─────────────────────────────────────────────────────────────────────────────

def figuras(t2, t1):
    plt = importar_matplotlib()
    if plt is None:
        return

    # f1: evolucion de la tasa de IA
    fig, ax = plt.subplots(figsize=(9, 5))
    estilo_ejes(ax, rejilla="y")
    finales, anio_max = [], int(t2.anio.max())
    for codigo, sub in t2.groupby("codigo"):
        sub = sub[(sub.anio >= ANIO_MIN) & (sub.n_A >= 20)].sort_values("anio")
        if len(sub) < 3:
            continue
        china = codigo == "cn"
        ax.plot(sub.anio, sub.tasa_IA_pct, color=ACENTO if china else GRIS,
                linewidth=2.6 if china else 1.4, zorder=3 if china else 2,
                marker="o" if china else None, markersize=4)
        finales.append((float(sub.tasa_IA_pct.iloc[-1]), int(sub.anio.iloc[-1]),
                        NOMBRES.get(codigo, codigo), china))
    etiquetas_finales(ax, finales, 0.55)
    ax.set_xlim(ANIO_MIN, anio_max + 1.7)
    ax.set_xticks(range(ANIO_MIN, anio_max + 1, 2))
    ax.set_ylabel("Trabajos de patrimonio que mencionan IA (%)", fontsize=9, color=TINTA_2)
    ax.set_title("Penetración de la IA en la investigación patrimonial", loc="left",
                 fontsize=11, color=TINTA, fontweight="bold")
    fig.text(0.01, 0.01, "Solo años con al menos 20 trabajos. Definición principal: "
             "una o más menciones de IA en título o resumen.", fontsize=8, color=TINTA_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(DIR_SALIDA, "f1_evolucion.png"), dpi=200)
    plt.close(fig)

    # f2: colaboracion internacional, con IC
    d = t1.sort_values("colab_intl_pct")
    fig, ax = plt.subplots(figsize=(8, 4.6))
    estilo_ejes(ax)
    for y, (_, r) in enumerate(d.iterrows()):
        china = r.codigo == "cn"
        col = ACENTO if china else GRIS
        ax.plot([r.colab_intl_ic_inf, r.colab_intl_ic_sup], [y, y], color=col, linewidth=2,
                solid_capstyle="round", zorder=2)
        ax.scatter([r.colab_intl_pct], [y], s=60 if china else 40, color=col,
                   edgecolor=SUPERFICIE, linewidth=1.5, zorder=3)
        ax.text(min(r.colab_intl_ic_sup + 1.5, 96), y,
                f"{r.colab_intl_pct:.0f} %  (n={int(r.colab_intl_base):,})".replace(",", "."),
                va="center", fontsize=8, color=TINTA if china else TINTA_2,
                fontweight="bold" if china else "normal")
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d.pais, fontsize=9.5)
    for lab, (_, r) in zip(ax.get_yticklabels(), d.iterrows()):
        lab.set_color(TINTA if r.codigo == "cn" else TINTA_2)
        lab.set_fontweight("bold" if r.codigo == "cn" else "normal")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Trabajos de IA y patrimonio con coautoría internacional (%)", fontsize=9, color=TINTA_2)
    ax.set_title("Colaboración internacional", loc="left", fontsize=11, color=TINTA, fontweight="bold")
    fig.text(0.01, 0.01, "Punto: estimación. Línea: IC de Wilson al 95 %. "
             "Base: trabajos con país de afiliación identificado.", fontsize=8, color=TINTA_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(os.path.join(DIR_SALIDA, "f2_colaboracion.png"), dpi=200)
    plt.close(fig)
    print("  figuras guardadas: f1_evolucion, f2_colaboracion")


# ─────────────────────────────────────────────────────────────────────────────

def informe(t1, t1b, t2, t3, solape, info, anio_max):
    L = ["INFORME DE ANALISIS - IA y patrimonio cultural",
         "=" * 62, "",
         f"Periodo analizado: {ANIO_MIN}-{anio_max}. Duplicados eliminados: {int(info.duplicados.sum())}.",
         "Todos los intervalos son de Wilson al 95 %.", "",
         "PANORAMA POR PAIS",
         t1[["pais", "corpus_A_patrimonio", "corpus_B_IA_patrimonio", "tasa_IA_pct",
             "tasa_IA_ic_inf", "tasa_IA_ic_sup", "colab_intl_pct", "colab_intl_ic_inf",
             "colab_intl_ic_sup", "citas_medianas", "A_sin_resumen_pct"]].to_string(index=False), ""]

    L.append("SENSIBILIDAD DE LA TASA DE IA (puesto 1 = tasa mas alta de los nueve)")
    piv = t1b.pivot_table(index="definicion", columns="pais", values="tasa_IA_pct")
    L.append(piv.round(2).to_string())
    L.append("")
    pu = t1b.pivot_table(index="definicion", columns="pais", values="puesto")
    L.append("Puesto de cada pais bajo cada definicion:")
    L.append(pu.astype(int).to_string())
    L.append("")

    L.append("EVOLUCION DE LA TASA DE IA (%)")
    ev = t2[t2.anio >= 2019].pivot_table(index="anio", columns="pais", values="tasa_IA_pct", aggfunc="first")
    L.append(ev.round(1).to_string())
    L.append("")

    L.append("PERFIL TECNOLOGICO (% del corpus B que menciona cada tecnica)")
    L.append(t3[["pais", "n"] + [c for c in TERMINOS_IA if c in t3.columns]].to_string(index=False))
    L.append("")

    L.append("SOLAPE ENTRE CORPUS NACIONALES (el filtro es por cualquier afiliacion)")
    L.append(solape.to_string(index=False))
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anio-min", type=int, default=ANIO_MIN)
    ap.add_argument("--anio-max", type=int, default=ANIO_MAX_DEFECTO)
    args = ap.parse_args()

    os.makedirs(DIR_SALIDA, exist_ok=True)
    A_full, info = cargar_corpus(args.anio_min, max(args.anio_max, 2026), verbose=False)
    A = {p: d[d.publication_year <= args.anio_max].reset_index(drop=True) for p, d in A_full.items()}
    B = derivar_B(A)
    print(f"Cargados {len(A)} paises: {', '.join(NOMBRES.get(p, p) for p in sorted(A))}")
    print(f"Periodo {args.anio_min}-{args.anio_max}; duplicados eliminados: {int(info.duplicados.sum())}\n")

    w = lambda df, n: df.to_csv(os.path.join(DIR_SALIDA, n), index=False, encoding="utf-8-sig")
    t1 = t1_panorama(A, B);              w(t1, "t1_panorama.csv")
    t1b = t1b_sensibilidad(A, A_full);   w(t1b, "t1b_sensibilidad.csv")
    t2 = t2_evolucion(A, B);             w(t2, "t2_evolucion.csv")
    t3 = t3_tecnicas(B);                 w(t3, "t3_tecnicas.csv")
    w(t4_venues(B), "t4_venues.csv")
    w(t5_instituciones(B), "t5_instituciones.csv")
    solape = solape_entre_paises(B);     w(solape, "t1c_solape.csv")

    figuras(t2, t1)
    texto = informe(t1, t1b, t2, t3, solape, info, args.anio_max)
    with open(os.path.join(DIR_SALIDA, "informe.txt"), "w", encoding="utf-8") as fh:
        fh.write(texto)
    print("\n" + texto)
    print(f"\nTodo guardado en {DIR_SALIDA}/")


if __name__ == "__main__":
    main()
