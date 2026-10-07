#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agenda patrimonial: ¿a que patrimonio se refiere la investigacion de cada pais?

Pregunta
--------
Para cada pais, de los trabajos sobre patrimonio cultural (corpus A) y de los
que ademas involucran IA (corpus B): que proporcion se ocupa de lugares del
propio pais y que proporcion de lugares ajenos. Y, dentro de lo ajeno, hacia
que regiones mira. Es una forma de observar la AGENDA de un sistema cientifico:
una investigacion que exporta su mirada al patrimonio de otros (como la
francesa o la britanica) tiene un perfil distinto de la que se concentra en el
propio (como la china, la india o la egipcia).

Que mide y que no mide
----------------------
Mide a que lugares SE REFIERE el titulo o el resumen de un trabajo, segun los
paises que nombra. No mide si el trabajo trata de un sitio patrimonial, ni lo
que ocurre en trabajos que no nombran ningun lugar (que suelen ser
metodologicos y quedan fuera del calculo; se informa la cobertura).

Definiciones (todas versionadas aqui, ninguna escondida en los datos)
---------------------------------------------------------------------
Referente de un trabajo : el conjunto de paises cuyo nombre aparece como
                          palabra completa en titulo + resumen.
  propio                : nombra solo el pais del autor.
  mixto                 : nombra el propio y algun otro.
  ajeno                 : nombra otros paises y no el propio.
  sin_referente         : no nombra ningun pais.
  especial (solo China) : nombra unicamente Hong Kong, Macao o Taiwan.

Metrica principal       : ajeno_excl = ajeno / (propio + mixto + ajeno).
                          "Trabajos cuyo referente es exclusivamente ajeno."
Metrica secundaria      : menciona_ajeno = (ajeno + mixto) / (propio + mixto + ajeno).
                          Incluye los comparativos.

Hong Kong, Macao y Taiwan
-------------------------
La descarga usa institutions.country_code:cn, que NO incluye hk, mo ni tw
(QUERY.txt: "hk/mo/tw agrupados con cn: no"). Para la clasificacion se tratan
como categoria aparte ("especial"): ni propios ni ajenos. Es una decision
metodologica que debe declararse; la tabla de sensibilidad muestra el
resultado tratandolos como propios y como ajenos.

Uso
---
    python agenda.py --unesco whc-sites-2025.xls
    python agenda.py                      # sin la capa de sitios UNESCO

Salida (resultados/)
--------------------
    t7_agenda.csv             propio / mixto / ajeno por pais y corpus, con IC
    t7b_periodos.csv          lo mismo, 2015-2019 frente a 2020-2025
    t7b_serie_anual.csv       serie anual (corpus A)
    t7c_regiones.csv          hacia que regiones mira cada pais
    t7d_ruta_seda.csv         marcador "Ruta de la Seda / Franja y la Ruta"
    t7d_ruta_seda_anual.csv   su evolucion anual
    t7e_muestra_validacion.csv   muestra para validar a mano (ver validacion.py)
    t7f_sensibilidad.csv      el resultado principal bajo definiciones alternativas
    f3_agenda.png, f4_regiones.png, f5_serie_agenda.png
    intermedios/trabajos_clasificados.csv.gz   una fila por trabajo (no versionar)
"""

import argparse
import os
import re
import sys
import textwrap
import unicodedata
from collections import Counter

import pandas as pd

from comun import (ACENTO, ANIO_MAX_DEFECTO, ANIO_MIN, DIR_SALIDA, ETIQUETAS_REGION,
                   GENTILICIOS, GRIS, NOMBRES, REGION_DE_ISO, SECUENCIAL, SUPERFICIE, TINTA,
                   TINTA_2, Gazetteer, cargar_corpus, cargar_unesco, construir_paises,
                   construir_ciudades, construir_regiones, estilo_ejes, etiquetas_finales, fila_proporcion,
                   importar_matplotlib, pct, tokenizar)

ESPECIAL = {"hk", "mo", "tw"}

# Territorios que forman parte del propio pais y no deben contarse como ajenos.
# Se limita a los departamentos y colectividades de ultramar de Francia: un
# trabajo frances sobre Guadalupe es un trabajo sobre territorio frances. Los
# territorios britanicos de ultramar (Gibraltar, Bermudas...) NO son parte del
# Reino Unido y se tratan como ajenos.
TERRITORIOS_PROPIOS = {"fr": {"gp", "mq", "gf", "re", "yt", "pm", "bl", "mf", "wf", "nc", "pf"}}
CLASES = ["propio", "mixto", "ajeno", "especial", "sin_referente"]
PERIODOS = {"2015-2019": (2015, 2019), "2020-2025": (2020, 2025)}

# Filtros contra el ruido de la capa de sitios UNESCO. Las formas cortas de los
# nombres oficiales ("palaces", "wetlands", "roman") son a menudo palabras comunes.
#   1. Regla de mayuscula: un toponimo se escribe con mayuscula inicial; si una
#      variante aparece en minuscula en la mitad o mas de sus apariciones en
#      resumenes, es una palabra comun y se descarta. Se adapta al corpus.
#   2. Techo de frecuencia: una variante presente en mas de esta fraccion del
#      total de trabajos tampoco es un toponimo ("roman", "earth").
UMBRAL_SITIO = 0.01
FRACCION_MAYUSCULA_MIN = 0.5
MIN_OCURRENCIAS_CASO = 5

# Definiciones alternativas del referente, para el analisis de sensibilidad.
# nombre: (usa_gentilicios, usa_sitios, usa_ciudades, tratamiento de hk/mo/tw)
# La definicion PRINCIPAL (nombres de pais) es la que se valido a mano. Las
# demas capas aumentan la recuperacion: nombran lugares sin nombrar el pais.
VARIANTES = {
    "principal (nombres de pais; hk/mo/tw aparte)": (False, False, False, "separado"),
    "+ gentilicios de los 9 paises": (True, False, False, "separado"),
    "+ sitios UNESCO": (False, True, False, "separado"),
    "+ ciudades (GeoNames)": (False, False, True, "separado"),
    "+ sitios UNESCO y ciudades": (False, True, True, "separado"),
    "+ gentilicios, sitios y ciudades (maxima recuperacion)": (True, True, True, "separado"),
    "hk/mo/tw como propios de China": (False, False, False, "propio"),
    "hk/mo/tw como ajenos a China": (False, False, False, "ajeno"),
}
PRINCIPAL = next(iter(VARIANTES))


# ─────────────────────────────────────────────────────────────────────────────
# CLASIFICACION
# ─────────────────────────────────────────────────────────────────────────────

def clasificar(pais, refs, tratamiento="separado"):
    """Clase de un trabajo dado el conjunto de paises que nombra."""
    refs = set(refs)
    propios = TERRITORIOS_PROPIOS.get(pais, set())
    if refs & propios:
        refs = (refs - propios) | {pais}
    esp = set()
    if pais == "cn":
        esp = refs & ESPECIAL
        refs -= ESPECIAL
        if esp and tratamiento == "propio":
            refs.add("cn")
        elif esp and tratamiento == "ajeno":
            refs |= esp
    propio = pais in refs
    ajeno = bool(refs - {pais})
    if propio and ajeno:
        return "mixto"
    if propio:
        return "propio"
    if ajeno:
        return "ajeno"
    if esp and tratamiento == "separado":
        return "especial"
    return "sin_referente"


def refs_de_sitios(pais, conjuntos):
    """Paises que aporta la capa de sitios. Un sitio transfronterizo al que el
    propio pais pertenece cuenta solo como propio: no lo hace "mixto" por
    compartirlo (el Qhapaq Nan es de seis paises, y para Peru es propio)."""
    out = set()
    for isos in conjuntos:
        out |= {pais} if pais in isos else set(isos)
    return out


def procesar(A, sitios=None, ciudades=None, verbose=True):
    """Recorre todos los trabajos y devuelve un DataFrame, una fila por trabajo."""
    gz_p = Gazetteer(construir_paises())
    gz_r = Gazetteer(construir_regiones())
    gz_g = Gazetteer(GENTILICIOS)
    gz_s = Gazetteer(sitios) if sitios else None
    gz_c = Gazetteer(ciudades) if ciudades else None

    filas = []
    n_total = sum(len(d) for d in A.values())
    hecho = 0
    for pais, d in sorted(A.items()):
        for r in d.itertuples(index=False):
            pal = tokenizar(r.title, r.abstract)
            m_p = gz_p.buscar(pal)
            m_r = gz_r.buscar(pal)
            m_g = gz_g.buscar(pal)
            m_s = gz_s.buscar(pal) if gz_s else []
            m_c = gz_c.buscar(pal) if gz_c else []
            filas.append({
                "pais": pais, "openalex_id": r.openalex_id, "anio": int(r.publication_year),
                "title": r.title, "abstract": r.abstract,
                "n_terminos_ia": int(r.n_terminos_ia), "tiene_resumen": bool(r.tiene_resumen),
                "ciencias_vida": bool(r.ciencias_vida),
                "p_nom": frozenset(cc for _, cc in m_p),
                "p_gen": frozenset(cc for _, cc in m_g),
                "s_sets": tuple(frozenset(v) for _, v in m_s),
                "s_vars": tuple(n for n, _ in m_s),
                "c_sets": tuple(frozenset({v}) for _, v in m_c),
                "c_vars": tuple(n for n, _ in m_c),
                "r_kw": frozenset(reg for _, reg in m_r),
                "ruta_terminos": tuple(n for n, reg in m_r if reg == "ruta_seda"),
                "ev_paises": tuple(n for n, _ in m_p),
            })
            hecho += 1
        if verbose:
            print(f"  {NOMBRES.get(pais, pais):<12} {len(d):>6,} trabajos   ({hecho:,}/{n_total:,})")
    return pd.DataFrame(filas)


def _normalizar_con_caso(texto):
    """Como normalizar() pero conservando mayusculas, para la regla de mayuscula."""
    t = unicodedata.normalize("NFD", str(texto))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", " ", t).strip()


def filtrar_ruidosos(T, col_vars, etiqueta, umbral=UMBRAL_SITIO, verbose=True):
    """Devuelve el conjunto de variantes de la capa `col_vars` (s_vars o c_vars)
    que hay que descartar, por la regla de mayuscula o el techo de frecuencia."""
    if not len(T) or not any(T[col_vars].map(len)):
        return set()
    donde = {}                                    # variante -> indices de trabajos
    for i, vs in enumerate(T[col_vars]):
        for v in set(vs):
            donde.setdefault(v, []).append(i)
    tope = max(10, int(umbral * len(T)))
    abstracts = T.abstract.tolist()

    por_frecuencia, por_minuscula, detalle = set(), set(), {}
    for v, idxs in donde.items():
        if len(idxs) > tope:
            por_frecuencia.add(v)
            continue
        objetivo = v.split()
        k = len(objetivo)
        may = tot = 0
        for i in idxs:
            pal = _normalizar_con_caso(abstracts[i]).split()
            bajo = [p.lower() for p in pal]
            for j in range(len(pal) - k + 1):
                if bajo[j:j + k] == objetivo:
                    tot += 1
                    may += pal[j][:1].isupper()
        detalle[v] = (may, tot)
        if tot >= MIN_OCURRENCIAS_CASO and may / tot < FRACCION_MAYUSCULA_MIN:
            por_minuscula.add(v)

    genericas = por_frecuencia | por_minuscula
    if verbose:
        print(f"  {etiqueta}: {len(donde)} variantes detectadas; descartadas {len(genericas)} "
              f"({len(por_frecuencia)} por frecuencia > {tope} trabajos, "
              f"{len(por_minuscula)} por escribirse en minuscula)")
        top = sorted(por_frecuencia, key=lambda v: -len(donde[v]))[:8]
        if top:
            print("    por frecuencia: " + ", ".join(f"{v} ({len(donde[v])})" for v in top))
        top = sorted(por_minuscula, key=lambda v: -len(donde[v]))[:12]
        if top:
            print("    por minuscula:  " + ", ".join(f"{v} ({len(donde[v])})" for v in top))
        conservadas = sorted((v for v in donde if v not in genericas), key=lambda v: -len(donde[v]))[:20]
        print("    mas frecuentes conservadas (revisar a mano): "
              + ", ".join(f"{v} ({len(donde[v])})" for v in conservadas))
    return genericas


def clasificar_todo(T, genericas_s, genericas_c):
    """Agrega a T las columnas de clase para cada variante de definicion."""
    # Tras descartar las variantes genericas, reconstruir los conjuntos de cada capa
    T = T.copy()
    for col_s, col_v, gen in (("s_sets", "s_vars", genericas_s), ("c_sets", "c_vars", genericas_c)):
        sets_n, vars_n = [], []
        for sets, vs in zip(T[col_s], T[col_v]):
            keep = [(s, v) for s, v in zip(sets, vs) if v not in gen]
            sets_n.append(tuple(s for s, _ in keep))
            vars_n.append(tuple(v for _, v in keep))
        T[col_s], T[col_v] = sets_n, vars_n

    for i, (nombre, (gent, sit, ciu, trat)) in enumerate(VARIANTES.items()):
        col = f"cl_{i}"
        clases = []
        for p, nom, gen, s_s, c_s in zip(T.pais, T.p_nom, T.p_gen, T.s_sets, T.c_sets):
            refs = set(nom)
            if gent:
                refs |= gen
            if sit:
                refs |= refs_de_sitios(p, s_s)
            if ciu:
                refs |= refs_de_sitios(p, c_s)
            clases.append(clasificar(p, refs, trat))
        T[col] = clases
    T["clase"] = T["cl_0"]

    # regiones ajenas: regiones de los paises extranjeros nombrados + palabras de region
    reg = []
    for p, nom, kw in zip(T.pais, T.p_nom, T.r_kw):
        ajenos = {c for c in nom if c != p and not (p == "cn" and c in ESPECIAL)}
        reg.append(frozenset({REGION_DE_ISO[c] for c in ajenos if c in REGION_DE_ISO} | set(kw)))
    T["regiones"] = reg
    T["ruta_seda"] = T.ruta_terminos.map(len) > 0
    return T


# ─────────────────────────────────────────────────────────────────────────────
# TABLAS
# ─────────────────────────────────────────────────────────────────────────────

def corpus(T, nombre):
    return T if nombre == "A" else T[T.n_terminos_ia >= 1]


def fila_agenda(sub, col="clase"):
    """Conteos y proporciones con IC para un subconjunto de trabajos de un pais."""
    c = Counter(sub[col])
    n = len(sub)
    con_ref = c["propio"] + c["mixto"] + c["ajeno"]
    f = {"n": n, "n_con_referente": con_ref,
         "cobertura_pct": pct(con_ref, n),
         **{k: c[k] for k in CLASES}}
    f.update(fila_proporcion("ajeno_excl", c["ajeno"], con_ref))
    f.update(fila_proporcion("menciona_ajeno", c["ajeno"] + c["mixto"], con_ref))
    f["menciona_ajeno_sobre_total_pct"] = pct(c["ajeno"] + c["mixto"], n)
    return f


def t7_agenda(T):
    filas = []
    for nombre in ("A", "B"):
        C = corpus(T, nombre)
        for p in sorted(C.pais.unique()):
            sub = C[C.pais == p]
            filas.append({"pais": NOMBRES.get(p, p), "codigo": p, "corpus": nombre,
                          **fila_agenda(sub)})
    return pd.DataFrame(filas).sort_values(["corpus", "ajeno_excl_pct"], ascending=[True, False])


def t7b_periodos(T):
    filas = []
    for nombre in ("A", "B"):
        C = corpus(T, nombre)
        for p in sorted(C.pais.unique()):
            for per, (a, b) in PERIODOS.items():
                sub = C[(C.pais == p) & (C.anio >= a) & (C.anio <= b)]
                filas.append({"pais": NOMBRES.get(p, p), "codigo": p, "corpus": nombre,
                              "periodo": per, **fila_agenda(sub)})
    return pd.DataFrame(filas)


def t7b_serie(T):
    filas = []
    for p in sorted(T.pais.unique()):
        for anio, sub in T[T.pais == p].groupby("anio"):
            f = fila_agenda(sub)
            filas.append({"pais": NOMBRES.get(p, p), "codigo": p, "anio": anio,
                          "n": f["n"], "n_con_referente": f["n_con_referente"],
                          "ajeno_excl_pct": f["ajeno_excl_pct"],
                          "menciona_ajeno_pct": f["menciona_ajeno_pct"]})
    return pd.DataFrame(filas)


def t7c_regiones(T):
    filas = []
    for nombre in ("A", "B"):
        C = corpus(T, nombre)
        for p in sorted(C.pais.unique()):
            sub = C[C.pais == p]
            n = len(sub)
            cuenta = Counter(r for rs in sub.regiones for r in rs)
            for reg in ETIQUETAS_REGION:
                k = cuenta[reg]
                filas.append({"pais": NOMBRES.get(p, p), "codigo": p, "corpus": nombre,
                              "region": ETIQUETAS_REGION[reg], "region_clave": reg,
                              "n_trabajos": k, "n_corpus": n,
                              **fila_proporcion("pct_corpus", k, n)})
    return pd.DataFrame(filas)


def t7d_ruta_seda(T):
    filas = []
    for nombre in ("A", "B"):
        C = corpus(T, nombre)
        for p in sorted(C.pais.unique()):
            sub = C[C.pais == p]
            m = sub[sub.ruta_seda]
            c = Counter(m.clase)
            terminos = Counter(t for ts in m.ruta_terminos for t in set(ts))
            filas.append({
                "pais": NOMBRES.get(p, p), "codigo": p, "corpus": nombre,
                "n_corpus": len(sub), "n_con_marcador": len(m),
                **fila_proporcion("pct_corpus", len(m), len(sub)),
                "con_marcador_propio": c["propio"], "con_marcador_mixto": c["mixto"],
                "con_marcador_ajeno": c["ajeno"], "con_marcador_sin_referente": c["sin_referente"],
                "con_marcador_especial": c["especial"],
                # orden total (frecuencia y luego alfabetico): sin desempates dependientes del hash
                "terminos": "; ".join(f"{t} ({k})" for t, k in
                                      sorted(terminos.items(), key=lambda kv: (-kv[1], kv[0]))[:4]),
            })
    return pd.DataFrame(filas)


def t7d_ruta_seda_anual(T):
    filas = []
    for p in sorted(T.pais.unique()):
        for anio, sub in T[T.pais == p].groupby("anio"):
            k = int(sub.ruta_seda.sum())
            filas.append({"pais": NOMBRES.get(p, p), "codigo": p, "anio": anio,
                          "n_corpus": len(sub), "n_con_marcador": k,
                          "pct": pct(k, len(sub), 2)})
    return pd.DataFrame(filas)


def t7f_sensibilidad(T):
    """El resultado principal (% ajeno_excl) bajo cada definicion alternativa,
    con el puesto de China entre los nueve (1 = el mas orientado a lo ajeno).

    Ademas de las definiciones del referente (VARIANTES), una variante de
    corpus: se excluyen los trabajos de tema principal en ciencias de la vida."""
    variantes = [(nombre, f"cl_{i}", False) for i, nombre in enumerate(VARIANTES)]
    variantes.append(("principal, sin tema principal de ciencias de la vida", "cl_0", True))
    filas = []
    for nombre in ("A", "B"):
        C0 = corpus(T, nombre)
        for var, col, sin_vida in variantes:
            C = C0[~C0.ciencias_vida] if sin_vida else C0
            for p in sorted(C.pais.unique()):
                f = fila_agenda(C[C.pais == p], col)
                filas.append({"corpus": nombre, "definicion": var, "pais": NOMBRES.get(p, p),
                              "codigo": p, "n": f["n"], "n_con_referente": f["n_con_referente"],
                              "cobertura_pct": f["cobertura_pct"],
                              "ajeno_excl_pct": f["ajeno_excl_pct"],
                              "ajeno_excl_ic_inf": f["ajeno_excl_ic_inf"],
                              "ajeno_excl_ic_sup": f["ajeno_excl_ic_sup"]})
    S = pd.DataFrame(filas)
    S["puesto"] = S.groupby(["corpus", "definicion"]).ajeno_excl_pct.rank(ascending=False, method="min")
    S["de_n_paises"] = S.groupby(["corpus", "definicion"]).pais.transform("count")
    return S


def t7e_muestra(T, semilla=42, por_estrato=10):
    """Muestra estratificada para validar a mano.

    Estratos: China y el resto de paises en conjunto, cada uno con las clases
    propio, mixto, ajeno y sin_referente. Los trabajos sin referente permiten
    estimar lo que el buscador NO encuentra (recuperacion incompleta)."""
    partes = []
    for grupo, filtro in (("China", T.pais == "cn"), ("Otros", T.pais != "cn")):
        for clase in ("propio", "mixto", "ajeno", "sin_referente"):
            sub = T[filtro & (T.clase == clase)]
            if len(sub):
                s = sub.sample(min(por_estrato, len(sub)), random_state=semilla)
                partes.append(s.assign(grupo=grupo))
    M = pd.concat(partes)
    M["evidencia"] = [
        "paises: " + ", ".join(ev) if ev else "(ninguno)" for ev in M.ev_paises]
    M["resumen_inicio"] = M.abstract.str.slice(0, 300)
    out = M[["openalex_id", "grupo", "pais", "anio", "title", "clase", "evidencia",
             "resumen_inicio"]].rename(columns={"title": "titulo", "clase": "clasificacion_auto"})
    out["etiqueta_manual"] = ""     # ok | error | ambiguo
    out["fuera_de_tema"] = ""       # si | no  (el trabajo no es de patrimonio cultural)
    out["comentario"] = ""
    return out.sample(frac=1, random_state=semilla).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# FIGURAS
#   Estilo "enfasis": China en el color de acento, el resto en gris neutro.
#   La historia es China frente al conjunto, no nueve categorias distintas.
# ─────────────────────────────────────────────────────────────────────────────

def figuras(T, ta, tr, ts_serie):
    plt = importar_matplotlib()
    if plt is None:
        return

    # f3: % de trabajos cuyo referente es exclusivamente ajeno, con IC
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True)
    for ax, nombre, titulo in zip(axes, ("A", "B"),
                                  ("Toda la investigación patrimonial (A)",
                                   "Patrimonio con IA (B)")):
        d = ta[ta.corpus == nombre].sort_values("ajeno_excl_pct")
        estilo_ejes(ax)
        for y, (_, r) in enumerate(d.iterrows()):
            china = r.codigo == "cn"
            col = ACENTO if china else GRIS
            ax.plot([r.ajeno_excl_ic_inf, r.ajeno_excl_ic_sup], [y, y], color=col,
                    linewidth=2, solid_capstyle="round", zorder=2)
            ax.scatter([r.ajeno_excl_pct], [y], s=60 if china else 40, color=col,
                       edgecolor=SUPERFICIE, linewidth=1.5, zorder=3)
            ax.text(min(r.ajeno_excl_ic_sup + 1.5, 97), y,
                    f"{r.ajeno_excl_pct:.0f} %  (n={int(r.n_con_referente):,})".replace(",", "."),
                    va="center", fontsize=8, color=TINTA if china else TINTA_2,
                    fontweight="bold" if china else "normal")
        ax.set_yticks(range(len(d)))
        ax.set_yticklabels(d.pais, fontsize=9.5)
        for lab, (_, r) in zip(ax.get_yticklabels(), d.iterrows()):
            lab.set_color(TINTA if r.codigo == "cn" else TINTA_2)
            lab.set_fontweight("bold" if r.codigo == "cn" else "normal")
        ax.set_xlim(0, 100)
        ax.set_title(titulo, fontsize=11, color=TINTA, loc="left")
        ax.set_xlabel("Trabajos cuyo referente es solo patrimonio ajeno (%)", fontsize=9, color=TINTA_2)
    fig.suptitle("¿Hacia qué patrimonio mira la investigación de cada país?",
                 x=0.01, ha="left", fontsize=13, color=TINTA, fontweight="bold")
    fig.text(0.01, 0.01, "Punto: estimación. Línea: intervalo de confianza de Wilson al 95 %. "
             "Entre paréntesis, trabajos que nombran algún país.",
             fontsize=8, color=TINTA_2)
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(os.path.join(DIR_SALIDA, "f3_agenda.png"), dpi=200)
    plt.close(fig)

    # f4: mapa de calor de regiones (corpus A)
    d = tr[tr.corpus == "A"].pivot_table(index="pais", columns="region_clave", values="pct_corpus_pct")
    orden_reg = list(ETIQUETAS_REGION)
    d = d[orden_reg]
    d = d.loc[d.mean(axis=1).sort_values().index]
    fig, ax = plt.subplots(figsize=(12, 4.9))
    ax.set_facecolor(SUPERFICIE)
    vmax = max(float(d.max().max()), 1)
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", SECUENCIAL)
    ax.imshow(d.values, cmap=cmap, aspect="auto", vmin=0, vmax=vmax)
    ax.set_xticks(range(len(orden_reg)))
    ax.set_xticklabels([textwrap.fill(ETIQUETAS_REGION[r], 15) for r in orden_reg],
                       fontsize=8.5, color=TINTA_2)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d.index, fontsize=9.5)
    for lab in ax.get_yticklabels():
        china = lab.get_text() == "China"
        lab.set_color(TINTA if china else TINTA_2)
        lab.set_fontweight("bold" if china else "normal")
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    for i in range(d.shape[0]):
        for j in range(d.shape[1]):
            v = d.values[i, j]
            ax.text(j, i, f"{v:.1f}".replace(".", ","), ha="center", va="center", fontsize=8.5,
                    color="white" if v > 0.55 * vmax else TINTA)
    ax.set_title("Regiones mencionadas fuera del propio país (% de los trabajos de cada país, corpus A)",
                 fontsize=11, color=TINTA, loc="left", pad=52, fontweight="bold")
    fig.text(0.01, 0.01, "La primera columna es un marcador de discurso (incluye menciones al propio país); "
             "las demás cuentan solo lugares ajenos.", fontsize=8, color=TINTA_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(DIR_SALIDA, "f4_regiones.png"), dpi=200)
    plt.close(fig)

    # f5: serie anual de "menciona ajeno" (corpus A)
    fig, ax = plt.subplots(figsize=(9, 5))
    estilo_ejes(ax, rejilla="y")
    ultimos = []
    for p, sub in ts_serie.groupby("codigo"):
        sub = sub[(sub.n_con_referente >= 30)].sort_values("anio")
        if len(sub) < 3:
            continue
        china = p == "cn"
        ax.plot(sub.anio, sub.menciona_ajeno_pct, color=ACENTO if china else GRIS,
                linewidth=2.6 if china else 1.4, zorder=3 if china else 2,
                marker="o" if china else None, markersize=4)
        ultimos.append((float(sub.menciona_ajeno_pct.iloc[-1]), sub.anio.iloc[-1],
                        NOMBRES.get(p, p), china))
    etiquetas_finales(ax, ultimos, 3.2)
    ax.set_xlim(ANIO_MIN, ANIO_MAX_DEFECTO + 1.7)
    ax.set_xticks(range(ANIO_MIN, ANIO_MAX_DEFECTO + 1, 2))
    ax.set_ylim(0, 100)
    ax.set_ylabel("Trabajos que nombran algún país ajeno (%)", fontsize=9, color=TINTA_2)
    ax.set_title("Mirada hacia lo ajeno, año a año (corpus A)", loc="left",
                 fontsize=11, color=TINTA, fontweight="bold")
    fig.text(0.01, 0.01, "Solo años con al menos 30 trabajos que nombran un país.",
             fontsize=8, color=TINTA_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(DIR_SALIDA, "f5_serie_agenda.png"), dpi=200)
    plt.close(fig)
    print("  figuras guardadas: f3_agenda, f4_regiones, f5_serie_agenda")


# ─────────────────────────────────────────────────────────────────────────────

def texto_resumen(ta, tp, ts, td):
    """Resumen legible para el informe."""
    L = ["AGENDA PATRIMONIAL: PROPIO FRENTE A AJENO", "=" * 62, ""]
    L.append("Definicion: de los trabajos que nombran algun pais en titulo o resumen,")
    L.append("que proporcion se refiere exclusivamente a paises ajenos. IC de Wilson al 95 %.")
    L.append("")
    for nombre, etiqueta in (("A", "CORPUS A (todo el patrimonio)"), ("B", "CORPUS B (patrimonio + IA)")):
        d = ta[ta.corpus == nombre]
        L.append(etiqueta)
        L.append(d[["pais", "n", "cobertura_pct", "n_con_referente", "propio", "mixto", "ajeno",
                    "especial", "ajeno_excl_pct", "ajeno_excl_ic_inf", "ajeno_excl_ic_sup",
                    "menciona_ajeno_pct"]].to_string(index=False))
        L.append("")
    L.append("PERIODOS (menciona_ajeno_pct, corpus A)")
    piv = tp[tp.corpus == "A"].pivot_table(index="pais", columns="periodo", values="menciona_ajeno_pct")
    L.append(piv.round(1).to_string())
    L.append("")
    L.append("SENSIBILIDAD: ajeno_excl_pct de China y puesto entre los nueve (1 = mas ajeno)")
    c = ts[ts.codigo == "cn"][["corpus", "definicion", "ajeno_excl_pct", "ajeno_excl_ic_inf",
                                "ajeno_excl_ic_sup", "puesto", "de_n_paises"]]
    L.append(c.to_string(index=False))
    L.append("")
    L.append("MARCADOR 'RUTA DE LA SEDA / FRANJA Y LA RUTA'")
    L.append(td[td.corpus == "A"][["pais", "n_corpus", "n_con_marcador", "pct_corpus_pct",
                                    "con_marcador_propio", "con_marcador_mixto",
                                    "con_marcador_ajeno", "con_marcador_sin_referente"]].to_string(index=False))
    return "\n".join(L)


def guardar_muestra(tm):
    """Escribe la muestra de validacion SIN pisar etiquetas hechas a mano: si el
    archivo ya tiene etiquetas, la muestra nueva va a un archivo aparte."""
    ruta = os.path.join(DIR_SALIDA, "t7e_muestra_validacion.csv")
    if os.path.exists(ruta):
        previo = pd.read_csv(ruta, encoding="utf-8-sig")
        if previo.get("etiqueta_manual", pd.Series(dtype=str)).fillna("").astype(str).str.strip().ne("").any():
            alt = os.path.join(DIR_SALIDA, "t7e_muestra_validacion.nueva.csv")
            tm.to_csv(alt, index=False, encoding="utf-8-sig")
            print(f"  AVISO: {ruta} ya tiene etiquetas manuales y no se sobrescribe.\n"
                  f"         La muestra regenerada esta en {alt}.")
            return
    tm.to_csv(ruta, index=False, encoding="utf-8-sig")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unesco", help="Lista del Patrimonio Mundial (xls/xlsx/csv); activa la capa de sitios")
    ap.add_argument("--anio-min", type=int, default=ANIO_MIN)
    ap.add_argument("--anio-max", type=int, default=ANIO_MAX_DEFECTO)
    ap.add_argument("--semilla", type=int, default=42, help="semilla de la muestra de validacion")
    args = ap.parse_args()

    os.makedirs(DIR_SALIDA, exist_ok=True)
    os.makedirs(os.path.join(DIR_SALIDA, "intermedios"), exist_ok=True)
    A, _ = cargar_corpus(args.anio_min, args.anio_max)

    sitios = None
    if args.unesco and os.path.exists(args.unesco):
        print("Capa de sitios UNESCO:")
        sitios, _ = cargar_unesco(args.unesco)
    else:
        print("Sin --unesco: se omiten las definiciones con sitios (se tratan como la principal).")

    ciudades = None
    try:
        print("Capa de ciudades (GeoNames):")
        ciudades = construir_ciudades(excluir=set(construir_paises()) | set(construir_regiones()))
        print(f"  {len(ciudades):,} nombres de ciudad")
    except ImportError:
        print("  geonamescache no instalado: se omite la capa de ciudades "
              "(pip install geonamescache)")

    print("Buscando referentes geograficos en titulo + resumen...")
    T = procesar(A, sitios, ciudades)
    gen_s = filtrar_ruidosos(T, "s_vars", "sitios")
    # Para ciudades no hay techo de frecuencia: Londres o Roma son legitimamente muy
    # citadas. Alli basta la regla de mayuscula y la lista de nombres ruidosos.
    gen_c = filtrar_ruidosos(T, "c_vars", "ciudades", umbral=1.0)
    T = clasificar_todo(T, gen_s, gen_c)

    if not sitios or not ciudades:
        print("  (las variantes que usan capas no disponibles equivalen a la principal)")

    print("Calculando tablas...")
    ta, tp, tser = t7_agenda(T), t7b_periodos(T), t7b_serie(T)
    tr, td, tda = t7c_regiones(T), t7d_ruta_seda(T), t7d_ruta_seda_anual(T)
    ts = t7f_sensibilidad(T)
    tm = t7e_muestra(T, args.semilla)

    w = lambda df, nombre: df.to_csv(os.path.join(DIR_SALIDA, nombre), index=False, encoding="utf-8-sig")
    w(ta, "t7_agenda.csv"); w(tp, "t7b_periodos.csv"); w(tser, "t7b_serie_anual.csv")
    w(tr, "t7c_regiones.csv"); w(td, "t7d_ruta_seda.csv"); w(tda, "t7d_ruta_seda_anual.csv")
    w(ts, "t7f_sensibilidad.csv")
    guardar_muestra(tm)
    T.drop(columns=["abstract", "p_nom", "p_gen", "s_sets", "s_vars", "c_sets", "c_vars", "r_kw", "ruta_terminos",
                    "ev_paises", "regiones"]).to_csv(
        os.path.join(DIR_SALIDA, "intermedios", "trabajos_clasificados.csv.gz"),
        index=False, encoding="utf-8-sig")

    figuras(T, ta, tr, tser)

    texto = texto_resumen(ta, tp, ts, td)
    with open(os.path.join(DIR_SALIDA, "informe_agenda.txt"), "w", encoding="utf-8") as fh:
        fh.write(texto)
    print("\n" + texto)
    print(f"\nTodo guardado en {DIR_SALIDA}/")
    print("Siguiente paso: revisar a mano resultados/t7e_muestra_validacion.csv y correr "
          "python validacion.py evaluar")


if __name__ == "__main__":
    main()
