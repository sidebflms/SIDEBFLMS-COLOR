"""El diagnostico: ¿cuanto de este grado me puedo llevar en un `.cube`?

Esta es la pregunta que hace especial a `core.reverse`. Recuperar un LUT lo hace
cualquiera; decir **hasta donde llega el LUT y donde empieza lo que no es un
LUT** es lo que evita entregarle a un cliente un `.cube` que "casi" reproduce el
grado y que falla justo en la cara del actor.

DE QUE ESTA HECHO EL DIAGNOSTICO
--------------------------------
1. `residuo` = ΔE2000 por pixel entre lo que predice `LUT(CDL(original))` y el
   coloreado de verdad. Es el mapa `spatial_residual`.
2. `movimiento` = ΔE2000 por pixel entre el original y el coloreado. Es "cuanto
   grado hay".
3. `lut_reproducible = 1 - media(residuo) / media(movimiento)`, sujeto a 0..1.
   Se lee en castellano: **"de todo lo que este grado mueve el color, me llevo
   este tanto por uno"**. Si el grado no mueve nada (los dos planos son el
   mismo), la fraccion no esta definida y se devuelve 1.0 si el residuo tambien
   es despreciable, que es lo cierto: un grado identidad es un LUT identidad.

POR QUE ESA FORMULA Y NO "1 - residuo/8"
----------------------------------------
Porque un residuo de 2 dE2000 sobre un grado que mueve 40 es ruido, y el mismo
residuo de 2 sobre un grado que mueve 3 es que no has recuperado nada. Un numero
absoluto no distingue esos dos casos y este si. El absoluto tambien se da
(`residuo_de_medio`, `residuo_de_p95`), porque para decidir si se entrega hace
falta saber si lo que falta **se ve**.

TRES PRUEBAS DISTINTAS, NO UNA (reescrito el dia 2)
---------------------------------------------------
La version de la primera noche buscaba las tres formas (vineta, degradado, zona
local) sobre **un unico campo**: el ΔE2000 del residuo, apenas suavizado, y con
un umbral de zonas locales calculado como `mediana + 4·1.4826·MAD`. Esa version
detectaba bien una ventana y **era ciega a una vineta sola**. Las dos razones,
las dos medidas y las dos escritas aqui para que no se repitan:

1. **La MAD era el estadistico equivocado.** La MAD es robusta frente a valores
   atipicos, y una vineta **no es un valor atipico**: toca casi todos los
   pixeles del cuadro. El estimador se la tragaba como linea base, el umbral se
   disparaba y no salia ninguna zona. No era una calibracion: era el estadistico
   mal elegido.
2. **El ΔE2000 no es el campo donde se ve una vineta.** Una vineta es
   **multiplicativa sobre la imagen**, asi que su ΔE depende del brillo local
   del contenido y no solo del radio. El perfil radial del ΔE explicaba solo un
   R2 = 0.2887 de su varianza sobre el caso de vineta sola: por debajo del 0.30
   que pedia la puerta, y por un 4%. Subir el suavizado abria la puerta
   (R2 = 0.3107 con `min(h,w)//24`) pero eso es calibrar contra un caso.

Lo que hay ahora son **tres pruebas sobre dos campos distintos**, en este orden:

**El campo de ganancia.** `G = log(coloreado + eps) - log(prediccion + eps)`,
por canal. Es lo que el grado hace que el LUT no explica, medido como
**ganancia** y no como distancia de color: una vineta multiplicativa es
exactamente plana en este campo, independientemente del contenido. La tabla de
separacion esta en `NOTAS.md`; el resumen es que el recorrido del perfil radial
del logaritmo de la ganancia de luma separa "no hay nada espacial" (0.000) y
"grano" (0.004) de cualquier cosa espacial (>= 0.19) **por un factor de
cuarenta**, mientras que el mismo recorrido medido en ΔE2000 no separa nada.

1. **Vineta** (baja frecuencia radial). Se suaviza el campo de ganancia de luma
   con una gaussiana de `SIGMA_RADIAL·min(h,w)`, se **estima el centro de la
   caida** ajustando `g ~ c0 + c1·x + c2·y + c3·(x²+y²)` y tomando el vertice, y
   se bina el campo en `CORONAS` coronas alrededor de ese centro. Hay vineta si
   el perfil explica `>= UMBRAL_R2_RADIAL` de la varianza del campo, su
   correlacion de Pearson con el radio supera `UMBRAL_MONOTONIA_RADIAL` **en
   valor absoluto** y su recorrido supera `UMBRAL_RECORRIDO_GANANCIA`.
   **El signo se mide y se dice**: negativo = oscurece hacia fuera, que es la
   vineta clasica; positivo = aclara hacia fuera. Las dos son igual de
   imposibles de meter en un LUT, pero al colorista no le da igual cual es.
2. **Degradado** (baja frecuencia lineal). Sobre lo que queda del campo de
   ganancia despues de restarle el modelo radial se ajusta `g ~ a·x + b·y + c`.
3. **Zona local** (baja frecuencia compacta). Se suaviza el campo de ganancia
   **por canal** con `SIGMA_LOCAL·min(h,w)`, se le resta el modelo radial (si
   hubo vineta) y se toma la norma sobre los tres canales. El umbral es
   `max(SUELO_GANANCIA_LOCAL, mediana + FRACCION_DE_PICO·(p99.5 - mediana))`:
   un contorno a media altura del pico, con un suelo absoluto por debajo del
   cual la desviacion de ganancia ni se ve ni se distingue del grano.
   **Por canal y no en luma** a proposito: una secundaria que solo cambia el
   tinte sin tocar el brillo es invisible en un campo de luma y aqui se ve.

Y una cuarta medida que **no es una forma sino una familia**:

4. **Textura** (alta frecuencia). `residuo - pasa_bajo(residuo)`, y su
   desviacion tipica. Grano, enfoque, reduccion de ruido y halacion viven ahi.
   No son geometria y no caben en un LUT, pero tampoco son "una zona": se
   reportan aparte, con la etiqueta `"textura"`, cubriendo el cuadro entero.

EL SENTIDO DEL FALLO IMPORTA
----------------------------
Decir **"esto es un LUT" cuando no lo es es mucho peor** que lo contrario. Lo
primero manda a Mario a llevarse un `.cube` que no reproduce el grado y a
enterarse delante de un cliente; lo segundo solo le hace trabajar de mas. Por
eso, donde hay que elegir, **estos umbrales estan calibrados hacia el falso
positivo**: el suelo de la zona local se pone bajo (un 8% de ganancia), la
monotonia radial se pide en valor absoluto, y la puerta del R2 radial se deja en
0.30 cuando la vineta mas floja medida da 0.83.

**LIMITES QUE HAY QUE SABER** (medidos, no supuestos; las cifras estan en
`NOTAS.md`):

- Una vineta **descentrada** si se detecta: el centro se estima, no se supone.
  Lo que no se estima es la **elipticidad**: una vineta muy ovalada se ajusta
  peor y puede quedarse por debajo del R2.
- Una ventana **centrada y redonda** sigue siendo indistinguible de una vineta
  invertida. Es el falso positivo conocido, y va hacia el lado seguro.
- Con una **vineta sola** salen ademas unas cuantas "zona local" espurias en las
  esquinas. No son un capricho del umbral: el LUT, al ajustarse contra un plano
  ya vineteado, absorbe parte de la vineta **de forma dependiente del color**, y
  lo que queda en las esquinas es un error de ganancia real del 25%. Decirlo es
  mas honesto que esconderlo, pero hay que saber que la etiqueta se queda corta:
  eso es la vineta, no otra ventana. Medido en `NOTAS.md`.
- El detector **no sabe de sujetos**: una correccion secundaria por tono de piel
  (todas las caras, esten donde esten) sale como varias "zona local" repartidas,
  no como "una secundaria de piel". Eso ya no es geometria, es segmentacion, y
  no esta.
- Cuando no encaja en ninguna forma pero el residuo esta ahi, se emite "zona
  local" con su caja. Decir "hay algo espacial aqui" sin saber que es sigue
  siendo informacion util; inventarse la etiqueta no lo seria.

EN QUE ORDEN SALEN LAS ZONAS (reescrito el dia 4)
-------------------------------------------------
**De mas a menos MASA**: la suma, sobre los pixeles de la componente, de la
desviacion de ganancia suavizada. O sea area por intensidad media. Y la
`magnitude` de cada zona es el ΔE2000 medio **sobre los pixeles de la
componente**, no sobre su rectangulo.

Hasta el dia 3 las zonas se ordenaban por el PICO del campo de ganancia y
despues `_recortar` las volvia a ordenar por el ΔE2000 medio DEL RECTANGULO.
Los dos son estadisticos de intensidad, y los dos premian lo pequeno y
concentrado. Medido sobre la escena de la medicion independiente (viñeta y
ventana en luz lineal, sombra profunda en una esquina):

- la ventana ocupa 14.418 pixeles de un rectangulo de 26.104 (el 55%), asi que
  su ΔE medio de rectangulo se diluye a 11.38 mientras el de sus pixeles es
  14.93; el cuadrito de la esquina ocupa 731 de 899 y no se diluye (12.73);
- por masa no hay discusion: 3909 contra 142, un factor 27.

La cifra completa, con el comando, en `NOTAS.md` §6.7.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from core.color import delta_e2000
from core.contracts import (
    CDL,
    LUMA_REC709,
    LUT3D,
    WORKING_SPACE,
    ColorSpaceName,
    CoverageMap,
    Hotspot,
    ReverseDiagnosis,
)
from core.umbrales import (
    AREA_MINIMA_HOTSPOT,
    FRACCION_DE_PICO,
    SUELO_GANANCIA_LOCAL,
    UMBRAL_COBERTURA_BAJA,
    UMBRAL_DE_HOTSPOT,
    UMBRAL_DE_PURO,
    UMBRAL_MONOTONIA_RADIAL,
    UMBRAL_MOVIMIENTO_NULO,
    UMBRAL_R2_LINEAL,
    UMBRAL_R2_RADIAL,
    UMBRAL_RECORRIDO_GANANCIA,
    UMBRAL_RECORRIDO_LINEAL,
    UMBRAL_REPRODUCIBLE_PURO,
    UMBRAL_TEXTURA,
)

__all__ = [
    "AREA_MINIMA_HOTSPOT",
    "CORONAS",
    "FRACCION_DE_PICO",
    "MAX_HOTSPOTS",
    "RADIO_MAXIMO_CENTRO",
    "SIGMA_LOCAL",
    "SIGMA_RADIAL",
    "SIGMA_TEXTURA",
    "SUELO_GANANCIA_LOCAL",
    "UMBRAL_DE_HOTSPOT",
    "UMBRAL_DE_PURO",
    "UMBRAL_MONOTONIA_RADIAL",
    "UMBRAL_R2_LINEAL",
    "UMBRAL_R2_RADIAL",
    "UMBRAL_RECORRIDO_GANANCIA",
    "UMBRAL_RECORRIDO_LINEAL",
    "UMBRAL_REPRODUCIBLE_PURO",
    "UMBRAL_TEXTURA",
    "AnalisisEspacial",
    "analizar_espacial",
    "campo_de_ganancia",
    "diagnosticar",
    "mapa_de_residuo",
]

# Los umbrales que deciden un veredicto que Mario lee ("es un LUT puro",
# "esto es una vineta", "esto es textura") viven en `core.umbrales`, que es el
# unico sitio donde se escriben. Aqui se reexportan con el mismo nombre de
# siempre para no romper a quien los importe de este modulo, pero el valor y su
# porque estan alli. Los `SIGMA_*` NO son umbrales: son la escala de suavizado
# con la que se mira cada campo, o sea implementacion de este modulo, y por eso
# se quedan aqui.

#: Sigma de la gaussiana con la que se suaviza el campo de ganancia para buscar
#: la vineta, en **fraccion de `min(alto, ancho)`**. Una vineta es lo mas de
#: baja frecuencia que hay en un fotograma; con menos suavizado, el error del
#: ajuste del LUT (que es de alta frecuencia y sigue al contenido) se cuela en
#: el R2 y lo hunde. Es exactamente el fallo que tenia la version de la noche 1.
SIGMA_RADIAL: float = 0.05

#: Lo mismo para buscar zonas locales. Mas fino que el radial porque una ventana
#: tiene un tamano y hay que respetarlo: con `SIGMA_RADIAL` la caja se hincha.
SIGMA_LOCAL: float = 0.03

#: Y lo mismo para separar la alta de la baja frecuencia del residuo ΔE2000.
SIGMA_TEXTURA: float = 0.02

#: Mas de esto no se ensena: la GUI no cabe y nadie lee doce cajas.
MAX_HOTSPOTS: int = 8

#: Coronas del perfil radial.
CORONAS: int = 24

#: Hasta donde se acepta el centro estimado de la caida radial, en coordenadas
#: donde el borde del fotograma vale 1. **El centro optico de una vineta cae
#: dentro del encuadre**: es por donde pasa el eje de la lente. Si el vertice
#: del ajuste sale fuera, la caida no es radial y se vuelve al centro
#: geometrico, que es donde el R2 dira la verdad en vez de disfrazar de vineta
#: lo que es una ventana. Medido sobre el material de prueba: las vinetas dan
#: un vertice a 0.07-0.39 del centro (tambien las descentradas a mano) y las
#: ventanas a 2.7 y 21.5. La separacion es de un orden de magnitud.
RADIO_MAXIMO_CENTRO: float = 1.0

#: Para no dividir por cero al pasar a logaritmos. En el espacio de trabajo el
#: negro esta en 0, asi que hace falta un suelo; 1e-4 esta unas 11 paradas por
#: debajo del 18% de gris, o sea por debajo de cualquier negro con detalle.
_EPS_LOG: float = 1e-4

#: Las etiquetas que cubren el cuadro entero y describen una FORMA, no una zona.
#: Nunca se descartan al recortar a `MAX_HOTSPOTS`: son el titular.
_ETIQUETAS_DE_FORMA: tuple[str, ...] = ("vineta", "degradado", "textura")


def mapa_de_residuo(
    original: np.ndarray,
    coloreado: np.ndarray,
    cdl: CDL,
    lut: LUT3D,
    *,
    space: ColorSpaceName = WORKING_SPACE,
) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve `(residuo, movimiento)`, los dos en ΔE2000 por pixel `(h, w)`.

    `residuo`   = lo que el grado hace y `LUT(CDL(x))` NO explica.
    `movimiento`= lo que el grado hace, sin mas.
    """
    orig = np.asarray(original, dtype=np.float64)
    col = np.asarray(coloreado, dtype=np.float64)
    pred = lut.apply(cdl.apply(orig))
    residuo = np.asarray(delta_e2000(pred, col, space), dtype=np.float64)
    movimiento = np.asarray(delta_e2000(orig, col, space), dtype=np.float64)
    return residuo, movimiento


def _media_finita(a: np.ndarray) -> float:
    fin = np.isfinite(a)
    return float(a[fin].mean()) if fin.any() else float("nan")


def _suavizar(a: np.ndarray, radio: int) -> np.ndarray:
    """Media movil cuadrada de lado `2·radio+1`.

    Se conserva tal cual porque `tests/auditoria/` la usa para reproducir las
    cifras de la noche 1. El detector de hoy usa gaussianas (`_gaussiana`).
    """
    if radio < 1:
        return a
    return ndimage.uniform_filter(a, size=2 * radio + 1, mode="nearest")


def _gaussiana(a: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0.0:
        return np.asarray(a, dtype=np.float64)
    return ndimage.gaussian_filter(np.asarray(a, dtype=np.float64), sigma=sigma, mode="nearest")


def _sanear(a: np.ndarray, relleno: float = 0.0) -> np.ndarray:
    """Sustituye los no finitos por `relleno` (o por la media de los finitos).

    Un solo NaN envenena una gaussiana entera, asi que hay que quitarlos antes
    de filtrar. Se hace aqui y en un solo sitio.
    """
    arr = np.asarray(a, dtype=np.float64)
    fin = np.isfinite(arr)
    if fin.all():
        return arr
    if relleno == 0.0 and fin.any():
        relleno = float(arr[fin].mean())
    return np.where(fin, arr, relleno)


def _radio_normalizado(h: int, w: int, cx: float = 0.0, cy: float = 0.0) -> np.ndarray:
    """Distancia al punto `(cx, cy)`, en coordenadas donde el borde vale 1.

    `(0, 0)` es el centro geometrico del fotograma; `(1, 1)` la esquina inferior
    derecha. La normalizacion **no** divide por sqrt(2), asi que la esquina de
    una vineta centrada cae en r = sqrt(2) ~ 1.41.
    """
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx - (w - 1) / 2) / max((w - 1) / 2, 1e-9) - cx
    v = (yy - (h - 1) / 2) / max((h - 1) / 2, 1e-9) - cy
    return np.sqrt(u * u + v * v)


def _perfil_por_coronas(
    campo: np.ndarray, r: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(modelo (h,w), perfil (CORONAS,), centros de corona (CORONAS,))."""
    bordes = np.linspace(0.0, float(r.max()) + 1e-9, CORONAS + 1)
    idx = np.clip(np.digitize(r, bordes) - 1, 0, CORONAS - 1)
    plano = idx.ravel()
    val = campo.ravel()
    fin = np.isfinite(val)
    cnt = np.bincount(plano[fin], minlength=CORONAS).astype(np.float64)
    suma = np.bincount(plano[fin], weights=val[fin], minlength=CORONAS)
    perfil = np.divide(suma, np.maximum(cnt, 1.0))
    vacias = cnt == 0
    if vacias.any() and not vacias.all():
        buenas = np.flatnonzero(~vacias)
        perfil[vacias] = np.interp(np.flatnonzero(vacias), buenas, perfil[buenas])
    centros = 0.5 * (bordes[:-1] + bordes[1:])
    return perfil[idx], perfil, centros


def _perfil_radial(res: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Perfil por coronas alrededor del centro **geometrico** del fotograma.

    Se conserva con esta firma porque `tests/auditoria/` reproduce con ella las
    cifras de la noche 1. El detector de hoy usa `_perfil_por_coronas` con el
    centro estimado.
    """
    h, w = res.shape
    return _perfil_por_coronas(res, _radio_normalizado(h, w) / np.sqrt(2.0))


def _r2(res: np.ndarray, modelo: np.ndarray) -> float:
    fin = np.isfinite(res) & np.isfinite(modelo)
    if fin.sum() < 16:
        return 0.0
    y = res[fin]
    m = modelo[fin]
    var = float(((y - y.mean()) ** 2).mean())
    if var <= 1e-12:
        return 0.0
    err = float(((y - m) ** 2).mean())
    return float(np.clip(1.0 - err / var, 0.0, 1.0))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64) - np.mean(a)
    b = np.asarray(b, dtype=np.float64) - np.mean(b)
    den = float(np.sqrt((a @ a) * (b @ b)))
    return float(a @ b / den) if den > 1e-30 else 0.0


def _coordenadas(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    """x, y normalizados a -1..1 con el centro del fotograma en (0, 0)."""
    yy, xx = np.mgrid[0:h, 0:w]
    x = (xx - (w - 1) / 2) / max((w - 1) / 2, 1e-9)
    y = (yy - (h - 1) / 2) / max((h - 1) / 2, 1e-9)
    return x, y


def _modelo_lineal(res: np.ndarray) -> np.ndarray:
    """Ajuste `res ~ a·x + b·y + c` por minimos cuadrados, evaluado en todo."""
    h, w = res.shape
    x, y = _coordenadas(h, w)
    yv = res.ravel()
    fin = np.isfinite(yv)
    if fin.sum() < 16:
        return np.zeros_like(res)
    base = np.stack([x.ravel(), y.ravel(), np.ones(yv.size)], axis=1)
    sol, *_ = np.linalg.lstsq(base[fin], yv[fin], rcond=None)
    return (base @ sol).reshape(h, w)


def _centro_de_la_caida(g: np.ndarray) -> tuple[float, float]:
    """Centro de la caida radial, ajustando `g ~ c0 + c1·x + c2·y + c3·(x²+y²)`.

    El vertice de esa cuadratica isotropa es `(-c1/2c3, -c2/2c3)`, y es el mejor
    centro en minimos cuadrados si la caida es de verdad radial.

    **Si el vertice sale fuera del encuadre se devuelve el centro geometrico**,
    y no es un detalle: estimar el centro sin esta condicion le da al detector
    la libertad de poner el origen en la esquina opuesta a una ventana y hacer
    que la ventana parezca una vineta. Medido: con el vertice libre, una ventana
    sola sube de R2=0.034 a R2=0.367 y se queda a un pelo de la puerta. Con la
    condicion vuelve a 0.034, y las vinetas descentradas se siguen detectando,
    que era para lo que se estimaba el centro.
    """
    h, w = g.shape
    x, y = _coordenadas(h, w)
    gv = _sanear(g).ravel()
    base = np.stack([np.ones(gv.size), x.ravel(), y.ravel(), (x * x + y * y).ravel()], axis=1)
    sol, *_ = np.linalg.lstsq(base, gv, rcond=None)
    _, c1, c2, c3 = sol
    if abs(c3) < 1e-9:
        return 0.0, 0.0
    cx = -c1 / (2 * c3)
    cy = -c2 / (2 * c3)
    if not np.isfinite(cx) or not np.isfinite(cy):
        return 0.0, 0.0
    if float(np.hypot(cx, cy)) > RADIO_MAXIMO_CENTRO:
        return 0.0, 0.0
    return float(cx), float(cy)


@dataclass(frozen=True)
class _Zona:
    """Una componente conexa del campo de fuerza local, ya medida."""

    caja: tuple[int, int, int, int]
    #: Suma de la fuerza (logaritmo de ganancia) sobre los pixeles de la
    #: componente: area por intensidad media. Es lo que ordena.
    masa: float
    #: ΔE2000 medio sobre los pixeles de la componente (no del rectangulo).
    residuo_medio: float


def _zonas(campo: np.ndarray, umbral: float, residuo: np.ndarray) -> list[_Zona]:
    """Las componentes de `campo > umbral`, medidas y ordenadas por masa.

    **Por que masa y no pico.** El pico premia lo pequeno y concentrado, y lo
    pequeno y concentrado es justo lo que fabrican los artefactos: la huella que
    deja el LUT en los colores oscuros que comparte con la ventana, o el borde
    de una sombra profunda, donde el logaritmo de valores codificados amplifica
    cualquier diferencia. Una ventana es grande y coherente, y eso no lo fabrica
    un artefacto local.

    **Por que el ΔE de la componente y no el del rectangulo.** Un rectangulo que
    envuelve una forma irregular se llena de pixeles que no son la zona, y la
    media se diluye tanto mas cuanto mas grande y menos rectangular es la
    forma. Una zona pequena y cuadrada no se diluye. Promediar sobre el
    rectangulo es otra forma de premiar lo pequeno.
    """
    h, w = campo.shape
    marcado = np.isfinite(campo) & (campo > umbral)
    if not marcado.any():
        return []
    etiquetas, cuantas = ndimage.label(marcado)
    area_min = max(int(AREA_MINIMA_HOTSPOT * h * w), 4)
    res = np.asarray(residuo, dtype=np.float64)
    fuera: list[_Zona] = []
    for rebanada, k in zip(ndimage.find_objects(etiquetas), range(1, cuantas + 1), strict=True):
        if rebanada is None:
            continue
        trozo = etiquetas[rebanada] == k
        if int(trozo.sum()) < area_min:
            continue
        sy, sx = rebanada
        dentro = res[rebanada][trozo]
        finitos = np.isfinite(dentro)
        fuera.append(
            _Zona(
                caja=(
                    int(sx.start), int(sy.start), int(sx.stop - sx.start), int(sy.stop - sy.start)
                ),
                masa=float(np.nansum(campo[rebanada][trozo])),
                residuo_medio=float(dentro[finitos].mean()) if finitos.any() else float("nan"),
            )
        )
    # Desempate fijo por posicion: el orden no puede depender de como numera
    # `ndimage.label` si dos masas empatan al ultimo bit.
    fuera.sort(key=lambda z: (-z.masa, z.caja))
    return fuera


def campo_de_ganancia(prediccion: np.ndarray, coloreado: np.ndarray) -> np.ndarray:
    """`log(coloreado + eps) - log(prediccion + eps)`, por canal, `(h, w, 3)`.

    **Es el campo donde se ve la geometria del grado.** Un efecto multiplicativo
    (una vineta, una ventana de ganancia, un degradado de exposicion) es
    constante aqui a igualdad de posicion, **haya lo que haya en la imagen**.
    En ΔE2000 no lo es: el ΔE que produce una misma ganancia depende del brillo
    y del color del pixel, y esa dependencia del contenido es justo el ruido que
    hundia el R2 radial de la version anterior.
    """
    p = np.maximum(np.asarray(prediccion, dtype=np.float64), 0.0) + _EPS_LOG
    c = np.maximum(np.asarray(coloreado, dtype=np.float64), 0.0) + _EPS_LOG
    return _sanear(np.log(c) - np.log(p), relleno=0.0)


@dataclass(frozen=True)
class AnalisisEspacial:
    """Lo que miden las cuatro pruebas, antes de convertirlo en `Hotspot`.

    Existe para poder **medir el detector** en un test y para poder poner la
    tabla de separacion en `NOTAS.md` sin tener que reconstruirla a mano. Es de
    `core.reverse` y no de `core.contracts`: no cruza ninguna frontera entre
    modulos, solo sale de aqui hacia los tests.

    Todos los campos de ganancia estan en **logaritmo natural**: 0.12 son unas
    0.17 paradas de luz.
    """

    #: Recorrido del perfil radial del logaritmo de la ganancia de luma.
    recorrido_ganancia: float
    #: Fraccion de la varianza del campo de ganancia que explica el perfil.
    r2_radial: float
    #: Pearson del perfil contra el radio. **Negativo = oscurece hacia fuera.**
    pearson_radial: float
    #: Centro estimado de la caida, en pixeles `(x, y)` del fotograma.
    centro: tuple[float, float]
    hay_vineta: bool
    #: Recorrido y R2 del plano inclinado ajustado a lo que queda.
    recorrido_lineal: float
    r2_lineal: float
    hay_degradado: bool
    #: Desviacion tipica del residuo de ALTA frecuencia, en ΔE2000.
    textura: float
    hay_textura: bool
    #: Pico (percentil 99.5) del campo de residuo de ganancia por canal.
    pico_local: float
    #: Umbral efectivo con el que se han recortado las zonas.
    umbral_local: float
    #: Cajas `(x, y, w, h)` de las zonas locales, de MAS A MENOS MASA (dia 4;
    #: antes, de mas a menos pico).
    zonas: tuple[tuple[int, int, int, int], ...]
    #: Masa de cada zona, en el mismo orden: suma de la fuerza local (logaritmo
    #: de ganancia) sobre sus pixeles, o sea `pixeles x logaritmo`.
    masas: tuple[float, ...] = ()
    #: ΔE2000 medio sobre los PIXELES de cada zona, en el mismo orden. Es lo que
    #: sale como `Hotspot.magnitude`.
    residuos_zonas: tuple[float, ...] = ()


def analizar_espacial(
    residuo: np.ndarray, prediccion: np.ndarray, coloreado: np.ndarray
) -> AnalisisEspacial:
    """Las cuatro pruebas, en el orden que manda: primero la forma global.

    `residuo` es el ΔE2000 por pixel `(h, w)`; `prediccion` es
    `LUT(CDL(original))` y `coloreado` el plano de verdad, los dos `(h, w, 3)`.

    **El orden importa**: se ajusta el modelo radial, se resta, y las zonas
    locales se buscan en lo que queda. Sin restar, la vineta se funde con la
    ventana de una esquina y sale un unico manchurron que no es ninguna de las
    dos cosas.
    """
    res = np.asarray(residuo, dtype=np.float64)
    h, w = res.shape
    lado = float(min(h, w))

    # --- el campo de ganancia, en dos escalas ---
    ganancia = campo_de_ganancia(prediccion, coloreado)
    luma_pred = np.maximum(np.asarray(prediccion, dtype=np.float64) @ LUMA_REC709, 0.0)
    luma_col = np.maximum(np.asarray(coloreado, dtype=np.float64) @ LUMA_REC709, 0.0)
    g_luma = _sanear(np.log(luma_col + _EPS_LOG) - np.log(luma_pred + _EPS_LOG))
    g_gruesa = _gaussiana(g_luma, SIGMA_RADIAL * lado)

    # --- 1. vineta: baja frecuencia radial sobre el campo de ganancia ---
    cx, cy = _centro_de_la_caida(g_gruesa)
    r = _radio_normalizado(h, w, cx, cy)
    modelo_radial, perfil, centros = _perfil_por_coronas(g_gruesa, r)
    r2_radial = _r2(g_gruesa, modelo_radial)
    pearson_radial = _pearson(perfil, centros)
    recorrido_g = float(perfil.max() - perfil.min())
    hay_vineta = (
        recorrido_g >= UMBRAL_RECORRIDO_GANANCIA
        and r2_radial >= UMBRAL_R2_RADIAL
        and abs(pearson_radial) >= UMBRAL_MONOTONIA_RADIAL
    )

    # --- 2. degradado: plano inclinado sobre lo que queda ---
    resto_grueso = g_gruesa - modelo_radial if hay_vineta else g_gruesa
    modelo_lin = _modelo_lineal(resto_grueso)
    r2_lineal = _r2(resto_grueso, modelo_lin)
    recorrido_lineal = float(np.nanmax(modelo_lin) - np.nanmin(modelo_lin))
    hay_degradado = r2_lineal >= UMBRAL_R2_LINEAL and recorrido_lineal >= UMBRAL_RECORRIDO_LINEAL

    # --- 3. textura: alta frecuencia del ΔE2000 ---
    res_sano = _sanear(res)
    alta = res_sano - _gaussiana(res_sano, SIGMA_TEXTURA * lado)
    textura = float(alta.std())
    hay_textura = textura >= UMBRAL_TEXTURA

    # --- 4. zonas locales: baja frecuencia compacta, por canal ---
    fina = np.stack(
        [_gaussiana(ganancia[..., c], SIGMA_LOCAL * lado) for c in range(3)], axis=-1
    )
    if hay_vineta:
        fina = np.stack(
            [fina[..., c] - _perfil_por_coronas(fina[..., c], r)[0] for c in range(3)], axis=-1
        )
    else:
        fina = fina - fina.reshape(-1, 3).mean(axis=0)
    fuerza = np.linalg.norm(fina, axis=-1)
    mediana = float(np.percentile(fuerza, 50))
    pico = float(np.percentile(fuerza, 99.5))
    umbral_local = max(SUELO_GANANCIA_LOCAL, mediana + FRACCION_DE_PICO * (pico - mediana))
    zonas = _zonas(fuerza, umbral_local, res)

    return AnalisisEspacial(
        recorrido_ganancia=recorrido_g,
        r2_radial=r2_radial,
        pearson_radial=pearson_radial,
        centro=(
            float((cx + 1.0) * (w - 1) / 2.0),
            float((cy + 1.0) * (h - 1) / 2.0),
        ),
        hay_vineta=hay_vineta,
        recorrido_lineal=recorrido_lineal,
        r2_lineal=r2_lineal,
        hay_degradado=hay_degradado,
        textura=textura,
        hay_textura=hay_textura,
        pico_local=pico,
        umbral_local=umbral_local,
        zonas=tuple(z.caja for z in zonas),
        masas=tuple(z.masa for z in zonas),
        residuos_zonas=tuple(z.residuo_medio for z in zonas),
    )


def _recortar(hotspots: list[Hotspot]) -> list[Hotspot]:
    """A `MAX_HOTSPOTS`, sin tirar nunca una etiqueta de forma.

    Si se ordena todo por magnitud y se corta, una vineta de 3 dE2000 se queda
    fuera por culpa de ocho esquinas de 9 dE2000 que son **esa misma vineta**.
    El titular no se pierde por el detalle.

    **Las zonas NO se reordenan aqui** (dia 4). Llegan ordenadas por masa desde
    `analizar_espacial`, y ese es el orden en que la GUI las lista y por el que
    se corta. Hasta el dia 3 se reordenaban aqui por `magnitude`, que era el
    ΔE2000 medio del rectangulo, y eso ponia primero un cuadrito de 31x29 px en
    una esquina en sombra por delante de la ventana de verdad.
    """
    formas = [hp for hp in hotspots if hp.label in _ETIQUETAS_DE_FORMA]
    resto = [hp for hp in hotspots if hp.label not in _ETIQUETAS_DE_FORMA]
    hueco = max(MAX_HOTSPOTS - len(formas), 0)
    return formas + resto[:hueco]


def diagnosticar(
    original: np.ndarray,
    coloreado: np.ndarray,
    cdl: CDL,
    lut: LUT3D,
    cobertura: CoverageMap,
    *,
    space: ColorSpaceName = WORKING_SPACE,
) -> ReverseDiagnosis:
    """¿Cuanto de este grado cabe en un `.cube`, y que se queda fuera?

    `original` y `coloreado` tienen que venir **ya alineados** (misma forma).
    `cobertura` no cambia el diagnostico geometrico: entra para poder avisar de
    que un residuo alto puede ser falta de cobertura y no algo espacial, que son
    dos enfermedades distintas con el mismo sintoma.
    """
    orig = np.asarray(original, dtype=np.float64)
    col = np.asarray(coloreado, dtype=np.float64)
    prediccion = lut.apply(cdl.apply(orig))
    residuo = np.asarray(delta_e2000(prediccion, col, space), dtype=np.float64)
    movimiento = np.asarray(delta_e2000(orig, col, space), dtype=np.float64)
    h, w = residuo.shape
    notas: list[str] = []

    res_medio = _media_finita(residuo)
    mov_medio = _media_finita(movimiento)
    finitos = np.isfinite(residuo)
    res_p95 = float(np.percentile(residuo[finitos], 95)) if finitos.any() else float("nan")
    res_max = float(residuo[finitos].max()) if finitos.any() else float("nan")

    if not np.isfinite(res_medio) or not np.isfinite(mov_medio):
        reproducible = 0.0
        notas.append(
            "Hay pixeles no finitos (NaN o infinito) en la pareja; el diagnostico solo mira "
            "los finitos y la fraccion reproducible no es de fiar."
        )
    elif mov_medio < UMBRAL_MOVIMIENTO_NULO:
        # El grado no mueve el color: no hay fraccion que calcular.
        reproducible = 1.0 if res_medio < UMBRAL_MOVIMIENTO_NULO else 0.0
        notas.append(
            f"El coloreado apenas se mueve respecto al original ({mov_medio:.3f} dE2000 de media). "
            f"Esto no es un grado, es el mismo plano."
        )
    else:
        reproducible = float(np.clip(1.0 - res_medio / mov_medio, 0.0, 1.0))

    if not finitos.any():
        return ReverseDiagnosis(
            lut_reproducible=0.0,
            is_pure_lut=False,
            spatial_residual=None,
            hotspots=(),
            notes=(*notas, "No queda ni un pixel finito que mirar."),
        )

    analisis = analizar_espacial(residuo, prediccion, col)
    hotspots: list[Hotspot] = []

    if analisis.hay_vineta:
        sentido = "oscurece" if analisis.pearson_radial < 0 else "aclara"
        cx, cy = analisis.centro
        # La caja cubre el fotograma entero a proposito: una vineta no tiene una
        # "zona", tiene una forma. El centro estimado va en la nota, que es
        # donde se puede decir en castellano y con sus unidades.
        hotspots.append(
            Hotspot(x=0, y=0, w=w, h=h, magnitude=float(_media_finita(residuo)), label="vineta")
        )
        notas.append(
            f"La ganancia que le falta al LUT depende del RADIO y {sentido} hacia fuera "
            f"({analisis.recorrido_ganancia:.3f} en logaritmo de ganancia del centro al borde, "
            f"o sea {analisis.recorrido_ganancia / np.log(2):.2f} paradas; "
            f"R2={analisis.r2_radial:.2f}, correlacion con el radio "
            f"{analisis.pearson_radial:+.2f}). Eso es una vineta, con el centro estimado en "
            f"({cx:.0f}, {cy:.0f}) px, y una vineta NO cabe en un LUT."
        )

    if analisis.hay_degradado:
        hotspots.append(
            Hotspot(
                x=0, y=0, w=w, h=h,
                magnitude=float(_media_finita(residuo)),
                label="degradado",
            )
        )
        notas.append(
            f"Lo que queda de la ganancia crece en linea recta de un lado a otro del fotograma "
            f"({analisis.recorrido_lineal:.3f} en logaritmo, R2={analisis.r2_lineal:.2f}): "
            f"parece un degradado, y un degradado tampoco cabe en un LUT."
        )

    if analisis.hay_textura:
        hotspots.append(
            Hotspot(
                x=0, y=0, w=w, h=h,
                magnitude=float(_media_finita(residuo)),
                label="textura",
            )
        )
        notas.append(
            f"El residuo que queda es de ALTA frecuencia ({analisis.textura:.2f} dE2000 de "
            f"desviacion tipica una vez quitada la parte suave): eso es grano, enfoque, "
            f"reduccion de ruido o halacion. No es una zona del cuadro y no es un LUT; es "
            f"textura, y se recupera volviendo a rodar o volviendo a revelar, no con un .cube."
        )

    for (x, y, cw, ch), real in zip(analisis.zonas, analisis.residuos_zonas, strict=True):
        # La magnitud se reporta sobre el residuo ΔE2000 TOTAL: al usuario le
        # importa cuanto se desvia ahi de verdad, no cuanto vale el campo
        # intermedio con el que yo he decidido buscarla. Y se promedia sobre
        # los pixeles de la zona, no sobre su rectangulo (ver `_zonas`).
        hotspots.append(Hotspot(x=x, y=y, w=cw, h=ch, magnitude=real, label="zona local"))
    if analisis.zonas:
        notas.append(
            f"Hay {len(analisis.zonas)} zona(s) del fotograma donde la ganancia se desvia de lo "
            f"que el color explica por encima de {analisis.umbral_local:.3f} en logaritmo (pico "
            f"{analisis.pico_local:.3f}): pinta de ventana o de secundaria. Van de mas a menos "
            f"extension por intensidad: la primera es la que mas imagen cambia, no la que tiene "
            f"el pixel mas fuerte."
        )
        if analisis.hay_vineta:
            notas.append(
                "OJO con esas zonas: con una vineta encima, parte de ellas son la propia vineta. "
                "El LUT absorbe la vineta de forma dependiente del color y lo que sobra se "
                "amontona en las esquinas. La forma (la vineta) es el titular; las cajas, el "
                "detalle."
            )

    hotspots = _recortar(hotspots)

    puro = (
        not hotspots
        and np.isfinite(res_p95)
        and res_p95 <= UMBRAL_DE_PURO
        and reproducible >= UMBRAL_REPRODUCIBLE_PURO
    )
    if puro:
        notas.insert(
            0,
            f"Este grado SI es un LUT: el 95% del fotograma cae por debajo de {res_p95:.2f} dE2000 "
            f"de error y me llevo el {reproducible * 100:.1f}% del movimiento de color.",
        )
    else:
        notas.insert(
            0,
            f"Me llevo el {reproducible * 100:.1f}% del grado en un .cube. Lo que queda: "
            f"{res_medio:.2f} dE2000 de media, {res_p95:.2f} en el percentil 95 y {res_max:.2f} "
            f"en el peor pixel.",
        )

    fraccion = cobertura.coverage_fraction()
    if fraccion < UMBRAL_COBERTURA_BAJA and not puro:
        notas.append(
            f"Ojo: el plano solo cubre el {fraccion * 100:.2f}% de las celdas del cubo. Parte del "
            f"residuo puede ser falta de datos y no algo espacial."
        )

    # `spatial_residual` va NORMALIZADO 0..1 dividiendo por el maximo, porque es
    # un mapa para pintar. La magnitud en dE2000 vive en `Hotspot.magnitude` y en
    # la primera nota; asi no hay dos sitios donde mirar el mismo numero.
    tope = res_max if np.isfinite(res_max) and res_max > 1e-9 else 1.0
    mapa = (residuo / tope).astype(np.float32)
    notas.append(f"`spatial_residual` esta normalizado: 1.0 equivale a {tope:.2f} dE2000.")

    return ReverseDiagnosis(
        lut_reproducible=float(reproducible),
        is_pure_lut=bool(puro),
        spatial_residual=mapa,
        hotspots=tuple(hotspots),
        notes=tuple(notas),
    )
