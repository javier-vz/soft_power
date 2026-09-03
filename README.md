# Inteligencia artificial y patrimonio cultural: un estudio bibliométrico comparado

Este repositorio contiene los datos, el código y los resultados de un estudio sobre
la producción científica que aplica inteligencia artificial al patrimonio cultural,
con especial atención al caso de China y a su comparación con otros países.

La pregunta que organiza el trabajo es sencilla de enunciar y difícil de responder
sin comparación: **¿en qué se distingue la investigación china en este campo?**
Para responderla no basta con describir la producción de un país. Hace falta un
punto de referencia, y por eso el estudio descarga corpus equivalentes de nueve
países usando exactamente la misma consulta.

---

## Cómo está organizado

```
soft_power/
├── descarga_openalex.py     obtiene los corpus desde la API de OpenAlex
├── analisis.py              produce todas las tablas y figuras
├── QUERY.txt                la consulta congelada, con su fecha
├── whc-sites-2025.xls       Lista del Patrimonio Mundial de la UNESCO
├── datos/                   corpus descargados (un archivo por país)
└── resultados/              tablas, figuras e informe
```

---

## Cómo se ejecuta

Se necesita Python 3 con cuatro bibliotecas:

```bash
pip install requests pandas matplotlib xlrd
```

**Paso 1. Descargar los corpus.** Antes de nada conviene comprobar que la consulta
funciona contra la API:

```bash
python descarga_openalex.py --diagnostico
```

Y luego descargar. El proceso es reanudable: si se interrumpe, basta volver a
ejecutarlo y continuará donde quedó.

```bash
python descarga_openalex.py --todos
```

Si la API responde con límite de tasa, conviene ir de a pocos países:

```bash
python descarga_openalex.py --paises it gr eg --pausa 1.5
```

**Paso 2. Analizar.**

```bash
python analisis.py --unesco whc-sites-2025.xls
```

Detecta por sí solo los países disponibles en `datos/` y escribe todo en
`resultados/`. El análisis de autorreferencia patrimonial es el más lento, unos
minutos, porque compara cada trabajo con miles de nombres de sitios.

---

## Qué hace la descarga, y por qué así

La búsqueda se realiza en dos pasos deliberadamente separados.

El **primer paso** consulta la API pidiendo únicamente trabajos sobre patrimonio.
Es el término más específico y, por tanto, el filtro más liviano para el servidor.

El **segundo paso** aplica localmente el filtro de inteligencia artificial sobre el
título y el resumen. Esto tiene dos ventajas sobre enviar una consulta booleana
completa. Evita la sintaxis anidada, que es la parte más frágil de la búsqueda de
OpenAlex y la causa habitual de errores. Y deja el criterio de inclusión como
código versionado y auditable, no como una cadena opaca dentro de una URL:
cualquiera puede revisarlo o ajustarlo sin volver a descargar nada.

De cada país se obtienen dos archivos:

| Archivo | Contenido |
|---|---|
| `openalex_A_<país>_v1.csv` | corpus amplio: todo lo recuperado sobre patrimonio |
| `openalex_B_<país>_v1.csv` | corpus filtrado: lo que además menciona inteligencia artificial |

La proporción entre ambos, **B dividido A**, es la métrica central del estudio: qué
parte de la investigación patrimonial de un país involucra inteligencia artificial.
Es directamente comparable entre países porque no depende del tamaño de cada
sistema científico.

Cada registro guarda además las columnas `terminos_ia_hallados` y `n_terminos_ia`,
que permiten auditar por qué un trabajo entró al corpus B. Si pasó el filtro solo
por mencionar una vez la palabra «convolutional», eso queda a la vista.

---

## Qué produce el análisis

| Archivo | Contenido |
|---|---|
| `t1_panorama.csv` | volumen, tasa de IA, colaboración internacional y citación por país |
| `t2_evolucion.csv` | serie anual de la tasa de IA |
| `t3_tecnicas.csv` | qué técnicas predominan en cada país |
| `t4_venues.csv` | dónde publica cada país |
| `t5_instituciones.csv` | instituciones más productivas y su apertura internacional |
| `t6_autorreferencia.csv` | cuánto estudia cada país su propio patrimonio |
| `t6b_detecciones.csv` | cada detección individual, para revisión manual |
| `f1_evolucion.png` | curvas comparadas de la tasa de IA |
| `f2_colaboracion.png` | colaboración internacional por país |
| `informe.txt` | resumen legible de todo lo anterior |

---

## La medida de autorreferencia patrimonial

Es la parte metodológicamente más delicada, y conviene entender cómo funciona
antes de usar sus resultados.

El procedimiento busca, en el título y el resumen de cada trabajo, el nombre de
algún sitio de la Lista del Patrimonio Mundial. Si el sitio pertenece al país que
firma el trabajo, cuenta como patrimonio propio; si no, como ajeno.

El problema es que los nombres oficiales son largos y compuestos, mientras que los
artículos usan la forma breve. Nadie escribe «Historic Sanctuary of Machu Picchu»:
escriben «Machu Picchu». Por eso el sistema genera **variantes** de cada nombre,
recortando descriptores genéricos y separando los sitios que agrupan varios
lugares. De 1.248 sitios se obtienen unas 3.860 formas buscables.

Esa generación introduce ruido, y el código lo controla con cuatro salvaguardas:

**Búsqueda por palabra completa.** Sin esta precaución aparecen falsos positivos
graves: «berat» (ciudad albanesa) coincide dentro de *deliberate*, «lakes» dentro
de *flakes* (lascas líticas, frecuentísimas en arqueología) y «pirin» dentro de
*inspiring*.

**Filtro por frecuencia.** Un topónimo real no puede aparecer en una fracción
grande del corpus. Las variantes presentes en más del 0,5 % de los trabajos se
descartan automáticamente. Esta regla es preferible a una lista negra manual
porque se adapta al corpus y no depende de anticipar cada fragmento problemático.

**Solo nombres en inglés y español.** El corpus de OpenAlex está indexado en
inglés, de modo que los nombres en francés, ruso, árabe o chino no aportan
recuperación y sí producen colisiones. El caso más claro es «Gênes», nombre francés
de Génova, que coincide con la palabra inglesa *genes* en un corpus científico.

**Sitios transfronterizos preservados.** Se descartan las palabras sueltas
asociadas a muchos países, pero no los nombres de dos o más palabras: un sitio como
el Qhapaq Ñan pertenece legítimamente a seis países y debe conservarse.

Aun así, el emparejamiento es heurístico. Por eso se escribe `t6b_detecciones.csv`
con cada detección individual, su sitio asignado y su clasificación. **Conviene
revisar a mano una muestra y reportar la proporción de aciertos.** Ese archivo ya
resultó útil durante el desarrollo: fue lo que reveló los falsos positivos
descritos arriba.

La columna `cobertura_pct` indica qué proporción del corpus fue posible clasificar.
Es baja, entre el 3 % y el 11 %, y debe declararse: el análisis se realiza sobre el
subconjunto de trabajos donde fue posible identificar un sitio, no sobre el corpus
completo.

---

## Estado actual

Nueve países descargados (China, Italia, Grecia, Egipto, Francia, Japón, India,
Perú y Reino Unido), con la consulta congelada el 28 de agosto de 2026 y el
registro de cada descarga en `datos/log_descarga.csv`.

Tres observaciones preliminares, sujetas a la validación manual pendiente:

**China lidera la penetración de la inteligencia artificial en la investigación
patrimonial**, con una tasa muy superior a la de Italia pese a que ambos países
tienen corpus patrimoniales de tamaño equivalente. La divergencia es reciente:
hasta 2019 todos los países se situaban en valores similares.

**China presenta la colaboración internacional más baja** del conjunto, muy por
debajo de Francia y Japón. Es un dato que matiza cualquier lectura simple sobre
proyección internacional y conviene reportar junto con el anterior.

**El contraste más marcado no es el esperado.** En autorreferencia patrimonial,
China no se distingue de los demás países con gran acervo patrimonial. Quienes se
apartan del conjunto son el Reino Unido y Francia, cuya investigación patrimonial
computacional se dedica mayoritariamente a patrimonio ajeno. Son dos modos
distintos de hacer arqueología computacional: aplicarla sobre lo propio o
exportarla como método.

---

## Pendientes

- Descargar Estados Unidos y España para completar el conjunto de comparación.
- Ejecutar una pasada con `--completo`, que incluye los datos de financiamiento
  (las columnas `grants` y `funders` quedan vacías en el modo rápido).
- Validar manualmente una muestra de cincuenta detecciones y reportar la
  proporción de aciertos.
- Verificar si los sitios chinos se nombran de forma menos detectable que los
  europeos, lo que sesgaría la comparación de cobertura.

---

## Notas para quien reutilice esto

La consulta está congelada en `QUERY.txt` con su fecha. **Si se modifica, hay que
subir el número de versión y volver a descargar todos los países**: mezclar corpus
obtenidos con consultas distintas invalida la comparación, que es justamente lo que
sostiene el estudio.

La carpeta `datos/` ocupa más de 200 MB. Conviene excluirla del control de
versiones mediante `.gitignore` y depositarla en un repositorio de datos con
identificador permanente.
