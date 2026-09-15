# NOTAS — agente F · reverse

Qué se decidió, qué se descartó y por qué. Con números medidos, no impresiones.

**Este archivo se escribió el día 2, no el día 1.** El agente que escribió el
módulo murió por el límite de la API antes de escribir un solo test propio y
antes de dejar estas notas. Lo que sigue está reconstruido **leyendo el código y
`git show 4f94c8d`**, y donde no he podido deducir el porqué lo digo con esas
palabras (§9) en vez de inventarme una explicación que suene bien. Lo del
detector espacial (§6) sí es mío y está medido de primera mano.

Todo lo de aquí se comprueba solo:

```bash
.venv/bin/python -m pytest tests/test_reverse_espacial.py tests/test_reverse_bordes.py -q
.venv/bin/python -m pytest tests/test_entregables.py -q -s
```

---

## 0. Las cifras que se piden primero

| | criterio | resultado |
|---|---|---|
| **T1 · ida y vuelta** | ΔE2000 medio < 1.0 · máximo < 3.0 en la zona cubierta | **0.1415** · **1.7409** |
| **T2 · lo que no es un LUT** | no puede decir 100% LUT y tiene que señalar la zona | **70.0%** reproducible; la zona solapa el **99.4%** con la ventana real |
| **T2 · contrapeso** | sin nada espacial tiene que decir que SÍ es un LUT | **99.2%** reproducible, `is_pure_lut = True`, **cero** hotspots |

**T1 y T2 no se han movido ni una milésima respecto a la noche 1** (0.1415 /
1.7409 y 70.0%). Es a propósito y es la comprobación de que el arreglo del día 2
está **entero** en el detector y no toca el ajuste del LUT.

Cifras de apoyo:

- Cobertura real de un solo plano: **165 celdas de 35.937**, el **0.46%** del
  cubo. Las otras 35.772 están inventadas, y `coverage.counts == 0` dice cuáles.
- **Límite conocido y medido**: la ida y vuelta de un plano **sin gradar** no
  vuelve exacta. **0.3122 ΔE2000 de media y 6.3554 en el peor píxel**, con el
  CDL saliendo identidad exacta. Lo que no vuelve exacto es el LUT: las celdas
  sin muestras se rellenan suavizando y ese suavizado se cuela en las celdas del
  borde de la zona con datos; con un 0.46% de cobertura hay muchísimo borde.
  **Esta cifra no la he cambiado**: es la misma de la noche 1.
- Compresión h264 fuerte (ffmpeg, yuv420p 8 bits, crf 12) encima de un grado que
  sí es un LUT: **94.41%** reproducible, 0.981 ΔE2000 de media, 2.124 en el p95,
  y **cero hotspots espaciales**. O sea: la compresión degrada la cifra —y debe
  degradarla, parte del grado ya no está— pero no se convierte en una ventana.

---

## 1. Las dos capas, y por qué en ese orden

```
coloreado ≈ LUT( CDL( original ) )
```

**Primero el CDL, luego el LUT sobre el resultado.** Sin variantes. Es el mismo
orden que usa `MatchResult` del agente C, y eso no es casualidad: dos módulos que
devuelven un `(CDL, LUT)` con órdenes distintos es como se fabrica un bug que
nadie encuentra porque en las pruebas de cada uno funciona.

Por qué dos capas y no sólo el LUT:

- Un LUT es una caja negra de 35.937 números que no se lee, no se discute y no se
  retoca. El CDL son diez números con nombre.
- El CDL va al nodo 2 de Resolve **por parámetro**, que es lo único que la API
  deja escribir de verdad sin ficheros.
- Y el de fondo: como el CDL se lleva la mayor parte del movimiento, **lo que le
  queda al LUT es pequeño**, y un residuo pequeño se extrapola muchísimo mejor a
  las 35.772 celdas que nadie ha visto.

El CDL lo ajusta `core.matching.ajustar_cdl` (agente C), no este módulo. Aquí
sólo se decide **con qué píxeles**: como mucho `MAX_PIXELES_CDL` = 60.000, por
submuestreo **determinista de paso constante** (nada de aleatoriedad: dos
ejecuciones tienen que dar el mismo grado). El LUT sí usa todos los píxeles.

Por debajo de `MUESTRAS_MINIMAS_CDL` = 64 píxeles válidos no se ajusta CDL: se
devuelve la identidad y se dice en las notas. Diez parámetros con cuatro píxeles
es ruido con forma de grado.

---

## 2. Cómo se alinea

`core/reverse/alineado.py`. Tres cosas, y sólo tres:

1. **Igualar resolución**, reescalando **a la más pequeña de las dos**. Subir de
   resolución inventa detalle, y el detalle inventado acaba dentro del LUT como
   si fuera una medida. Bilineal en numpy puro con convenio de centro de píxel
   (`+0.5`), que es el de OpenCV y el de ffmpeg; con el convenio de esquina la
   imagen se desplaza medio píxel, que es justo lo que este archivo evita.
2. **Estimar un desplazamiento entero** por correlación de fase sobre la
   **magnitud del gradiente** con ventana de Hann. Sobre el gradiente y no sobre
   la imagen porque el color cambia entero con el grado y los bordes no se mueven.
3. **Verificarlo antes de aplicarlo.** La correlación de fase se equivoca. Se
   mide la correlación de gradientes con y sin el desplazamiento y sólo se aplica
   si mejora en más de `MARGEN_MEJORA` = 0.01.

Lo que **no** hace, y hay que saberlo: rotación, escala local ni subpíxel. Un
desplazamiento de medio píxel se queda sin corregir y se nota en el residuo. Por
encima de `MAX_DESPLAZAMIENTO_PX` = 32 px no corrige y lo dice: a esa distancia
lo más probable es que no sean el mismo plano, y desplazar 200 píxeles una imagen
para que «encaje» es como se fabrica un resultado bonito y falso.

Cuando la correlación final baja de `UMBRAL_CORRELACION_FIABLE` = 0.50,
`info["fiable"]` sale a `False` y `invertir_grado` lo convierte en una nota y en
una razón de confianza. **Medido** (está en el código, y lo confirman mis tests):
el mismo plano da > 0.9; un retrato contra un exterior da ~0.0.

### Un fallo que arreglé el día 2

`correlacion_de_gradientes` **lanzaba** con imágenes de menos de 2 píxeles en
algún eje: `np.gradient` necesita al menos dos elementos y el guardia
(`ga.size < 8`) estaba **después** de llamarlo. Una pareja de 1×1 píxel reventaba
con un `ValueError` de numpy en vez de contestar. Ahora `_gradiente` devuelve
ceros cuando no hay gradiente que calcular, la correlación sale **0.0** —que es
lo correcto: no es que los bordes no encajen, es que no hay bordes— y `alinear`
lo trata como «no me fío». Test: `test_una_imagen_de_un_solo_pixel_no_revienta`.

---

## 3. Cómo se acumulan las correspondencias, y qué es `counts`

`core/reverse/acumulacion.py`. Un píxel **no cae en una celda**: cae entre ocho
nodos y contribuye a los ocho con los mismos pesos con los que `LUT3D.apply()`
los va a interpolar después. El reparto trilineal es el **adjunto exacto** de esa
interpolación, y es lo que convierte el ajuste del LUT en unos mínimos cuadrados
bien planteados en vez de en una media de cajones.

Medido por el agente de la noche 1 y anotado en su docstring: repartiendo «al
nodo más cercano» el ΔE2000 medio sobre el retrato salía **2.3**; con el reparto
trilineal y el refinado, **0.3**.

`CoverageMap.counts[i,j,k]` = **cuántos píxeles reales usan ese nodo al
interpolar** con peso trilineal por encima de `PESO_DE_MUESTRA` = 1/8. El 1/8 no
es arbitrario: es el peso que un píxel da a cada uno de sus ocho nodos cuando cae
justo en el centro de la celda, o sea el peso mínimo que puede tener el nodo que
más le importa. De ahí salen tres propiedades:

- todo píxel es muestra de al menos un nodo: ninguno se pierde;
- `counts >= 1` implica suma de pesos ≥ 1/8, o sea que **nunca se divide por un
  peso microscópico**. Sin ese corte, una celda que recibe 1e-12 de peso se
  «ajusta» a ese píxel, el paso de Jacobi se amplifica por 1e12 y el LUT sale con
  escalones: **52 celdas no monótonas y 120 escalones de banding**, medidos;
- **`counts == 0` es exactamente el conjunto de celdas inventadas.** Ni una más,
  ni una menos. Es la promesa del mapa de cobertura y se cumple por
  construcción, no por buena voluntad.

`covered_mask()` (`counts >= min_samples`) es **otra pregunta** y más estricta:
no «¿hay dato?» sino «¿hay dato suficiente para fiarse?». Es un subconjunto.

---

## 4. Cómo se rellenan los huecos, y con qué criterio

`core/reverse/relleno.py`. **Qué celdas**: exactamente las de `counts == 0`.
**Cómo**: en dos capas.

**Capa 1, base afín global.** Sobre las celdas medidas se ajusta por mínimos
cuadrados ponderados la aplicación `v = M x + c` que mejor las explica. Es lo que
el grado hace «en general», y es lo que hace que lejos de los datos el LUT
**continúe la tendencia** en vez de aplanarse.

Con **cresta de Tikhonov hacia la identidad**, escalada al mayor autovalor
(`RIDGE_BASE` = 1e-2). Esto no es cosmética: los colores de una imagen no llenan
el cubo, viven en una nube alargadísima donde la luma manda y el croma casi no
varía, y en las direcciones sin grosor los mínimos cuadrados eligen cualquier
cosa que evaluada en la esquina del cubo se va lejísimos. **Medido** con original
== coloreado (grado identidad exacto): sin cresta la base salía con
`M = [[0.64, 0.31, 0.08], …]` y el LUT se desviaba **0.63** de la identidad en
las esquinas; con la cresta, **0.009**. Lo que la cresta dice en castellano: *en
las direcciones que los datos no fijan no me invento un grado, dejo la
identidad*.

**Capa 2, extensión armónica del residuo.** En las celdas medidas se calcula
`r = v_medido − (M x + c)` y ese residuo se extiende resolviendo Laplace con las
celdas medidas como Dirichlet (arranque por vecino más cercano + 60 barridos de
Jacobi de 6 vecinos). El resultado es la superficie **más suave posible** que
pasa exactamente por lo medido.

Por qué así y no de otra forma:

- **Vecino más cercano a secas**: produce mesetas con escalones en las fronteras
  de Voronoi, y `core.io.qc_lut` lo caza como banding. Con razón: se ve.
- **Dejar la identidad fuera de la cobertura**: sería un LUT con una isla de
  grado en medio de un mar de identidad, con un salto en el borde de la isla.
  Peor que extrapolar: se ve como un corte.
- **Sólo Laplace, sin base afín**: Laplace tiende a la media de lo conocido lejos
  de los datos, o sea aplana el grado donde no hay cobertura.

**Y la proyección monótona al final.** Un grado de verdad es monótono en cada
canal: no existe el grado que al subirle el rojo a un píxel le baja el rojo. Así
que cuando el LUT ajustado sale con una bajada, **eso no es el grado, es el
ajuste**. Medido en el T1: siete celdas con bajadas de entre 3e-4 y 9e-3, todas
en la frontera entre lo medido y lo extrapolado, donde la extensión armónica hace
un pliegue. Coste medido de la proyección: el ΔE2000 medio del T1 **no se mueve**
(0.141 antes y después) y el máximo sube de 2.19 a 2.30. A cambio, cero errores
de monotonía en `qc_lut`.

**El refinado.** El LUT no sale de la media ponderada: sale de resolver `A t = y`
por mínimos cuadrados con Jacobi precondicionado por la diagonal, sobre las
celdas medidas. Converge siempre (por Gershgorin los autovalores de `D⁻¹AᵀA` caen
en [0,1], así que el error nunca crece). Medido:

| iteraciones | ΔE2000 medio | máximo |
|---|---|---|
| 1 (la media ponderada de toda la vida) | 1.23 | 11.3 |
| 24 | 0.35 | 2.4 |
| 40 | 0.22 | 2.3 |
| **60** (`ITERACIONES_REFINADO`) | **0.14** | **2.30** |

Más de 60 sigue bajando la media pero ya no compensa lo que tarda (~40 ms por
iteración sobre 640×360).

### Un fallo que arreglé el día 2

Cuando **todo** el material, después del CDL, cae fuera del dominio 0..1, la
acumulación lo sujeta al borde y las 35.937 celdas se ajustan contra **una sola
esquina del cubo**. Lo que salía era un LUT **constante**: todo el gamut al mismo
color. Medido con un plano entero en 40.0 y el coloreado en 48.0: todas las
celdas a 1.0, y `core.io.qc_lut` lo cazaba con el código `lut_plano`… pero para
entonces ya se había entregado. Ahora, con `fuera >= 1.0`, se devuelve la
identidad y se dice en las notas, incluida la salida práctica («si el material es
log sin normalizar, normalízalo antes»). Es un caso real: un EXR de un cielo, o
log sin normalizar. Test:
`test_un_plano_que_no_entra_en_el_cubo_da_LUT_identidad_y_lo_dice`.

---

## 5. `lut_reproducible` y `is_pure_lut`

```
lut_reproducible = clip(1 − media(residuo) / media(movimiento), 0, 1)
```

donde `residuo` es el ΔE2000 por píxel entre `LUT(CDL(original))` y el coloreado,
y `movimiento` el ΔE2000 entre el original y el coloreado. Se lee en castellano:
**«de todo lo que este grado mueve el color, me llevo este tanto por uno»**.

Por qué esa fórmula y no «1 − residuo/8»: porque un residuo de 2 ΔE2000 sobre un
grado que mueve 40 es ruido, y el mismo residuo de 2 sobre un grado que mueve 3
es que no has recuperado nada. Un número absoluto no distingue esos dos casos y
éste sí. El absoluto también se da (`delta_e_mean`, `_p95`, `_max`), porque para
decidir si se entrega hace falta saber si lo que falta **se ve**.

Si el grado no mueve nada (`movimiento` medio < 0.05 ΔE2000) la fracción no está
definida y se devuelve 1.0 si el residuo también es despreciable. **Efecto
lateral confuso y conocido**: con los dos planos idénticos se entra por esa rama,
el residuo del relleno (0.3122) supera ese mismo 0.05, y `is_pure_lut` sale
`False`. Está anotado en `tests/test_entregables.py` y en `BITACORA.md` como cosa
a revisar. **De dónde sale el 0.05 no lo he podido deducir** (§9).

`is_pure_lut` pide **tres cosas a la vez**:

1. **cero hotspots** (ninguna de las cuatro formas: viñeta, degradado, textura,
   zona local);
2. `residuo_p95 <= UMBRAL_DE_PURO` = **1.0 ΔE2000**. Ese 1.0 es el umbral clásico
   de «dos colores que no se distinguen puestos uno al lado del otro», o sea: el
   95% del fotograma cae por debajo de lo que el ojo distingue;
3. `lut_reproducible >= UMBRAL_REPRODUCIBLE_PURO` = **0.95**. **De dónde sale ese
   0.95 no lo he podido deducir** (§9). No lo he tocado.

Las tres a la vez, y no dos: quitar la primera deja pasar una viñeta con residuo
bajo, y quitar la segunda deja pasar un grado que mueve muchísimo y del que te
llevas el 96% (que en absoluto sigue siendo un error enorme).

---

## 6. El detector espacial: cómo distingue hoy una viñeta de una ventana

**Esto es lo que se reescribió el día 2.** La versión de la noche 1 detectaba
bien una ventana y **era ciega a una viñeta sola**.

### 6.1 Qué estaba mal, exactamente

Dos cosas, y ninguna era una calibración:

1. **La MAD era el estadístico equivocado.** El umbral de zonas locales se
   calculaba como `mediana + 4·1.4826·MAD` sobre el campo de residuos. La MAD es
   robusta frente a valores atípicos, y **una viñeta no es un valor atípico**:
   toca casi todos los píxeles del cuadro. El estimador se la tragaba como línea
   base y el umbral se disparaba.
2. **El ΔE2000 no es el campo donde se ve una viñeta.** Una viñeta es
   **multiplicativa sobre la imagen**, así que su ΔE depende del brillo local del
   contenido y no sólo del radio. El perfil radial del ΔE explicaba un **R² =
   0.2887** de su varianza sobre el caso de viñeta sola: por debajo del 0.30 que
   pedía la puerta, **y por un 4%**.

Subir el radio de suavizado abría la puerta (R² = 0.3107 con `min(h,w)//24`) y
**no es lo que se ha hecho**: eso es calibrar contra un caso.

### 6.2 El campo de ganancia, que es la idea de fondo

```
G = log(coloreado + eps) − log(predicción + eps)      por canal
```

Un efecto multiplicativo —una viñeta, una ventana de ganancia, un degradado de
exposición— es **constante aquí a igualdad de posición, haya lo que haya en la
imagen**. En ΔE2000 no lo es, y esa dependencia del contenido es justo el ruido
que hundía el R².

**La comparación, medida sobre los mismos seis montajes, mismas puertas.** A la
izquierda el campo de ΔE2000 con el suavizado de la noche 1; a la derecha el
campo de ganancia de luma con σ = 0.05·min(h,w):

| montaje | ΔE: R² | ΔE: r(radio) | ΔE: recorrido | **gan: R²** | **gan: r(radio)** | **gan: recorrido** |
|---|---|---|---|---|---|---|
| T2d nada espacial | 0.0484 | −0.352 | 0.080 | **0.0736** | **+0.118** | **0.0001** |
| T2e grano | 0.0559 | +0.915 | 0.564 | **0.2456** | **+0.688** | **0.0039** |
| T2a viñeta 0.35 | 0.2251 | +0.688 | 6.024 | **0.8321** | **−0.838** | **0.2694** |
| T2a viñeta 0.55 | 0.2887 | +0.880 | 9.107 | **0.8789** | **−0.875** | **0.5089** |
| T2b ventana 1.6 | 0.0370 | +0.662 | 5.177 | **0.0337** | **+0.058** | **0.0504** |
| T2c viñeta+ventana | 0.0669 | +0.833 | 8.609 | **0.5007** | **−0.798** | **0.4057** |

Tres cosas salen de ahí:

- **El R² del ΔE no separa nada**: la viñeta más fuerte (0.2887) está más cerca
  del grano (0.0559) que de aprobar. Con el campo de ganancia, la viñeta **más
  floja** da 0.83 y la ventana 0.034: un factor de **25**.
- **El signo importa, y en el ΔE no existe.** En ΔE2000 todo correla positivo
  (hasta el grano, +0.915) porque el ΔE no tiene signo. En ganancia, una viñeta
  oscurece hacia fuera y correla **−0.84**; una ventana, **+0.06**.
- **El recorrido separa por un factor de cuarenta**: «nada espacial» 0.0001 y
  grano 0.0039 contra 0.27 y 0.51 de las viñetas.

### 6.3 Las cuatro pruebas, en este orden

**1 · Viñeta** (baja frecuencia radial, sobre el campo de ganancia de luma).
Se estima **el centro de la caída** ajustando `g ≈ c₀ + c₁x + c₂y + c₃(x²+y²)` y
tomando el vértice, y se bina el campo en 24 coronas alrededor de ese centro. Hay
viñeta si pasa **las tres puertas**:

| puerta | constante | valor |
|---|---|---|
| recorrido del perfil | `UMBRAL_RECORRIDO_GANANCIA` | 0.12 (≈ 0.17 paradas) |
| R² del perfil | `UMBRAL_R2_RADIAL` | 0.30 |
| \|Pearson\| con el radio | `UMBRAL_MONOTONIA_RADIAL` | 0.55 |

El valor absoluto en la monotonía es deliberado: una viñeta que **aclara** hacia
fuera es igual de imposible de meter en un LUT, y el signo se reporta aparte (la
nota dice «oscurece» o «aclara»). Test:
`test_una_vineta_que_ACLARA_hacia_fuera_tambien_se_detecta`.

**El centro estimado tiene una condición, y no es un detalle.** Si el vértice del
ajuste cae fuera del encuadre (`RADIO_MAXIMO_CENTRO` = 1.0 en coordenadas donde
el borde vale 1), se vuelve al centro geométrico. Sin esa condición, el detector
tiene libertad para poner el origen en la esquina opuesta a una ventana y hacer
que **la ventana parezca una viñeta**. Medido: con el vértice libre, una ventana
sola sube de **R² 0.034 a 0.367** y se queda a un pelo de la puerta de 0.30.
Con la condición vuelve a 0.034. Y las viñetas descentradas se siguen detectando,
que era para lo que se estimaba el centro. La separación del vértice es de un
orden de magnitud:

| montaje | distancia del vértice al centro |
|---|---|
| viñeta 0.35 | 0.067 |
| viñeta 0.55 | 0.085 |
| viñeta descentrada a mano (−0.40, −0.35) | 0.394 |
| grano | 0.857 |
| **ventana 1.6** | **2.749** |
| **ventana 1.15** | **21.481** |
| **nada espacial** | **214.7** |

**2 · Degradado** (baja frecuencia lineal). Sobre lo que queda del campo de
ganancia tras restarle el modelo radial se ajusta `g ≈ a·x + b·y + c`. Puertas:
`UMBRAL_R2_LINEAL` = 0.50 y `UMBRAL_RECORRIDO_LINEAL` = 0.10. **No se dispara en
ninguno de los seis montajes**, y hay un test que lo comprueba en los seis montajes de
memoria (`test_T2d_un_degradado_no_aparece_donde_no_lo_hay`), porque ésta es la
puerta más fácil de disparar sin querer: casi cualquier residuo tiene algo de
inclinación.

**3 · Textura** (alta frecuencia del ΔE2000). `residuo − pasa_bajo(residuo)` con
σ = 0.02·min(h,w), y su desviación típica. Grano, enfoque, reducción de ruido y
halación viven ahí. **No son una zona del cuadro**: se reportan aparte, con la
etiqueta `"textura"`, cubriendo el fotograma entero. Umbral `UMBRAL_TEXTURA` =
2.5 ΔE2000. Medido:

| montaje | desviación típica de la alta frecuencia |
|---|---|
| nada espacial | 0.111 |
| ventana 1.6 | 1.259 |
| viñeta 0.55 | 1.440 |
| **grano (σ 0.012)** | **3.830** |

Lo que hay entre 1.3 y 1.7 en los casos espaciales **no es textura del material**:
es el error del ajuste del LUT en los bordes del contenido. Por eso el umbral no
puede bajar de ~2: el margen real es de 3.83 contra 1.44, un factor 2.7.

**4 · Zona local** (baja frecuencia compacta, sobre el campo de ganancia **por
canal**). Se suaviza con σ = 0.03·min(h,w), se le resta el modelo radial si hubo
viñeta, y se toma la norma sobre los tres canales. El umbral es

```
max( SUELO_GANANCIA_LOCAL , mediana + FRACCION_DE_PICO·(p99.5 − mediana) )
```

con `SUELO_GANANCIA_LOCAL` = 0.08 y `FRACCION_DE_PICO` = 0.40. Las dos mitades
hacen cosas distintas y las dos hacen falta:

- la segunda es un **contorno a media altura del pico**, o sea un criterio **sin
  escala**: una ventana de +15% se recorta igual de bien que una de +60%, y no
  hay ningún número calibrado contra un caso;
- el suelo absoluto es lo que impide que el contorno se dibuje sobre ruido cuando
  no hay pico. 0.08 es un 8% de ganancia local, algo más de un octavo de parada.
  **Medido**: el grano más fuerte probado llega a **0.0135** de pico y «nada
  espacial» a **0.0006**; la ventana, a **0.5945**. Factor 44 sobre el grano.

**Por canal y no en luma** a propósito: una secundaria que sube el rojo y baja el
azul sin tocar el brillo es invisible en un campo de luma. Test:
`test_T2b_una_ventana_que_solo_cambia_el_TINTE_tambien_se_ve`.

### 6.4 Lo que sale, caso por caso

| montaje | etiquetas | IoU con la caja real |
|---|---|---|
| T2a viñeta sola (0.55) | `vineta` + 7 zonas locales | — |
| T2a viñeta floja (0.35) | `vineta` + 7 zonas locales | — |
| T2b ventana sola (1.6) | `zona local` | **0.977** |
| T2b ventana floja (1.15) | `zona local` | **0.745** |
| T2b ventana sólo de tinte | `zona local` | **0.512** |
| T2c viñeta + ventana | `vineta` + 2 zonas locales | **0.909** |
| T2d nada espacial | **ninguna** | — |
| T2e grano | `textura` | — |
| T2f compresión h264 | **ninguna** | — |

Centro estimado en las viñetas centradas: **(339.4, 189.9)** y **(303.7, 187.5)**
sobre un fotograma de 640×360, o sea **22.4 y 17.8 px** del centro real. La caída
de una viñeta es plana cerca del centro, así que ahí el centro está mal
condicionado y pedir más sería pedir precisión que el dato no tiene.

### 6.5 Hasta dónde llega, medido

- **Con una viñeta sola salen 7 «zona local» espurias** en las esquinas. No es un
  capricho del umbral y no lo he escondido: el LUT, al ajustarse contra un plano
  ya viñeteado, absorbe parte de la viñeta **de forma dependiente del color**, y
  lo que sobra se amontona en las esquinas. Ahí el error de ganancia es **real**:
  el pico del residuo de ganancia es el **44.6%** del recorrido de la viñeta
  (0.1202 sobre 0.2694) en la viñeta floja y el **49.8%** (0.2534 sobre 0.5089)
  en la fuerte — dos medidas, la misma proporción. Se podría suprimir poniendo el
  suelo local a la mitad del recorrido de la viñeta, y **no lo he hecho** porque
  eso es un factor ajustado sobre dos casos del mismo generador y se comería una
  ventana de verdad escondida bajo una viñeta fuerte, que es un falso **negativo**
  y es el lado peligroso. Queda como la primera cosa a discutir con Mario (§8).
  Lo que sí está garantizado es que **la viñeta nunca se cae por el tope de ocho
  hotspots**: `_recortar` conserva siempre las etiquetas de forma y sólo recorta
  las zonas locales. Sin eso, la viñeta (magnitud = residuo medio del cuadro) se
  quedaría fuera por culpa de sus propias esquinas.
- **Una ventana centrada y redonda** sigue siendo indistinguible de una viñeta
  invertida. Es el falso positivo conocido, y va hacia el lado seguro.
- **La elipticidad no se estima.** El centro sí, la forma no: una viñeta muy
  ovalada se ajusta peor y puede quedarse por debajo del R².
- **El detector no sabe de sujetos.** Una secundaria por tono de piel (todas las
  caras, estén donde estén) sale como varias «zona local» repartidas, no como
  «una secundaria de piel». Eso ya no es geometría, es segmentación, y no está.

### 6.6 El sentido del fallo, que es lo que manda

Decir **«esto es un LUT» cuando no lo es es mucho peor** que lo contrario. Lo
primero manda a Mario a llevarse un `.cube` que no reproduce el grado y a
enterarse delante de un cliente; lo segundo sólo le hace trabajar de más.

Por eso, donde hay que elegir, **estos umbrales están calibrados hacia el falso
positivo**: el suelo de la zona local se pone bajo (8% de ganancia), la monotonía
radial se pide en valor absoluto, la puerta del R² radial se deja en 0.30 cuando
la viñeta más floja medida da 0.83, y las siete zonas espurias de §6.5 se
reportan en vez de suprimirse.

El contrapeso está en los tests y no es negociable: **T2d tiene cero hotspots**
(`assert d.hotspots == ()`), T2e no emite ninguna zona local y T2f tampoco. Un
detector que siempre dice «aquí hay algo» es tan inútil como uno que nunca lo
dice, y además es peor, porque el que lo lea dejará de hacerle caso.

---

## 7. `spatial_residual`

Va **normalizado 0..1 dividiendo por el máximo**, porque es un mapa para pintar y
la GUI lo pinta tal cual. La magnitud en ΔE2000 vive en `Hotspot.magnitude` y en
la primera nota, así que no hay dos sitios donde mirar el mismo número. La última
nota dice siempre a cuántos ΔE2000 equivale el 1.0.

---

## 8. Lo que decidí yo solo el día 2, y que podrías querer cambiar

1. **La etiqueta `"textura"` es nueva.** `core/contracts.py` comenta que `label`
   es «"vineta", "zona local", "degradado"»; he añadido una cuarta. El campo es un
   `str` libre y la GUI sólo lo imprime, así que no rompe nada, pero **el
   comentario del contrato se queda corto** y eso lo tiene que cambiar el
   orquestador, no yo.
2. **Las siete zonas locales espurias de una viñeta sola** (§6.5). Se suprimen
   con dos líneas si prefieres el informe limpio al informe completo. Yo he
   elegido completo porque el falso positivo es el lado seguro.
3. **`analizar_espacial` y `AnalisisEspacial` son API pública nueva** de
   `core.reverse`. No tocan `core/contracts.py` —no cruzan ninguna frontera entre
   módulos— y existen para poder **medir el detector** en un test y para que esta
   tabla no haya que reconstruirla a mano. Si te sobran, se vuelven privadas.
4. **Con todo el material fuera del dominio devuelvo la identidad** (§4). Antes
   devolvía un LUT constante. Es un cambio de comportamiento en un caso raro pero
   real.
5. **Los tests de borde usan el retrato a 256×144**, no a tamaño completo. A
   tamaño completo cada `invertir_grado` son 60 iteraciones de Jacobi sobre
   230.400 píxeles y hay una docena de casos. Lo que miden esos tests (que no
   reviente y que lo diga) no depende del tamaño; lo que sí depende está en los
   entregables, que van a tamaño completo.

---

## 9. Lo que NO he podido deducir

Está aquí y no en un comentario que suene bien porque **decir «esto no he podido
averiguar por qué es así» vale más que una explicación falsa**. Todas estas
constantes las he dejado como estaban.

- **`UMBRAL_REPRODUCIBLE_PURO` = 0.95.** El 1.0 ΔE2000 de `UMBRAL_DE_PURO` sí
  tiene razón escrita (el umbral clásico de dos colores indistinguibles). De
  dónde sale el 0.95 no lo dice ni el código, ni el commit, ni la bitácora.
- **El corte de `movimiento` medio < 0.05 ΔE2000** para entrar en la rama «esto
  no es un grado, es el mismo plano». No hay ninguna medida detrás en el código.
  Y tiene un efecto lateral conocido (§5) que sí está anotado.
- **`LAMBDA_SUAVIDAD` = 0.25.** El docstring explica muy bien qué **significa**
  («peso equivalente en píxeles»), pero no de dónde sale el 0.25.
- **`_BARRIDOS_EN_BUCLE` = 10** (los barridos de suavizado en caliente dentro del
  bucle de refinado, frente a los 60 del relleno completo). No hay medida.
- **`AREA_MINIMA_HOTSPOT` = 0.002** (el 0.2% del fotograma). Hay razón cualitativa
  («por debajo es grano, no una zona») pero ninguna medida.
- **`CORONAS` = 24.** Ni medida ni razón. Lo he mantenido.
- **`MAX_PIXELES_CDL` = 60.000.** El docstring dice «no mejora nada por encima de
  este número», pero no da la curva que lo demuestra.
- **`MUESTRAS_MINIMAS_CDL` = 64** y **`MARGEN_MEJORA` = 0.01**. Razón cualitativa,
  cero números.

---

## 10. Qué entrada plausible creo que todavía rompe esto

Por orden de probabilidad de que le pase a Mario:

1. **Un plano casi monocromo** (una noche, una niebla, un fundido). La nube de
   color no tiene volumen, la base afín se apoya entera en la cresta y el LUT sale
   casi identidad fuera de la nube. La confianza lo dice (el número de condición
   se hunde), pero el `.cube` que salga sólo vale para ese plano.
2. **Un grado con una secundaria de tono**, del tipo «todas las caras un punto más
   cálidas». Depende del sujeto, no de la posición ni sólo del color, y este
   detector lo verá como varias zonas locales repartidas sin saber qué son.
3. **Un desplazamiento subpíxel** entre original y coloreado (un reencuadre de
   0.5 px, un remuestreo distinto). `alinear` sólo corrige enteros; lo que queda
   se cuela en el residuo como si fuera grado, y en un plano con mucho detalle
   puede llegar a disparar la textura.
4. **Una viñeta muy ovalada o anamórfica**: el modelo es isótropo (§6.5).
5. **Material con un LUT de salida ya aplicado y recortado** (un plano entregado
   en Rec.709 quemado). Las altas luces no tienen información, el LUT ajusta la
   zona quemada contra una constante, y aunque el grado de las zonas sanas
   aguanta (medido: 0.529 ΔE2000 en la zona sana contra 0.913 en la quemada), el
   `.cube` resultante aplana los blancos de cualquier otro plano.

---

## 11. Los tests de este módulo

| archivo | qué prueba | cuántos |
|---|---|---|
| `tests/test_reverse_espacial.py` | el detector espacial: T2a-T2f, la tabla de separación, las tres puertas una a una | 18 |
| `tests/test_reverse_bordes.py` | un fotograma, 1 px, un solo color, reencuadre vertical, otra resolución, planos que no se corresponden, desencuadre grande, cubo casi vacío, todo fuera de dominio, altas luces recortadas, NaN, todo NaN, fuera de rango, negro absoluto, identidad | 16 |

De extremo a extremo prueba `tests/test_entregables.py` (T1 y T2), que es del
orquestador y es el contrato de este módulo.
