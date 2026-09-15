"""Huella de contenido: 96 numeros que dicen DE QUE VA el plano.

El objetivo, y es exigente: la huella tiene que decir "esto es un retrato de
estudio" y **no** decir "esto esta graduado en frio". Si cambiara al aplicar un
grado no serviria para nada, porque para lo que la usa el agente C es
precisamente para avisar de que dos planos no son comparables **antes** de
intentar igualarlos.

DE QUE ESTA HECHA (96 = 64 + 16 + 16)
-------------------------------------
Las tres piezas son **de rango (rank)** o de orientacion, nunca de valor. Ese es
el truco entero: el rango de una celda dentro de la imagen no cambia si le
aplicas una funcion monotona creciente, y un grado es, en lo esencial, una
funcion monotona por canal. Un CDL con el mismo slope/power en los tres canales
no altera **ni un rango**; la saturacion del CDL no altera la luma **en
absoluto** (la formula es `luma + s*(x - luma)` con los mismos pesos Rec.709,
asi que la luma sale identica); y un LUT de look, mientras sea monotono, apenas
los mueve.

1. **64 = rejilla 8x8 de luma.** Se parte la imagen en 8x8 celdas, se promedia la
   luma de cada una y se guarda su RANGO normalizado a 0..1 menos 0.5. Es "donde
   estan las zonas claras y las oscuras", o sea la composicion del plano.
2. **16 = histograma de orientacion del gradiente** de la luma (16 sectores de 0
   a 180 grados), contando solo los pixeles cuya magnitud de gradiente esta por
   encima de la mediana. Distingue un horizonte (todo horizontal) de una cara
   (orientaciones repartidas). La orientacion de un gradiente no cambia al pasar
   la imagen por una curva monotona; la magnitud si, por eso el umbral es la
   mediana (un rango, otra vez) y no un numero fijo.
3. **16 = rejilla 4x4 de densidad de detalle**: que fraccion de cada celda tiene
   gradiente fuerte, otra vez por rangos. Dice DONDE esta el detalle: en un
   retrato esta concentrado en la cara; en un exterior, en la linea del horizonte
   y en el camino.

**NO hay ningun descriptor de color, y es a proposito.** La primera version tenia
un cuarto bloque con la distribucion espacial de la saturacion. Medido: bajo un
CDL fuerte ese bloque daba coseno 0,63 consigo mismo, y bajo un LUT de look
**-0,15**. O sea que no describia el plano: describia el grado. Se cayo entero.
Los numeros estan en NOTAS.md §3.

CADA BLOQUE VA CENTRADO EN CERO. Sin centrar, todo vector de numeros positivos
se parece a todo (dos imagenes cualesquiera darian coseno ~0,9 y la huella no
separaria nada). Centrado, dos planos sin relacion dan coseno alrededor de 0.

PESOS: 55% de la energia a la composicion, 25% a la orientacion, 20% a la
densidad de detalle. La composicion es lo que mas separa un estudio de un
exterior; las otras dos afinan.

CASO DEGENERADO: una imagen plana (un solo color, un solo pixel, negro entero)
no tiene ni composicion, ni gradientes, ni detalle. Su huella es el vector
uniforme `1/sqrt(96)`: todas las imagenes planas se parecen entre si (que es
verdad) y se parecen cero a cualquier plano real (porque los bloques de un plano
real suman cero). Sin este caso especial la norma L2 seria 0 y se incumpliria el
contrato, que exige norma 1.

NaN: es lo UNICO del modulo que no propaga NaN, y es a proposito. El contrato
exige norma L2 = 1 y un NaN la haria imposible. Los pixeles no finitos se
sustituyen por la mediana de los finitos antes de calcular nada. El NaN no se
pierde de vista: `ColorStats` si lo propaga (media, desviacion, covarianza y
percentiles salen NaN) y `analizar_imagen`/`analizar_clip` dejan un aviso.
"""

from __future__ import annotations

import numpy as np

from core.color import convert
from core.contracts import FINGERPRINT_LEN, LUMA_REC709, WORKING_SPACE, ColorSpaceName

#: Lado de la rejilla de composicion (8x8 = 64 numeros).
REJILLA_LUMA: int = 8

#: Sectores del histograma de orientacion (0..180 grados).
BINS_ORIENTACION: int = 16

#: Lado de la rejilla de densidad de detalle (4x4 = 16 numeros).
REJILLA_DETALLE: int = 4

#: Lado al que se remuestrea la luma para calcular gradientes. Fijo, para que la
#: huella de un 4K y la del mismo plano en HD sean comparables.
LADO_GRADIENTE: int = 64

#: Reparto de energia entre los tres bloques. Suma 1.
PESOS: tuple[float, float, float] = (0.55, 0.25, 0.20)

_TAMANOS = (REJILLA_LUMA**2, BINS_ORIENTACION, REJILLA_DETALLE**2)
if sum(_TAMANOS) != FINGERPRINT_LEN:  # pragma: no cover - red de seguridad
    raise AssertionError(f"la huella suma {sum(_TAMANOS)} y el contrato pide {FINGERPRINT_LEN}")


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------


def _imagen_valida(img: np.ndarray, quien: str) -> np.ndarray:
    arr = np.asarray(img, dtype=np.float64)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"{quien}: esperaba (alto, ancho, 3), llego {np.shape(img)}")
    if arr.shape[0] < 1 or arr.shape[1] < 1:
        raise ValueError(f"{quien}: la imagen no tiene ni un pixel (forma {arr.shape})")
    return arr


def _sanear(x: np.ndarray) -> np.ndarray:
    """Sustituye lo no finito por la mediana de lo finito (0.0 si no hay nada)."""
    finito = np.isfinite(x)
    if bool(finito.all()):
        return x
    relleno = float(np.median(x[finito])) if bool(finito.any()) else 0.0
    return np.where(finito, x, relleno)


def _malla(x: np.ndarray, filas: int, cols: int) -> np.ndarray:
    """Media de `x` (alto, ancho) por celda de una rejilla `filas` x `cols`.

    Las celdas que se quedan sin ningun pixel (imagenes mas pequenas que la
    rejilla) se rellenan con la media global: asi no se inventan estructura.
    """
    alto, ancho = x.shape
    fi = np.minimum(np.arange(alto) * filas // alto, filas - 1)
    ci = np.minimum(np.arange(ancho) * cols // ancho, cols - 1)
    plano = (fi[:, None] * cols + ci[None, :]).ravel()
    suma = np.bincount(plano, weights=x.ravel(), minlength=filas * cols)
    cuenta = np.bincount(plano, minlength=filas * cols)
    global_ = float(x.mean())
    with np.errstate(invalid="ignore", divide="ignore"):
        medias = np.where(cuenta > 0, suma / np.maximum(cuenta, 1), global_)
    return medias.reshape(filas, cols)


def _rangos_centrados(v: np.ndarray) -> np.ndarray:
    """Rangos normalizados a 0..1 menos 0.5. Los empates reparten el rango medio.

    Con todos los valores iguales salen todos 0.5 y, centrados, cero: es la forma
    de decir "aqui no hay estructura" sin inventarse una.
    """
    plano = np.asarray(v, dtype=np.float64).ravel()
    n = plano.size
    if n < 2:
        return np.zeros(n, dtype=np.float64)
    orden = np.argsort(plano, kind="stable")
    rangos = np.empty(n, dtype=np.float64)
    rangos[orden] = np.arange(n, dtype=np.float64)
    ordenados = plano[orden]
    i = 0
    while i < n:  # empates: rango medio del grupo
        j = i + 1
        while j < n and ordenados[j] == ordenados[i]:
            j += 1
        if j - i > 1:
            rangos[orden[i:j]] = (i + j - 1) / 2.0
        i = j
    return rangos / (n - 1) - 0.5


def _gradiente(luma: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(gy, gx, magnitud) de la luma remuestreada a LADO_GRADIENTE x LADO_GRADIENTE."""
    pequena = _malla(luma, LADO_GRADIENTE, LADO_GRADIENTE)
    gy, gx = np.gradient(pequena)
    return gy, gx, np.hypot(gx, gy)


def _bloque_luma(luma: np.ndarray) -> np.ndarray:
    return _rangos_centrados(_malla(luma, REJILLA_LUMA, REJILLA_LUMA))


def _bloque_orientacion(gy: np.ndarray, gx: np.ndarray, fuerte: np.ndarray) -> np.ndarray:
    if not bool(fuerte.any()):
        return np.zeros(BINS_ORIENTACION, dtype=np.float64)
    angulo = np.arctan2(gy, gx) % np.pi  # 0..pi: una linea no tiene sentido
    idx = np.minimum((angulo / np.pi * BINS_ORIENTACION).astype(np.int64), BINS_ORIENTACION - 1)
    hist = np.bincount(idx[fuerte], minlength=BINS_ORIENTACION).astype(np.float64)
    return hist / hist.sum() - 1.0 / BINS_ORIENTACION


def _bloque_detalle(fuerte: np.ndarray) -> np.ndarray:
    densidad = _malla(fuerte.astype(np.float64), REJILLA_DETALLE, REJILLA_DETALLE)
    return _rangos_centrados(densidad)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def huella_de_contenido(img: np.ndarray, *, space: ColorSpaceName = WORKING_SPACE) -> np.ndarray:
    """(FINGERPRINT_LEN,) float32 con norma L2 = 1. Ver el docstring del modulo."""
    arr = _imagen_valida(img, "huella_de_contenido")
    if space != WORKING_SPACE:
        arr = np.asarray(convert(arr, space, WORKING_SPACE), dtype=np.float64)

    luma = _sanear(arr @ LUMA_REC709)
    gy, gx, magnitud = _gradiente(luma)
    fuerte = magnitud > float(np.median(magnitud))
    bloques = (
        _bloque_luma(luma),
        _bloque_orientacion(gy, gx, fuerte),
        _bloque_detalle(fuerte),
    )

    partes = []
    for bloque, peso in zip(bloques, PESOS, strict=True):
        norma = float(np.linalg.norm(bloque))
        partes.append(bloque * (np.sqrt(peso) / norma) if norma > 0.0 else bloque * 0.0)
    v = np.concatenate(partes)

    norma = float(np.linalg.norm(v))
    if norma <= 0.0:
        # Imagen plana: no hay contenido que describir. Ver el docstring.
        v = np.full(FINGERPRINT_LEN, 1.0 / np.sqrt(FINGERPRINT_LEN), dtype=np.float64)
    else:
        v = v / norma
    return v.astype(np.float32)


def parecido_de_huellas(a: np.ndarray, b: np.ndarray) -> float:
    """0..1 entre dos huellas. 1 = identicas, 0 = no tienen nada que ver.

    Es el coseno entre los dos vectores, recortado por abajo a 0. Como los tres
    bloques van centrados en cero, dos planos sin relacion dan coseno alrededor
    de 0, y a veces negativo — que para esto significa lo mismo: no son
    comparables. Recortar en vez de reescalar a 0..1 es deliberado: asi el umbral
    que use el agente C significa "se parecen tanto por ciento", y no "estan
    tanto por ciento por encima de lo que se parecerian dos planos al azar".
    """
    va = np.asarray(a, dtype=np.float64).ravel()
    vb = np.asarray(b, dtype=np.float64).ravel()
    for v, nombre in ((va, "a"), (vb, "b")):
        if v.shape != (FINGERPRINT_LEN,):
            raise ValueError(
                f"parecido_de_huellas: la huella {nombre} tiene que ser "
                f"({FINGERPRINT_LEN},), llego {v.shape}"
            )
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na <= 0.0 or nb <= 0.0 or not np.isfinite(na) or not np.isfinite(nb):
        return 0.0
    return float(np.clip(np.dot(va, vb) / (na * nb), 0.0, 1.0))


__all__ = [
    "BINS_ORIENTACION",
    "LADO_GRADIENTE",
    "PESOS",
    "REJILLA_DETALLE",
    "REJILLA_LUMA",
    "huella_de_contenido",
    "parecido_de_huellas",
]
