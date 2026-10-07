#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validacion manual de la clasificacion de agenda.

El emparejamiento de topónimos es heuristico: hay que medir cuanto acierta.
agenda.py escribe resultados/t7e_muestra_validacion.csv, una muestra
estratificada (seed fija) de trabajos con su clasificacion automatica y la
evidencia (los paises detectados). Esta herramienta calcula la precision a
partir de las etiquetas que rellenes a mano.

Como etiquetar
--------------
Abre el CSV y rellena, para cada fila:

  etiqueta_manual   ok        la clasificacion automatica es correcta: los
                              paises detectados son realmente un referente
                              del trabajo, y no hay otro que se omita.
                    error     la clasificacion es incorrecta: un pais
                              detectado es espurio (homonimo, mencion
                              institucional) o falta un referente evidente.
                    ambiguo   no se puede decidir (mencion incidental, resumen
                              vacio). No cuenta ni a favor ni en contra.

  fuera_de_tema     si | no   si el trabajo NO es de patrimonio cultural
                              (p. ej. taxonomia de insectos de un museo).

Para las filas con clasificacion_auto = sin_referente, "ok" significa que
efectivamente no nombra ningun lugar; "error" que si lo nombra y el buscador no
lo vio (por ejemplo una ciudad). Eso mide la RECUPERACION, no la precision.

Uso
---
    python validacion.py evaluar                                # t7e_muestra_validacion.csv
    python validacion.py evaluar validacion/revision_preliminar_claude.csv
"""

import argparse
import os
import sys

import pandas as pd

from comun import DIR_SALIDA, wilson

VALIDAS = {"ok", "error", "ambiguo"}


def evaluar(ruta, salida):
    d = pd.read_csv(ruta, encoding="utf-8-sig")
    d["etiqueta_manual"] = d["etiqueta_manual"].fillna("").astype(str).str.strip().str.lower()
    malas = d[~d.etiqueta_manual.isin(VALIDAS | {""})]
    if len(malas):
        sys.exit(f"Etiquetas no reconocidas en {len(malas)} filas: "
                 f"{sorted(set(malas.etiqueta_manual))}. Usa ok / error / ambiguo.")
    rev = d[d.etiqueta_manual != ""]
    if not len(rev):
        sys.exit(f"{ruta} no tiene etiquetas rellenas todavia.")
    print(f"{len(rev)} de {len(d)} filas etiquetadas ({ruta})\n")

    filas = []

    def fila(nombre, sub):
        ok = int((sub.etiqueta_manual == "ok").sum())
        err = int((sub.etiqueta_manual == "error").sum())
        amb = int((sub.etiqueta_manual == "ambiguo").sum())
        decididas = ok + err
        lo, hi = wilson(ok, decididas)
        filas.append({"estrato": nombre, "n": len(sub), "ok": ok, "error": err, "ambiguo": amb,
                      "acierto_pct": round(100 * ok / decididas, 1) if decididas else float("nan"),
                      "ic_inf": round(lo, 1), "ic_sup": round(hi, 1)})

    con_ref = rev[rev.clasificacion_auto != "sin_referente"]
    fila("PRECISION: todos los trabajos con referente", con_ref)
    for clase in ("propio", "mixto", "ajeno"):
        fila(f"  precision, clase {clase}", con_ref[con_ref.clasificacion_auto == clase])
    for grupo in ("China", "Otros"):
        fila(f"  precision, grupo {grupo}", con_ref[con_ref.grupo == grupo])
    sin = rev[rev.clasificacion_auto == "sin_referente"]
    if len(sin):
        fila("RECUPERACION: sin referente que de verdad no nombra lugar", sin)

    res = pd.DataFrame(filas)
    print(res.to_string(index=False))

    if "fuera_de_tema" in rev.columns:
        ft = rev[rev.fuera_de_tema.fillna("").astype(str).str.lower().isin(["si", "no"])]
        if len(ft):
            k = int((ft.fuera_de_tema.str.lower() == "si").sum())
            lo, hi = wilson(k, len(ft))
            print(f"\nFuera de tema (no es patrimonio cultural): {k} de {len(ft)} "
                  f"= {100 * k / len(ft):.1f} % (IC 95 %: {lo:.1f}-{hi:.1f})")
            print("  OJO: la muestra esta estratificada por clase y grupo; este porcentaje describe "
                  "la muestra,\n  no el corpus. Para el corpus, usar el marcador por topicos "
                  "(t7f_sensibilidad).")

    errores = rev[rev.etiqueta_manual == "error"]
    if len(errores):
        print("\nERRORES (para mejorar el buscador):")
        for _, r in errores.iterrows():
            print(f"  [{r.clasificacion_auto}] {str(r.titulo)[:80]} | {r.evidencia} | {r.comentario}")

    os.makedirs(os.path.dirname(salida) or ".", exist_ok=True)
    res.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nResumen guardado en {salida}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evaluar", help="calcula la precision a partir de las etiquetas")
    e.add_argument("archivo", nargs="?", default=os.path.join(DIR_SALIDA, "t7e_muestra_validacion.csv"))
    e.add_argument("--salida", default=os.path.join(DIR_SALIDA, "validacion_resumen.csv"))
    args = ap.parse_args()
    if args.cmd == "evaluar":
        evaluar(args.archivo, args.salida)


if __name__ == "__main__":
    main()
