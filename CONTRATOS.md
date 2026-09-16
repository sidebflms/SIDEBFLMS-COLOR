# CONTRATOS — SIDEBFLMS COLOR

**La fuente de verdad es [`core/contracts.py`](core/contracts.py).** Este documento
explica el porqué; el código manda. Si los dos se contradicen, el código tiene razón
y este archivo es un bug.

**Están congelados.** Ningún agente edita `core/contracts.py`. Si tu módulo necesita
un campo nuevo o una firma distinta, se lo pides al orquestador. El motivo no es
burocracia: es que siete agentes escribiendo a la vez sobre las mismas dataclases
acaban en un repo que no importa.

---

## Las siete convenciones que no se negocian

1. **Imágenes**: `float32`, forma `(alto, ancho, 3)`, canales **R, G, B**.
   Rango nominal 0..1, pero **los valores fuera de rango son legales y hay que
   preservarlos** — el material log y el sobreexpuesto los tienen. Nada de `uint8`
   cruzando una frontera entre módulos.
2. **Listas de píxeles**: `(N, 3)`, mismo orden RGB.
3. **Espacio de trabajo**: `WORKING_SPACE` = DaVinci Wide Gamut + DaVinci
   Intermediate. Toda estadística, todo emparejamiento y el dominio de todo LUT
   viven ahí, salvo que la firma diga otra cosa.
4. **`LUT3D.table` se indexa `[ri, gi, bi] -> (r, g, b)`. El eje 0 es el ROJO.**
   En el *fichero* `.cube` el rojo es el que varía más rápido, así que el orden de
   líneas del fichero es `table.transpose(2,1,0,3).reshape(-1,3)`. El agente D es el
   único que tiene que pensar en esto; el resto usa `LUT3D.apply()` y se olvida.
5. **Índices de nodo de Resolve: 1-based**, como la API. Fuera de `core/resolve`
   no se usan índices de nodo.
6. **`core/` no importa PySide6 ni DaVinciResolveScript.** Nunca. Si un test de
   `core/` necesita Qt, el diseño está mal.
7. **Ninguna función de `core/` escribe fuera de una ruta que le pasen por
   parámetro.** Cero escrituras en el sistema, en `~` o en `/Volumes`.

---

## Qué implementa cada quién

`core/contracts.py` **ya trae implementados**, y son propiedad del orquestador:

| Ya funciona hoy | Por qué lo implemento yo |
|---|---|
| `CDL.apply()`, `is_identity()`, `as_resolve_payload()` | Lo usan C, F, E, H y los tests de entrega. Si fuera un stub, nadie podría probar nada esta noche. |
| `LUT3D.apply()` (trilineal), `LUT3D.identity()` | Igual: es la operación central del proyecto. |
| `CoverageMap.covered_mask()`, `coverage_fraction()` | Tres líneas, y evita que F y G discrepen en qué cuenta como «cubierto». |
| `ColorStats.to_dict()` / `from_dict()` | Serialización trivial; que la defina uno solo evita dos formatos de disco. |
| `confidence_level()` | **Único** sitio donde un número se convierte en alta/media/baja. No redefinas umbrales en tu módulo. |

El resto de dataclases son sólo datos. Las rellenas tú.

---

## El diccionario, módulo a módulo

### `ColorStats` — agente **B** lo produce, **C** y **F** lo consumen
Resumen estadístico de un plano. Arrays en `float64` y en `WORKING_SPACE`, **salvo
`skin_locus`, que va en Oklab** porque es donde el locus de pieles tiene sentido
geométrico. `saturation_hist` tiene `SAT_BINS` = 64 y suma 1. `skin_locus` es `None`
si no se detectó piel suficiente, y `skin_fraction` dice cuánta.

### `CDL` — **C** y **F** lo producen, **E** lo escribe en Resolve
Es lo único que la API deja escribir por parámetro, así que es el nodo 2 entero.
La fórmula está en el docstring y **el orden importa**: el `max(x, 0)` va *antes*
de la potencia (lo manda el estándar ASC; elevar un negativo a 0.8 daría NaN).
La saturación se aplica al final, con pesos de luma Rec.709.

`power > 0` en los tres canales o el constructor lanza. Es a propósito: un `power`
de 0 o negativo no es un grado, es un bug que llega desde un ajuste mal condicionado.

### `LUT3D` — **D** lo lee y escribe, **F** lo genera, **C** lo puede generar
`table` es `(N, N, N, 3)` `float32`. `apply()` interpola trilinealmente y **sujeta al
borde** fuera de dominio, no extrapola — que es lo que hace Resolve, y así lo que ves
aquí es lo que verás allí. Tamaños soportados: 17, 33, 65. Por defecto **33**.

### `Confidence` — todos
`score` en 0..1, `level` derivado con `confidence_level()`, `reasons` en **castellano
y ordenadas por importancia** (van tal cual a la GUI), `metrics` con los números
crudos por si alguien quiere discutir la nota.

### `ClipAnalysis` — agente **B**
`fingerprint` es `(FINGERPRINT_LEN,)` = 96, `float32`, **con norma L2 = 1** (para que
comparar dos huellas sea un producto escalar). `pixels` es opcional: una muestra de
píxeles para quien necesite la distribución completa y no sólo el resumen.

### `MatchResult` — agente **C**
`delta_e_before` / `delta_e_after` son ΔE2000 medios. `content_mismatch` a `True`
significa «estas dos escenas no son comparables, no te fíes del número», y la GUI
tiene que enseñarlo aunque la confianza salga alta.

### `CoverageMap` / `ReverseDiagnosis` / `ReverseResult` — agente **F**
`counts[i,j,k]` = cuántas muestras reales cayeron en esa celda del cubo.
`variance[i,j,k]` = varianza del residuo dentro de la celda. **Ahí está la clave del
test T2**: si un color concreto unas veces se transforma de una manera y otras de
otra, el grado no es un LUT, y esa varianza alta es la prueba.

`lut_reproducible` va de 0 a 1: qué fracción del grado te puedes llevar en un `.cube`.

### `ResolveBridge` — agente **E**
Un `Protocol`. **Cada método corresponde 1:1 con una llamada verificada de la API**
(sección 2 del encargo). Si echas algo en falta, no existe: cambia el diseño, no el
protocolo. Dos implementaciones: `FakeResolve` (siempre, es contra lo que se prueba)
y `LiveResolve` (sólo si mañana el probe dice que se puede).

Todo fallo hablando con Resolve sale como `ResolveError`. La GUI captura sólo eso.

### `ColorSession` — agente **D**
Lo que se guarda y se abre: un `.sidebcolor`, que es un zip con `session.json`,
`luts/*.cube` y miniaturas opcionales.

---

## Las constantes que compartimos

| Constante | Valor | Quién la mira |
|---|---|---|
| `WORKING_SPACE` | `davinci_wg_intermediate` | todos |
| `LUT_SIZE_DEFAULT` | `33` | D, F |
| `LUT_SIZES_SOPORTADOS` | `(17, 33, 65)` | D |
| `PERCENTILE_LEVELS` | 11 niveles de 0.1 a 99.9 | B, C |
| `SAT_BINS` | `64` | B |
| `FINGERPRINT_LEN` | `96` | B, C |
| `VERSION_NAME` | `"SIDEB COLOR"` | E, H |
| `NODE_NORMALIZACION` / `_BALANCE` / `_LOOK` | `1` / `2` / `3` | E, H |
| `CONFIDENCE_ALTA` / `_MEDIA` | `0.75` / `0.45` | todos |
| `LUMA_REC709` | `(0.2126, 0.7152, 0.0722)` | sólo el CDL |

---

## La regla de las cifras — añadida el día 3, y por un motivo concreto

**Ninguna cifra se publica sin poder decir de dónde salió.**

«Publicar» es cualquiera de estas cinco: `BITÁCORA.md`, el `reason` de un `xfail` o un
`skip`, un comentario del código, un `NOTAS.md`, o un texto que se vea en la interfaz.

Cada número publicado tiene que tener una fila en **[`CIFRAS.md`](CIFRAS.md)** con:

| qué | por qué |
|---|---|
| **el valor** | obvio |
| **el montaje exacto** sobre el que se midió | es donde falló: la cifra estaba bien medida, pero **sobre otro montaje** |
| **el comando que lo reproduce** | si no se puede reproducir, no es una medida, es un recuerdo |
| **la fecha** | un número de hace tres semanas sobre un módulo que cambió ayer no vale |

**Si un número no puede tener esa fila, no se publica: se escribe «no medido».**

### Y en concreto, para `xfail` y `skip`

**Un `xfail` o un `skip` sin cifras reproducibles en su mensaje es un test mal marcado.**
El `reason` no es un comentario: es lo que va a leer quien se encuentre ese test dentro de
seis meses, y es lo único que le va a decir si el límite sigue ahí o ya se arregló.

Un `reason` bien escrito dice **qué falla, con qué número, contra qué umbral, y qué haría
falta para cerrarlo**. Uno mal escrito dice «no funciona todavía».

### De dónde sale esta regla

La noche del 14 al 15 de septiembre de 2026 se publicó un `xfail` que decía
`lut_reproducible = 0.851` y `R² = 0.076`. Los dos números estaban **medidos sobre un
montaje distinto del que usaba el test**. Los reales eran **0.7319** y **0.2887**.

No fue un error de precisión: **cambiaba el diagnóstico**. Con 0.076 la lectura era «el
residuo no tiene nada de radial», o sea un problema de fondo; con 0.2887 la lectura era
que de las tres puertas del detector pasaban dos y sólo cerraba la tercera, **por un 4%**.
Mandaba a buscar un problema estructural donde había un umbral rozando.

Lo cazó una auditoría independiente al día siguiente, no el que lo escribió. Ver
`AUDITORIA-DIA2.md`, caso 4.

---

## Tests que pasan en vacío — añadido el día 4

**Un test que no comprueba nada da verde, y el verde miente.** Van tres en este proyecto:

1. **Día 2**: `assert fuente.count("_exigir_version_propia") >= 5`. Pasaba aunque las cinco
   menciones estuvieran en comentarios y no hubiera ni una llamada.
2. **Día 3**: una cuarentena que toleraba un fallo conocido. Se arregló el fallo y quedó
   afirmando `0 <= 1`.
3. **Día 4**: la mitad de `test_el_mapa_de_cobertura_distingue_lo_medido_de_lo_inventado`
   miraba un corte del cubo **sin ninguna celda cubierta**. Desde el día 2 afirmaba algo
   sobre un conjunto vacío.

### Lo que vigila la máquina

`tests/test_sin_vacio.py` recorre los tests y avisa de aserciones sobre colecciones que
pueden quedarse vacías **sin que nadie se entere**: las que salen de `glob`, `rglob`,
`iterdir`, `os.walk`, `findChildren`, de un filtro con `if`, o de una función auxiliar que
devuelva una de ésas. Caza `for … : assert`, `assert all(…)`, `assert not any(…)` y
«acumular en una lista y luego `assert not lista`», si no hay antes una guarda. Tiene
controles negativos y positivos. **Si añades una excepción, que sea con su razón en una
línea; si la lista pasa de 15, el test salta.**

### Lo que tiene que vigilar una persona al revisar

El detector no ve esto, porque vigilarlo sin ruido no ha sido posible:

- **Bucles sobre fixtures, atributos o llamadas** (`est.clips`, `list_nodes()`, una
  fixture de escenas): comprueba antes que no vienen vacíos.
- **Un `if …: continue`** dentro de un bucle de comprobación: puede saltarse todas las
  vueltas.
- **`.count()` sobre código fuente**: cuenta también comentarios y docstrings. Para contar
  llamadas, usa el AST.
- **Un `xfail(strict=True)` sin `raises=`**: cualquier excepción —un `KeyError`, un import
  roto— cuenta como el fallo esperado, y el test se queda en «xfail» por el motivo
  equivocado. Si lo que se espera es que falle una aserción, pon `raises=AssertionError`.
- **Una guarda puesta *después* de la aserción** no guarda nada.
- **Un test que sólo imprime** cifras sin afirmar nada es una medición, no un test: está
  bien que exista, pero que no cuente como cobertura de nada.

### La receta, cuando encuentres uno

**Primero la guarda, sin cambiar lo que el test afirma**:
`assert cosas, "no hay nada que comprobar: <por qué podría estar vacío>"`.
Si al ponerla el test se pone rojo, **eso es un hallazgo**: se deja rojo, se marca
`xfail(strict=True, raises=AssertionError)` con la cifra y el comando, y se dice.
