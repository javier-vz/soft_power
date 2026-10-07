# Historial de cambios

## 1.1 — octubre de 2026

La consulta (`QUERY.txt`, **v1**) y los corpus descargados **no cambian**. Cambia el análisis.

### Correcciones a afirmaciones de la 1.0

| Afirmación de la 1.0 | Estado | Detalle |
|---|---|---|
| «China presenta la colaboración internacional más baja del conjunto» | **Falsa. Retirada.** | China 22,9 %; la India tiene 17,2 % (`t1_panorama.csv` ya lo mostraba). China es la segunda más baja, con intervalos que casi se solapan. |
| «China lidera la penetración de la IA» | **Matizada.** | Se sostiene bajo cinco de siete definiciones. Con dos o más términos de IA, China y la India empatan técnicamente. |
| «En autorreferencia China no se distingue de los demás países con gran acervo patrimonial; se apartan el Reino Unido y Francia» | **Se confirma, con mejor medida.** | La medida original (sitios UNESCO) clasificaba 85 trabajos chinos (4,6 % del corpus B). La nueva clasifica 6.956 del corpus A (38 %). El patrón es el mismo, y ahora con intervalos. |

### Errores corregidos

- **Duplicados.** El corpus A de China tenía 195 identificadores repetidos (la deduplicación del
  script de descarga es posterior a esa descarga). Se eliminan al cargar.
- **2026 en las tasas.** Es un año parcial (la descarga es de agosto) y deprimía las tasas
  recientes. Se excluye por defecto (`--anio-max 2026` lo restituye). Efecto sobre la tasa de IA
  global de cada país:

  | | China | India | Grecia | Italia | Japón | Perú | Egipto | Francia | Reino Unido |
  |---|---|---|---|---|---|---|---|---|---|
  | v1.0 (2015-2026) | 8,26 | 6,49 | 4,65 | 3,24 | 3,32 | 2,42 | 1,92 | 1,89 | 1,68 |
  | v1.1 (2015-2025) | 7,47 | 5,92 | 4,22 | 3,15 | 3,06 | 2,19 | 1,75 | 1,77 | 1,42 |

  El orden de los países casi no cambia; las cifras absolutas sí.
- **`QUERY.txt` se reescribía en cada ejecución** con la fecha del día, de modo que la «fecha de
  congelación» era la de la última corrida y no la de las descargas (11-17 de agosto; el archivo
  decía 28 de agosto). Ahora se escribe una sola vez y el script se niega a continuar si los
  criterios cambian sin subir `VERSION_QUERY`.
- **Falsos positivos de la autorreferencia** (`t6b`): «ayuntamiento», «ukraine» y «human rights»
  salían como sitios UNESCO. «Ukraine» venía de separar nombres transfronterizos («... in Poland
  and Ukraine»); ahora se descartan las variantes que son nombres de país. El resto está en la
  lista de nombres ruidosos.
- **Entidades HTML** en títulos y resúmenes (`&amp;ldquo;`, etiquetas `<p xmlns=...>`) se limpian
  al cargar.
- **Docstring** de `descarga_openalex.py` con un nombre propio; reemplazado.

### Nuevo

- **`agenda.py`**: clasifica cada trabajo como propio / mixto / ajeno según los países que
  nombra, con regiones, marcador de la Ruta de la Seda, series por periodo y año, y análisis de
  sensibilidad bajo nueve definiciones del referente. Sustituye a la autorreferencia por sitios.
- **`comun.py`**: carga de corpus, intervalos de Wilson, buscador de topónimos por n-gramas
  (mucho más rápido que el cotejo regex por variante; reconoce solo palabras completas), regla
  de mayúscula contra palabras comunes, estilo de figuras compartido.
- **`validacion.py`** y `validacion/revision_preliminar_claude.csv`: herramienta para medir la
  precisión sobre una muestra, y una primera revisión de 80 trabajos (precisión 55/55 entre los
  decididos; recuperación de «sin referente» del 35 %). **No sustituye la validación humana.**
- **`tests/test_gazetteer.py`**: 13 pruebas de falsos positivos conocidos.
- **`t1b_sensibilidad.csv`**: la tasa de IA bajo siete definiciones.
- **`t1c_solape.csv`**: cuánto se solapan los corpus nacionales.
- **`requirements.txt`**, **`.gitignore`**, este historial.
- **Intervalos de confianza de Wilson** en todas las proporciones.
- **Figuras** en estilo de énfasis (China en azul, el resto en gris): `f3_agenda.png`,
  `f4_regiones.png`, `f5_serie_agenda.png`; `f1` y `f2` rehechas con intervalos.

### Cambiado

- El corpus B se deriva de A (`n_terminos_ia >= 1`) en vez de leerse de los archivos `B`.
- La normalización de texto ahora elimina la puntuación y deja solo palabras, para poder buscar
  por n-gramas. Los textos y los nombres del diccionario pasan por la misma función.
- La colaboración internacional se calcula sobre trabajos con país de afiliación identificado.
- `README.md` reescrito: hallazgos con intervalos, definiciones, validación y límites.
- Nombres de país con tildes en las tablas (Japón, Perú, España).

### Retirado

- `resultados/t6_autorreferencia.csv` y `t6b_detecciones.csv`, y la opción `--unesco` de
  `analisis.py`. Reemplazados por `agenda.py`. Las cifras de la 1.0 quedan en el historial de git.

### Problemas conocidos

- La **recuperación** del buscador es baja (§ 5.1 del README): la cobertura es un piso.
- El corpus A incluye **taxonomía de especímenes de museo** (1,9-12,9 % según el país).
- Falta la **validación humana independiente**.

---

## 1.0 — agosto-septiembre de 2026

Descarga de nueve países (China, Italia, Grecia, Egipto, Francia, Japón, India, Perú y Reino
Unido) con la consulta v1; análisis de tasa de IA, evolución, técnicas, venues, instituciones y
autorreferencia por sitios UNESCO.
