# NOTAS — agente A · color

Qué decidí, qué descarté y por qué. Está escrito para que mi revisor pueda
discreparme con criterio, así que hay números medidos, no impresiones.

Todo lo de aquí se comprueba solo: `.venv/bin/python -m pytest tests/test_color_*.py`
(298 tests, todos en verde a día de hoy).

---

## 1. Las dos convenciones que hay que entender antes de tocar nada

**Lineal** = escena-lineal con **0.18 = 18% de gris**. Es lo que produce
`tests/media/generate.py` y lo que entra y sale de `log_encode`/`log_decode`.
Los `linear_davinci_wg` y `linear_rec709` del contrato son eso: primarios, sin
curva.

**Codificado** = el *code value normalizado* del fabricante, o sea el código de
10 bits dividido entre 1023. Es la convención en la que están publicados los
números que todo el mundo cita:

| Espacio | 18% de gris codificado |
|---|---|
| S-Log3 | 0.410557 (= 420/1023) |
| V-Log | 0.423311 |
| Canon Log 3 | 0.343389 |
| DJI D-Log | 0.398765 |
| DaVinci Intermediate | 0.336043 |
| Rec.709 (OETF BT.709) | 0.409008 |

Los seis salen **idénticos** (diferencia máxima 0.0e+00, literal) a los de
`colour-science` con sus parámetros por defecto. Eso es lo que verifica
`test_coincide_con_colour_science`.

### El 0.9 de Canon

La fórmula de Canon Log 3 está definida sobre reflectancia**/0.9**: el 18% de
gris entra en la fórmula como 0.2, no como 0.18. Sony, Panasonic, DJI y
Blackmagic no hacen eso. Por eso `_clog3_encode` divide por 0.9 y las demás no.
No es un apaño: está en el documento de Canon, y es lo que hace que salga
clavado el 32.8 IRE que Canon publica para el 18% de gris.

### Canon: dos formas de la misma curva

Canon publica la curva en dos formas equivalentes: la de rango completo (v1,
constantes 0.42889912 / 0.069886632) y la de code value de rango legal (v1.2,
constantes 0.36726845 / 0.12240537). **Implementé la v1.2** para que los seis
espacios compartan convención. Son la misma curva: v1.2 = rango_legal(v1).
Empecé con la v1 y por eso mis primeros valores no cuadraban con colour; lo dejo
escrito porque es exactamente la trampa en la que va a caer el siguiente.

---

## 2. De dónde sale cada fórmula

| Espacio | Fuente | Anclas que afirmo como test |
|---|---|---|
| S-Log3 | Sony, *Technical Summary for S-Gamut3.Cine/S-Log3* | 18% → 420/1023 exacto; x=0 → 95/1023; corte en 0.01125 con code value 171.2103 |
| V-Log | Panasonic, *V-Log/V-Gamut Reference Manual* | x=0 → 0.125 exacto; cut1=0.01 → cut2=0.181 exacto; tabla IRE 7.3 / 42 / 61 |
| Canon Log 3 | Canon, *White Paper on Canon Log Gamma Curves* (rev. 1.2) | 18% → 32.8 IRE de rango completo; injertos en ±0.014 → 0.097465473 y 0.15277891 |
| DJI D-Log | DJI, *D-Log/D-Gamut White Paper* | x=0 → 0.0929 exacto |
| DaVinci Intermediate | Blackmagic, *DaVinci Wide Gamut* white paper | 18% → 0.336; LIN_CUT·M = LOG_CUT |
| Rec.709 | ITU-R BT.709-6 §1.2 | pendiente 4.5 cerca del negro; 1.0 → 1.0 |

**Lo que colour-science NO tiene con el nombre que decía el encargo:**
`log_encoding_DaVinciIntermediate` **no existe**. Está como
`colour.models.oetf_DaVinciIntermediate` / `oetf_inverse_DaVinciIntermediate`.
Hay un test (`test_colour_no_trae_davinci_como_log_encoding`) que lo afirma para
que nadie pierda media hora buscándolo.

Cromaticidades: las ocho coinciden al bit con las de `colour-science`.

---

## 3. Decisiones que Mario podría querer cambiar

### 3.1 Uso la matriz CALCULADA, no la que imprime el fabricante

Sony, Panasonic y DJI imprimen en su PDF, además de las cromaticidades, la
matriz RGB→XYZ ya calculada y **redondeada**. `colour-science` usa la impresa.
Yo la calculo a partir de las cromaticidades. Diferencias medidas:

| Espacio | Diferencia máx. con la matriz impresa | Decimales que imprime |
|---|---|---|
| S-Gamut3.Cine | 4.5e-11 | ~10 |
| V-Gamut | 4.7e-07 | 6 |
| **DJI D-Gamut** | **1.8e-04** | 4 |
| Cinema Gamut, Rec.709, DaVinci WG | 2.2e-16 (colour también la calcula) | — |

**Por qué la calculada:** la calculada manda el blanco RGB (1,1,1) exactamente a
D65. La impresa no: la de DJI se desvía 2.6e-4 en XYZ, o sea que con ella un
gris neutro de un dron **sale con un tinte**, pequeñísimo pero sistemático.
Prefiero un neutro exacto a cuadrar con el redondeo de un PDF.

**Lo discutible:** si mañana comparamos un plano de dron contra lo que hace
Resolve y sale una diferencia de 0.02%, es esto. Cambiarlo es una línea
(`ColorSpaceInfo.matrix_rgb_to_xyz`). Está medido y afirmado en
`test_matriz_impresa_por_el_fabricante_vs_la_calculada`.

### 3.2 `rec709` es la OETF de CÁMARA, no la EOTF de pantalla

`rec709` implementa la OETF de la BT.709 (4.5x / 1.099·x^0.45 − 0.099), no la
EOTF de la BT.1886 ni la curva sRGB. Es lo que hace falta para ir de
escena-lineal a un Rec.709 "de vídeo". Si alguien esperaba gamma 2.4 de
pantalla, esto no es eso, y es una decisión que se puede querer revisar cuando
el agente H enseñe imágenes en la GUI.

Fuera de 0..1 extiendo por **simetría impar** (f(−x) = −f(x)), que es lo que
hacen Resolve y colour y lo único que preserva los negativos que manda el
contrato 1.

### 3.3 Política de NaN: se propaga, no se lanza

Coherente en todo el módulo. Un NaN de entrada sale NaN en la imagen, en el
Oklab, en el Lab, en el ΔE por píxel y **también en `delta_e2000_mean`**.

Descarté `nanmean` a propósito: si la media barriera los NaN, el agente C
recibiría un número plausible sobre un plano corrupto y nadie se enteraría.
Que salga NaN obliga a mirar. Si a Mario le molesta, el cambio es una línea,
pero entonces hay que decidir quién avisa.

`skin_mask_oklab` es la excepción razonable: un píxel NaN devuelve `False`, no
NaN, porque el tipo de retorno es booleano.

### 3.4 Precisión: se respeta la que te den

`convert`, `log_encode`, `log_decode`, `to_working` y `from_working` devuelven
**float32** (contrato 1) salvo que la entrada sea float64, en cuyo caso
devuelven float64. Bajar un float64 a float32 sin que lo haya pedido nadie es
tirar 16 bits de mantisa. Las funciones perceptuales devuelven **siempre
float64**, porque `ColorStats` los guarda así.

**Los pasos INTERMEDIOS van siempre en float64.** Esto era un bug real que me
cazó el test de bordes: decodificar un 9.5 codificado en S-Log3 da 8.4e39 de
escena-lineal, y eso **no cabe en float32** (que se queda en 3.4e38). Si
`convert` bajaba a float32 entre paso y paso, ese intermedio se volvía infinito
y el resultado final salía NaN, aunque el resultado final cabía de sobra. De ahí
`encode_raw` / `decode_raw`.

### 3.5 `convert(x, X, X)` corta por lo sano

Devuelve una copia bit a bit de la entrada, sin pasar por la curva ni por la
matriz. Ida y vuelta por un logaritmo en coma flotante no devuelve exactamente
lo que entró, y el encargo pedía identidad exacta. También preserva los NaN.

---

## 4. Límites reales que dejo medidos, no escondidos

### 4.1 V-Log no es invertible en su punto de corte

La curva **publicada** de Panasonic no es monótona en x = 0.01: la rama
logarítmica vale ahí 0.18099969 y la rama lineal llega hasta 0.181. Hay un
saltito hacia atrás. Como la función no es inyectiva en esa franja, **ningún**
decodificador puede invertirla; no es un fallo de mi implementación.

- Ancho de la ventana mala: **5.5e-8 en x** (≈ 8e-6 paradas de luz).
- Error máximo dentro de ella: **5.6e-8**.

Lo mismo, tres órdenes de magnitud más fino, en DaVinci Intermediate:
ventana de **3.3e-11** en x = 0.00262409.

S-Log3, Canon Log 3, D-Log y Rec.709 **sí** invierten exacto en el corte (error
< 1e-14), porque en esas el salto va en el otro sentido. Está afirmado en
`test_estas_curvas_si_son_exactas_en_el_corte`.

Elegí los umbrales del decodificador como *el valor que da el codificador en el
punto de corte*, y no como la constante que imprime el fabricante. Con la
constante impresa, S-Log3 dejaría de invertir exacto en una franja de 2.9e-6.

**No toqué ninguna fórmula para "arreglar" esto.** Cambiarla sería dejar de leer
lo que graba una Lumix.

### 4.2 Cancelación con valores absurdos

Un valor codificado de 3.0 en S-Log3 son 1.9e9 de escena-lineal. Al pasar por la
matriz de primarios ese canal gigante se mezcla con los otros dos, y al volver,
reconstruir un número de orden 0.01 restando dos de orden 1e8 se come once de
los dieciséis dígitos del float64: el error relativo de la ida y vuelta sube a
~1.6e-5. No tiene arreglo dentro del módulo y no hace falta (3.0 codificado no
sale de ninguna cámara), pero está medido en
`test_valores_absurdos_pierden_precision_y_hay_que_saberlo`.

### 4.3 Tolerancias: de dónde sale cada una

Ninguna está elegida para que pase algo. Cada una sale de la precisión del dato:

| Test | Tolerancia | Por qué esa |
|---|---|---|
| anclas exactas (420/1023, 0.125, 0.0929) | 1e-12 | son exactas por construcción |
| Sharma ΔE2000 | 5e-5 | los valores publicados traen 4 decimales |
| cruce con colour (curvas) | 1e-10 | es la misma fórmula; la diferencia real es 0.0 |
| cruce con colour (ΔE2000) | 1e-10 | ídem |
| DaVinci LIN_CUT·M vs LOG_CUT | 1e-7 | ocho decimales impresos × M=10.44 ya son ±5.2e-8; la diferencia real es 2.1e-8 |
| blanco de Oklab = 1.0 | 2e-4 | las matrices de Ottosson vienen redondeadas; el residuo de 1.2e-4 es suyo |
| ida y vuelta float64 | 1e-9 relativo | dos logaritmos, dos exponenciales y dos matrices |

---

## 5. ΔE2000

Implementación propia siguiendo las notas de **Sharma, Wu y Dalal (2005)**.
Verificada en tres frentes:

1. **18 pares del conjunto de referencia de Sharma**, elegidos entre los que
   rompen implementaciones ingenuas: tonos a caballo de 0/360°, croma cero,
   y el entorno de 275°. Coinciden con el valor publicado con error < 5e-5.
2. **3000 pares aleatorios** por todo el volumen de Lab contra
   `colour.difference.delta_E_CIE2000`: diferencia máxima < 1e-10.
3. **801 muestras barriendo h = 255..295°**, que es donde el término de rotación
   RT tiene su pico y donde está la discontinuidad de tono famosa: < 1e-10.

Los tres sitios donde una implementación ingenua falla y que están tratados
explícitamente: C'=0 (hay que forzar Δh'=0 y h̄'=h1'+h2', no promediar), la
media de tonos a caballo de 0/360, y `C^7` escrito como `1/(1+(25/C)^7)` para
que un croma enorme (que aquí pasa: especulares, material fuera de gamut) no
desborde el float64.

**Lo que NO hice:** no metí las 34 filas completas de la tabla de Sharma. Sin
red no podía verificar las que no recordaba con certeza, y prefiero 18 pares que
sé ciertos a 34 de los que 16 me los estaría inventando. Si alguien tiene el PDF
a mano, ampliar `SHARMA` en `tests/test_color_perceptual.py` es copiar filas.

---

## 6. `skin_mask_oklab` — los números reales, salgan como salgan

### La decisión de fondo: croma RELATIVO, no absoluto

La piel oscura tiene **la misma tonalidad** que la clara pero **mucho menos
croma absoluto**. Medido sobre los seis tonos de `SKIN_TONES_SRGB` en Oklab:

| Tono | L | croma C | tono h | C/L |
|---|---|---|---|---|
| 0 (más claro) | 0.903 | 0.045 | 56.1° | 0.049 |
| 1 | 0.833 | 0.062 | 53.7° | 0.074 |
| 2 | 0.752 | 0.076 | 54.9° | 0.102 |
| 3 | 0.629 | 0.082 | 54.1° | 0.131 |
| 4 | 0.474 | 0.072 | 51.8° | 0.151 |
| 5 (más oscuro) | 0.340 | 0.051 | 50.7° | 0.149 |

El ángulo de tono es estabilísimo (50.7° a 56.1°, ocho grados de margen en seis
tonos). El croma absoluto va de 0.045 a 0.082 y **vuelve a bajar**: un umbral de
croma absoluto pierde a la vez el tono 0 y el tono 5. El croma relativo a L, en
cambio, crece monótono. Por eso el criterio usa **C/L** y no C.

Umbrales finales (`SKIN_OKLAB_LIMITES`), sacados de un barrido sobre las seis
escenas optimizando la peor exhaustividad y la peor precisión a la vez:
tono 10°–85°, C/L 0.040–0.300, C ≥ 0.015, L 0.25–1.30.

### Precisión y exhaustividad medidas, tono a tono

Contra la verdad de `studio_scene(skin_tone_index=i).skin_mask`:

| Tono | píxeles marcados | verdad | **precisión** | **exhaustividad** |
|---|---|---|---|---|
| 0 (más claro) | 17.801 | 14.588 | **0,793** | **0,967** |
| 1 | 20.991 | 14.588 | **0,695** | **1,000** |
| 2 | 21.643 | 14.588 | **0,674** | **1,000** |
| 3 | 21.284 | 14.588 | **0,685** | **1,000** |
| 4 | 19.364 | 14.588 | **0,747** | **0,992** |
| 5 (más oscuro) | 15.631 | 14.588 | **0,840** | **0,900** |

**Con los tonos oscuros funciona peor, y ahí está el número: el tono 5 pierde un
10% de la piel.** Son las zonas más en sombra de la cara, donde el croma cae por
debajo del suelo absoluto de 0.015 y el tono deja de ser fiable por el grano.
Bajar ese suelo recupera esa piel pero mete el pelo (que es marrón cálido, tono
de piel) y la precisión del tono 5 se desploma. Elegí no bajarlo. Es una
decisión discutible y es de las primeras que pondría sobre la mesa.

### Sobre la precisión de 0,67–0,84

No es lo que parece. Midiendo qué son los "falsos positivos": entre el **77% y
el 86%** de ellos son píxeles con `skin_alpha > 0.2`, o sea el borde difuminado
de la cara, que la verdad de `studio_scene` excluye porque exige `alpha > 0.55`.
Contra una verdad más laxa (`alpha > 0.2`) la precisión es **0,950 / 0,950 /
0,949** para los tonos 0, 2 y 5 — plana, sin sesgo por tono.

Es decir: la máscara marca *de más* en el contorno, no *mal*. Para lo que la usa
la app (sacar el color medio del locus de piel, no recortar a nadie) eso es
inofensivo y hasta conveniente.

### Falsos positivos en material sin piel

- Rampa de gris: **0,0000**. Cero exacto.
- Exterior sin gente: **0,0175**. Es el camino de tierra, que es literalmente
  color piel; ningún detector de color lo va a distinguir.
- ColorChecker: **0,157**. Son los parches "dark skin", "light skin" y
  "orange". Correcto: es un detector de color, no de caras.

### La máscara no depende del espacio

`skin_mask_oklab` da **exactamente** el mismo resultado (coincidencia 1,00000)
tanto si le entra el material en `linear_rec709` como si le entra ya convertido
al espacio de trabajo, o codificado en S-Log3 o V-Log. Es lo que tiene que pasar
—Oklab es absoluto— y es la prueba de que `convert` no mete sesgo. Está afirmado
en `test_skin_mask_da_lo_mismo_desde_cualquier_espacio`.

---

## 7. Lo que NO llegué a hacer

- **Tabla completa de Sharma** (34 pares). Ver §5.
- **Adaptación cromática de verdad.** Los ocho espacios son D65, así que el
  Bradford que hay implementado sale identidad siempre. El camino está escrito y
  probado (`_cat_bradford`), pero **nunca se ha ejercitado con dos puntos
  blancos distintos**. El día que entre un DCI-P3 o un ACES hay que probarlo de
  verdad antes de fiarse.
- **Curvas de otras cámaras**: ARRI LogC3/LogC4, RED Log3G10, Fujifilm F-Log,
  Nikon N-Log, Apple Log. La arquitectura las admite (una entrada en
  `TRANSFERENCIAS` y otra en `SPACES`), pero no están.
- **Gamut mapping.** Convertir a un gamut más pequeño produce valores negativos
  y se preservan tal cual, como manda el contrato 1. Nadie los comprime. Si eso
  hace falta, es otro módulo.
- **Rendimiento.** No he medido ni optimizado nada. `convert` sobre un 4K son
  ~25 millones de operaciones en float64; funciona, pero si el agente H lo llama
  en un bucle de vista previa habrá que mirarlo.

---

## 8. Cosas que quise tocar y no toqué

`core/contracts.py`, `tests/media/generate.py` y `tests/conftest.py` están
intactos: no he editado ni una línea de nada que no sea `core/color/**` o
`tests/test_color_*.py`.

Lo único que me habría venido bien: una fixture compartida que devuelva las seis
escenas **ya en el espacio de trabajo**. La he montado dentro de mis tests con
`convert` y no hace falta cambiar nada; lo apunto por si el agente B acaba
necesitando lo mismo y merece la pena que la ponga el orquestador en
`conftest.py` en vez de duplicarla.
