# Revisión ola 1 — agente G (revisor 1)

**Fecha:** 15 de septiembre de 2026
**Módulos revisados:** `core/color/` (agente A), `core/io/` (agente D), `core/resolve/` + `probe/` (agente E).
**Método:** ejecución. Nada aprobado por lectura del código ni por el informe del autor.
**Intérprete:** `.venv/bin/python` (3.12.14, numpy 2.5.3, colour-science 0.4.x).

**No he tocado ni un módulo.** Todo lo que he escrito está en `tests/revision/test_ola1_*.py`
y en este documento. Los bugs se reportan, no se arreglan: los módulos no son míos.

> **Este documento tiene dos rondas.** La §0 es el estado final tras los
> arreglos (ronda 2). De la §1 en adelante está el trabajo de la ronda 1, tal y
> como se escribió, porque es el que explica por qué se cambió cada cosa.
> Donde un dato de la ronda 1 resultó ser falso, lo digo en la §0 y lo dejo
> tachado en su sitio en vez de borrarlo.

---

# RONDA 2 — re-verificación tras los arreglos

## 0.1 Veredicto actualizado

| Módulo | Ronda 1 | **Ronda 2** | Qué ha cambiado |
|---|---|---|---|
| `core/color/` | aprobado con reservas | **Aprobado** | Los dos hallazgos, cerrados. Las **siete** curvas (con la nueva `srgb`) coinciden con `colour-science` con diferencia **0.0e+00** en todo el dominio −2.88…+11.5, medido por mí sobre 4.011 muestras. Y `convert` devuelve float32 por las dos ramas y valida el tipo por las dos. Sin reservas abiertas. |
| `core/io/` | aprobado con reservas | **Aprobado** | El recuento de banding arreglado (3 escalones agrupados por eje en vez de 20 avisos, y el mensaje dice dónde está: «en el primer intervalo de la rejilla, pegado al negro»). El `.cube` con dos `LUT_3D_SIZE` contradictorios ya se rechaza. **Y D me ha corregido a mí un dato falso**: ver §0.5. |
| `core/resolve/` + `probe/` | aprobado con reservas | **Aprobado con una reserva menor** | La regla de oro ya no es una convención: es un `if` en `BaseResolveBridge`, cubre **las cinco** escrituras de grado y **`LiveResolve` la hereda** (verificado sobre el fuente, sin tocar Resolve). Índices de nodo y `--solo-diagnostico`, cerrados. La reserva es un hallazgo **nuevo** del propio arreglo: §0.4. |
| **Límite duro (escrituras fuera del repo)** | aprobado sin peros | **Aprobado, sin peros** | Sigue verde con los módulos cambiados y con `core/analysis` y `core/matching` ya en el repo. |

## 0.2 La suite entera, ahora

```
$ .venv/bin/python -m pytest
1343 passed, 1 warning in 78.31s (0:01:18)

$ .venv/bin/ruff check tests/revision
All checks passed!
```

**Cero rojos en todo el repo.** Mis 296 tests de revisión incluidos
(122 color + 71 io + 93 resolve + 10 límites).

Durante la re-verificación vi **un rojo transitorio** en
`tests/test_matching_huella.py::test_emparejar_acepta_las_huellas_y_cambia_de_opinion`
(agente C). Lo ejecuté aislado tres veces seguidas: verde las tres, y en la
siguiente pasada completa ya no aparecía. Era C escribiendo en ese momento, no
una regresión de A/D/E. **No es mío ni de los que reviso**; lo digo para que no
se me cuente ni se me olvide.

## 0.3 Qué fue de mis seis rojos

| Test de la ronda 1 | Hoy | Por qué |
|---|---|---|
| `test_curvas_coinciden_con_colour_science_tambien_en_negativos[rec709]` | **verde sin tocarlo** | A cambió la extensión a negativos. Lo he **endurecido**: ahora exijo `== 0.0` (no `< 1e-10`), sobre 4.011 muestras en vez de 130, y con `srgb` añadida al juez. |
| `test_convert_con_la_identidad_rompe_la_promesa_de_dtype` | **verde**, reescrito | Ahora recorre uint8/int32/int64/uint16 y exige float32 por las dos ramas. |
| `test_convert_con_la_identidad_ni_siquiera_valida_el_tipo` | **reescrito** | Arbitrado **en mi contra y con razón**: daba por bueno `bool → bool`, que era la foto de un defecto, no un requisito. Ahora exige `TypeError` por las dos ramas, para bool y para complex. |
| `test_un_cube_con_dos_LUT_3D_SIZE_contradictorios_se_traga_el_ultimo` | **verde sin tocarlo** | D lo rechaza. |
| `test_un_indice_de_nodo_decimal_se_trunca_en_SILENCIO` | **reescrito** | Mi test **se contradecía consigo mismo** (afirmaba el valor truncado *y* que esa misma llamada lanzara): era rojo con el bug y sin él. Arbitraje correcto. Ahora sólo el `raises`, sobre 11 entradas, y renombrado. |
| `test_un_indice_decimal_escribe_el_cdl_en_el_nodo_equivocado` | **reescrito** | Pedía implícitamente redondear. Ahora envuelve el `set_cdl` en `raises` y comprueba que no queda nada escrito. |
| `test_solo_diagnostico_DICE_que_no_escribe_nada...` | **verde sin tocarlo** | E lo arregló. |
| `test_un_codificado_de_200_desborda_a_infinito[srgb]` | **reescrito** | Rojo *nuevo* al aparecer `srgb`: mi `parametrize` recorría `SPACES`, así que un espacio nuevo entraba solo. La premisa («un codificado de 200 desborda») vale para las cinco curvas **logarítmicas** y no para una ley de potencia. Partido en dos tests, con el techo real de las de potencia medido (~1e200). |
| `test_fakeresolve_no_ofrece_ninguna_forma_PUBLICA_de_leer_el_cdl` | **verde**, una línea de montaje | Daño colateral: el montaje usaba un `set_cdl` crudo, que ahora lanza. **Verifiqué el fondo yo mismo**, que era lo que más me preocupaba: sigue sin haber fuga. Detalle en §0.6. |

**Tests nuevos de la ronda 2:** 45 (296 ahora frente a 251 entonces).

## 0.4 Hallazgo NUEVO, del propio arreglo (gravedad baja)

### La vía de escape protege mejor al falso que al puente de verdad

`PELIGRO_escribir_fuera_de_la_version` es un atributo **de clase** en
`BaseResolveBridge`. `FakeResolve.__init__` lo reasigna **en la instancia**;
`LiveResolve.__init__` **no**. Consecuencia, medida:

```
BaseResolveBridge.PELIGRO_escribir_fuera_de_la_version = True
  -> LiveResolve(...).PELIGRO_escribir_fuera_de_la_version == True    (regla APAGADA)
  -> FakeResolve(...).PELIGRO_escribir_fuera_de_la_version == False   (regla puesta)
```

Una línea perdida en cualquier punto del proceso apaga la regla de oro **en el
puente de verdad** y la deja puesta **en el falso**. Es exactamente la asimetría
que ningún test contra `FakeResolve` puede cazar, que es por lo que la escribo
mirando las dos clases a la vez.

No lo dejo rojo: hace falta que alguien escriba ese nombre horrible a propósito,
y la vía de escape tiene que existir. Pero el arreglo es una línea en
`LiveResolve.__init__` y deja las dos implementaciones simétricas, que es lo que
uno espera de una clase base.

- **Test:** `test_ola1_resolve.py::test_HALLAZGO_envenenar_la_clase_base_apaga_la_regla_en_Live_pero_no_en_Fake` (verde, documenta; se borra el día que se arregle).
- **Rebotar a:** agente **E**.

## 0.5 Un dato de mi informe de la ronda 1 era FALSO. Lo corrijo

En la §3.2 escribí que el zip-bomba con índice mentiroso *«obliga a leer un
cuarto de giga a memoria antes de decir que no»*, con una medición de
«430 → 686 MB de RSS».

**Es falso, y el error era de método**: estaba midiendo el RSS del proceso que
**fabrica** el zip (que sí reserva los 400 MB del payload), no el de
`abrir_sesion`. D me lo corrigió y tiene razón.

Medido bien, en un proceso limpio que sólo abre el fichero ya fabricado:

| | ronda 1 (mal medido) | **ronda 2 (bien medido)** |
|---|---|---|
| subida de RSS | «+256 MB» | **+0,0 MB** |
| tiempo | — | **0,4 ms** |

El motivo: `ZipExtFile` limita lo que descomprime al `file_size` que declara el
directorio central, así que un índice que miente diciendo 10 bytes hace que se
lean 10 bytes. El fallo sale después, en el CRC. **Mentir a la baja no compra
nada.** Pido disculpas por el dato: un número falso en un documento de revisión
manda a alguien a optimizar un problema que no existe.

**Dónde sí hay amplificación**, ya que estamos, medido: un índice **honesto**
justo por debajo del tope. Una entrada que declara 250 MB pasa el chequeo
(250 < 256) y se lee entera; comprimida es un zip de ~250 KB, o sea **~1.000:1**,
y ahí sí suben 500 MB de RSS. No es un bug (el presupuesto de 256 MB está
documentado y el fallo es limpio), pero es el número a mirar si algún día se
quiere apretar. Test: `test_el_coste_de_memoria_esta_en_el_indice_honesto_no_en_el_que_miente`.

## 0.6 Lo que he vuelto a comprobar yo, no por su palabra

- **Las siete curvas contra `colour-science`**, 4.011 muestras de −2.88 a +11.5:
  diferencia máxima **0.000e+00** en las siete, `srgb` incluida. Y la ida y
  vuelta sigue siendo exacta en negativos (< 1e-9 en los dos lados del corte),
  que es lo que se rompe con facilidad al mover cómo se extiende una curva.
- **El argumento de A sobre por qué el cambio no duele**: dice que a la app no le
  cambia un píxel porque los negativos acaban recortados o sujetos al borde por
  `LUT3D.apply`. **Me convence, pero no es la razón que importa.** La razón
  buena es la que él mismo da en el comentario del código: las dos extensiones
  son monótonas e invertibles, así que el contrato 1 se cumple con cualquiera de
  las dos, y **lo que decide es poder verificarlo contra un juez independiente**.
  Quedarse con la que no se puede comprobar, para ahorrarse un cambio que no
  cambia un píxel, habría sido el mal negocio.
- **La regla de oro, las cinco escrituras.** `set_cdl`, `set_lut`,
  `set_node_enabled`, `copy_grades` y `reset_all_grades`: las cinco lanzan
  `EscrituraFueraDeVersion` sobre `Version 1` y las cinco funcionan dentro de
  `SIDEB COLOR`. Encontré dos que en la ronda 1 no había probado
  (`set_node_enabled` y `reset_all_grades`) y también están cubiertas.
- **`copy_grades` es atómico**: comprueba **todos** los destinos antes de tocar
  ninguno. Verificado con dos destinos, uno bueno y uno malo: el bueno conserva
  intacto su LUT.
- **`LiveResolve` hereda la regla de verdad**, no es una red de pruebas: hereda
  de `BaseResolveBridge` y llama a `_exigir_version_propia` **cinco veces**, las
  mismas que `FakeResolve`. Comprobado leyendo el AST de `live.py`, sin importar
  `DaVinciResolveScript` (verificado además en proceso limpio: importar
  `core.resolve.live` no carga ningún módulo de Resolve).
- **La vía de escape**: apagada por defecto, es atributo y no método (no se puede
  llamar de pasada), un typo en el constructor es `TypeError`, y dentro de
  `core/` no la usa nadie.
- **La fuga de lectura de CDL sigue sin existir** — era lo que más me preocupaba
  y lo he vuelto a mirar entero, no sólo la línea que fallaba: el único público
  con «cdl» en el nombre es `set_cdl`, no hay `get_cdl`, `NodeInfo` sigue
  teniendo sólo `index/label/enabled/lut_path`, y los públicos de más respecto
  al `Protocol` son **los mismos siete** de la ronda 1. Ninguno nuevo.
- **El recuento de banding de D**: 3 avisos agrupados por eje (antes 20), métrica
  nueva `escalones_de_banding = 3`, y el mensaje ahora dice «en el primer
  intervalo de la rejilla (pegado al negro)», que es literalmente el diagnóstico
  de la ronda 1. Los cuatro LUT legítimos limpios siguen limpios, la identidad
  sigue limpia en 2/17/33/65 y el escalón de 0,3 se sigue cazando.

## 0.7 Donde D tiene razón contra mí: mis tests le cerraban las salidas

D dice que dos de mis tests fijaban cifras que cerraban las dos salidas que yo
mismo le había propuesto. **Lo he comprobado y es verdad, las dos veces:**

| Mi aserción de la ronda 1 | Qué salida cerraba |
|---|---|
| `sucios[...] == [17, 33, 65]` (la gamma sale sucia en los tres tamaños) | Si D excluía el primer intervalo de la rejilla, la gamma saldría **limpia** y mi test se pondría rojo. |
| `metricas['celdas_con_banding'] == 3*n*n` | Si D contaba posiciones distintas en esa métrica, saldría 3 y mi test se pondría rojo. |

Es un error de método mío, y merece la pena dejarlo escrito porque es fácil de
repetir: **un test de revisión tiene que afirmar el defecto, no la
implementación concreta del defecto.** Al congelar el número exacto convertí mi
propia recomendación en algo que el autor no podía aplicar sin romperme un test
—y D acabó teniendo que añadir una métrica nueva (`escalones_de_banding`) en vez
de arreglar la vieja, que era lo limpio.

**He relajado los dos yo mismo.** Ahora afirman lo que de verdad creo que tiene
que cumplirse (los limpios siguen limpios; si la gamma se marca es sólo por
banding; los avisos van agrupados y apuntan al primer intervalo) y miden el
recuento sin congelarlo, enseñándolo en el mensaje del `assert`.

En lo de **no subir el umbral, D tiene razón y yo también**: es un verdadero
positivo (se desvía 11/255 de la curva que dice representar incluso con 65
puntos) *y* el recuento engañaba. Ha arreglado lo segundo sin tocar lo primero,
que es exactamente lo correcto. Retiro la parte de mi §3.4.1 donde daba a
entender que el aviso sobraba: lo que sobraba era el «12.675».

## 0.8 ¿Ha introducido alguna regresión algún arreglo?

**No, ninguna.** Lo he mirado en los tres frentes:

- La suite entera está en verde (1343), con los tests propios de A, D y E, los de
  B y C, y los míos.
- El camino bueno sigue funcionando: escribí un test por cada una de las cinco
  escrituras **dentro** de `SIDEB COLOR`, porque una protección que además
  impide trabajar es un bug, no una protección. Las cinco devuelven True.
- `aplicar_grado_seguro` sigue haciendo la secuencia en orden
  (`open_page → version_names → add_version → … → set_cdl → set_lut → get_lut`)
  y sigue siendo idempotente.
- El límite duro (nada se escribe fuera del repo) sigue verde con el código
  cambiado.

## 0.9 De qué sigo sin fiarme

1. **De `LiveResolve`, entero.** Sigue sin ejecutarse ni una línea contra Resolve
   de verdad. Ahora tiene además la regla de oro dentro, lo cual es bueno, pero
   significa que hay cinco llamadas más de `current_version()` por escritura que
   nadie ha visto funcionar. Si `current_version()` devuelve algo inesperado con
   Resolve delante (una cadena vacía, `None`), la regla de oro **bloquearía todas
   las escrituras** y la app no serviría para nada hasta que alguien lo viera.
   **Es lo primero que probaría mañana con Resolve abierto**, antes que las seis
   incógnitas.
2. **De `es_version_nuestra`, un poco.** Va por nombre porque no hay otra forma
   (la API no marca quién creó una versión), y el autor lo dice. Pero si Mario
   tiene una versión suya llamada `SIDEB COLOR algo`, la app se la creerá suya y
   escribirá encima. Es improbable y está documentado; lo dejo dicho.
3. **De la asimetría de la vía de escape** (§0.4), hasta que se cierre.
4. **De que la semántica de `FakeResolve` sea la de Resolve.** No ha cambiado
   nada en esta ronda y sigue siendo el riesgo de fondo, como dice el propio E.

---

# RONDA 1 — el trabajo original

## 0. Veredicto en una línea por módulo *(ronda 1; sustituido por la §0.1)*

| Módulo | Veredicto | Por qué |
|---|---|---|
| `core/color/` | **Aprobado con reservas** | La matemática aguanta todo lo que le he tirado. Pero la afirmación de NOTAS.md de que las seis curvas coinciden con `colour-science` **no es cierta para `rec709` con entrada negativa**, y el contrato 1 dice que los negativos son legales. Y `convert(x, X, X)` se salta la promesa de dtype y toda validación de tipo. |
| `core/io/` | **Aprobado con reservas** | Las defensas de ficheros hostiles son de las mejores que he visto: he fabricado zip-slip, zip-bomba con índice mentiroso, `.npy` con pickle y billion-laughs en UTF-16, y no ha caído ninguno. La reserva es el **detector de banding**: marca la curva de gamma de salida (el LUT más común que existe) en 17, 33 **y 65**, y la métrica que enseña exagera el problema ×4.225. Más un hueco menor de ambigüedad al leer. |
| `core/resolve/` + `probe/` | **Aprobado con reservas** | `aplicar_grado_seguro` hace las cosas en el orden correcto y lo he verificado. Pero **la regla de oro no la impone nadie**: `set_cdl`, `set_lut` y `copy_grades` escriben en la versión del usuario sin pasar por `AddVersion`. Además hay una truncación silenciosa de índices de nodo y `--solo-diagnostico` dice que no escribe nada y escribe dos ficheros. |
| **Límite duro (escrituras fuera del repo)** | **Aprobado, sin peros** | Ni `core/color`, ni `core/io`, ni `core/resolve` escriben fuera de la ruta que les pasan. Comprobado estática **y** dinámicamente. Detalle sobre `probe/` en §5. |

---

## 1. Lo que corrí, con la salida real

### 1.1 Estado de partida (antes de escribir nada mío)

```
$ .venv/bin/python -m pytest -q
........................................................................ [ 12%]
........................................................................ [ 24%]
........................................................................ [ 36%]
........................................................................ [ 48%]
........................................................................ [ 60%]
........................................................................ [ 72%]
........................................................................ [ 84%]
........................................................................ [ 96%]
..................                                                       [100%]
594 passed in 3.33s
```

Verde de verdad. Los 298 + 140 + 115 tests que dicen A, D y E existen y pasan.

### 1.2 Mi suite de revisión

```
$ .venv/bin/python -m pytest tests/revision -q
...F....................F............................................... [ 28%]
..........................................................F............. [ 57%]
.............................................FF......................... [ 86%]
................................F..                                      [100%]
FAILED tests/revision/test_ola1_color.py::test_curvas_coinciden_con_colour_science_tambien_en_negativos[rec709]
FAILED tests/revision/test_ola1_color.py::test_convert_con_la_identidad_rompe_la_promesa_de_dtype
FAILED tests/revision/test_ola1_io.py::test_un_cube_con_dos_LUT_3D_SIZE_contradictorios_se_traga_el_ultimo
FAILED tests/revision/test_ola1_resolve.py::test_un_indice_de_nodo_decimal_se_trunca_en_SILENCIO
FAILED tests/revision/test_ola1_resolve.py::test_un_indice_decimal_escribe_el_cdl_en_el_nodo_equivocado
FAILED tests/revision/test_ola1_resolve.py::test_solo_diagnostico_DICE_que_no_escribe_nada_y_escribe_dos_ficheros
6 failed, 245 passed
```

```
$ .venv/bin/ruff check tests/revision
All checks passed!
```

### 1.3 La suite entera al terminar

```
$ .venv/bin/python -m pytest
=========================== short test summary info ============================
FAILED tests/revision/test_ola1_color.py::test_curvas_coinciden_con_colour_science_tambien_en_negativos[rec709]
FAILED tests/revision/test_ola1_color.py::test_convert_con_la_identidad_rompe_la_promesa_de_dtype
FAILED tests/revision/test_ola1_io.py::test_un_cube_con_dos_LUT_3D_SIZE_contradictorios_se_traga_el_ultimo
FAILED tests/revision/test_ola1_resolve.py::test_un_indice_de_nodo_decimal_se_trunca_en_SILENCIO
FAILED tests/revision/test_ola1_resolve.py::test_un_indice_decimal_escribe_el_cdl_en_el_nodo_equivocado
FAILED tests/revision/test_ola1_resolve.py::test_solo_diagnostico_DICE_que_no_escribe_nada_y_escribe_dos_ficheros
6 failed, 1027 passed in 23.33s
```

**Los seis rojos son míos y están puestos a propósito.** Nada de A, D ni E se ha
puesto rojo por mi culpa.

Sobre los agentes que trabajaban a la vez, y que **no he revisado**:

- **Agente B (`core/analysis/`)**: aterrizó durante la noche con 117 tests
  (`test_analysis_stats/huella/frames/bordes`). Todos en verde.
- **Agente C (`core/matching/`)**: aterrizó mientras yo cerraba, con
  `test_matching_cdl.py` y `test_matching_mkl.py`. En una pasada intermedia le vi
  un rojo (`test_matching_cdl.py::test_listas_de_distinta_longitud_funcionan`)
  que en la pasada siguiente ya estaba arreglado: está trabajando ahora mismo.
  **No es mío ni de los que reviso**; lo digo sólo para que nadie me lo cuente
  como un rojo de esta revisión.

Reparto aproximado de los tests recolectados (la cifra de B y C se mueve porque
siguen escribiendo):

| Fichero | Tests | Fichero | Tests |
|---|---:|---|---:|
| `test_color_spaces` | 88 | `test_resolve_fake` | 57 |
| `test_color_bordes` | 88 | `test_io_cube` | 43 |
| `test_color_transfer` | 69 | `test_io_qc` | 31 |
| `test_color_perceptual` | 53 | `test_io_cdl` | 30 |
| `test_analysis_*` (agente B) | 117 | `test_matching_*` (agente C) | ~71 |
| `test_resolve_*` | 115 | `test_io_hald` | 12 |
| `test_contratos` / `test_media_generate` | 41 | **`tests/revision/*` (míos)** | **251** |

---

## 2. `core/color/` — agente A

### Veredicto: **aprobado con reservas**

### 2.1 «¿Qué entrada plausible rompe esto?»

**Una imagen con valores negativos, si alguien compara `rec709` contra
`colour-science`.** Es plausible: material log convertido, un gamut mapping que
deja negativos (que el propio contrato 1 manda preservar), o simplemente que
mañana el agente H use `colour` para pintar una vista previa y salgan dos
imágenes distintas.

Y **una imagen uint8**, que es exactamente lo que le llega a la GUI de un PNG:
`convert(img, "rec709", "rec709")` le devuelve uint8 sin avisar.

Fuera de ahí, **no he encontrado nada más y lo he intentado en serio**: NaN en
las catorce funciones públicas, valores codificados de −0.5 a 200, imagen negra
entera, blanca entera, un canal a cero, rojo saturado puro, arrays vacíos,
formas degeneradas, la discontinuidad de 275°, croma que desborda el float64 y
L\* negativa. Todo aguanta. Lo digo con la salida delante, no de oídas.

### 2.2 Bugs

#### BUG A-1 — `rec709` NO coincide con `colour-science` en negativos (media)

`core/color/NOTAS.md` §2 afirma: *«Los seis salen **idénticos** (diferencia
máxima 0.0e+00, literal) a los de `colour-science`»*.

El test del autor (`test_coincide_con_colour_science`) barre
`0.18 * 2**linspace(-6, 6)` más `0.0, 0.18, 0.9, 1.0`. **Todo positivo.** Con
entrada negativa:

| x (escena-lineal) | `log_encode(x, "rec709")` | `colour.models.oetf_BT709` | diferencia |
|---:|---:|---:|---:|
| −0.05 | −0.186452726 | −0.225000000 | **3.855e-02** |

Las otras cinco curvas coinciden con diferencia **0.0** también en negativos
(lo afirma `test_las_otras_cinco_curvas_si_aguantan_los_negativos`, que está en
verde). El fallo es de `rec709` sola.

El motivo: el módulo extiende la BT.709 por **simetría impar** (`f(−x) = −f(x)`)
y `colour` extiende la **rama lineal** (`4.5·x`). 3.9e-2 son ~39 códigos de 10
bits, casi 4 IRE.

**No digo que la implementación esté mal** — la simetría impar es monótona,
invertible y es lo que hace Resolve. Digo que:

1. la afirmación de NOTAS.md está sobrevendida y hay que corregirla;
2. el único juez independiente del proyecto discrepa en un dominio que el
   contrato 1 declara legal, y eso hay que **elegirlo a conciencia**, no
   descubrirlo cuando dos imágenes no cuadren;
3. el test del autor no cubre lo que su propia nota promete.

- **Test:** `tests/revision/test_ola1_color.py::test_curvas_coinciden_con_colour_science_tambien_en_negativos[rec709]` — **ROJO**
- **Arreglo:** una línea en NOTAS.md si se decide quedarse con la simetría impar
  (y ampliar el barrido del test del autor a negativos para que quede atado), o
  cambiar `_bt709_encode` si se prefiere cuadrar con colour.

#### BUG A-2 — `convert(x, X, X)` rompe la promesa de dtype y no valida nada (baja-media)

El docstring del módulo promete float32 salvo entrada float64. La rama
`src == dst` hace `arr.copy()` y devuelve el dtype de entrada, sea el que sea:

| entrada | `convert(x, "rec709", "rec709")` | `convert(x, "rec709", "linear_rec709")` |
|---|---|---|
| float64 | float64 ✅ | float64 ✅ |
| float32 | float32 ✅ | float32 ✅ |
| **uint8** | **uint8** ❌ | float32 ✅ |
| **bool** | **bool**, sin error ❌ | `TypeError` ✅ |

Quien llama no puede saber qué le van a devolver sin mirar antes si los dos
espacios coinciden. Y un uint8 cruzando una frontera entre módulos es justo lo
que prohíbe el contrato 1.

- **Tests:** `test_convert_con_la_identidad_rompe_la_promesa_de_dtype` (**ROJO**) y
  `test_convert_con_la_identidad_ni_siquiera_valida_el_tipo` (verde, documenta el otro lado).
- **Arreglo:** validar y castear también en la rama de identidad. Ojo: hay que
  hacerlo sin perder la copia bit a bit de float32/float64, que **sí** funciona
  y está atada en `test_convert_identidad_es_exacta_bit_a_bit_incluso_con_nan_e_infinitos`.

#### Observaciones menores (no son bugs, quedan escritas)

- Un valor **codificado de 200** desborda a `inf` en cinco de las seis curvas, con
  un `RuntimeWarning: overflow` **no silenciado**, a diferencia de lo que hace
  `_frac_c7` en `perceptual.py`, que sí lo silencia a propósito. Incoherencia
  cosmética. Test: `test_un_codificado_de_200_desborda_a_infinito` (verde).
- `delta_e2000_mean` sobre un array **vacío** devuelve NaN y suelta
  `RuntimeWarning: Mean of empty slice`. Un clip de cero fotogramas llegará aquí
  como array vacío y el agente C recibirá un NaN que no viene de ningún píxel
  roto. Merece un mensaje propio. Test: `test_delta_e2000_mean_de_una_imagen_vacia_da_nan_con_aviso` (verde).

### 2.3 Lo que he verificado y ESTÁ BIEN (no me lo he creído, lo he corrido)

- **NaN se propaga en las catorce funciones públicas**, no en dos. Comprobado una
  por una, y además con el NaN entrando por a\* y b\*, no sólo por L\*
  (14 + 3 tests, todos verdes). `skin_mask_oklab` devuelve `False`, que es lo
  correcto para un tipo booleano.
- **La ida y vuelta en los extremos.** Un −0.5 y un 9.5 codificados vuelven con
  error < 1e-9 en las seis curvas. El 9.5 en S-Log3 son ~8e39 de escena-lineal,
  que **no cabe en float32**: si algún paso intermedio bajara la precisión esto
  saldría infinito. El apaño de `encode_raw`/`decode_raw` funciona.
- **`convert(x, X, X)` es la identidad EXACTA bit a bit**, NaN e infinitos
  incluidos. Comparado con `tobytes()`, no con `allclose`.
- **ΔE2000 en la discontinuidad de 275°.** 801 muestras barriendo h = 255..295
  contra `colour.difference.delta_E_CIE2000`: diferencia máxima **4.44e-16**.
  Y los seis casos degenerados (croma cero en los dos, croma cero en uno,
  tonos a caballo de 0/360, croma de 1e5 que desbordaría un `C**7` ingenuo,
  L\* negativa, el cero absoluto) cuadran con colour a < 1e-9.
- **La máscara de piel, tono a tono**, medida por mí contra
  `studio_scene(...).skin_mask`. **La tabla de NOTAS.md §6 es exacta**,
  decimal a decimal: exhaustividad 0,967 / 1,000 / 1,000 / 1,000 / 0,992 /
  **0,900**, y precisión 0,79 / 0,70 / 0,67 / 0,69 / 0,75 / 0,84.
- **El camino de tierra del exterior: sí se lo traga**, 1,75% de la imagen, como
  dice el autor. Rampa de gris: 0,0000 exacto. ColorChecker: 15,7%.
  Los tres números atados en un test.

### 2.4 Dónde discrepo del `NOTAS.md` de A

1. **§2, «los seis salen idénticos, diferencia 0.0e+00»** — falso para `rec709`
   en negativos. Ver BUG A-1. Es la única afirmación de todo el documento que no
   se sostiene, y por lo demás el documento es notablemente honesto.
2. **§3.4, «se respeta la precisión que te den»** — es una buena política, pero
   la rama de identidad de `convert` la lleva al absurdo (uint8 dentro, uint8
   fuera). Ver BUG A-2.
3. **§6, el suelo de croma absoluto de 0,015 que pierde el 10% de la piel más
   oscura** — el autor lo plantea como discutible y lo deja. **Estoy de acuerdo
   con su decisión**, y lo digo explícitamente: bajarlo mete el pelo y la
   precisión del tono 5 se desploma. Pero el número (0,900 de exhaustividad en
   el tono más oscuro frente a 1,000 en los medios) tiene que estar en la GUI
   cuando la confianza se calcule sobre piel oscura, no sólo en un `NOTAS.md`.
   Es un sesgo medido y conocido; que no se pierda.

---

## 3. `core/io/` — agente D

### Veredicto: **aprobado con reservas**

### 3.1 «¿Qué entrada plausible rompe esto?»

**Ningún fichero hostil.** Le he fabricado 20 `.cube` rotos, 11 CDL hostiles
(incluyendo un billion-laughs colado en UTF-16 para esquivar el `re.search`) y
seis zips maliciosos construidos byte a byte, y no ha caído ni uno. No he
conseguido ni una ejecución de código, ni un `MemoryError`, ni un traceback que
no fuera un `ErrorIO` en castellano.

Lo que sí rompe el módulo en el sentido de «lo hace inútil» es **un LUT
perfectamente legítimo**: la curva de gamma de salida `x**(1/2.2)`, que es el
LUT más común del mundo. Sale marcado como banding en 17, 33 **y 65**, con la
métrica diciendo «12.675 celdas». Si Mario abre tres LUT de salida y los tres le
salen en rojo, deja de mirar los avisos, y entonces el QC no sirve para nada —
que es literalmente lo que el docstring de `qc.py` dice que hay que evitar.

Y un hueco pequeño de ambigüedad: un `.cube` con **dos `LUT_3D_SIZE`
contradictorios** se acepta en silencio.

### 3.2 Bugs

#### BUG D-1 — El QC marca la curva de gamma de salida en los tres tamaños (media)

Medido sobre siete LUT legítimos × 3 tamaños:

| LUT legítimo | N=17 | N=33 | N=65 |
|---|---|---|---|
| identidad | limpio | limpio | limpio |
| contraste suave (smoothstep) | limpio | limpio | limpio |
| curva en S suave | limpio | limpio | limpio |
| viraje cálido | limpio | limpio | limpio |
| desaturación 50% | limpio | limpio | limpio |
| gamma 2.2 (pantalla → lineal) | limpio | limpio | limpio |
| **gamma de salida `x**(1/2.2)`** | **banding** | **banding** | **banding** |
| CDL realista → LUT | gamut (correcto) | gamut | gamut |

**Falsos positivos de banding: 3 de 24 combinaciones**, todos de la misma curva.
Y aquí está la disección, que es lo importante:

| N | `metricas['celdas_con_banding']` | posiciones del eje realmente marcadas | peor salto |
|---:|---:|---|---:|
| 17 | 867 | **sólo el índice 0** (de 0..14) | 0,1786 |
| 33 | 3.267 | **sólo el índice 0** (de 0..30) | 0,1303 |
| 65 | **12.675** | **sólo el índice 0** (de 0..62) | 0,0951 |

**Es UN escalón de rejilla, el primero, pegado al negro, contado una vez por cada
línea paralela y por cada eje** (3 ejes × 65 × 65 = 12.675). La curva tiene
pendiente infinita en 0, así que el primer intervalo siempre se sale, con
cualquier número de puntos y con cualquier curva de tipo log o gamma. Subir el
número de puntos no lo arregla nunca.

Así que discrepo del autor en dos cosas a la vez:

- No es sólo «`t**0.45` se marca y es un verdadero positivo». Es **toda la
  familia de curvas de codificación de salida**, que es lo que la gente mete en
  un LUT, y se marca **también con 65 puntos**, donde el remedio que propone el
  autor («el remedio es 65 puntos, no bajar el umbral») ya no existe.
- **La métrica engaña por un factor de 4.225.** Decir «12.675 celdas con
  banding» cuando es una posición de rejilla es lo que hace que un aviso
  correcto parezca una catástrofe.

**Lo que propondría** (y no toco, porque no es mi módulo): excluir el primer y el
último intervalo de cada eje del detector, o contar **posiciones distintas** del
eje en vez de pares (línea, posición). Las dos cosas son pequeñas y arreglan el
problema sin subir `SALTO_MINIMO_BANDING`, que es lo que el autor propone en su
§10.1 y que **sí** mataría la detección de escalones de verdad.

> **Ronda 2.** D agrupó los avisos por eje (3 en vez de 20) y añadió la métrica
> `escalones_de_banding`, sin tocar el umbral. Y me hizo ver que mis dos tests
> de esta sección **congelaban las cifras** y le cerraban las dos salidas que yo
> mismo proponía aquí. Tenía razón; los he relajado. Ver §0.7.

- **Tests:** `test_cuantos_falsos_positivos_da_el_qc_sobre_luts_legitimos` y
  `test_el_banding_de_la_gamma_de_salida_es_UN_escalon_contado_miles_de_veces`
  (los dos **verdes**: documentan y atan los números medidos).
- **Contrapeso, para que nadie "arregle" esto subiendo el umbral:**
  `test_el_qc_encuentra_el_escalon_de_verdad_cuando_lo_hay` — un salto de 0,3 en
  mitad de la rampa tiene que seguir cazándose.

#### BUG D-2 — Dos `LUT_3D_SIZE` contradictorios se aceptan en silencio (baja)

```
LUT_3D_SIZE 2
LUT_3D_SIZE 3
0.5 0.5 0.5      (×27)
```
→ se lee tan tranquilo como un LUT de 3.

El módulo rechaza `LUT_3D_SIZE` y `LUT_1D_SIZE` a la vez con un mensaje
impecable («no sé cuál de los dos leer»). Dos `LUT_3D_SIZE` distintos es la
misma ambigüedad y el mismo síntoma (un fichero cortado y pegado, o dos LUT
concatenados por un exportador roto), y ahí no avisa nadie: gana el último.

- **Test:** `test_un_cube_con_dos_LUT_3D_SIZE_contradictorios_se_traga_el_ultimo` — **ROJO**
- **Arreglo:** tres líneas, el mismo patrón que ya existe para el caso 3D+1D.

#### Observaciones menores

- **Zip-bomba con índice mentiroso: la defensa aguanta.**
  Fabriqué un zip de **398 KB** con una entrada de 400 MB y parcheé a mano el
  `uncompressed size` del directorio central para que dijera 10 bytes. El
  chequeo de `_revisar_zip` pasa (suma 10) y la única defensa que queda es el
  tope duro de `_leer_entrada`, que **funciona** y levanta `ErrorBundle`.
  ~~Pero ese tope es `max_descomprimido` (256 MB), así que un fichero de 398 KB
  obliga a leer un cuarto de giga a memoria antes de decir que no (medido: el
  RSS del proceso sube de 430 a 686 MB).~~
  **DATO FALSO, corregido en la ronda 2 — ver §0.5.** Lo medí mal (era el RSS
  del proceso que fabricaba el zip, no el de `abrir_sesion`). El coste real es
  **0,0 MB y 0,4 ms**: `ZipExtFile` limita lo que descomprime al `file_size`
  declarado, así que mentir a la baja no compra nada. Lo que sí queda en pie es
  que el mensaje dice «Bad CRC-32» y no «zip-bomba», que despista.
- **Entradas duplicadas en el zip.** Un `.sidebcolor` con dos `session.json`
  hace que gane la segunda. Hoy es inofensivo (no se extrae nada al disco) pero
  el día que alguien añada «extraer miniaturas a una carpeta», el fichero que se
  valida y el que se extrae podrían no ser el mismo. Test verde documentándolo.
- **La bomba de UTF-16 no la para el filtro que el autor cree.** El
  `re.search(r"<!\s*(DOCTYPE|ENTITY)")` no casa contra un billion-laughs
  codificado en UTF-16. Lo que salva la situación es la capa de antes: el
  `crudo.decode("utf-8-sig")` estricto, que rechaza el UTF-16. La defensa
  aguanta, pero **aguanta por una razón distinta de la que dice NOTAS.md §5**, y
  eso importa el día que alguien "mejore" la lectura aceptando otros encodings.
  Dejo el test puesto para que ese día salte.

### 3.3 Lo que he verificado y ESTÁ BIEN

- **Los ejes, por un fichero de verdad.** Escribí un LUT en el que sólo el rojo
  depende de la entrada roja, lo pasé por el disco y lo releí: sigue tocando el
  rojo. Y el `.cube` y el HALD usan órdenes **opuestos**, que es correcto, y los
  dos están atados en el mismo test.
- **20 ficheros `.cube` hostiles**, todos rechazados con `ErrorFormatoCube` en
  castellano: vacío, sólo espacios, binario con NUL, UTF-16 con BOM,
  `LUT_3D_SIZE 4096` (los 824 GB), 0, −3, 1, «treinta y tres», declarar 8 filas y
  traer 7, declarar 8 y traer 9, `nan`, `inf`, 4 números por línea, 3D y 1D a la
  vez, sin cabecera, cabecera después de los datos, `DOMAIN_MIN > DOMAIN_MAX`,
  `DOMAIN_MIN nan`, y un acento en latin-1. Ni un traceback.
- **Y 6 ficheros raros pero legítimos que SÍ se leen**: BOM de UTF-8, CRLF de
  Windows, CR solo de Mac clásico, comas, punto y coma, tabuladores. Un lector
  demasiado estricto sería igual de inútil.
- **Zip-slip: 7 rutas hostiles**, todas rechazadas con el archivo entero,
  fabricando el zip a mano y no con la API del módulo: `../../../../etc/passwd`,
  `/etc/passwd`, `luts/../../fuera.cube`, `C:/Windows/...`, `luts\..\..\...`,
  `./x.cube` y `luts//x.cube`.
- **`.npy` con pickle: NO ejecuta nada.** Fabriqué un `.npy` cuyo pickle llamaba
  a `os.system` para crear un fichero testigo. Falla al cargarlo y el testigo no
  aparece. `allow_pickle=False` es la línea más importante de todo `core/io` y
  está bien puesta.
- **11 CDL hostiles**, todos rechazados: billion laughs en UTF-8 y en UTF-16,
  XXE con `file:///etc/passwd`, `<! DOCTYPE` con espacio, vacío, no-XML, XML sin
  `ColorCorrection`, `Power 0`, `Slope nan`, `Slope` con 2 números, y
  anidamiento de 5.000 niveles (que no revienta la pila de expat). Y el CDL
  legítimo con namespace `urn:ASC:CDL:v1.2` sí se lee.
- **La identidad pasa limpia en 2, 17, 33 y 65.** La regla de oro del QC se
  cumple.
- **El modo exacto del bundle funciona de verdad.** Con valores de 1.2e-7 y de
  1000.125 en la misma tabla, `decimales=None` da ida y vuelta **bit a bit**
  (`tobytes()` idéntico) y `decimales=6` no. La explicación de las nueve cifras
  significativas frente a los nueve decimales es correcta y está bien medida.
- **`escribir_cube` con un NaN no deja un fichero a medias.**

### 3.4 Dónde discrepo del `NOTAS.md` de D

1. **§3, «el remedio es 65 puntos, no bajar el umbral»** — no es cierto para
   las curvas de codificación de salida: con 65 puntos se sigue marcando, porque
   el problema es el primer intervalo de la rejilla y la pendiente infinita en 0.
   Ver BUG D-1. Y la solución que propongo no es bajar el umbral, es no mirar el
   primer intervalo.
2. **§10.1, «si los avisos de banding cansan, sube `SALTO_MINIMO_BANDING`»** —
   **no lo hagas.** He dejado un test (`test_el_qc_encuentra_el_escalon_de_verdad_cuando_lo_hay`)
   que se pondría rojo si alguien lo sube lo bastante como para callar la gamma.
   El problema no es la magnitud del umbral, es **dónde** se mide.
3. **§8, «como el índice puede mentir, cada entrada se lee con un tope duro»** —
   es cierto y funciona. ~~El tope duro son 256 MB, que es el mismo número que
   el presupuesto de todo el archivo.~~ En la ronda 2 comprobé que por la vía
   del índice mentiroso esto no cuesta nada (§0.5); la sugerencia de un tope por
   entrada y por tipo sigue teniendo sentido, pero por el caso del índice
   **honesto** (~1.000:1 de amplificación), no por el del mentiroso.
4. **§5, sobre por qué no pasa el billion laughs** — pasa por el decodificador
   UTF-8, no por el `re.search`, en cuanto el ataque llega en UTF-16. Ver arriba.
5. **§9, `LUTQualityReport` y `ProblemaQC` en `qc.py` en vez de en
   `contracts.py`** — **estoy de acuerdo con el autor**: cruzan una frontera
   (la GUI los va a pintar) y deberían estar en `contracts.py`. Es cosa del
   orquestador, no suya; queda apuntado aquí también para que no se pierda.

---

## 4. `core/resolve/` y `probe/` — agente E

### Veredicto: **aprobado con reservas**

### 4.1 «¿Qué entrada plausible rompe esto?»

**Un índice de nodo que no sea un entero exacto.** `validar_indice_nodo` hace
`int(node_index)`, que se traga floats, cadenas y booleanos y **trunca sin
avisar**. Un índice que salga de una división, de un `sum()` de floats o de un
control de la GUI y valga 2,9999999999 —que para cualquiera es el nodo 3— acaba
escribiendo en el nodo **2**. Escribir en el nodo equivocado en silencio es
precisamente el fallo que este módulo existe para evitar.

Y, más grave por lo que significa: **cualquier llamada directa a `set_cdl`,
`set_lut` o `copy_grades`**. La regla de oro no la impone el puente; la impone
una función que nadie está obligado a llamar. Detalle abajo.

### 4.2 La pregunta que me hiciste explícitamente: ¿se puede escribir un grado sin pasar por `AddVersion`?

**Sí. Se puede. Es un agujero en la regla de oro.** Lo he comprobado y lo he
dejado escrito:

```python
fake = FakeResolve(n_clips=1)
fake.current_version("clip001")            # -> 'Version 1'   (la de Mario)
fake.set_cdl("clip001", 2, mi_cdl)         # -> True
fake.set_lut("clip001", 3, "SIDEB/l.cube") # -> True
fake.version_names("clip001")              # -> ['Version 1']  <- NO hay SIDEB COLOR
fake.current_version("clip001")            # -> 'Version 1'
```

El CDL y el LUT acaban **en la versión del usuario**. Ni se crea la versión, ni
se cambia de versión, ni avisa nadie.

Y hay una segunda puerta, ésta además **destructiva**: `copy_grades` reemplaza
el árbol de nodos **entero** del clip de destino, en su versión activa, sin
crear ninguna versión antes. Si el destino tenía el grado de Mario en
`Version 1`, se lo lleva por delante. Verificado: un LUT que el usuario tenía en
el nodo 3 del clip de destino desaparece.

**Matiz honesto, y es importante:** el `Protocol` es un espejo 1:1 de la API real
y la API real tampoco lo impide, así que es defendible que el puente no
intervenga. Pero hoy la regla de oro vive **sólo** en `aplicar_grado_seguro`, y
el agente H (GUI) tiene el puente entero a mano. **Esto hay que decidirlo, no
dejarlo pasar.** Mi recomendación: que `set_cdl`, `set_lut` y `copy_grades` se
nieguen (o al menos avisen por `_avisos`) cuando la versión activa no sea
`VERSION_NAME`. Cuesta cuatro líneas y cierra la puerta para siempre.

- **Tests (los dos verdes, documentan lo que el código hace HOY):**
  `test_AGUJERO_se_puede_escribir_un_grado_sin_pasar_por_add_version`
  `test_AGUJERO_copy_grades_tambien_pisa_la_version_del_usuario`
- No los dejo rojos porque no afirman un fallo de implementación, afirman una
  decisión de diseño que hay que tomar. El día que se cierre el agujero, estos
  dos tests son los que hay que dar la vuelta.

### 4.3 Bugs

#### BUG E-1 — Truncación silenciosa del índice de nodo (media)

```python
validar_indice_nodo(3.0 - 1e-10, 3)  # -> 2     (¡se pidió el 3!)
validar_indice_nodo("2", 3)          # -> 2
validar_indice_nodo(True, 3)         # -> 1
```

Y llega hasta el final: `fake.set_cdl("clip001", 3.0 - 1e-10, cdl)` devuelve
`True` y deja el CDL **en el nodo 2**, que es el de balance, no el de look.

El docstring dice «tiene que ser un entero». Que lo compruebe.

- **Tests:** `test_un_indice_de_nodo_decimal_se_trunca_en_SILENCIO` y
  `test_un_indice_decimal_escribe_el_cdl_en_el_nodo_equivocado` — **los dos ROJOS**
- **Arreglo:** `if not isinstance(node_index, int) or isinstance(node_index, bool): raise NodoInvalido(...)`.

#### BUG E-2 — `--solo-diagnostico` dice que no escribe nada, y escribe dos ficheros (baja-media)

La ayuda del propio script:

> `--solo-diagnostico  mira el entorno y si el modulo se importa, y PARA. No se conecta a Resolve, **no escribe nada**.`

Ejecutado en una carpeta vacía:

```
$ cd /una/carpeta/vacia && python probe/api_probe.py --solo-diagnostico
--- antes ---
.  ..
[...]
  Informe JSON: /una/carpeta/vacia/informe_probe_resolve.json
  Informe texto: /una/carpeta/vacia/informe_probe_resolve.txt
--- despues ---
.  ..  informe_probe_resolve.json  informe_probe_resolve.txt
```

`main()` termina siempre por `terminar()`, que llama a `Informe.escribir()` con
el valor por defecto de `--informe` (`informe_probe_resolve.json`) **en la
carpeta desde la que se ejecuta**, y además hace `os.makedirs` de su carpeta.

Consecuencia práctica: si Mario lo ejecuta desde el repo —que es lo natural,
porque el script está ahí— le deja dos ficheros sueltos dentro del repo. Y es
justo el primer flag que la ayuda le recomienda usar («empieza siempre por
aquí»).

- **Test:** `test_solo_diagnostico_DICE_que_no_escribe_nada_y_escribe_dos_ficheros` — **ROJO**
- **Arreglo:** una línea. O no escribir con `--solo-diagnostico`, o cambiar el
  texto de la ayuda. Yo cambiaría el texto: el informe es útil también en el
  diagnóstico, sólo hay que decir dónde cae.

#### Observación menor — una ruta absoluta de Windows se cuela

`validar_ruta_lut_relativa("C:\\luts\\look.cube")` la da por buena:
`os.path.isabs` en macOS sólo mira si empieza por `/`. En macOS no llega a
ningún sitio malo (sería un nombre de fichero raro) pero el módulo presume de
cortar las absolutas y ésta no la corta. Test verde documentándolo.

### 4.4 Lo que he verificado y ESTÁ BIEN

- **`aplicar_grado_seguro` hace las cosas en el orden que promete.** Comprobado
  sobre la traza real de llamadas: `add_version` va **antes** de la primera
  escritura, siempre.
- **La ruta de LUT se valida ANTES de tocar nada.** Con una ruta absoluta, la
  lista de llamadas al puente queda **vacía**: ni `OpenPage`, ni `AddVersion`, ni
  una versión creada para nada. Bien pensado.
- **Índices de nodo:** 0, −1, −100, 4 y 99 sobre un clip de 3, 10²⁰, `None`,
  `"hola"` y un complejo: todos lanzan `NodoInvalido`.
- **Rutas de LUT:** 13 formas de equivocarse (absolutas, `//Volumes/...`, `~/`,
  `~mario/`, `../`, `SIDEB/../../`, con barra invertida, `.dctl`, `.3dl`, sin
  extensión, vacía, sólo espacios) y todas mueren.
- **Sin los tres nodos NO se escribe nada.** Verificado que después de la
  excepción `_grados_escritos` está **vacío**: no queda un CDL a medias.
- **La séptima incógnita** (`version_hereda_grafo=False`): la app se para y
  avisa en vez de escribir a ciegas, y la versión sí se crea, así que el grado
  original sigue en la suya.
- **Idempotencia:** cinco pasadas seguidas de `aplicar_grado_seguro` sobre el
  mismo clip dejan exactamente `['Version 1', 'SIDEB COLOR']`. No hay
  `SIDEB COLOR 2`.
- **Las seis marcas `# TODO(F0-n)` existen las seis** y —esto es lo que más me
  interesaba— **no se han multiplicado**: fuera de `incognitas.py` hay
  exactamente dos, una en `bridge.py` (F0-5) y otra en `fake.py` (F0-1), como
  promete el NOTAS. Hay un test que lo afirma con el diccionario exacto, así que
  si mañana crecen, salta.
- **El código funciona con LAS DOS respuestas de cada incógnita**, no sólo con la
  conservadora. 13 combinaciones ejercitadas de punta a punta, y además he
  comprobado que **cada una cambia algo observable**:

  | Incógnita | conservadora | la otra | qué cambia de verdad |
  |---|---|---|---|
  | F0-1 drx | 8 formatos | 9 formatos | `export_stills('drx')` pasa de devolver `[]` y no escribir nada, a escribir un fichero |
  | F0-2 still con grado | `False` | `True` | `still_sirve_para_medir()` |
  | F0-3 .dctl | `('.cube',)` | `('.cube', '.dctl')` | la validación de ruta deja pasar el `.dctl` |
  | F0-4 instalación | `/Library/...` | `<home>/Library/Containers/...` | la carpeta de LUTs entera |
  | F0-5 OpenPage | acaba en `color` | **se queda en `edit`** | no se cambia de página |
  | F0-6 fusionscript | `None` | `True`/`False` | sólo se enseña, no afecta |

- **`FakeResolve` NO ofrece ninguna forma pública de leer el CDL.** Lo he
  comprobado a conciencia, porque era la pregunta que más me preocupaba: el
  único método público con «cdl» en el nombre es `set_cdl`; los dos que sí leen
  (`_cdl_escrito`, `_grados_escritos`) empiezan por guion bajo y se ven a la
  legua; `NodeInfo` no lleva CDL dentro; y `FakeResolve` no tiene `get_cdl`.
  Los siete métodos públicos que tiene de más respecto al `Protocol` son la
  maquinaria de fingir averías (`fallar_en`, `devolver_false_en`,
  `dejar_de_fallar`, `conectar`, `desconectar`) más dos que **sí existen en la
  API real** (`SetCurrentStillAlbum` y leer el grafo post-clip de un grupo, que
  es `GetLUT`/`GetNodeLabel`). **No hay trampa que se descubra mañana.** Lo he
  atado con un test que lista los siete exactos.
- **El look de un grupo es el nodo 1 del post-clip, no el 3.** Pedir el 3
  revienta, como debe.
- **`FakeResolve.export_stills` no se sale del directorio que le dan.** Cuatro
  prefijos hostiles (`../fuera_`, `a/b_`, `..\fuera_`, `/absoluto_`) rechazados,
  y el directorio padre queda con un solo hijo.
- **Importar `core.resolve` no carga `DaVinciResolveScript`, ni `fusionscript`,
  ni PySide6.** Repetido en proceso limpio.

### 4.5 Dónde discrepo del `NOTAS.md` de E

1. **§2, la regla de oro** — el documento la describe como si viviera en el
   puente, y vive sólo en `aplicar_grado_seguro`. Ver §4.2. Es la discrepancia
   principal que tengo con este módulo.
2. **§5, «lanza lo que es un error de programa»** — de acuerdo con el criterio,
   pero entonces un índice de nodo decimal es un error de programa de manual y
   hoy no lanza. Ver BUG E-1.
3. **§3.1, «`_grados_escritos` empieza por guion bajo a propósito»** —
   **totalmente de acuerdo, y funciona**. Lo verifiqué buscando fugas y no hay
   ninguna. Es la decisión más acertada del módulo.
4. **Aviso sobre el probe**: `--solo-diagnostico` **sí importa** el módulo de
   scripting de Resolve (es lo que necesita para contestar F0-6). Eso es por
   diseño y está en la ayuda, pero conviene que Mario lo sepa: el flag no es
   puramente pasivo. En esta máquina la importación funciona y el probe contesta
   **F0-6 = SÍ** ya hoy. **No me he conectado a Resolve** en ningún momento.

---

## 5. El límite duro: ¿escribe alguien fuera del repo?

### Veredicto: **aprobado, sin peros, para `core/`**

Comprobado de dos formas, porque una sola no basta:

**Estática.** Inventario completo de llamadas de escritura en el árbol sintáctico
de `core/`:

| Paquete | Ficheros que escriben | Llamadas |
|---|---|---|
| `core/color` | **ninguno** | — |
| `core/io` | `cube.py`, `cdl_xml.py`, `bundle.py` | `open`, `mkdir` |
| `core/resolve` | `fake.py` | `open` |

Las cinco están dentro de funciones que reciben la ruta **por parámetro**, y las
tres de `core/io` exigen `crear_directorios=True` para fabricar una carpeta.
Cero literales `/Volumes`, `/tmp`, `/var/folders` o `/Users/` en código (sólo
en docstrings). Cero `tempfile` en `core/`. `Path.home()` aparece exactamente
una vez, en `incognitas.lut_dir()`, y **sólo para construir una cadena que se
enseña**: verificado que no crea la carpeta.

**Dinámica.** Foto del repo entero (sin `.git`/`.venv`/caches) antes y después de
ejecutar **todo** lo que `core/` sabe escribir contra un `tmp_path`: `.cube` en
17/33/65 en modo normal y exacto, `.cc`, `.ccc`, `.cdl`, dos `.sidebcolor` y los
stills de `FakeResolve`. **Ni un fichero del repo aparece, cambia o desaparece.**
Y las funciones de lectura (`leer_cube`, `leer_cdl`, `qc_lut`) no dejan rastro.

Tests: `tests/revision/test_ola1_limites.py` (10, todos verdes).

### La única excepción, y no es de `core/`

`probe/api_probe.py` sí escribe en dos sitios, y hay que decirlo aunque no sea
`core/`:

1. `tempfile.mkdtemp(prefix="sidebcolor_probe_")` para los ficheros de prueba —
   **sólo** si Mario llega a la fase de escritura, y **después de que el probe le
   pida permiso** (`preguntar_permiso`). Se puede fijar con `--dir-pruebas`.
2. El informe, con `os.makedirs` + dos ficheros, **siempre**, incluso con
   `--solo-diagnostico`. Eso es el BUG E-2.

El probe es una herramienta que Mario ejecuta a mano y con Resolve delante, no
código de la app, así que la convención 7 no le aplica literalmente. Pero el
punto 2 contradice su propia ayuda y hay que arreglarlo.

---

## 6. Resumen de bugs, por gravedad

| # | Gravedad | Módulo | Qué es | **Tras la ronda 2** |
|---|---|---|---|---|
| E-1 | **media** | `core/resolve` | El índice de nodo se trunca en silencio: se pide el 3, se escribe en el 2 | OK **ARREGLADO**. Sólo `int`, y el `bool` fuera. |
| A-1 | **media** | `core/color` | `rec709` difiere de `colour-science` en 3.9e-2 con entrada negativa; NOTAS.md afirma 0.0 | OK **ARREGLADO**. Las 7 curvas a 0.0e+00 en todo el dominio. |
| D-1 | **media** | `core/io` | El QC marca la gamma de salida como banding en 17/33/65, y la métrica exagera x4.225 | OK **ARREGLADO a medias, y bien**: el recuento se agrupa (3 en vez de 20) y el aviso se queda, porque es un verdadero positivo. Ver §0.7. |
| R-0 | **media** (diseño) | `core/resolve` | La regla de oro no la impone el puente: las escrituras van a la versión del usuario | OK **ARREGLADO**, y con cambio de diseño: `_exigir_version_propia` en la clase base, las 5 escrituras, heredado por `LiveResolve`. |
| E-2 | baja-media | `probe/` | `--solo-diagnostico` dice «no escribe nada» y escribe dos ficheros en el CWD | OK **ARREGLADO**. |
| A-2 | baja-media | `core/color` | `convert(x, X, X)` devuelve uint8/bool y se salta la validación de tipo | OK **ARREGLADO** por las dos ramas. |
| D-2 | baja | `core/io` | Dos `LUT_3D_SIZE` contradictorios se aceptan en silencio | OK **ARREGLADO**. |
| — | baja | `core/io` | ~~Zip-bomba con índice mentiroso: cuesta 256 MB de RAM~~ | **ERA UN DATO FALSO MÍO**. Cuesta 0 MB. Ver §0.5. |
| NUEVO | baja | `core/resolve` | La vía de escape apaga la regla en `LiveResolve` pero no en `FakeResolve` | **ABIERTO**. Hallazgo de la ronda 2. Ver §0.4. |
| — | baja | `core/resolve` | Una ruta absoluta de Windows pasa la validación de «ruta relativa» | abierto, muy menor |
| — | muy baja | `core/color` | Un codificado de 200 desborda a `inf` con `RuntimeWarning` no silenciado | abierto; sólo las 5 curvas log (las de potencia aguantan hasta ~1e200) |
| — | muy baja | `core/color` | `delta_e2000_mean` de un array vacío: NaN + «Mean of empty slice» | abierto, muy menor |
| — | muy baja | `core/io` | Entradas duplicadas en el zip: gana la última | abierto, no explotable hoy |

---

## 7. Los tests que he escrito

**251 tests nuevos** en la ronda 1, **296 tras la ronda 2**, en cuatro ficheros.
En la ronda 1 había 6 en rojo, todos a propósito; **hoy no hay ninguno**: los
siete hallazgos están arreglados y los tests reescritos afirman la conducta
nueva. El reparto por fichero hoy es 122 / 71 / 93 / 10.

| Fichero | Tests | Rojos | Qué ataca |
|---|---:|---:|---|
| `tests/revision/test_ola1_color.py` | 102 | 2 | Juez independiente con mis valores (negativos incluidos), NaN en las 14 públicas, promesa de dtype, extremos de la ida y vuelta, ΔE2000 en 275° y en 6 casos degenerados, 6 imágenes extremas, máscara de piel tono a tono, formas degeneradas |
| `tests/revision/test_ola1_io.py` | 68 | 1 | Ejes por fichero real, 20 `.cube` hostiles + 6 raros pero legítimos, falsos positivos del QC medidos, zip-slip ×7, zip-bomba honesta y **mentirosa**, `.npy` con pickle, 11 CDL hostiles, ida y vuelta exacta del bundle |
| `tests/revision/test_ola1_resolve.py` | 71 | 3 | Índices de nodo, rutas de LUT ×13, versiones, el agujero de la regla de oro, fugas de API en `FakeResolve`, las seis incógnitas × las dos respuestas, el probe (`--help` y `--solo-diagnostico`, sin conectar) |
| `tests/revision/test_ola1_limites.py` | 10 | 0 | El límite duro: inventario estático de escrituras + foto del repo antes/después |

Todos pasan `ruff check tests/revision` limpio.

### Los seis rojos, uno a uno

1. `test_curvas_coinciden_con_colour_science_tambien_en_negativos[rec709]` —
   BUG A-1. Rojo porque la afirmación de NOTAS.md no se sostiene en negativos.
2. `test_convert_con_la_identidad_rompe_la_promesa_de_dtype` — BUG A-2. Rojo
   porque `convert(uint8, X, X)` devuelve uint8 y el docstring promete float32.
3. `test_un_cube_con_dos_LUT_3D_SIZE_contradictorios_se_traga_el_ultimo` —
   BUG D-2. Rojo porque un fichero ambiguo se lee en silencio.
4. `test_un_indice_de_nodo_decimal_se_trunca_en_SILENCIO` — BUG E-1. Rojo porque
   `validar_indice_nodo(3 − 1e-10)` devuelve 2 en vez de lanzar.
5. `test_un_indice_decimal_escribe_el_cdl_en_el_nodo_equivocado` — BUG E-1, la
   consecuencia hasta el final. Rojo porque el CDL acaba en el nodo 2.
6. `test_solo_diagnostico_DICE_que_no_escribe_nada_y_escribe_dos_ficheros` —
   BUG E-2. Rojo porque escribe `informe_probe_resolve.json` y `.txt` en el CWD.

---

## 8. Lo que NO he revisado

- `core/analysis/` (agente B) y `core/matching/` (agente C): se estaban
  escribiendo a la vez que esta revisión. No son míos y no los he tocado ni
  mirado. Estado al cerrar: los dos en verde. Ver la nota de §1.3 sobre el rojo
  transitorio que le vi a C.
- `core/resolve/live.py`: no lo ha ejecutado nadie nunca, y yo tampoco. No he
  intentado conectarme a DaVinci Resolve en ningún momento, ni he importado
  `DaVinciResolveScript` ni `fusionscript` desde mis tests. Lo único que ha
  tocado ese módulo es el propio `probe/api_probe.py --solo-diagnostico`
  ejecutado en un subproceso, que es lo autorizado.
- El rendimiento. `convert` sobre un 4K son ~25 millones de operaciones en
  float64 y nadie lo ha medido, como el propio agente A reconoce. Si el agente H
  lo llama en un bucle de vista previa, eso hay que mirarlo, y no esta noche.
- Material real. Cero. Todo en `tmp_path`.
