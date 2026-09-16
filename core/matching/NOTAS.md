# NOTAS — agente C · matching

Qué decidí, qué descarté y por qué. Con números medidos, no impresiones, para
que mi revisor pueda discreparme con criterio.

Todo lo de aquí se comprueba solo:
`.venv/bin/python -m pytest tests/test_matching_*.py` (243 tests, todos en verde
a día de hoy).

**Ronda 2** (lo que cambió después de la primera entrega): `UMBRAL_HUELLA`
calibrado con la huella real del agente B (§4), la huella pasa a **decidir** el
desajuste de contenido cuando la hay, `emparejar` acepta `huellas=`, y mi propia
propuesta de medir la distancia después del transporte se midió y **se
descartó** (§4.5). Además el agente A arregló el salto del negro en L*a*b* que
reporté, y el caso "escena → negro" pasó de 7.65 de ΔE a **0.0** (§8).

---

## 0. Las cifras que se piden primero

### T3 — igualado de cuatro cámaras

Misma escena (retrato de estudio, tono de piel 2) grabada por cuatro cámaras con
las curvas y los primarios **de verdad** (`core.color.convert`), cada una con su
desviación de balance y exposición:

| | espacio | exposición | ganancia RGB |
|---|---|---|---|
| FX3 (referencia) | S-Log3 / S-Gamut3.Cine | 0.0 EV | 1.00, 1.00, 1.00 |
| Canon | C-Log3 / Cinema Gamut | −0.7 EV | 1.08, 1.00, 0.88 |
| Lumix | V-Log / V-Gamut | +0.5 EV | 0.93, 1.00, 1.12 |
| DJI | D-Log / D-Gamut | +0.9 EV | 1.04, 0.98, 0.95 |

**ΔE2000 medio entre cámaras (media de los seis pares):**

| | antes | después |
|---|---|---|
| **cifra del criterio** | **9.889** | **0.296** |

Criterio del encargo: `> 8.0` antes y `< 2.0` después. **Se cumple**, con un
factor **33** de mejora. Par a par:

| par | antes | después |
|---|---|---|
| FX3–Canon | 6.893 | 0.285 |
| FX3–Lumix | 6.183 | 0.195 |
| FX3–DJI | 10.402 | 0.190 |
| Canon–Lumix | 13.039 | 0.477 |
| Canon–DJI | 16.711 | 0.404 |
| Lumix–DJI | 6.106 | 0.226 |

Ningún par suelto se queda por encima de 0.48, o sea que el 0.296 no es una
media que esconda a nadie. Variantes medidas:

- **con el tono de piel más oscuro** (índice 5): 9.296 → **0.296**. Igual de
  bueno; no es un método que solo funcione con pieles claras.
- **con LUT de residuo** encima del CDL: 9.889 → **0.265**. Mejora, pero poco:
  el CDL ya se come casi todo (ver §5).
- **cambiando cuál de las cuatro es la referencia**: las cuatro cumplen.

Está en `tests/test_matching_camaras.py` y la función reutilizable es
`core.matching.igualar_camaras()`, que no depende de nada de `tests/`.

### Recuperación de un CDL conocido

Se fabrican siete CDL (identidad, suave, fuerte, con saturación, sin color, con
offsets negativos, y todo a la vez), se le aplican a una escena y se ajusta el
CDL contra el par (origen, destino):

| escena | peor error de parámetro de los siete |
|---|---|
| retrato de estudio | **4.4e-16** |
| exterior | **1.6e-15** |
| ColorChecker | **6.7e-16** |

O sea: **exacto hasta el último bit del float64**. Con ruido gaussiano encima el
error crece proporcionado (σ=1e-4 → 8.6e-5; σ=1e-3 → 7.8e-4; σ=1e-2 → 5.2e-3),
que es lo que descarta que lo esté acertando de casualidad.

**Pero ojo con el asterisco**: eso es con **parejas** de píxeles. Si las dos
listas no se corresponden, el destino se construye con el transporte MKL, que es
afín, y un CDL con `power != 1` deja de recuperarse exacto: error de parámetro
**0.137** (todo en `power`) y ΔE **0.34**. Está medido y afirmado en
`test_sin_parejas_un_cdl_NO_LINEAL_ya_no_se_recupera_exacto`.

---

## 1. Monge-Kantorovich: `eigh`, no `sqrtm`

`A = Sx^(-1/2) (Sx^(1/2) Sy Sx^(1/2))^(1/2) Sx^(-1/2)`, `b = mu_y − A mu_x`.

`scipy.linalg.sqrtm` está descartado y no por gusto: es para matrices generales,
pasa por Schur y **devuelve `complex128` en cuanto hay un autovalor negativo de
redondeo**. Y los hay siempre: la covarianza estimada de una imagen real trae
autovalores de −1e-19 continuamente. Un complejo metido en una tubería de float
significa NaN de ahí en adelante. Con `numpy.linalg.eigh` los veo, los **sujeto a
cero** antes de la raíz, y además la simetría de `A` sale exacta (que es lo que
hace que ida y vuelta se cancelen al bit).

Verificado: `A Sx A = Sy` con error < 1e-12; transportar una distribución a sí
misma da la identidad con error 1.7e-15; ida y vuelta devuelve los píxeles de
partida con error 1.8e-14.

### Covarianza singular: cómo la regularizo (§ la parte que más me importa)

Lo fácil sería `Sx + eps·I`. **No lo hago, y el motivo es que es peor que el
problema**: en una dirección donde el origen no tiene ninguna varianza, la
fórmula pide una ganancia `sqrt(lambda_y / eps)`, o sea que cuanto más pequeño
pones el épsilon **más amplificas una dirección de la que no sabes nada**. Con
`eps = 1e-10` y una varianza de destino normal salen ganancias de 1e5: grano
convertido en manchas de color.

Lo que hago:

1. `Sx = U diag(l) U^T` con `eigh`, y `l` sujeto a ≥ 0.
2. Se llama **degenerada** a toda dirección con `l_i <= TOL_RANGO · max(l)`, con
   **`TOL_RANGO = 1e-8`** (la mitad de los dígitos de un float64: por debajo de
   ahí el autovalor es ruido de la propia estimación).
3. En esas direcciones, `l_i` se sustituye por **la varianza que el DESTINO tiene
   en esa misma dirección**, `u_i^T Sy u_i`. Efecto: la ganancia en una dirección
   sin información sale **~1**. No se toca lo que no se puede medir.
4. Si tampoco el destino tiene varianza ahí, cae a un piso **relativo a la escala
   del problema**: `1e-12 · max(escala_x, escala_y, 1e-12)`. Es solo para no
   dividir por cero; con píxeles en 0..1 vale ~1e-24.
5. Red de seguridad final: como `A` es simétrica, sus autovalores **son** las
   ganancias, y se sujetan a **`GANANCIA_MAX = 100`**. Con material real no salta
   nunca; está para que un caso patológico dé un número feo en vez de un infinito.

Medido: origen en blanco y negro (rango 1) contra una nube de color da ganancias
entre 0.2 y 5 en las dos direcciones muertas, no 1e5.

**El límite de esto, medido y no escondido**: con el origen degenerado, las
direcciones propias de `Sx` son arbitrarias (los vectores propios de la matriz
cero). Si `Sy` no es diagonal en esa base, `A` sale *cerca* de la identidad pero
no exactamente: con un solo píxel de origen, elementos fuera de la diagonal de
hasta **0.10** y ganancias entre **0.93 y 1.09**. Afirmado en
`test_un_solo_pixel_de_origen_contra_una_nube_casi_no_deforma_nada`.

**Asimetría que dejé a propósito**: si es el DESTINO el que no tiene varianza, el
transporte colapsa (A ≈ 0) y no lo evito. Colapsar es la respuesta correcta del
transporte óptimo a una masa puntual, es numéricamente estable, y de que no se
cuele como un igualado bueno ya se encargan la confianza (0.000) y el detector de
contenido.

### Lo que descarté

**Hacer el MKL en lineal en vez de en el espacio de trabajo.** Es tentador: una
diferencia de exposición y balance es *exactamente* diagonal en lineal, así que
el transporte sería exacto. Lo descarté porque en lineal la covarianza la mandan
los especulares y el cielo (el generador tiene valores de 9.0 frente a un 0.18 de
gris medio): el transporte lo decidiría el sol y no la cara. En log, que es donde
trabaja un colorista, la covarianza está bien condicionada. Además el contrato 3
dice que el emparejamiento vive en `WORKING_SPACE`. Si alguien quiere revisarlo,
es cambiar dos líneas de `_nucleo`, pero hay que medirlo con especulares dentro.

---

## 2. Ajuste a CDL: dos fases y límites explícitos

**Fase 1 (cerrada)**: con `power = 1` y `saturation = 1` el modelo es lineal por
canal → tres `lstsq` ponderados de dos parámetros. Después, con esa predicción,
la saturación también sale de una regresión de un parámetro (proyección del croma
del destino sobre el croma de la predicción). Si un canal del origen no tiene
varianza, la pendiente no es identificable: `slope = 1` y el offset se lleva la
diferencia de medias.

**Fase 2**: `scipy.optimize.least_squares` con **`method="trf"`** — el único de
los tres que acepta límites — y `x_scale="jac"`, tolerancias 1e-12 y
`max_nfev=400`. Es un problema de residuo cero cuando el destino sí es un CDL, y
por eso Gauss-Newton converge a precisión de máquina.

**Límites (`LIMITES_CDL`), que no son adorno:**

| | mínimo | máximo |
|---|---|---|
| slope | 1e-3 | 1e3 |
| offset | −10 | 10 |
| **power** | **0.05** | **20** |
| saturation | 0 | 5 |

`CDL.__post_init__` lanza con `power <= 0`, y un optimizador sin sujetar **se va a
un power negativo en cuanto el residuo es plano** — pasa con material de un solo
color, donde `x**p` con `x` constante da lo mismo para infinitos pares
slope/power. Sujetar el power a ≥ 0.05 no es maquillaje: **un power de 0.05 ya es
un grado imposible**, ningún colorista lo escribe. El límite está para que el
fallo salga como "power pegado al límite" (y la confianza lo note) en vez de como
una excepción a las dos de la mañana. Hay un test que le tira encima cuatro
destinos degenerados y comprueba que el `power` siempre sale > 0.

Detalle: el optimizador **no construye un `CDL` en cada iteración** (serían
decenas de miles de validaciones); usa `_aplica_parametros`, y hay un test que
comprueba que las dos fórmulas coinciden **bit a bit** (`atol=0, rtol=0`). Si se
separaran, el ajuste convergería a una cosa y se devolvería otra.

Otra: si el refinado sale peor que el arranque lineal (pasa con nubes
degeneradas), me quedo con el arranque. No hay ninguna razón para devolver algo
peor de lo que ya tenía.

Tope de puntos que ve el optimizador: **20.000**. Son diez parámetros; más puntos
no mejoran nada y multiplican el tiempo. El submuestreo es determinista (semilla
fija `20260915`): dos ejecuciones dan el mismo CDL, y hay un test que lo afirma.

---

## 3. Confianza: la fórmula, escrita

Siete métricas, cada una a una **subnota 0..1** por una rampa lineal entre un
valor "bien" y un valor "mal":

| métrica | bien (subnota 1) | mal (subnota 0) | escala |
|---|---|---|---|
| `n_muestras` | 20.000 | 24 | log10 |
| `solape` | 0.90 | 0.40 | lineal |
| `condicion` | 1e5 | 1e10 | log10 |
| `residuo_de` | 1.0 ΔE | 8.0 ΔE | lineal |
| `extrapolacion` | 0.02 | 0.40 | lineal |
| `ganancia` | 4x | 100x | log10 |
| `fraccion_no_finita` | 0.0 | 0.25 | lineal |

Y luego, **sobre las que de verdad se han pasado** (las que faltan no cuentan ni
a favor ni en contra):

```
nota = sqrt( min(subnotas) * media_geometrica(subnotas) ) * pena_desajuste
```

con `pena_desajuste = 1` si las escenas son comparables y **0.35** si no.

**Por qué esa mezcla y no una media.** La media geométrica sola es demasiado
indulgente: seis subnotas perfectas y una de 0.30 dan 0.84, o sea "alta", y eso
es mentira. El mínimo solo es demasiado severo: una pega convierte en "baja" un
ajuste por lo demás impecable. La media geométrica de los dos (que es lo que hace
la raíz del producto) da 0.50 en ese ejemplo, o sea "media", que es exactamente
lo que hay que enseñar. Hay un test que lo afirma.

**La penalización por desajuste multiplica a propósito**: un desajuste de
contenido **no** se compensa con un ajuste numéricamente bueno; de hecho cuanto
mejor sale el número, más peligroso es.

`level` sale **siempre** de `confidence_level()` de `core.contracts`. No hay ni
un umbral de alta/media/baja escrito en mi módulo, y hay un test que lo comprueba.

### Dos calibraciones que tuve que rehacer, y son las cosas que más me habría equivocado

**1. `condicion`.** Empecé con "bien = 1e3, mal = 1e9" y **el test de las cuatro
cámaras salía con confianza 0.000 y ΔE 0.13**. Medido después: un retrato de
estudio tiene condición **1.1e3**, un exterior **1.3e3**, una carta de color 77 y
un campo de ruido 5. O sea que 1e3 **no es una nube degenerada, es una escena
normal**: en una imagen de verdad la variación de luma es mil veces la de croma y
eso no tiene nada de malo. El corte real está donde deja de haber información: un
degradado de un solo tono da **1.1e10** y una rampa de gris (rango 1 de verdad)
**1e299**. De ahí el 1e5 / 1e10.

**2. `solape`.** Empecé con el coeficiente de Bhattacharyya entre las dos
gaussianas, en crudo. **No mide nada útil en esta app**: un plano con un grado
fuerte encima da solape **0.00** contra el mismo plano sin grado, y ese es
literalmente el caso para el que existe el programa. Un plano bien igualable
salía con confianza 0.000.

Lo cambié por el solape de los **histogramas 3D reales** del origen **ya
transportado** contra la referencia. Eso sí dice algo: el transporte MKL iguala
media y covarianza por construcción, así que si después de eso los dos
histogramas siguen sin pisarse, es que a estas dos nubes **no les basta una
aplicación afín**. Valores medidos contra el retrato de estudio:

| | solape tras el transporte |
|---|---|
| el mismo plano | 1.000 |
| el mismo plano a −1 EV / +1.5 EV | 0.993 / 0.995 |
| el mismo plano con ruido encima | 0.976 |
| la mitad de arriba del fotograma | 0.876 |
| el mismo decorado con otro tono de piel | 0.920 (claro) / 0.776 (oscuro) |
| un campo de ruido | 0.834 |
| una rampa de gris | 0.661 |
| una carta de color | 0.557 |
| **un exterior** | **0.449** |

De ahí el corte 0.90 / 0.40. El Bhattacharyya gaussiano sigue exportado
(`coeficiente_bhattacharyya`) porque para ordenar candidatos a referencia
partiendo solo de un `ColorStats` es lo que hay, pero **no puntúa**.

### Claves desconocidas: lanzo

`puntuar_confianza(**metricas)` lanza `TypeError` con una clave que no conoce. Es
deliberado y es discutible: si el agente F llama con `cobertura=...`, su código
se rompe. Preferí eso a que un `residuos=` en vez de `residuo_de=` salga como una
nota silenciosamente optimista. La lista está en `METRICAS_ACEPTADAS` y en el
docstring.

---

## 4. Desajuste de contenido: manda la huella, y aquí está la tabla

El detector tiene que separar "el mismo plano con otra luz o con otro grado"
(que SÍ hay que igualar) de "otra escena" (que hay que marcar). Hay **dos
instrumentos** para esa pregunta y **no son igual de buenos**.

### 4.1 Los rasgos de píxeles (lo que tenía en la ronda 1)

Dos rasgos elegidos para no moverse con la exposición ni con el balance:

1. **`perfil`** — percentiles de luma normalizados: menos la mediana, entre el
   recorrido p5..p95. Quita el desplazamiento (exposición) y la escala
   (contraste); queda la forma del histograma.
2. **`croma`** — histograma 2D de `(R−G, B−G)` **centrado en su propia media y
   dividido por su propia dispersión**, comparado con Hellinger. Centrar mata el
   balance de blancos (que es justo lo que queremos poder corregir) y normalizar
   mata la ganancia; queda *cómo están repartidos los colores de la escena unos
   respecto de otros*. Rejilla 12×12 sobre ±3σ, medio recuento de suavizado de
   Laplace por celda.

`distancia = perfil + croma`, umbral **0.70**.

Descarté las correlaciones entre canales y la dispersión cromática absoluta:
**no separaban** (estudio contra exterior daba 0.022 de diferencia de
correlación, *menos* que dos tonos de piel distintos, 0.051). Estaban de adorno
y hacían daño.

### 4.2 La huella de `ClipAnalysis` (ronda 2, ya calibrada)

`d_huella = 1 − coseno`, con el coseno **recortado por abajo a cero**, igual que
`parecido_de_huellas` del agente B (los tres bloques de la huella van centrados
en cero, así que dos planos sin relación dan coseno ~0 y a veces negativo, y
para esto las dos cosas significan lo mismo).

**`UMBRAL_HUELLA = 0.50`**, o sea: se exige un **parecido de al menos 0.50**.
Antes estaba en 0.60 (parecido ≥ 0.40) y era un número puesto a ojo porque el
agente B escribía la huella a la vez que yo.

### 4.3 LA TABLA con la que decidí

Medida sobre el material del generador con la huella real de `core.analysis`.
La columna "¿marca sin huella?" es lo que haría la vía de rasgos sola.

| par | distancia rasgos | ¿marca sin huella? | parecido huella |
|---|---|---|---|
| **COMPARABLES — ninguno puede marcarse** | | | |
| estudio2 vs estudio2 | 0.000 | no | 1.0000 |
| estudio2 vs estudio2 −1EV | 0.269 | no | 0.9777 |
| estudio2 vs estudio2 −2EV | 0.468 | no | 0.9488 |
| estudio2 vs estudio2 +1.5EV | 0.309 | no | 0.9647 |
| estudio2 vs estudio2 CDL fuerte | 0.511 | no | 0.9988 |
| estudio2 vs estudio2 CDL extremo | 0.564 | no | 0.9982 |
| estudio2 vs estudio2 LUT look | 0.447 | no | 0.9936 |
| estudio2 vs estudio2 **CDL + look real** | **0.612** | no | 0.9967 |
| estudio2 vs estudio2 CDL+LUT (imagen destrozada) | **2.097** | **SÍ (falso)** | 0.9100 |
| estudio2 CDL extremo vs estudio2 CDL+LUT | **2.025** | **SÍ (falso)** | 0.9024 |
| estudio2 vs estudio0 | 0.365 | no | 0.9846 |
| estudio2 vs estudio5 | 0.438 | no | 0.7903 |
| estudio0 vs estudio5 | 0.588 | no | **0.7561** ← el peor |
| estudio2 vs cam Canon | 0.061 | no | 0.9988 |
| estudio2 vs cam DJI | 0.054 | no | 0.9973 |
| cam Canon vs cam DJI | 0.083 | no | 0.9948 |
| **NO COMPARABLES — todos tienen que marcarse** | | | |
| estudio2 vs exterior | 1.072 | sí | 0.0000 |
| estudio5 vs exterior | 1.196 | sí | 0.0000 |
| estudio2 CDL+LUT vs exterior | 2.359 | sí | 0.0000 |
| estudio2 vs carta | 0.841 | sí | 0.0000 |
| estudio2 vs rampa | 1.069 | sí | 0.0000 |
| estudio2 vs degradado | 1.018 | sí | 0.0000 |
| estudio2 vs ruido | 0.753 | sí | 0.1505 |
| exterior vs rampa | 1.081 | sí | 0.0643 |
| exterior vs carta | 1.073 | sí | 0.0099 |
| exterior vs degradado | 1.142 | sí | 0.0000 |
| carta vs rampa | 1.163 | sí | 0.1989 |
| degradado vs rampa | 1.178 | sí | **0.2193** ← el mejor |

**Los dos huecos, uno al lado del otro:**

| instrumento | peor par comparable | mejor par NO comparable | hueco |
|---|---|---|---|
| **huella** (parecido) | **0.7561** | **0.2193** | **0.5368** |
| rasgos de píxeles (distancia) | 0.612 (*) | 0.753 | 0.141 |

(*) excluyendo los dos pares de la imagen destrozada, que la vía de rasgos
**marca mal**. Contándolos, la vía de rasgos no tiene hueco: se invierte.

**El umbral de la huella, 0.50, cae casi en el centro del hueco**: deja 0.2561
de margen por el lado de los comparables y 0.2807 por el de los no comparables.
Eso es lo que afirma `test_el_umbral_cae_en_el_hueco_medido_y_el_hueco_es_grande`,
que además exige que el hueco siga siendo mayor que 0.40: si alguien toca la
huella o los rasgos y el hueco se estrecha, se pone rojo **antes** de que
empiecen a salir falsos positivos en la GUI.

### 4.4 Por eso la huella decide sola

Cuando hay huella en los dos lados, **la huella levanta la bandera y los rasgos
de píxeles no**. Meter un instrumento cuatro veces peor en un OR al lado del
bueno solo añade falsos positivos: los dos pares marcados en rojo en la tabla
saldrían marcados igual. Los rasgos se siguen midiendo y se cuentan en
`razones` (con una frase distinta: "puede ser solo que uno lleve un grado fuerte
encima"), así que la información no se pierde, pero no deciden.

Sin huella se cae a los rasgos, que es la vía débil. Está dicho en el docstring
de `emparejar`, y por eso `emparejar` acepta ahora `huellas=(a, b)`.

**El punto ciego de la huella, que hay que saber**: no lleva **ningún**
descriptor de color (el agente B lo quitó a propósito, porque el que tenía
describía el grado y no el plano). O sea que dos escenas con la misma
composición y colores completamente distintos le parecerían la misma. Con el
material del generador no pasa, pero es donde yo buscaría el primer fallo.

### 4.5 Medir la distancia DESPUÉS del transporte: probado y descartado

Era mi propia propuesta de la ronda 1 para arreglar el falso positivo del grado
fuerte. La medí antes de escribirla. **No funciona: arregla una punta y rompe la
otra.**

| par | distancia antes | después del transporte |
|---|---|---|
| mismo plano + CDL fuerte | 0.511 | **0.070** ✔ arregla |
| mismo plano + CDL extremo | 0.564 | **0.189** ✔ arregla |
| mismo plano + CDL extremo + LUT | 2.097 | **1.927** ✘ sigue roto |
| mismo plano + LUT de look solo | 0.397 | **0.364** — casi igual |
| piel 0 vs piel 5 (mismo decorado) | 0.588 | **0.673** ✘ empeora |
| retrato vs campo de ruido (¡distintos!) | 0.753 | **0.421** ✘ empeora |
| retrato vs degradado (¡distintos!) | 1.018 | **0.761** ✘ empeora |
| exterior vs degradado (¡distintos!) | 1.142 | **0.758** ✘ empeora |

**El hueco se invierte**: después del transporte el peor par comparable (0.673)
queda POR ENCIMA del mejor par no comparable (0.421), así que **no existe ningún
umbral que los separe**. Y tiene sentido visto a posteriori: el transporte iguala
media y covarianza por construcción, o sea que borra justo la parte de la
diferencia que SÍ distinguía dos escenas y deja solo la de orden superior, que
para esta pregunta es ruido.

Probé también `min(antes, después)`: tampoco. Sigue invertido por el par
"retrato vs campo de ruido" (0.421) contra "piel 0 vs piel 5" (0.588).

Así que mi propuesta de la ronda 1 era **mala**, y lo dejo escrito porque el
siguiente que lea aquel informe va a tener la misma idea. El arreglo bueno era
la huella, que ya existe.

## 5. Qué significan `delta_e_before` y `delta_e_after` (leer esto antes de creerse un número)

Con dos listas de píxeles que no se corresponden una a una, "el ΔE entre el plano
y la referencia" **no está definido**: no hay parejas que restar. Lo que mide la
app es:

```
delta_e_before = ΔE2000 medio entre el origen y su transporte ideal T(origen)
delta_e_after  = ΔE2000 medio entre lo corregido y ese mismo T(origen)
```

O sea: **"cuánto había que mover el plano"** y **"cuánto le falta todavía"**. Con
origen y referencia idénticos, `T` es la identidad y los dos salen exactamente 0.

**El asterisco importante**: `delta_e_after` mide la distancia **al transporte**,
no a la verdad. Y el transporte es afín, así que el techo lo pone el MKL y no el
CDL. Cadena completa medida sobre el retrato de estudio con un grado conocido
encima (ΔE2000 medio **contra el plano original**, píxel a píxel):

| | ΔE2000 |
|---|---|
| sin corregir | 32.73 |
| **con el transporte MKL ideal** | **1.66** ← el techo del método |
| con el CDL que sale de `emparejar` | 1.72 |
| con el CDL + el LUT de residuo | 1.65 |
| con un CDL ajustado sobre **parejas** de píxeles | **0.12** |

Y `emparejar` reporta `delta_e_after = 0.86` en ese caso. Los dos números son
ciertos y miden cosas distintas; quien enseñe uno en la GUI tiene que saber cuál.
**El CDL solo pierde 0.06 respecto al transporte, y el LUT los recupera. Los 1.65
que quedan son del modelo afín**: para bajarlos hay que tener las parejas (que es
lo que hace el agente F con ingeniería inversa), no ajustar mejor el CDL.

Cuando los dos planos **sí** se corresponden píxel a píxel (las cuatro cámaras),
lo que interesa es el ΔE directo entre imágenes, y eso lo mide
`core.matching.camaras`, que es de donde salen las cifras de §0.

---

## 6. El LUT: es el RESIDUO, va DESPUÉS del CDL

`con_lut=True` devuelve un `LUT3D` pensado para el nodo 3, detrás del CDL del
nodo 2. Se construye al revés: para cada punto `y` de la rejilla (que es un valor
ya salido del CDL) se busca de qué entrada venía, `x = cdl^-1(y)`, y se escribe el
transporte ideal de esa entrada, `T(x) = A x + b`. Así `LUT(CDL(x)) = T(x)`.

**No los apiles al revés y no apliques solo el LUT**: por sí solo no hace nada
útil, porque asume que el CDL ya ha pasado.

Donde el CDL recortó (el `max(x, 0)` del estándar) la inversa no existe y lo que
se escribe es el borde. Es la misma decisión que toma `LUT3D.apply` fuera de
dominio, así que al menos es coherente.

En la práctica el LUT aporta poco (0.296 → 0.265 en el test de las cuatro
cámaras) **porque el transporte es afín y el CDL ya lo aproxima casi entero**.
Cobra sentido el día que el objetivo deje de ser afín.

---

## 7. NaN: aquí me desvío de `core.color`, y lo digo

`core.color` propaga los NaN a propósito, para que un plano roto no dé un número
plausible. **Aquí no se puede**: un `CDL` con un NaN dentro no existe (el
constructor lanza), así que propagar significaría no poder devolver nada.

Lo que hago: las filas no finitas se **descartan**, y a cambio

1. se cuentan y van a la confianza como `fraccion_no_finita`, que la baja, y
2. sale una nota en `MatchResult.notes` con el porcentaje exacto de cada lado.

O sea: no se barre bajo la alfombra, se cuenta. Si **no queda ni un píxel finito**
sí se lanza `ValueError`. `aplicar_mkl`, que es un producto de matrices y no tiene
este problema, **sí** propaga los NaN como el resto del proyecto.

Si a Mario le parece que un plano con NaN tiene que negarse a emparejar del todo,
el cambio es una línea en `_nucleo`.

---

## 8. El negro absoluto en CIE L*a*b*: encontrado aquí, arreglado por el agente A

Me lo encontré en la ronda 1 midiendo el caso "escena → negro puro", que dejaba
un `delta_e_after` de **7.65** que no venía del ajuste.

`core.color.rgb_to_lab` de un negro **exacto** devolvía **L\* = −16**, no 0: la
extensión impar de la f() de CIE L*a*b* estaba escrita con `s = np.sign(t)`, y
`np.sign(0) = 0`, mientras que la rama lineal de la CIE vale 16/116. Había un
**salto de 16 unidades de L\*** justo en el cero, y `delta_e2000` entre un negro
exacto y un "casi negro" de 1e-30 daba **8.57**.

No lo toqué (es del agente A) y se lo pasé al orquestador con el diagnóstico y el
arreglo de una línea. **Ya está arreglado.** Comprobado en esta ronda:

| | antes | ahora |
|---|---|---|
| `rgb_to_lab([0,0,0])` | `[-16, 0, 0]` | `[0, 0, 0]` |
| `delta_e2000(negro, 1e-30)` | 8.57 | 0.0 |
| mi caso "escena → negro": `delta_e_after` | 7.65 | **0.0** |

`test_el_negro_absoluto_ya_no_da_un_salto_en_lab` se queda de guardia: es barato
y caza la regresión al instante.

## 9. Lo que decidí yo solo y Mario podría querer cambiar

1. **El significado de `delta_e_before` / `delta_e_after`** (§5). Es la decisión
   con más consecuencias para la GUI. La alternativa sería no dar ningún número
   cuando no hay parejas, que me parece peor.
2. **El LUT es el residuo, no el grado entero** (§6). Encaja con el diseño de tres
   nodos, pero significa que `MatchResult.lut` **no se puede aplicar solo**.
3. **Los NaN se descartan en vez de propagarse** (§7).
4. **`puntuar_confianza` lanza con una clave desconocida** (§3) en vez de
   ignorarla.
5. **`GANANCIA_MAX = 100`** y **`power >= 0.05`**: son topes que elegí yo. Con el
   material del generador no se tocan nunca.
6. **60.000 píxeles** por lado en `emparejar` y **20.000** en el optimizador.
   Puestos por tiempo de ejecución; con material real (4K, varios fotogramas)
   habría que volver a mirarlo.
7. **El umbral de contenido 0.70** y los pesos 1/1 de `perfil` y `croma`. Están
   calibrados con el generador; con material real de Mario habría que repetir la
   tabla de §4. Con huella ya no deciden, así que importan menos.
8. **Que la huella decida sola cuando la hay**, en vez de ir en un OR con los
   rasgos de píxeles (§4.4). Es la decisión de la ronda 2 y está sostenida por la
   tabla, pero significa que el punto ciego de la huella (no mira el color) pasa
   a ser el punto ciego del detector entero.
9. **`emparejar` acepta ahora `huellas=(a, b)`**, un parámetro nuevo (sólo por
   nombre, opcional: ninguna llamada existente se rompe). Sin él, `emparejar` con
   píxeles sueltos se queda en la vía débil.

## 10. Lo que NO llegué a hacer

- **Pesos por piel dentro de `emparejar`.** `ajustar_cdl` acepta `pesos` y está
  probado, pero `emparejar` no los usa: haría falta la máscara de piel del agente
  B y no quise depender de él. Es un `pesos=` de nada cuando exista.
- ~~Recalibrar el umbral de la huella~~ — **hecho en la ronda 2**, §4.
- **Transporte no lineal.** Todo lo que hay aquí es afín. El techo de 1.66 ΔE de
  §5 es suyo. Un transporte por cuantiles o un MKL por regiones lo bajaría, y es
  por donde yo seguiría.
- **Rendimiento.** El test de las cuatro cámaras tarda 0.8 s con imágenes de
  640×360. No he medido nada en 4K.

## 11. Cosas que quise tocar y no toqué

`core/contracts.py`, `core/color/**`, `tests/media/generate.py` y
`tests/conftest.py` están intactos: no he editado ni una línea de nada que no sea
`core/matching/**` o `tests/test_matching_*.py`.

Dos cosas que le pediría al orquestador:

1. **El salto del negro en `rgb_to_lab`** (§8). Es del agente A y es una línea.
2. Nada más. Las fixtures `estudio_trabajo` / `exterior_trabajo` /
   `pieles_trabajo` y `a_trabajo()` de `conftest.py` me han valido tal cual.


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

**De este módulo se han mudado**: `UMBRAL_DESAJUSTE` y `UMBRAL_HUELLA` (deciden
`content_mismatch`, o sea la frase «estas dos escenas no son comparables»), y
`PENA_DESAJUSTE` más las siete rampas de `UMBRALES` (deciden la nota, y la nota
decide el alta/media/baja de la lista de clips). Las rampas se llaman
`RAMPAS_DE_CONFIANZA` en `core/umbrales.py` y se siguen reexportando aquí como
`UMBRALES`, **el mismo objeto**, con un test que lo comprueba.

**Y tres que no tenían nombre**: el `0.35` de `d_croma`, el `0.12` de
`d_perfil` (los dos deciden qué razones en castellano se escriben) y el `0.85`
de `subnotas[clave] < 0.85` de `confianza.py`, que decide qué subnotas se
convierten en una frase que Mario lee. Hoy son `UMBRAL_CROMA_EXPLICABLE`,
`UMBRAL_PERFIL_EXPLICABLE` y `UMBRAL_SUBNOTA_EXPLICABLE`. De ninguno de los tres
hay medida escrita en ninguna parte, y así está dicho.

Un detalle que conviene tener anotado y que **no se ha tocado**: el `100.0` del
extremo malo de la rampa `ganancia` vale lo mismo que `mkl.GANANCIA_MAX`, que es
el recorte duro. Son el mismo número haciendo dos trabajos distintos —uno puntúa
y el otro recorta— así que se dejan separados, pero ahora está escrito.

**Se quedan aquí**: `LIMITES_CDL`, `MAX_PUNTOS_AJUSTE`, `SEMILLA`,
`MAX_PIXELES_EMPAREJAR`, `TOL_RANGO`, `GANANCIA_MAX`, `BINS_CROMA`,
`RANGO_CROMA`, `ALFA_SUAVIZADO`, `PESO_PERFIL` y `PESO_CROMA`. Son parámetros
del método, no criterios de decisión.

El `UMBRAL_HUELLA * 0.5` de `contenido.py` sigue escrito así, derivado del
umbral bueno, y no como un `0.25` a pelo. Es a propósito: derivar es mejor que
copiar.
