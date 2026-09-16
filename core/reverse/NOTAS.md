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

### 6.7 La zona PRINCIPAL (día 4): el mapa acertaba y la primera línea no

**El fallo** (medición independiente del día 3, `MEDICION-INDEPENDIENTE.md`
§3): con una viñeta y una ventana suaves aplicadas **en luz lineal** y una
sombra profunda en una esquina, el 93.6% de los 500 píxeles de mayor residuo
caían dentro de la ventana, pero la primera «zona local» era un cuadrito de
31×29 px en la esquina, con solape 0.0.

**La causa, medida antes de tocar nada.** Había tres sospechosos: el pico, el
campo y el recorte de la caja. Cifras sobre la escena de la medición:

```bash
# desde la raiz del repo; ~40 s. La columna ΔE rectangulo es la magnitud de antes.
.venv/bin/python - <<'PY' 2>/dev/null
import numpy as np
from scipy import ndimage
from core.color import delta_e2000
from core.reverse import invertir_grado, analizar_espacial
from core.reverse import diagnostico as D
from tests.medicion import escena as E
for nombre, kw in (("vineta+ventana", {}), ("ventana sola", {"vineta": 0.0})):
    o = E.escena_trabajo(); c = E.coloreado_con_lo_espacial(o, E.tabla_lut_conocida(), **kw)
    r = invertir_grado(o, c); p = r.lut.apply(r.cdl.apply(o.astype(np.float64)))
    de = np.asarray(delta_e2000(p, c.astype(np.float64)), dtype=np.float64)
    a = analizar_espacial(de, p, c.astype(np.float64))
    g = D.campo_de_ganancia(p, c); lado = min(de.shape)
    f = np.linalg.norm(np.stack([D._gaussiana(g[..., k], D.SIGMA_LOCAL * lado) for k in range(3)], -1)
                       - np.stack([D._gaussiana(g[..., k], D.SIGMA_LOCAL * lado) for k in range(3)], -1).reshape(-1, 3).mean(0), axis=-1)
    for (x, y, w, h), m, rz in zip(a.zonas, a.masas, a.residuos_zonas):
        print(f"{nombre:15s} caja=({x},{y},{w},{h}) pico={f[y:y+h, x:x+w].max():.3f} masa={m:.0f} "
              f"dE_componente={rz:.2f} dE_rectangulo={de[y:y+h, x:x+w].mean():.2f}")
PY
```

| montaje | zona | pico | masa | ΔE píxeles | ΔE rectángulo |
|---|---|---|---|---|---|
| viñeta+ventana | **ventana** (89,301,251,104) | **0.469** | **3909** | **14.93** | 11.38 |
| viñeta+ventana | esquina (0,284,31,29) | 0.217 | 142 | 12.30 | **12.73** |
| ventana sola | esquina (0,274,41,41) | **0.146** | **170** | **6.06** | **5.82** |
| ventana sola | trozo de ventana (249,267,32,88) | 0.107 | 161 | 5.38 | 4.68 |

Se lee así:

1. **No era el pico.** En el caso publicado `analizar_espacial` ya ponía la
   ventana primera (0.469 contra 0.217). El que le daba la vuelta era
   `_recortar`, que **reordenaba por `magnitude`**, y `magnitude` era el
   ΔE2000 medio **del rectángulo**.
2. **Era la dilución del rectángulo.** La ventana ocupa 14.418 píxeles de un
   rectángulo de 26.104 (el 55%): su ΔE se diluye de 14.93 a 11.38. El cuadrito
   ocupa 731 de 899 y no se diluye. **El ΔE2000 no se amplificaba en la
   sombra**: sobre sus píxeles, la esquina tiene MENOS ΔE que la ventana.
3. **El pico tampoco es de fiar.** En mi montaje del taller
   (`test_T2g_*`), el pico sí ponía la esquina primero. Pico y ΔE de rectángulo
   son estadísticos de intensidad, y los dos premian lo pequeño y concentrado.
4. **El campo sí es causa, pero en otro caso** («ventana sola»): ahí todos los
   criterios eligen la esquina, porque en el logaritmo de valores
   **codificados** una ganancia de luz lineal vale ~`C·log2(g)/y`, o sea que se
   amplifica donde el valor codificado es bajo. Medido dentro de la ventana:
   |log-ganancia codificada| (sonda de sesión, sin script en el repo) 0.0835 en píxeles con luma codificada 0.15–0.3
   contra 0.0270 con 0.3–0.5 (×3.1); la misma ganancia en luz lineal da 0.2307
   contra 0.1438 (×1.6, lo que queda es lo que el LUT absorbe). **Eso no se ha
   arreglado**: ver «lo que se probó y no entró».

**El arreglo**, entero en `diagnostico.py` y sin ningún umbral nuevo:

- las zonas se ordenan por **masa** = suma de la fuerza local (log-ganancia
  suavizada) sobre los píxeles de la componente, o sea área × intensidad;
- `Hotspot.magnitude` es el ΔE2000 medio **sobre los píxeles de la
  componente** (el contrato dice «residuo medio en la zona», y la zona es la
  componente, no su rectángulo);
- `_recortar` **ya no reordena**: respeta el orden por masa, que es el que ve
  la GUI y por el que se corta a `MAX_HOTSPOTS`.
- La caja sigue siendo el rectángulo de la componente conexa del campo de baja
  frecuencia umbralizado. Ya lo era.

**Lo que NO cambia, y es a propósito**: qué zonas salen y con qué caja. El
conjunto de componentes es idéntico bit a bit; sólo cambia el orden y la
magnitud. Por eso no puede aparecer ni un falso positivo nuevo, y por eso T1
(0.1415 / 1.7409), T2 (0.7002 / solape 0.9941) y la salida de los seis casos
del día 2 son idénticos.

**Ojo, consecuencia**: `max(hotspots, key=magnitude)` **ya no es la zona
principal**. La principal es la primera de la tupla. En «ventana sola» del
taller, la primera es la ventana (5.31 ΔE) y la segunda la esquina (6.20 ΔE).
`tests/test_entregables.py` y `tests/medicion/` eligen por `max(magnitude)`;
en sus montajes de hoy coincide, pero no está garantizado.

**Lo que sale en la medición independiente después del arreglo**: las dos
cajas son las mismas, en orden inverso: #0 la ventana (89,301,251,104),
magnitud 14.9342, solape 0.4294; #1 la esquina (0,284,31,29), magnitud 12.2974,
solape 0.0000. El centinela `test_T2_las_dos_cajas_y_su_desempate_estan_aferrados`
se pone rojo (es lo que tiene que hacer) y el `xfail` **sigue siendo xfail**:
la zona principal ya es la ventana, pero su caja sólo solapa el 43% y el
criterio pide 80%.

**Lo que se probó para la caja y no entró** (sonda de sesión, cifras en el
informe del día 4, no hay script en el repo):

- **log-ganancia en luz lineal** con el suelo de la propia curva DaVinci
  Intermediate (`log(lin + 0.0075)`): arregla «ventana sola» de la medición,
  pero **empeora** la caja del taller (IoU 0.90 → 0.56) y **añade zonas** donde
  no hay grado (la huella del LUT en la cara con una ventana floja o de tinte:
  1 → 2 zonas; viñeta lineal sola: 2 → 4 y 2 → 5). Un falso positivo nuevo no
  compensa;
- separar lóbulos por signo: la esquina es 100% negativa y la ventana
  positiva, pero lo que ensancha la caja de la ventana es residuo positivo y
  cromático justo debajo, así que no cambia nada (solape 0.54);
- caja por momentos (rectángulo uniforme con la misma media y varianza): encoge
  demasiado; la ventana del día 2 pasa de IoU 0.98 a 0.64;
- restar siempre el perfil radial: quita la esquina y las zonas de viñeta
  lineal sola, pero la caja de la ventana se queda en IoU 0.32.

**Por qué la caja no llega al 80%**: el LUT se traga la ventana allí donde los
colores sólo existen dentro de ella (los parches de la fila de abajo), y deja
residuo real, mismo signo, en el fondo de colores parecidos justo debajo y a la
derecha. Ninguna forma de recortar un campo de residuo distingue eso de la
ventana; haría falta mirar **bordes**, que es otro detector.

**Tests nuevos** (`tests/test_reverse_espacial.py`, 9 más, 27 en total):

| test | qué afirma |
|---|---|
| `test_T2g_la_zona_principal_es_la_ventana_y_no_la_esquina_en_sombra` ×2 | en el taller (escena propia, sombra en la esquina inferior derecha, luz lineal) la primera zona es la ventana: IoU 0.898 con viñeta, 0.922 sin ella. Con el código del día 3 era la esquina, IoU 0.000 |
| `test_T2g_el_montaje_sigue_teniendo_la_trampa` | centinela: con el criterio viejo la esquina seguiría primera (IoU 0.000); si deja de serlo, el test de arriba no prueba nada |
| `test_T2g_una_ventana_en_sombra_de_verdad_se_sigue_viendo` | ventana a −1.33 paradas de la mediana: primera, IoU 0.755 |
| `test_T2g_una_ventana_en_sombra_sin_vineta_limite_conocido` | **xfail estricto**: sin viñeta, la huella del LUT en la franja oscura de la izquierda (6.04 ΔE, 113×360 px) pesa más que la ventana |
| `test_T2g_el_taller_sin_nada_espacial_no_se_inventa_zonas` | contrapeso: la sombra sola no es una zona; cero hotspots, LUT puro |
| `test_T2h_una_zona_grande_y_floja_va_antes_que_una_pequena_e_intensa` | 240×140 a ×1.35 (12.35 ΔE) va antes que 60×50 a ×1.9 (24.17 ΔE), y la pequeña sigue listada |
| `test_T2h_si_la_intensa_tambien_cambia_mas_imagen_va_primera` | se ordena por masa, no por área |
| `test_zonas_ordena_por_masa_y_mide_el_residuo_sobre_la_componente` | `_zonas` con un campo fabricado, sin LUT |

**Masa contra intensidad, y por qué gana la masa.** La primera línea dice qué
reconstruir primero para recuperar más imagen, y lo pequeño e intenso es
justo lo que fabrican los artefactos (el cuadrito de la esquina). El precio,
dicho: un retoque diminuto y muy fuerte (unos ojos) sale detrás de un lavado
amplio y suave aunque al ojo le importe más. Y un límite que ya existía y que
este test destapó: **si la floja no llega al 40% del pico de la intensa, ni
sale** (sonda de sesión: 240×140 a ×1.2 junto a 60×50 a ×2.2 da una sola zona, la pequeña). El umbral local es
relativo al pico del cuadro, así que una ventana fuerte esconde a una floja.

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

**De este módulo se han mudado**: `UMBRAL_DE_HOTSPOT`, `UMBRAL_DE_PURO`,
`UMBRAL_REPRODUCIBLE_PURO`, las cinco puertas de viñeta y degradado
(`UMBRAL_R2_RADIAL`, `UMBRAL_MONOTONIA_RADIAL`, `UMBRAL_RECORRIDO_GANANCIA`,
`UMBRAL_R2_LINEAL`, `UMBRAL_RECORRIDO_LINEAL`), `SUELO_GANANCIA_LOCAL`,
`FRACCION_DE_PICO`, `UMBRAL_TEXTURA`, `AREA_MINIMA_HOTSPOT`,
`MUESTRAS_MINIMAS_CDL` y `UMBRAL_CORRELACION_FIABLE` — todas deciden una
etiqueta o una frase que sale en pantalla.

**Y tres que no tenían nombre siquiera**, que es de lo que iba el encargo:

- el `0.05` de `mov_medio < 0.05`, escrito **dos veces seguidas** en la misma
  condición de `diagnostico.py`, que es lo que decide «esto no es un grado, es
  el mismo plano». Hoy es `UMBRAL_MOVIMIENTO_NULO`. Sigue sin saberse de dónde
  sale (§9);
- el `0.005` de cobertura del cubo, **escrito dos veces**: en
  `diagnostico.py` y en `invertir.py`, con dos frases distintas y sin nada que
  garantizara que seguían coincidiendo. Hoy es `UMBRAL_COBERTURA_BAJA`. Es
  exactamente la forma del bug de `gui/reverse_puente.py`;
- el `0.001` de `fuera > 0.001` en `invertir.py`. Hoy es
  `UMBRAL_FUERA_DE_DOMINIO_AVISO`.

Y el **`4` de «esta celda tiene datos suficientes»**, que estaba escrito
**tres** veces: como defecto de `min_muestras` en `acumulacion.py`, como
defecto de `min_muestras` en `invertir.py` y como defecto de
`CoverageMap.min_samples` en `core/contracts.py`. Los dos de aquí apuntan ya a
`MUESTRAS_MINIMAS_CELDA`; **el de los contratos sigue siendo una tercera
escritura del mismo número** y ese archivo es del orquestador, así que se ha
dejado un test (`test_el_cuatro_de_la_cobertura_sigue_cuadrando_con_el_de_los_contratos`)
que salta si los dos se separan.

**Se quedan aquí**, porque no deciden ningún veredicto: los tres `SIGMA_*` (son
la escala de suavizado con la que se mira cada campo), `CORONAS`,
`MAX_HOTSPOTS` (es un tope de presentación), `RADIO_MAXIMO_CENTRO` (es una
condición de validez del modelo, no un umbral sobre una medida), `_EPS_LOG`,
`PESO_DE_MUESTRA` (es el peso geométrico mínimo de un nodo, 1/8: no es
calibrable, sólo tiene sentido dentro del reparto trilineal), `MAX_PIXELES_CDL`,
`ITERACIONES_REFINADO`, `BARRIDOS_SUAVIZADO`, `RIDGE_BASE`, `LAMBDA_SUAVIDAD`,
`PESO_MINIMO`, `MAX_DESPLAZAMIENTO_PX` y `MARGEN_MEJORA`.

La lista de §9 —lo que no se pudo deducir— **se ha respetado entera**: los
«no se sabe» van copiados tal cual en `core/umbrales.py`, sin inventar ninguna
justificación que suene bien.

---

## 12. DÍA 4 · modo por lote: N planos del mismo trabajo, UN grado

**Agente LOTE, 16-09-2026.** Punto de partida: `MEDICION-T5.md`. El grado de un
plano no vale en otro, y dar más cobertura por sí sola no arregla el máximo. Si
el colorista tiene el máster y los brutos enteros, todos los planos comparten
look y se pueden acumular. Esta sección dice qué se ha hecho, qué se ha medido y
qué **no**.

Comandos de todas las cifras de esta sección (se copian tal cual desde la raíz):

```bash
.venv/bin/python -m pytest tests/test_reverse_lote_cobertura.py -s -q       # §12.3, ~40 s
.venv/bin/python -m pytest tests/test_reverse_lote_determinacion.py -s -q   # §12.4 y §12.5, ~2.5 min
.venv/bin/python -m pytest tests/test_reverse_lote.py -s -q                 # §12.5, ~4 min
.venv/bin/python -m pytest tests/test_entregables.py -s -q -k T1            # contrato, sin cambios
```

**Montaje de todas**: proyecto sintético de `tests/test_reverse_lote_material.py`.
Son 40 planos (retrato, exterior, interior y noche, alternando) a **320×180** por
la carga de la máquina, con UN grado conocido: CDL + LUT 33³ de look suave
(curva S, sombras frías, altas cálidas, compresión de croma, secundarias
anchas). ΔE2000 del repo. **No es T5**: aquí ningún grado se aplica a un plano
que no haya entrado en el ajuste. Eso lo mide el medidor independiente.

### 12.1 La API

```python
from core.reverse import invertir_grado_lote, comprobar_coherencia

r = invertir_grado_lote([(bruto1, master1), (bruto2, master2), ...], nombres=[...])
r.lut.apply(r.cdl.apply(otro_bruto))                 # el grado, igual que invertir_grado
r.confidence.metrics["lote_discrepantes"]            # 0.0 si todos llevan el mismo grado
informe = comprobar_coherencia(pares_alineados)      # el detalle por plano, como datos
```

Devuelve el mismo `ReverseResult` que `invertir_grado`, **sin tocar
`core/contracts.py`**. Lo que es del lote va en `confidence.metrics`
(`lote_planos`, `lote_planos_usados`, `lote_discrepantes`, `lote_sin_comparar`,
`lote_de_discrepancia_max`), en `notes` (ΔE y coherencia por plano) y, si hay
discrepancia, como primera razón de `confidence.reasons`. `diagnosis` es la del
plano peor. Para el medidor: `diagnosticar_planos=False` y
`verificar_coherencia=False` sólo ahorran tiempo; el LUT sale igual.

### 12.2 Cómo se acumula: se suman estadísticos, no LUTs

El ajuste del LUT (Jacobi precondicionado, §3–4) sólo necesita `A^T y`,
`A^T A` y `D`. Las tres cosas **se suman entre planos**. `Estadisticos`
(`acumulacion.py`) las guarda, con `A^T A` como plantilla de 27 vecinos por
nodo. `_ajustar_lut` ya no recorre píxeles: `D^-1 (A^T y − A^T A t)` es la misma
cuenta que antes, reordenada. Consecuencias medidas:

- **T1 idéntico**: 0.1415 / 1.7409 antes y después (comando de contrato).
  `acumular_correspondencias` da el mismo resultado bit a bit que el bucle
  anterior (test que copia ese bucle). Además comprobé a mano, contra una copia
  del `invertir.py` del día 3, que la tabla del LUT de T1 sale igual bit a bit
  (diferencia máxima 0.0). **Esa comprobación no tiene comando en el repo.**
- Un lote de un plano con `informacion="suma_w"` da el mismo LUT, bit a bit,
  que `invertir_grado` (test).
- `invertir_grado` es más rápido, porque el ajuste de 60 vueltas era el bucle
  por píxel. Tiempo orientativo, no es una cifra: depende de la carga.

### 12.3 Cobertura frente a número de planos

`[lote cobertura]` y `[lote determinacion]` en `test_reverse_lote_cobertura.py`.
«Nodos 4–15» = cubiertos (≥ 4 muestras) pero con pocas. Error en celdas
cubiertas: 8 puntos al azar por celda con los **8** nodos a ≥ 4 muestras, contra
el grado conocido. Así se pregunta por un color nuevo dentro de la zona
cubierta, no por los píxeles que se usaron para ajustar.

| Planos | % del cubo (≥4) | Nodos 1–3 | **Nodos 4–15** | 16–63 | ≥64 | Fracción de cubiertos con 4–15 | Celdas con 8 nodos | Máx. en esas celdas `suma_w` → `suma_w2` | % puntos > 3 `suma_w` → `suma_w2` |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.184 | 10 | 16 | 6 | 44 | 0.242 | 2 | 3.80 → 0.93 | 6.2 → 0.0 |
| 3 | 0.746 | 34 | 59 | 51 | 158 | 0.220 | 34 | 14.60 → 1.76 | 8.8 → 0.0 |
| 5 | 1.113 | 36 | **82** | 65 | 253 | 0.205 | 79 | 13.30 → 3.09 | 5.1 → 0.2 |
| 10 | 1.647 | 37 | 62 | 100 | 430 | 0.105 | 164 | 12.83 → 2.78 | 4.3 → 0.0 |
| 20 | 1.962 | 40 | 46 | 71 | 588 | 0.065 | 221 | 12.01 → 2.61 | 2.4 → 0.0 |
| 40 | **2.310** | 43 | **50** | 58 | 722 | 0.060 | 274 | **7.59 → 2.61** | 1.3 → 0.0 |

Resolución (`[lote resolucion]`): con 640×360 la cobertura sale algo mayor. Con 1
plano, 0.184% → 0.223%; con 3 planos, 0.746% → 0.824%.

Cómo lo leo:

1. **La cobertura se satura pronto.** De 20 a 40 planos sólo gana 0.35 puntos: 40
   planos de un trabajo llenan el **2.3%** del cubo. Acumular no convierte el
   LUT en «datos» fuera de la paleta del trabajo; el 97.7% sigue inventado.
2. **Los nodos cubiertos con pocas muestras no desaparecen.** Con 40 planos
   quedan **50** nodos con 4–15 muestras, del orden de los 59–82 que hay con 3–5
   planos: son la frontera de la zona cubierta, y la frontera crece con la zona.
   Lo que baja es su peso: del 24% de los cubiertos al 6%.
3. **Con el ajuste de siempre (`suma_w`), esos nodos siguen dominando el
   máximo.** Con 40 planos, el máximo en celdas cuyo nodo más flojo tiene 4–15
   muestras es 5.92, y el 5.6% de esos puntos pasa de 3. **Y lo que ordena el
   error es la distancia al píxel real**, como decía T5. A menos de 0.0025, el
   máximo es 1.56; a 0.01 o más, 7.59.

### 12.4 Lo que he cambiado de la determinación de los nodos: `suma_w2`

**La hipótesis de T5, confirmada desde dentro.** El ajuste decide cuánto manda
cada nodo frente a la suavidad con `alfa = suma_w / (suma_w + 0.25)`. `suma_w`
cuenta igual un píxel pegado al nodo (w ≈ 1) que ocho en la esquina opuesta de
la celda (w ≈ 0.13 cada uno): los dos suman ≈ 1. Pero los ocho lejanos casi no
fijan el nodo. Los mínimos cuadrados le atribuyen entonces el error de
interpolación de esos píxeles multiplicado por 1/w, y el nodo sale torcido
aunque tenga datos.

**Cambio**: medir la información con `suma_w2 = Σ w²`, que es la diagonal de
`A^T A` y lo que el nodo pesa de verdad, con `LAMBDA_SUAVIDAD_W2 = 4`. Es el
parámetro `informacion` de `_ajustar_lut`, `invertir_grado` e
`invertir_grado_lote`.

| Medida (comando) | `suma_w` (el de siempre) | `suma_w2` |
|---|---|---|
| **T1, un plano** (`[lote T1 informacion]`) | 0.1415 / **1.7409** | 0.1082 / **1.0325** |
| Look suave, 40 planos, máx. en celdas cubiertas (`[lote determinacion]`) | 7.59 | **2.61** |
| Look suave, 40 planos, máx. sobre los propios planos (`de_max_cubierto`) | 8.996 | 2.763 |
| Look suave, **1 plano** (plano 0), máx. sobre el propio plano | **1.758** | **2.364** |
| Look de secundarias estrechas, 40 planos, máx. en celdas cubiertas (`[lote look duro 40 planos]`) | 8.88 (2.2% > 3) | 5.67 (0.9% > 3) |
| Ídem, máx. sobre los propios planos | 10.016 | 7.804 |
| **Look de secundarias estrechas, UN plano, 11 planos A→A** (`[lote look duro un plano]`) | mediana 2.412, peor 10.213, **2 de 11 > 3** | mediana 3.146, peor 7.343, **7 de 11 > 3** |

**Decisión**:

- **Lote: `suma_w2` por defecto.** Con muchos planos gana en todo lo medido y con
  los dos looks.
- **Un plano: NO lo he cambiado.** `invertir_grado` sigue con `suma_w` y T1 sigue
  en 0.1415 / 1.7409. Con un plano, `suma_w2` mejora T1 pero empeora lo típico
  con un look de secundarias estrechas: 7 de 11 planos pasan de 3.0 frente a 2
  de 11. Y con el look suave empeora el máximo del plano 0. Es una decisión de
  producto con cifras en los dos sentidos, y le toca al orquestador. Cambiarla
  es pasar `informacion="suma_w2"`.
- El 4 salió de probar 1, 4 y 16 durante el desarrollo (16 ya no bajaba el
  máximo). **Esa comparación no tiene comando en el repo**; las cifras de la
  tabla son todas con λ = 4.

**Respuesta a «¿acumular mejora los nodos que dominaban el máximo?»**:
acumulando con el ajuste de siempre, **sólo en parte**. El máximo en celdas
cubiertas baja de 14.60 (3 planos) a 7.59 (40), pero los nodos de 4–15 muestras
siguen ahí (50) y siguen dominando el máximo (5.92). Acumulando **y** midiendo
la información con `suma_w2`, el máximo en celdas cubiertas se queda en ≤ 3.09
desde 5 planos y en 2.61 con 40. **Eso es dentro de la zona cubierta y con
material sintético; en otro plano, no medido (T5 lo dirá).**

### 12.5 La trampa: planos corregidos aparte

`comprobar_coherencia`, llamada siempre por `invertir_grado_lote` antes de sumar:

1. Suma los estadísticos de todos y, por cada plano `p`, **resta los suyos**.
   Eso es el grado de los demás, sin releer un píxel (15 vueltas en caliente).
2. En los píxeles de `p` cuyos 8 nodos tienen datos de los demás, compara la
   predicción de ese grado con la salida real (ΔE2000, mediana). Le **resta la
   mediana frente al LUT de `p` solo**, que es el suelo de lo que ningún LUT
   explica (ruido, compresión).
3. Saca al peor si pasa de `UMBRAL_DISCREPANCIA_LOTE` = 1.0 ΔE2000
   (= `DELTA_E_INDISTINGUIBLE`), recalcula sin él y repite. Si hay que sacar la
   mitad o más, dice «sin mayoría» y no señala a nadie.

Por qué así y no otra forma:

- **Píxel con píxel (vecino más cercano), descartado.** Un paso de 0.001 en un
  canal de un gris medio del espacio de trabajo son **0.743 / 1.426 / 0.869
  ΔE2000** (R / G / B; `[lote sensibilidad del espacio]`). Dos píxeles vecinos
  con el mismo grado difieren varios ΔE.
- **Sin restar el suelo, descartado** (`[lote suelo]`, proyecto coherente de 20
  planos con ruido gaussiano en el coloreado): con σ = 0.002 salen **3 falsos
  discrepantes** sin restar y 0 restando; con σ = 0.004, **10 y «sin mayoría»**
  sin restar y 0 restando (exceso máximo 0.016).

Resultados (`tests/test_reverse_lote.py`, proyecto de 20 planos; 3, 8 y 14
corregidos aparte con un CDL extra):

| Caso | Discrepantes | Exceso de los planos buenos (máx.) | Exceso de los corregidos |
|---|---|---|---|
| Coherente (`[lote coherente]`) | **ninguno** | 0.0992 | — |
| Coherente con ruido σ = 0.004 | **ninguno** | (`[lote suelo]`: 0.016) | — |
| 3 de 20, ×1.0 (`[lote 3 de 20]`) | **03, 08, 14** | < 1.0 (asertado) | 03 cálido 2.428 · 08 frío 6.321 · 14 abierto 12.918 |
| ×0.5 (`[lote sensibilidad]`) | 03, 08, 14 | 0.144 | 1.156 · 3.209 · 6.299 |
| ×0.25 | 08, 14 | 0.230 | **03: 0.553, no avisa** · 1.610 · 3.050 |

La puntuación reproduce lo que la corrección mueve su propio plano. Con ×0.25,
el cálido de noche mueve una mediana de 0.531 ΔE, por debajo de lo que se
distingue: no avisar ahí es lo que se pretende. El aviso dice qué planos y hacia
dónde, por ejemplo «08_retrato: 6.32 ΔE, más frío (L* −1.7, a* −2.1, b* −10.2)».
Si se ajusta con todos, la nota se multiplica por `PENA_LOTE_INCOHERENTE` (0.35)
y sale «baja» (`[lote avisa]`: 0.337). Con `excluir_discrepantes=True` ajusta
sin ellos y lo dice (`[lote excluir]`).

**Lo que todavía le engaña: lo espacial.** Con una viñeta de 0.45 en los 8
planos marca 3 (`[lote vineta]`). No es del todo un falso positivo: con viñeta,
el mismo color sale distinto según dónde esté, y el LUT acumulado **sí** falla
en esos planos. Pero la causa no es otro grado. Como el diagnóstico espacial
separa los dos casos (plano con otro grado: 0 hotspots; plano con viñeta:
hotspot `vineta`), el aviso lo cruza y añade «puede que no lleven otro grado
sino algo que un LUT no reproduce». Viñetas más suaves: **no medido**.

**Coste**: con 3 discrepantes son 4 rondas de 20 ajustes en caliente, más 20
ajustes propios que se hacen una sola vez. Del orden de decenas de segundos
para 20 planos a 320×180. Orientativo, no es una cifra.

### 12.6 Lo que no sé o no he hecho

- **Nada de esto está medido en material real.** La mediana coherente con
  compresión de verdad puede subir hacia el 1.0 del umbral. El ruido gaussiano
  sólo es una aproximación.
- **El umbral 1.0** tiene razón perceptual y margen medido (0.0992 frente a
  1.156, el corregido más flojo que avisa), pero sólo en este montaje.
- `PIXELES_COMPARTIDOS_MINIMOS_LOTE` = 200 y `PENA_LOTE_INCOHERENTE` = 0.35:
  **no se sabe por qué valen eso** (anotado en `core/umbrales.py`).
- `tests/test_umbrales.py::test_la_tabla_de_origen_cubre_todo_lo_que_se_mudo`
  **está rojo**. Pide anotar los tres umbrales nuevos en `VALORES_DE_ORIGEN`, y
  ese archivo no es mío. Ver el informe del día 4.
- Una corrección que sólo toca colores que ningún otro plano tiene no se puede
  detectar: no hay con qué comparar. Ese plano sale en `sin_comparar` si no
  comparte nada.
