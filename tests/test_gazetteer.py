#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests de los falsos positivos y casos limite conocidos del buscador de
toponimos. Cada uno corresponde a un error real observado en el desarrollo.

Uso (desde la raiz del repositorio):
    python tests/test_gazetteer.py
    # o, si tienes pytest:  pytest tests/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from comun import (Gazetteer, construir_paises, construir_regiones, normalizar,
                   tokenizar, variantes_nombre, wilson)

PAISES = Gazetteer(construir_paises())
REGIONES = Gazetteer(construir_regiones())


def paises_en(texto):
    return {cc for _, cc in PAISES.buscar(normalizar(texto).split())}


def regiones_en(texto):
    return {r for _, r in REGIONES.buscar(normalizar(texto).split())}


# ── Paises ───────────────────────────────────────────────────────────────────

def test_palabra_completa():
    # "berat" (ciudad albanesa) no debe aparecer dentro de "deliberate"
    assert paises_en("a deliberate choice of flakes and inspiring lakes") == set()


def test_inner_mongolia_es_china():
    assert paises_en("rock art of Inner Mongolia") == {"cn"}


def test_mongolia_sigue_siendo_mongolia():
    assert paises_en("nomadic heritage of Mongolia") == {"mn"}


def test_coincidencia_mas_larga():
    assert paises_en("temples of South Korea") == {"kr"}
    assert paises_en("the border with North Korea") == {"kp"}


def test_homonimos_excluidos():
    assert paises_en("a guinea pig, the state of Georgia and the Niger delta") == set()


def test_alias_frecuentes():
    assert paises_en("Roman remains in the UK and the USA") == {"gb", "us"}
    assert paises_en("Viet Nam and Türkiye") == {"vn", "tr"}
    assert paises_en("the Holy See") == {"va"}


def test_acentos_y_puntuacion():
    assert paises_en("Côte d'Ivoire") == {"ci"}
    assert paises_en("Hong Kong, Macao and Taiwan") == {"hk", "mo", "tw"}


def test_pronombre_us_no_es_estados_unidos():
    assert paises_en("let us study this") == set()


# ── Regiones ─────────────────────────────────────────────────────────────────

def test_ruta_de_la_seda():
    assert regiones_en("along the Silk Road") == {"ruta_seda"}
    assert regiones_en("the Belt and Road Initiative") == {"ruta_seda"}


def test_norte_de_africa_gana_a_africa():
    assert regiones_en("sites in North Africa") == {"oriente_medio_n_africa"}
    assert regiones_en("sites in West Africa") == {"africa_subsahariana"}


# ── Sitios UNESCO ────────────────────────────────────────────────────────────

def test_variantes_no_generan_basura():
    v = variantes_nombre("Archaeological Areas of Pompei, Herculaneum and Torre Annunziata")
    assert "pompei" in v and "herculaneum" in v
    assert "archaeological" not in v


def test_variantes_transfronterizas_generan_pais():
    # Esta variante existe en bruto; cargar_unesco la elimina por ser nombre de pais
    v = variantes_nombre("Wooden Tserkvas of the Carpathian Region in Poland and Ukraine")
    assert "ukraine" in v


# ── Estadistica ──────────────────────────────────────────────────────────────

def test_wilson():
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and 25 < hi < 30      # 0/10: el limite superior no es 0
    lo, hi = wilson(50, 100)
    assert 40 < lo < 41 and 59 < hi < 60
    assert wilson(0, 0)[0] != wilson(0, 0)  # nan


if __name__ == "__main__":
    pruebas = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    fallos = 0
    for nombre, f in pruebas:
        try:
            f()
            print(f"  ok    {nombre}")
        except AssertionError as e:
            fallos += 1
            print(f"  FALLA {nombre}: {e}")
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} pruebas pasan")
    sys.exit(1 if fallos else 0)
