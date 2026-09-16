# CALIBRACIÓN DE `FeaturesDestino` — las señales que SÍ miran el plano de destino

**Agente de calibración, día 5 (16-09-2026), tarea 2.** No he escrito `core/reverse/confianza_destino.py`
(lo escribió la sesión que me lanzó) ni el diagnóstico del día 4 (`CALIBRACION-CONFIANZA.md`).
Por la regla del proyecto («no arbitres un desacuerdo en el que eres parte», `CONTRATOS.md`),
mido con el mismo rigor con el que el agente del día 4 midió `ReverseResult.confidence`: si
algo no predice, lo digo tal cual. Nada en `gui/`, nada en `/Volumes`, sin red, sin Resolve.

---

## Veredicto

**Las señales SÍ llevan información real — mucho más que la nota actual — pero NINGUNA
combinación limpia llega al mismo listón de «alta = me lo llevo sin mirar» que exigió el día 4,
así que no se conectan a una etiqueta alta/media/baja que Mario vea en pantalla.**

Diferencia importante con el día 4, y es la buena noticia de este informe: la nota actual
(`ReverseResult.confidence`) tenía **AUC 0.500 exacto** dentro de una misma clase de material
(`CALIBRACION-CONFIANZA.md` §3.2) — la paradoja de Simpson se comía toda la correlación
aparente. Aquí, **`cobertura_destino` no tiene ese problema**: su AUC dentro de cada una de las
8 clases de material (rejilla × compresión × recorte) va de **0.726 a 0.966**, siempre en el
signo bueno, sin una sola inversión (§3.2). Es una señal real, no un artefacto de que la
compresión se lleve por delante nota y error a la vez.

Y aun así, el mejor corte que consigo — dentro de una clase homogénea de material, con al menos
15 casos — deja **82.4%** de aciertos (33³, sin compresión, con recorte de altas luces;
`cobertura_destino ≥ 0.975`, IC bootstrap no evaluable de forma fiable con n=17). Lejos del 95%
que el día 4 fijó como lo que tiene que significar «alta». La única combinación que SÍ cruza el
95% (§5) lo hace metiendo `variance_zona`, y `variance_zona` tiene su propio problema serio: su
signo **se invierte** dentro de la clase de material comprimido (§4) — es la misma clase de
paradoja de Simpson que tumbó la nota actual, escondida dentro de mi propia señal candidata. La
descarto por eso, no por capricho: ver §4 y §6.

`planos_acumulados` (día 5, la señal que sólo esta tarea podía medir porque `simple` la deja
fija en 1) **sí tiene un efecto real y medible, monótono, pero modesto**: la mediana del ΔE
máximo fuera de plano baja de 5.07 (1 plano) a 3.56 (8 planos) y el % que cumple sube de 27% a
46% (§4.4). No basta por sí sola para fijar un umbral, pero es información útil que antes no
existía.

**Decisión:** `core/reverse/confianza_destino.py` se deja exactamente como está (features
crudas, sin tocar). No se implementa `confianza_para_destino` ni se toca
`core/matching/confianza.py`, `core/umbrales.py` ni `core/contracts.py`. Ver §6 para el porqué,
que no es sólo «no llega al 95%» sino un motivo estructural: `confidence_level()` es, a
propósito, el único sitio del repo donde un número se convierte en alta/media/baja
(`core/contracts.py`, `core/umbrales.py` §1); forzar mi nota candidata por ahí con el mismo
`CONFIDENCE_ALTA = 0.75` da un «alta» que acierta el **29%** de las veces (§5) — peor que no
decir nada.

---

## 1 · Qué mide cada señal (leído, no tocado)

`core/reverse/confianza_destino.py::calcular_features_destino(coverage, plano_destino,
planos_acumulados=1)` devuelve `FeaturesDestino` con cinco campos; cuatro son las que pide el
encargo del día 5:

| Campo | Qué es |
|---|---|
| `cobertura_destino` | Fracción 0..1 del **peso trilineal** del plano de destino que cae en celdas del cubo que el LUT cubrió de verdad (`CoverageMap.covered_mask()`, `counts >= min_samples`). Específica de CADA plano de destino, no la cobertura global del cubo (que ronda el 0.3-2% y no distingue nada). |
| `muestras_p10_zona` / `muestras_mediana_zona` | Percentil 10 y mediana (ponderados por el mismo peso) del conteo real de muestras (`CoverageMap.counts`) en las celdas que el destino usa. |
| `variance_zona` | Varianza media ponderada del residuo (`CoverageMap.variance`) en esas celdas. |
| `planos_acumulados` | Se pasa tal cual desde quien llama; `CoverageMap` no sabe cuántos planos hay detrás de sus conteos. |

Todo ponderado por el **peso trilineal** (`core.reverse.acumulacion.pesos_trilineales`), no por
el vecino más cercano: es el mismo reparto que usa el ajuste del LUT. Los tests de aritmética
(`tests/test_reverse_confianza_destino.py`, 9 casos, todos con el resultado calculado a mano)
pasan sin tocarlos; no encontré ningún bug en el cálculo.

El módulo, por diseño, deja fuera de sí mismo la pregunta de si estas señales predicen algo
(su propio docstring lo dice: «Lo que NO hace este módulo es decidir la fórmula de confianza»).
Eso es lo que mide este informe.

---

## 2 · El montaje

Paquete nuevo, hermano de `tests/calibracion/`: **`tests/calibracion_destino/`**
(`material.py` NO se duplica: se reutiliza `tests/calibracion.material` entero — mismas
escenas, mismo grado conocido, mismo códec, mismo ΔE2000 independiente de `colour-science` que
usó el día 4). Sólo hay `medir.py` (nuevo) y `analizar.py` (nuevo).

**Dos bloques de casos**, los dos a 320×180, con las mismas 5 riquezas de color y el mismo
grado conocido (CDL + curva en S + secundaria) del día 4:

* **`simple`** (`invertir_grado`, `planos_acumulados = 1` siempre): 5 riquezas × 6 semillas × 2
  compresiones × 2 recortes = **120 extracciones**, cada una evaluada en 2 rejillas (17³, la del
  panel, y 33³, la del `.cube`) × 6 planos de destino (el propio y los 5 «fuera de plano» del
  día 4: otra toma de la misma paleta, tono +15°, tono +60° y +0.7 pasos, tono +150° con más
  saturación, otra paleta) = **1.440 filas**.
* **`lote`** (`invertir_grado_lote`, `planos_acumulados` ∈ {1, 2, 3, 5, 8}): 5 riquezas × 5
  valores de N × 2 compresiones × 2 repeticiones = **100 extracciones** (cada una con N tomas
  de la MISMA paleta y el MISMO grado, para que lo único que cambie sea cuántos planos entraron
  en la extracción), rejilla fija 33³ × 6 planos de destino = **600 filas**. Se llama con
  `verificar_coherencia=False`: los planos comparten grado a propósito (no es un test de
  coherencia) y verificarla sólo pagaría N ajustes de LUT de más sin medir nada nuevo.

**Total: 2.040 filas** (día 4 usó 2.400 para `reverse`; mismo orden de magnitud).

**La verdad y lo que se compara**, igual que el día 4: verdad en el plano de destino P =
`material.aplicar_grado(grado, P)`; predicción = `lut.apply(cdl.apply(P))` con el `(cdl, lut)`
que devolvió la extracción. `calcular_features_destino` recibe el plano de destino **después
del CDL** (`cdl.apply(P)`), porque es el dominio en el que vive `coverage` — así lo hace también
`tests/calibracion/medir.py` para `frac_px_en_celda_cubierta`. ΔE2000 de `colour-science`
(máximo, p95, medio), independiente de `core.color`.

**Guardia.** Cada fila lleva la huella sha256 (AST) de `core/reverse/{confianza_destino,
acumulacion, invertir, lote}.py` y `core/contracts.py`: `2c8eaea7888a` en las 2.040 filas y en
el código actual.

**Intervalos:** bootstrap por escena (`semilla_escena`, una por extracción — los 6 planos de
destino de una misma extracción comparten señales de cobertura y `planos_acumulados`), 1.000
remuestreos, semilla fija, percentiles 2.5 y 97.5. Mismo criterio que el día 4.

### Comandos

```bash
# medir (primer plano, ~2.5 min en total con 4 procesos; escribe tests/calibracion_destino/datos/)
.venv/bin/python -m tests.calibracion_destino.medir simple --desde 0 --hasta 120 --procesos 4
.venv/bin/python -m tests.calibracion_destino.medir lote   --desde 0 --hasta 100 --procesos 4

# analizar (~5 s; lee los CSV)
.venv/bin/python -m tests.calibracion_destino.analizar | grep "<etiqueta>"
```

La salida completa de la última ejecución está en `tests/calibracion_destino/salida_analisis.txt`.
**Todas las cifras de este documento salen de ahí, con el `grep` indicado.**

---

## 3 · ¿Correlacionan?

### 3.1 Cada señal sola, todo junto (`grep "CALD spearman"`, filas fuera de plano)

| Señal | Bloque | n | ρ máximo | ρ p95 | ρ medio |
|---|---|---|---|---|---|
| `cobertura_destino` | `simple` | 1.200 | −0.309 | −0.281 | −0.284 |
| `muestras_p10_zona` | `simple` | 1.200 | −0.300 | −0.269 | −0.255 |
| `muestras_mediana_zona` | `simple` | 1.200 | −0.223 | −0.129 | −0.132 |
| `variance_zona` | `simple` | 1.200 | **+0.391** | +0.358 | +0.397 |
| `cobertura_destino` | `lote` | 500 | −0.335 | −0.357 | −0.316 |
| `planos_acumulados` | `lote` | 500 | −0.140 (IC95 −0.248, −0.019) | −0.103 | −0.084 |

Negativo = signo bueno para las cuatro primeras (más cobertura o más muestras, menos error);
`variance_zona` tiene el signo bueno cuando es **positivo** (más varianza, más error) y aquí lo
es, todo junto.

### 3.2 DENTRO de cada clase de material — la comprobación que importa

El día 4 encontró una paradoja de Simpson exactamente aquí: una correlación global que
desaparece o se invierte dentro de cada clase de material (compresión × recorte). La repito con
las cuatro señales nuevas.

**`cobertura_destino`, ρ dentro de cada clase** (`grep "CALD spearman cobertura_destino] simple |"`):

| Rejilla | compresión=0 recorte=0 | c=0 r=1 | c=1 r=0 | c=1 r=1 |
|---|---|---|---|---|
| 17³ | −0.532 | −0.535 | −0.414 | −0.525 |
| 33³ | −0.422 | −0.441 | −0.460 | −0.403 |

**Ocho de ocho clases, mismo signo, y de hecho MÁS fuerte que el −0.309 global.** No hay
paradoja de Simpson: la correlación no la produce la compresión, está dentro de cada clase.

**AUC dentro de cada clase** (`grep "CALD auc_clase cobertura_destino"`), que es más estricto
porque usa directamente el criterio «cumple» en vez de un ranking continuo:

| Rejilla | c=0 r=0 | c=0 r=1 | c=1 r=0 | c=1 r=1 |
|---|---|---|---|---|
| 17³ | 0.904 (8 cumplen/150) | 0.962 (10/150) | 0.950 (3/150) | 0.966 (4/150) |
| 33³ | 0.726 (21/150) | 0.756 (34/150) | 0.913 (1/150) | 0.913 (1/150) |

**AUC entre 0.726 y 0.966 en las 8 clases, siempre por encima de 0.5.** `muestras_p10_zona` es
igual de consistente (`grep "CALD auc_clase muestras_p10_zona"`: 0.759–0.952 en las 8 clases).
Es la diferencia central con el día 4: **estas dos señales predicen dentro de cada clase, no
sólo cuando se mezclan todas**.

**`variance_zona` es distinta, y es donde SÍ aparece la paradoja** (`grep "CALD spearman
variance_zona] simple |"`):

| Rejilla | c=0 r=0 (ρ medio) | c=0 r=1 | c=1 r=0 | c=1 r=1 |
|---|---|---|---|---|
| 17³ | +0.536 | +0.287 | **−0.544** | **−0.677** |
| 33³ | +0.288 | +0.127 | **−0.318** | **−0.466** |

**Sin comprimir, el signo es el bueno (más varianza → más error). Con compresión, se invierte
en las 4 combinaciones.** El AUC global (+0.391 de ρ) es **0.248** (`grep "CALD auc
variance_zona"`, IC95 0.171–0.315): peor que al azar en la dirección «más varianza es peor»,
justo porque mezcla dos clases con el signo contrario. Ver §6 para la explicación que encontré.

### 3.3 `muestras_p10_zona` / `muestras_mediana_zona`: NO es monótona, y se reproduce el
hallazgo del día 4

El encargo pedía comprobarlo explícitamente: el día 4 encontró que los peores errores fuera de
plano salían de celdas con 7 o 14 muestras, no de celdas vacías. Con tramos de ANCHO FIJO cerca
de `MUESTRAS_MINIMAS_CELDA` (4) —los cuantiles lo esconden, porque más de la mitad de las filas
tienen `muestras_p10_zona = 0`— (`grep "CALD tramos_bajos muestras_p10_zona] simple"`):

| `muestras_p10_zona` | n | ΔE máx. mediana | Cumple |
|---|---|---|---|
| [0, 1) — celda vacía, puro relleno suave | 640 | 11.04 | **2.5%** |
| [1, 4) | 50 | 10.93 | **0.0%** |
| [4, 8) | 20 | 10.34 | **0.0%** |
| [8, 16) | 39 | 10.67 | 7.7% |
| [16, 32) | 48 | 7.29 | 8.3% |
| [32, 64) | 62 | 9.39 | 6.5% |
| [64, ∞) | 341 | 7.41 | 16.1% |

**Tener entre 1 y 8 muestras es PEOR que no tener ninguna** (0.0% frente a 2.5% que cumple), y
recién a partir de ~16-64 muestras se nota una mejora clara. Se repite en `lote`
(`grep "CALD tramos_bajos muestras_p10_zona] lote"`: [0,1) cumple 28.3%, [1,4) cae a 0.0%,
aunque con menos filas). **Confirma, con datos nuevos e independientes, la razón por la que
`confianza_destino.py` expone el conteo crudo en vez de una rampa ya hecha**: una rampa
monótona ingenua («más muestras = mejor, cuanto antes mejor») habría estado mal en exactamente
esta zona.

---

## 4 · `planos_acumulados`

Sólo varía en el bloque `lote` (en `simple` vale 1 siempre). `ρ = −0.140`, IC95 **[−0.248,
−0.019]** — el intervalo no cruza el cero, así que el efecto es real, aunque modesto
(`grep "CALD rho_ic planos_acumulados"`).

Por tramos (`grep "CALD tramos planos_acumulados"`):

| Planos acumulados | n | ΔE máx. mediana | Cumple |
|---|---|---|---|
| 1 | 100 | 5.07 | 27.0% |
| 2 | 100 | 4.85 | 39.0% |
| 3 | 100 | 4.66 | 28.0% |
| 5 | 100 | 4.04 | 41.0% |
| 8 | 100 | 3.56 | 46.0% |

Tendencia clara de 1 a 8 planos (mediana −29.8%, cumple +19 puntos), con ruido en el escalón
intermedio (3 planos). AUC de `planos_acumulados` solo: **0.569**, IC95 [0.512, 0.627]
(`grep "CALD auc planos_acumulados"`) — mejor que azar, IC no cruza 0.5, pero mucho más débil
que `cobertura_destino`. Es información real y nueva (antes de esta tarea, ningún sitio del
repo medía si acumular planos mejora lo que se lleva a OTRO plano; el día 4 sólo tenía T5 con
`planos_acumulados=1`), pero no basta por sí sola para fijar un corte.

---

## 5 · Intento de nota combinada, y el mismo criterio de umbral del día 4

**Criterio**: el menor corte t tal que, entre los casos con nota ≥ t, el extremo INFERIOR del
IC95 bootstrap del % que cumple (ΔE máximo < 3.0) sea ≥ 95%. Igual que el día 4.

Probé `sqrt(min(subnotas) × media_geométrica(subnotas))` (la misma forma que
`puntuar_confianza`) con distintas combinaciones, sobre las 1.700 filas fuera de plano de
`simple` + `lote` juntas (`grep "CALD umbral nota] todo"`):

| Combinación | RESULTADO (todo junto) | AUC |
|---|---|---|
| Sólo `cobertura_destino` | ninguno; mejor con n≥20: **66.7%** (nota ≥ 1.0000, n=24) | 0.714 |
| `cobertura_destino` + `muestras_p10_zona` (rampa 200/4) | ninguno; mejor: **65.2%** (n=23) | 0.702 |
| `cobertura_destino` + `muestras_p10_zona` (rampa 1000/8) | ninguno; mejor: **74.1%** (n=27) | 0.698 |
| + `variance_zona` (control, ver más abajo) | **t=0.95** ✔ cumple 100% (n=26) | 0.750 |

**Ninguna combinación honesta (sin `variance_zona`) llega al 95%.** Mezclar TODAS las clases de
material en un solo umbral es más duro que dentro de una clase homogénea (bases muy distintas:
17³ sin comprimir cumple ~5-7%, 33³ comprimido ~0.7%), así que repetí el umbral **dentro de
cada una de las 8 clases** (`grep "CALD umbral_clase cobertura_destino"`):

| Clase | Mejor cumple (n≥15) | En |
|---|---|---|
| 17³ sin compresión, sin recorte | 40.0% | cobertura ≥ 0.991 |
| 17³ sin compresión, con recorte | 53.3% | cobertura ≥ 0.991 |
| 17³ comprimido, sin recorte | 20.0% | cobertura ≥ 0.994 |
| 17³ comprimido, con recorte | 23.5% | cobertura ≥ 0.994 |
| 33³ sin compresión, sin recorte | 60.0% | cobertura ≥ 0.978 |
| **33³ sin compresión, con recorte** | **82.4%** ← lo mejor | cobertura ≥ 0.975 |
| 33³ comprimido, sin recorte | 6.7% | cobertura ≥ 0.978 |
| 33³ comprimido, con recorte | 6.7% | cobertura ≥ 0.978 |

**Ninguna de las 8 llega al 95%, ni con la estimación puntual.** El mejor caso (82.4%, n=17) es
material sin comprimir con recorte de altas luces en 33³ — justo la condición en la que el LUT
tiene más margen para explicar el residuo. Con compresión, `cobertura_destino` sola no basta ni
de lejos (6.7%): coherente con que la compresión mete ruido que ninguna señal de COBERTURA
puede ver, porque no es un problema de "cuántas celdas vi" sino de "cuánto ruido metió el códec
en lo que vi".

**La única combinación que cruza el 95%** (`cobertura_destino` + `muestras_p10_zona` +
`variance_zona`, `grep "CALD umbral nota] todo, fuera de plano, cobertura+muestras_p10+variance"`)
lo hace con `t=0.95`, n=26, cumple 100% (IC95 [1.000, 1.000]). **La descarto**: §3.2 y §6
explican por qué meter `variance_zona` es la razón de que cruce, y por qué eso no es de fiar.

---

## 6 · Por qué NO se conecta (y no es sólo "no llega al 95%")

Hay dos motivos, y el segundo es el que de verdad decide:

1. **El criterio del día 4 no se cumple** en ninguna combinación sin `variance_zona`, ni
   mezclando clases ni dentro de cada una (§5). El mejor caso real es 82.4% con 17 casos, no
   95%.
2. **La única forma de llegar al 95% usa una señal con una paradoja de Simpson propia**
   (`variance_zona`, §3.2/§6.1). Usarla para cruzar el listón sería repetir, dentro de mi propia
   señal candidata, el error exacto que el día 4 diagnosticó en la nota actual: una correlación
   global que sólo existe porque una condición (aquí, la compresión) mueve la señal y el error a
   la vez, y se invierte en cuanto se mira una clase homogénea.
3. **`confidence_level()` es, a propósito, el ÚNICO sitio del repo donde un número se convierte
   en alta/media/baja** (`core/contracts.py`; el criterio está declarado único en
   `core/umbrales.py` §1 y en `CONTRATOS.md`, y es la razón de ser de `core/umbrales.py` entero:
   el día 2 encontró exactamente este bug — un criterio redefinido en otro sitio — en
   `gui/reverse_puente.py`). Reusar `confidence_level()` con `CONFIDENCE_ALTA = 0.75` para MI
   nota candidata (que tiene otra escala, calibrada sobre otros datos) da: con la nota
   `cobertura_destino + muestras_p10_zona` (sin `variance_zona`) en `t=0.75`, **cumple el
   29.2%** de las veces (`grep "CALD umbral nota] todo, fuera de plano, cobertura+muestras_p10
   rampa=200/4"`, fila `t=0.75`). Un «alta» que acierta el 29% de las veces es exactamente el
   problema que este informe existe para no repetir.

### 6.1 Lo que he visto sin que me lo pidieran: por qué `variance_zona` se invierte con
compresión

`Estadisticos.cobertura()` pone `variance = 0` cuando `counts < 2`
(`core/reverse/acumulacion.py`, comentario: «con una muestra no hay varianza que medir»).  Es
correcto por construcción — no se puede medir varianza con un solo dato — pero tiene un efecto
secundario: una celda casi vacía (0 o 1 muestra) contribuye **variance = 0** a la media
ponderada, que se lee como «esta zona es limpísima» cuando en realidad es «no hay datos aquí».
Con material comprimido, el cubo se cubre de forma más dispersa (más celdas con 0-1 muestras,
menos con muchas), así que una fracción mayor del peso de `variance_zona` cae en ese «0 que no
es un 0 bueno». El resultado es que, bajo compresión, `variance_zona` tiende a bajar (parecer
mejor) precisamente en los casos peor cubiertos — la dirección contraria a la que hace falta.
No es un bug de aritmética (los tests de `tests/test_reverse_confianza_destino.py` comprueban
exactamente este caso —celdas con varianza puesta a 0— y pasan: es el comportamiento
documentado de `CoverageMap.variance`), es una interacción entre dos señales correctas por
separado (`variance` y la escasez de datos bajo compresión) que las vuelve engañosas juntas. Lo
reporto en vez de corregirlo o silenciarlo, como pide el encargo.

---

## 7 · Límites de esta medida

* **Material sintético**, igual que el día 4: mismas escenas, mismo grado, mismo códec. En
  material real, no medido.
* **`lote` con planos siempre coherentes.** Las N tomas de una extracción por lote comparten
  grado EXACTO a propósito, para aislar `planos_acumulados`. Qué pasa con `cobertura_destino` /
  `muestras_p10_zona` cuando el lote SÍ tiene planos discrepantes (el caso que
  `comprobar_coherencia` está pensado para cazar) no está medido aquí.
* **`planos_acumulados` sólo llega a 8.** Si el efecto sigue mejorando más allá, o se aplana,
  no está medido.
* **Sin comprobación de resolución.** El día 4 comprobó 320×180 contra 640×360 y la conclusión
  no cambiaba; aquí no se ha repetido esa comprobación por tiempo. Dado que las señales nuevas
  dependen de conteos de celdas del cubo (no de estadística de píxel a píxel como la nota
  actual), es razonable esperar que dependan aún menos de la resolución, pero es una suposición,
  no una medida.
* **El umbral por clase con n≥15-17 es poco robusto.** El bootstrap por escena con pocas escenas
  por encima del corte da intervalos anchos; el 82.4% de la mejor clase no tiene un IC95 fiable
  con esa n (por eso la tabla de §5 no lo lleva: `bloque_umbral_por_clase` exige n≥15 para
  calcular el bootstrap, pero con 15-17 casos el intervalo es demasiado ancho para decidir nada
  con él, y se reporta el mejor % con su n, no un IC que no significaría nada).
* **`nota_combinada` (§5) es una candidata mía, no una propuesta de diseño final.** Las rampas
  de `muestras_p10_zona` (200/4 y 1000/8) las elegí para explorar sensibilidad, no están
  medidas contra un panel de coloristas ni nada parecido.

---

## 8 · Tests

```bash
.venv/bin/python -m pytest tests/test_reverse_confianza_destino.py tests/test_umbrales.py tests/test_contratos.py tests/test_matching_confianza.py -q
```

**72 passed** (9 de `test_reverse_confianza_destino.py`, sin tocar; el resto sin cambios porque
no toqué `core/umbrales.py`, `core/contracts.py` ni `core/matching/confianza.py`).

```bash
.venv/bin/python -m pytest tests/ -q
```

**Suite completa: `EXIT=0`, sin ningún `F` (fallo) ni `ERROR`.** Los `x`/`s` que se ven en la
salida son los `xfail`/`skip` ya documentados de otros agentes (p. ej. el `xfail(strict=True)`
del día 4 en `tests/calibracion/test_calibracion.py` y las copias congeladas de T5), no algo
que haya movido yo.

No he escrito tests nuevos de `core/` porque no he tocado ningún archivo de `core/`: los únicos
archivos nuevos son de medición (`tests/calibracion_destino/`), que no es código de producción.

---

## 9 · Filas para `CIFRAS.md`

Montaje de todas: calibración, `tests/calibracion_destino/`, 320×180, huella `2c8eaea7888a`,
ΔE de `colour`. Comando de todas: `.venv/bin/python -m tests.calibracion_destino.analizar` con
el `grep` indicado. Fecha: **16-09**. Ver la tabla completa en `CIFRAS.md` §13.

---

## 10 · Lo que queda por decidir

1. **¿Vale la pena bajar el listón del 95%?** Es una decisión del encargo, no mía: el día 4 lo
   fijó porque «alta» tiene que significar «me lo llevo sin mirar». Si el listón real que
   necesita Mario es más bajo (p. ej. «avísame si baja de X, no me prometas nada por encima»),
   `cobertura_destino` sola (AUC 0.73-0.97 por clase) sí serviría para ESO, que es una pregunta
   distinta a la que este informe responde.
2. **`variance_zona` tal y como está no sirve para puntuar.** Si se quiere arreglar, el camino
   más directo por lo que encontré en §6.1 es no promediar `variance` con peso trilineal sin más,
   sino excluir (o ponderar aparte) las celdas con `counts < 2` en vez de dejar que su `variance
   = 0` se cuele en la media como si fuera una zona limpia. No lo he tocado: es una decisión de
   diseño de la señal, y cambiarla sería tocar el trabajo de quien escribió
   `confianza_destino.py`, que es exactamente lo que la regla de «no arbitres» me pide no hacer
   en solitario.
3. **`planos_acumulados` con lotes incoherentes**, y su interacción con `cobertura_destino`
   cuando SÍ hay planos descartados por `comprobar_coherencia`: no medido (§7).
