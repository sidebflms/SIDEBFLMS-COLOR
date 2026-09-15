# NOTAS — agente B · análisis

Qué decidí, qué descarté y por qué. Con números medidos, no impresiones, para que
mi revisor pueda discreparme con criterio.

Todo lo de aquí se comprueba solo:
`.venv/bin/python -m pytest tests/test_analysis_*.py` (117 tests, en verde hoy).

---

## 0. Los dos números de la huella, primero de todo

Es lo que pedía el encargo y es lo que más me jugaba, así que va arriba.

| Qué se mide | Valor |
|---|---|
| **Invariancia al grado** (estudio vs estudio + CDL fuerte + LUT de look) | **0,9967** |
| **Separación entre escenas** (estudio vs exterior al sol) | **0,0000** (coseno crudo −0,0198) |

Desglosado:

| Par | Parecido |
|---|---|
| estudio vs estudio + CDL fuerte | 0,9988 |
| estudio vs estudio + LUT de look | 0,9979 |
| estudio vs estudio + CDL + LUT | **0,9967** |
| estudio vs estudio con saturación ×2,5 | > 0,999 |
| estudio vs estudio ±2 pasos de luz | 0,958 / 0,949 |
| peor par entre los 6 tonos de piel (misma composición) | 0,756 |
| estudio vs exterior | **0,0000** (crudo −0,0198) |
| estudio vs ColorChecker | 0,0000 |
| estudio vs rampa de gris | 0,0000 |

El CDL de la prueba no es sutil: `slope (1.35, 0.92, 0.72)`, `offset (0.03, −0.02,
0.06)`, `power (0.85, 1.05, 1.25)`, `saturation 1.45`. Y el LUT lleva una curva en
S monótona en el rojo (`t − 0.12·sin(2πt)`) y gammas distintas en verde y azul.
Que el grado hace algo de verdad no es una suposición: hay un test de control
(`test_el_grado_cambia_el_color_de_verdad`) que exige que la media se mueva más de
0,05 y que el histograma de saturación se mueva más de 0,2 de distancia de
variación total. Si el grado fuera flojo, la invariancia no probaría nada.

Está todo en `tests/test_analysis_huella.py::test_la_huella_aguanta_el_grado_y_separa_las_escenas`.

---

## 1. La huella: de qué están hechos los 96 números

96 = **64 + 16 + 16**.

1. **64 — rejilla 8×8 de luma, por rangos.** Se promedia la luma de cada una de
   las 64 celdas y se guarda su *rango* (posición en el orden) normalizado a 0..1
   menos 0,5. Es la composición del plano: dónde están las zonas claras y las
   oscuras.
2. **16 — histograma de orientación del gradiente** de la luma, 16 sectores de 0°
   a 180°, contando sólo los píxeles con magnitud de gradiente por encima de la
   mediana. Distingue un horizonte (todo horizontal) de una cara (repartido).
3. **16 — rejilla 4×4 de densidad de detalle, por rangos.** Qué fracción de cada
   celda tiene gradiente fuerte. Dice *dónde* está el detalle: en un retrato, en
   la cara; en un exterior, en el horizonte y el camino.

### Por qué de rangos y no de valores

Porque **el rango no cambia al aplicar una función monótona creciente**, y un
grado es en lo esencial una función monótona por canal. Más aún: la saturación
del CDL no toca la luma **en absoluto** — la fórmula es `luma + s·(x − luma)` con
los mismos pesos Rec.709, así que la luma sale idéntica. De ahí el 0,999 de la
fila "saturación ×2,5".

### Lo que descarté, y es la decisión importante

La primera versión tenía un cuarto bloque: **16 números con la distribución
espacial de la saturación** (rejilla 4×4 de la saturación media, también por
rangos). Parecía buena idea: aporta color, que es de lo que va la app.

Medido bloque a bloque, coseno consigo mismo tras graduar:

| Bloque | Bajo CDL fuerte | Bajo CDL + LUT |
|---|---|---|
| 8×8 de luma | +0,9997 | +0,9994 |
| orientación | +0,9994 | +0,9977 |
| **saturación 4×4** | **+0,6294** | **−0,1500** |

El bloque de saturación **no describía el plano: describía el grado**. Con él
puesto, la invariancia total caía a **0,769**; quitándolo sube a **0,9967**. Y no
compensaba en separación: estudio vs exterior daba 0,053 en ese bloque, o sea
nada. Se cayó entero y sus 16 números se los llevó la densidad de detalle, que sí
es invariante (0,988) y sí separa (0,043 entre estudio y exterior).

**Consecuencia que hay que saber: la huella es ciega al color.** Dos planos con la
misma composición y colores distintos se parecen mucho. Para lo que la usa el
agente C (avisar de que dos escenas no son comparables) eso es correcto, porque
el color es precisamente lo que se va a igualar. Si mañana hiciera falta detectar
"mismo encuadre, temperatura de color imposible de casar", eso **no** lo da la
huella y hay que sacarlo de `ColorStats`, que para eso está.

### Pesos y centrado

Pesos: 55% composición, 25% orientación, 20% detalle. Cada bloque se normaliza a
norma 1 por separado y se escala por `sqrt(peso)`, así que el vector final tiene
norma 1 exacta y ningún bloque se come a los demás por ser más largo.

**Cada bloque va centrado en cero**, y esto no es cosmético: sin centrar, dos
vectores de números positivos cualesquiera dan coseno ~0,9 y la huella no separa
nada. Centrados, dos planos sin relación dan coseno alrededor de 0.

`parecido_de_huellas` devuelve el coseno **recortado por abajo a 0**. Un coseno
negativo (estudio vs exterior da −0,0198) significa lo mismo que 0 para esto: no
son comparables. Recortar en vez de reescalar 〔−1,1〕→〔0,1〕 es deliberado: así el
umbral que ponga el agente C significa "se parecen un tanto por ciento" y no
"están un tanto por ciento por encima del azar".

### El caso degenerado

Una imagen plana (negra, blanca, de un solo color, de un solo píxel) no tiene ni
composición, ni gradientes, ni detalle: los tres bloques salen a cero y la norma
sería 0, lo que **incumpliría el contrato** (`norma L2 = 1`). Se devuelve el
vector uniforme `1/√96`. Así todas las imágenes planas se parecen entre sí (que es
verdad) y se parecen **cero** a cualquier plano real, porque los bloques de un
plano real suman cero. Medido: negra vs blanca = 1,0000; negra vs estudio =
0,0000.

### NaN en la huella

Es **lo único del módulo que no propaga NaN**, y es a propósito: con un NaN dentro
la norma no puede ser 1 y el contrato se rompe. Los píxeles no finitos se
sustituyen por la mediana de los finitos. El NaN no se pierde de vista: las
estadísticas sí lo propagan y `ClipAnalysis.warnings` lo dice con el número de
píxeles afectados.

---

## 2. `ColorStats`, decisión a decisión

### Punto negro y punto blanco: percentiles **1** y **99**

No el mínimo y el máximo, que los decide un píxel muerto. Medido sobre el retrato
de estudio, matando 144 píxeles (el 0,06% de la imagen) y viendo cuánto se mueve
cada candidato:

| Candidato | Desplazamiento relativo máximo |
|---|---|
| mínimo | colapsa a 0 |
| p0.1 | **13,8%** |
| **p1 (el elegido)** | **2,4%** |
| p5 | 0,1% |

El p0.1 todavía lo deciden 230 píxeles en un plano de 640×360, que es un grupito
de píxeles rotos. El p5 aguantaría aún mejor, pero el 5% de los píxeles de un
plano oscuro ya no es "el negro": es media imagen. El p1 es donde deja de mandarlo
un accidente sin dejar de ser el negro. Simétrico arriba con el p99, que además
deja fuera el especular de la frente (que en `studio_scene` ocupa justo el 0,1%).

Los dos salen **del mismo array `percentiles`**, no se recalculan: hay un test que
exige igualdad bit a bit, para que nadie los desincronice.

### Saturación: `(max − min) / max` por píxel (la de HSV)

Sobre los valores del **espacio de trabajo**, 64 bins uniformes en 0..1, suma 1.

Por qué ésta:
- Está **acotada en 0..1 sin recortar nada**, lo que importa porque el contrato 1
  exige preservar los valores fuera de rango (el sol del exterior está a 9,0).
- Un neutro da 0 exacto y un primario puro da 1 exacto: los dos extremos
  significan algo.
- Los píxeles con máximo ≤ 0 (negro, o negativos de fuera de gamut) dan 0: sin luz
  no hay saturación que medir. Si no, `(0.4 − (−0.2))/0.4 = 1.5` se saldría del
  rango.

**Lo que descarté: el croma de Oklab** (`hypot(a, b)`). Es perceptualmente mejor y
para emparejar sería más fino, pero (a) no está acotado, así que habría que elegir
un rango arbitrario para los 64 bins, (b) es unas 20 veces más caro, y (c) dejaría
el histograma **fuera de `WORKING_SPACE`**, que es donde el contrato lo pide. Si a
Mario le interesa más el croma perceptual, el cambio es una función
(`saturacion_hsv`) y los bins; pero entonces hay que decidir el rango y decirlo.

**Ojo con una cosa**: la saturación se mide sobre valores *logarítmicos* (DaVinci
Intermediate), así que los números no son comparables con los de un vectorscopio
sobre material lineal. Son coherentes entre sí, que es para lo que se usan.

### Covarianza degenerada

- **Menos de 2 píxeles**: el denominador `N−1` es cero y la covarianza **no está
  definida**. Se devuelve la **matriz de ceros**, no NaN. Un NaN ahí sería
  indistinguible de un píxel roto, que es lo que de verdad hay que ver.
- **Imagen de un solo color**: sí está definida y sale **cero exacto**, sin
  ninguna división rara. No hace falta regularizar nada.
- **No hay regularización de ningún tipo.** Descarté sumar `ε·I`: quien invierta
  esta matriz (el agente C, si hace un ajuste por covarianza) tiene que ver que es
  singular y decidir él, no recibir una matriz maquillada que invierte "bien" y da
  un resultado sin sentido.
- Se usa `ddof=1` (covarianza muestral). Hay un test que exige que la diagonal
  cuadre con `std**2`, donde `std` va con `ddof=0`: cuadran a `rtol=1e-5` porque
  N es grande. Con N pequeño **no cuadrarían**, y es correcto que no cuadren.

### Piel

`skin_locus` es el Oklab medio de los píxeles que marca `core.color.skin_mask_oklab`
(no reimplemento nada). **"Suficiente" = al menos el 0,5% de los píxeles Y al menos
64 píxeles absolutos.**

- El 0,5% es para que un plano general no se guíe por una cara de 20 píxeles.
- Los 64 absolutos son para que en una miniatura de 64×64 no basten dos píxeles.
- Los seis tonos de piel de `studio_scene` pasan de sobra (el peor, ~9%).

Es un umbral elegido con la cabeza, no medido contra un conjunto de validación —
no tengo uno. Si aparece material real con caras pequeñas, es el primer número que
revisaría.

### NaN: se propaga

Misma política que `core.color`, y por el mismo motivo: si la media usara
`nanmean`, el agente C recibiría un número plausible sobre material corrupto y
nadie se enteraría. Con un solo píxel NaN salen NaN `mean`, `std`, `cov`,
`percentiles`, `black_point` y `white_point`.

**La única excepción es `saturation_hist`**, que cuenta sólo píxeles finitos. Si
propagara, no podría sumar 1 y rompería el contrato. Con la imagen **entera** a
NaN el histograma se queda **todo a cero** — el único caso en el que no suma 1, y
está escrito en el código, aquí y en un test. Inventarse una distribución habría
sido peor.

---

## 3. Extracción de fotogramas

### Cuántos: **12** por defecto

Medido sobre un clip de 50 fotogramas con deriva de exposición de ±0,6 pasos y un
objeto cruzando el encuadre, comparando contra el análisis de los 50:

| k | error relativo de la media | error del punto blanco | parecido de la huella | segundos |
|---|---|---|---|---|
| 1 | 0,281% | 4,08% | 0,9727 | 0,10 |
| 2 | 0,633% | 4,96% | 0,9846 | 0,18 |
| 4 | 0,105% | 1,22% | 0,9950 | 0,35 |
| 8 | 0,040% | 0,42% | 0,9992 | 0,71 |
| **12** | **0,039%** | **0,54%** | **0,9997** | **1,07** |
| 24 | 0,004% | 0,04% | 0,9999 | 1,65 |
| 50 | 0 | 0 | 1,0000 | 3,08 |

A partir de 8 las mejoras están en el cuarto decimal y el coste sigue subiendo
lineal. 12 da margen sobre 8 y deja el análisis de un plano por debajo del
segundo. Con 1 o 2 fotogramas el punto blanco se va un 4-5%, que ya es visible.

### Cómo se reparten, y el detalle sucio que costó medir

Se piden los `k` índices igualmente espaciados entre el primer fotograma y el
último. Traducir un índice a un `-ss` que ffmpeg entienda tiene dos trampas, las
dos medidas y afirmadas en `test_analysis_frames.py`:

1. Con `-ss` **antes** de `-i`, ffmpeg entrega **el primer fotograma cuyo pts es ≥
   el instante pedido**. Pedir el *centro* del fotograma `i` devuelve el `i+1`.
2. Pedir el centro del **último** fotograma **no devuelve nada**: ffmpeg se planta
   detrás del final del fichero y saca **cero bytes con código de salida 0**. O
   sea que ni siquiera falla: se calla.

Por eso se pide medio fotograma **antes** del que se quiere, `(idx − 0.5)/fps`.
Con eso sale exactamente `idx`, el último incluido. Hay un test de regresión
(`test_el_ultimo_fotograma_del_clip_es_alcanzable`) porque esto se rompe solo en
cuanto alguien "simplifique" el cálculo.

**Descarté** decodificar el clip entero con el filtro `select` (exacto y sin
trampas, pero en un plano largo hay que decodificarlo todo) y **descarté** el
seek de salida (`-ss` después de `-i`, exacto pero decodifica desde el principio
cada vez). El coste real del camino elegido es ~85 ms por fotograma, casi todo
lanzar el proceso y buscar; en un 4K será más.

### Precisión: `rawvideo` en `rgb48le`, 16 bits

Nunca PNG de 8 bits. Hay un test que cuenta niveles distintos en una rampa: salen
**350**, imposible en 8 bits. No son 65.536 porque el techo real lo pone el códec:
`generate.make_clip` escribe ProRes 4444 en `yuv444p10le`, o sea 10 bits.

Ida y vuelta de un gris por el clip: **< 1e-3** en escena-lineal.

### Qué espacio se asume cuando no se sabe

Por orden:

1. Lo que venga en `space=`. Manda siempre.
2. Lo que diga ffprobe (`color_transfer` / `color_primaries`). Hoy se reconocen
   `bt709`, `smpte170m`, `bt470bg` e `iec61966-2-1` (sRGB), y los cuatro se mapean
   a **`rec709`**. Se deja aviso de que se ha deducido.
3. Si no hay nada: **`rec709`** para vídeo (la OETF de cámara BT.709, no la gamma
   de pantalla) y **`linear_rec709`** para EXR/HDR. Se deja aviso, con el texto
   "*Si el material es log, pasa `space=` a mano*".

**Límite real, medido, que no escondo:** `iec61966-2-1` (sRGB) se mapea a `rec709`
y **no son la misma curva**. Se separan en las sombras. `tests/media/generate.py`
codifica los clips con la curva sRGB y este módulo los decodifica como Rec.709:
un gris de 0,045 escena-lineal vuelve como **0,0705** si se deshace con la curva
equivocada, un **+57%**. Está afirmado en
`test_la_curva_srgb_del_generador_no_es_la_de_rec709`.

No afecta al material de cámara (que viene etiquetado `bt709` y se decodifica
bien), pero sí a quien compare los clips sintéticos contra el `Scene.image`
original. **Lo correcto sería que `core.color` tuviera un espacio `srgb`**, y eso
no es mío: si el orquestador lo añade, aquí es una línea en `_TRANSFER_A_ESPACIO`.

### Imágenes sueltas

PNG/EXR/TIFF/JPG/BMP/HDR **no pasan por ffmpeg**: se leen con OpenCV. El motivo es
el EXR: contiene float32 con negativos y con especulares por encima de 1,0, y una
tubería `rgb48le` los recortaría. Hay un test que comprueba que el sol del
exterior (9,0) sobrevive al EXR.

### Averías: qué sale por cada una

Todas heredan de `ErrorAnalisis`, que es lo único que la GUI tiene que capturar.
Ninguna es un traceback.

| Qué pasa | Qué sale |
|---|---|
| la ruta no existe | `FicheroNoEncontrado`: "No existe el fichero: …" |
| la ruta es una carpeta | `FicheroNoEncontrado`: "Esperaba un fichero y … es una carpeta." |
| fichero de 0 bytes | `FormatoNoSoportado`: "El fichero esta vacio (0 bytes): …" |
| no es un vídeo | `FormatoNoSoportado`, con el motivo que da ffprobe |
| no es una imagen legible | `FormatoNoSoportado`, diciendo que mire el soporte OpenEXR |
| no hay ffmpeg/ffprobe | `HerramientaNoDisponible`, con el `brew install` que ya traía `core.paths` |
| ffmpeg no decodifica nada | `ErrorFFmpeg`: "…esta truncado, corrupto o el codec no esta soportado." |
| **clip truncado a mitad** | **NO lanza**: se queda con los fotogramas que sí, y lo dice en `warnings` |
| clip de 1 fotograma | 1 fotograma + aviso |
| menos fotogramas de los pedidos | los que haya + aviso con los dos números |

Lo del clip truncado es una decisión: un plano del que se salvan 7 de 12
fotogramas **sí** se puede analizar, y negarse sería peor que avisar. Si no se
salva ninguno, entonces sí lanza. Hay además un último intento sin buscar (el
primer fotograma del fichero) antes de rendirse, porque un índice roto de un `.mov`
suele dejar el primer fotograma legible.

---

## 4. Otras decisiones que Mario podría querer cambiar

### 4.1 La estadística de un clip se corta en 2 millones de píxeles

12 fotogramas de 4K son 100 millones de píxeles, y en float64 eso son 2,4 GB. Por
encima de `MAX_PIXELES_ESTADISTICA = 2_000_000` se toma una muestra aleatoria con
semilla fija. Con 2 millones de muestras el error típico de la media está en el
quinto decimal. **En los clips HD de los tests nunca se activa**, así que es un
camino menos ejercitado de lo que me gustaría.

### 4.2 `ClipAnalysis.path` de una imagen en memoria es `"<memoria>"`

`analizar_imagen` no tiene fichero y `path` es `str`, no `str | None`. Puse
`"<memoria>"` en vez de cadena vacía para que se lea en la GUI. Es una convención
que me inventé yo: si al agente H le estorba, se cambia en una línea.

### 4.3 La huella de un clip es la media de las huellas de sus fotogramas

Y luego se renormaliza. La alternativa (una sola huella sobre los fotogramas
apilados) daría un resultado raro porque los bloques son espaciales. Con la media,
un plano con un movimiento fuerte no queda descrito por el fotograma que tocó.
Efecto medido: la huella de 12 fotogramas de un clip con movimiento se parece
0,9997 a la de los 50.

### 4.4 `parecido_de_huellas` recorta los negativos a 0

Ver §1. Si el agente C prefiere ver el coseno crudo para calibrar umbrales, es una
línea, pero entonces el rango deja de ser 0..1 y el contrato de la firma cambia.

### 4.5 El aviso de "imagen prácticamente neutra"

Salta cuando el 99,9% de los píxeles cae en el primer bin de saturación. Es un
umbral a ojo, pensado para rampas y cartas de gris. En material real con un plano
muy desaturado podría saltar sin que haga falta.

---

## 5. Lo que NO hice

- **Detección de espacio por el contenido.** Si el fichero no trae metadatos y el
  material es log, se decodifica mal y sólo queda el aviso. Se podría adivinar
  mirando el histograma (el log no llega nunca al negro ni al blanco), pero
  adivinar el espacio de color a partir de los píxeles es una fuente de errores
  silenciosos y preferí un aviso ruidoso.
- **Descartar fotogramas malos.** Si un fotograma del clip es un fundido a negro
  o un flash, entra en la media como los demás. Detectar y descartar atípicos es
  fácil de hacer y difícil de hacer bien; no lo he intentado.
- **Rendimiento.** ~85 ms por fotograma, casi todo en lanzar ffmpeg. No he medido
  4K ni he intentado paralelizar. Si el agente H analiza 200 clips de una tanda,
  hay que mirarlo.
- **Nada con `pixels` más allá de muestrear.** `ClipAnalysis.pixels` es una
  muestra aleatoria con semilla fija, sin ninguna estratificación. Para estimar la
  distribución vale; para cubrir los colores raros del cubo (que es lo que
  necesitaría el agente F), un muestreo estratificado sería mejor.
- **EXR con primarios que no sean Rec.709.** Un EXR de ACES se leería como si
  fuera `linear_rec709` y saldría con el color cambiado. Hay que pasar `space=` a
  mano; no hay forma de detectarlo con OpenCV.

---

## 6. Cosas que quise tocar y no toqué

No he editado ni una línea fuera de `core/analysis/**` y `tests/test_analysis_*.py`.

Dos cosas que me habrían venido bien y que **son del orquestador**, así que las
dejo apuntadas en vez de hacerlas:

1. **Un espacio `srgb` en `core.color`.** Ver §3. Es lo que codifica
   `tests/media/generate.py` y hoy no se puede nombrar. Mientras tanto, cualquiera
   que compare un clip generado contra su `Scene.image` original tiene que
   deshacer la curva sRGB a mano (hay un ayudante `_lineal_de` en mis tests que
   enseña cómo).
2. **Que `generate.make_clip` etiquete el color** (`-color_primaries bt709
   -color_trc bt709 -colorspace bt709`). Hoy sus clips salen sin metadatos, así
   que el camino de deducción sólo se prueba reetiquetando el fichero a mano
   dentro del test.

Ninguna de las dos bloquea nada.


---

## DÍA 3 · dónde viven ahora los umbrales de decisión

El hallazgo más grave del día 2 no fue ninguno de los cuatro casos auditados:
fue que **`gui/reverse_puente.py` tenía su propia definición, más floja, de
«esto es un LUT puro»** (0.92 a secas, frente al 0.95 **y** el percentil 95 por
debajo de 1.0 ΔE2000 que pide el núcleo), y que la GUI caía a ese criterio ante
cualquier excepción. Eso no es un bug suelto: es una clase de bug, la de un
criterio que se puede escribir dos veces.

Los umbrales de este módulo que **deciden un veredicto que Mario lee** se han
mudado a **`core/umbrales.py`**, que es desde hoy el único sitio donde se
escribe un criterio de decisión. Aquí se reexportan con el mismo nombre de
siempre, así que nada de lo que importaba de este módulo se ha roto.

**Ni un valor se ha movido.** Lo afirma `tests/test_umbrales.py`, que lleva la
tabla de valores de origen tecleada desde el código anterior al barrido, y lo
confirman las cuatro cifras de titular de `tests/test_entregables.py`, que
salen idénticas.

Lo que **no** se ha mudado son los parámetros de implementación: sólo le
importan a este módulo y llevarlos a un archivo común habría creado un
módulo-Dios que acopla todo con todo.

`tests/test_umbrales_literales.py` recorre el AST de `core/` y se pone rojo si
vuelve a aparecer un literal de umbral suelto.

**De este módulo se han mudado** los tres que deciden un aviso que Mario lee en
la lista de clips: `FRACCION_PIEL_MINIMA` y `PIXELES_PIEL_MINIMOS` (deciden si
`skin_locus` sale `None` y si se avisa de que no hay piel suficiente) y el
`0.999` de `saturation_hist[0] >= 0.999`, que **no tenía nombre** y decide el
aviso «la imagen es prácticamente neutra entera». Hoy es `UMBRAL_NEUTRA_TOTAL`,
y va con lo que dice §4.5 tal cual: es un umbral a ojo.

**Se quedan aquí**: `PERCENTIL_NEGRO` y `PERCENTIL_BLANCO` (definen qué *es* el
punto negro y el blanco, no deciden nada), `MAX_PIXELES_ESTADISTICA`,
`MAX_PIXELES_POR_DEFECTO`, `SEMILLA_MUESTREO`, `N_FOTOGRAMAS_POR_DEFECTO`,
`TIMEOUT_S`, `REJILLA_LUMA`, `BINS_ORIENTACION`, `REJILLA_DETALLE`,
`LADO_GRADIENTE` y `PESOS`. Todos son parámetros de implementación.
