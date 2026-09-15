"""`ColorStats` y el analisis de un clip o de una imagen.

Todo lo que sale de aqui esta en `WORKING_SPACE` y en float64, salvo
`skin_locus`, que va en Oklab (lo dice el contrato, y es donde el locus de
pieles tiene sentido geometrico).

LAS CUATRO DECISIONES QUE HAY QUE CONOCER ANTES DE USAR ESTO
------------------------------------------------------------
1. **Punto negro y punto blanco son los percentiles 1 y 99**, no el minimo y el
   maximo. Un pixel muerto no puede decidir el punto negro de un plano.
2. **Saturacion = `(max - min) / max`** por pixel (la de HSV), sobre los valores
   del espacio de trabajo. 64 bins uniformes en 0..1 y el histograma suma 1.
3. **Covarianza degenerada**: con menos de 2 pixeles sale la matriz de ceros, no
   NaN. Con 2 o mas se usa la covarianza muestral (ddof=1), que con una imagen
   de un solo color da ceros exactos sin dividir por cero.
4. **NaN se propaga**, como en `core.color`: media, desviacion, covarianza y
   percentiles salen NaN si hay un solo pixel roto. La unica excepcion es el
   histograma de saturacion, que cuenta solo pixeles finitos (si no, no podria
   sumar 1) — y el aviso de que hay NaN se deja escrito en `ClipAnalysis`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.color import convert, rgb_to_oklab, skin_mask_oklab
from core.contracts import (
    PERCENTILE_LEVELS,
    SAT_BINS,
    WORKING_SPACE,
    ClipAnalysis,
    ColorSpaceName,
    ColorStats,
)

from .fingerprint import huella_de_contenido
from .frames import N_FOTOGRAMAS_POR_DEFECTO, extraer_fotogramas_con_avisos

#: Percentil que hace de punto negro. El 1 y no el 0.1: en un HD hay 2 millones
#: de pixeles, asi que el 0.1 todavia lo deciden 2.000 pixeles y un grupo de
#: pixeles muertos o un poco de grano negro caben de sobra ahi. Con el 1 hacen
#: falta 20.000 pixeles para mover el numero, que ya es una zona de la imagen.
PERCENTIL_NEGRO: float = 1.0

#: Y el 99 para el blanco, por simetria. El 99.9 se lo lleva un especular: en
#: `studio_scene` el brillo de la frente se sale a 2.4 y ocupa el 0.1% justo.
PERCENTIL_BLANCO: float = 99.0

#: Cuanta piel hace falta para fiarse del locus: 0.5% de los pixeles Y al menos
#: 64 pixeles. Lo primero es para que un plano general no se guie por una cara
#: de 20 pixeles; lo segundo para que en una miniatura pequena no baste con dos.
FRACCION_PIEL_MINIMA: float = 0.005
PIXELES_PIEL_MINIMOS: int = 64

#: Tope de pixeles que entran en la estadistica de un clip entero. 12 fotogramas
#: de 4K son 100 millones de pixeles y en float64 no caben en memoria; con 2
#: millones de muestras el error tipico de la media ya esta en el quinto decimal.
MAX_PIXELES_ESTADISTICA: int = 2_000_000

#: Muestra de pixeles que se guarda en `ClipAnalysis.pixels` si se pide.
MAX_PIXELES_POR_DEFECTO: int = 200_000

#: Semilla del submuestreo. Fija: dos analisis del mismo clip dan lo mismo.
SEMILLA_MUESTREO: int = 20260915


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def saturacion_hsv(img: np.ndarray) -> np.ndarray:
    """(...,) saturacion 0..1 de cada pixel: `(max - min) / max`.

    Es la saturacion de HSV calculada sobre los valores del ESPACIO DE TRABAJO.
    Un neutro da 0 y un primario puro da 1. Los pixeles con maximo <= 0 (negro,
    o negativos de fuera de gamut) dan 0: sin luz no hay saturacion que medir.
    Un pixel no finito sale NaN, y el histograma lo descarta.

    Por que esta y no otra (ver NOTAS.md §2): es acotada en 0..1 sin recortar
    nada, aguanta los valores fuera de rango que manda el contrato 1, y no
    necesita pasar por Oklab, que es 20 veces mas caro y ademas dejaria el
    histograma fuera de `WORKING_SPACE`, que es donde el contrato lo quiere.
    """
    arr = np.asarray(img, dtype=np.float64)
    maximo = arr.max(axis=-1)
    minimo = arr.min(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = (maximo - minimo) / np.where(maximo > 0.0, maximo, np.inf)
        return np.clip(s, 0.0, 1.0)



def _como_imagen_y_pixeles(datos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Acepta (alto, ancho, 3), (N, 3) o (k, alto, ancho, 3).

    Devuelve (imagen 2D para la mascara de piel, lista de pixeles (N, 3)). Una
    lista de pixeles se presenta como una imagen de una fila: a
    `skin_mask_oklab` le vale y el resultado es el mismo.
    """
    arr = np.asarray(datos, dtype=np.float64)
    if arr.ndim < 2 or arr.shape[-1] != 3:
        raise ValueError(
            f"estadisticas: esperaba (alto, ancho, 3) o (N, 3), llego {np.shape(datos)}"
        )
    if arr.ndim == 2:
        imagen = arr.reshape(1, -1, 3)
    elif arr.ndim == 3:
        imagen = arr
    elif arr.ndim == 4:
        k, alto, ancho, _ = arr.shape
        imagen = arr.reshape(k * alto, ancho, 3)
    else:
        raise ValueError(f"estadisticas: no se que hacer con la forma {arr.shape}")
    pixeles = imagen.reshape(-1, 3)
    if pixeles.shape[0] == 0:
        raise ValueError("estadisticas: no hay ni un pixel que analizar")
    return imagen, pixeles


def _covarianza(pixeles: np.ndarray) -> np.ndarray:
    """(3, 3) covarianza RGB.

    Con menos de dos pixeles la covarianza no esta definida (el denominador
    N-1 es cero): se devuelve la matriz de CEROS en vez de dejar salir NaN. Un
    NaN ahi seria indistinguible de un pixel roto, que es lo que de verdad hay
    que ver. Una imagen de un solo color si tiene covarianza definida, y sale
    cero exacto sin ninguna division rara.
    """
    if pixeles.shape[0] < 2:
        return np.zeros((3, 3), dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = np.cov(pixeles, rowvar=False, ddof=1)
    return np.asarray(cov, dtype=np.float64).reshape(3, 3)


def _histograma_saturacion(imagen: np.ndarray) -> np.ndarray:
    """(SAT_BINS,) que suma 1. Solo cuenta pixeles finitos; ver el modulo."""
    s = saturacion_hsv(imagen).ravel()
    s = s[np.isfinite(s)]
    hist = np.histogram(s, bins=SAT_BINS, range=(0.0, 1.0))[0].astype(np.float64)
    total = hist.sum()
    if total <= 0:
        # Ni un pixel finito. Es el unico caso en el que NO suma 1, y es
        # deliberado: inventarse una distribucion seria peor.
        return hist
    return hist / total


def _piel(imagen: np.ndarray) -> tuple[np.ndarray | None, float]:
    mascara = skin_mask_oklab(imagen, WORKING_SPACE)
    n = int(mascara.sum())
    fraccion = n / float(mascara.size)
    if n < PIXELES_PIEL_MINIMOS or fraccion < FRACCION_PIEL_MINIMA:
        return None, fraccion
    oklab = rgb_to_oklab(imagen[mascara], WORKING_SPACE)
    return np.asarray(oklab, dtype=np.float64).mean(axis=0), fraccion


def _submuestrear(pixeles: np.ndarray, tope: int) -> np.ndarray:
    if tope <= 0 or pixeles.shape[0] <= tope:
        return pixeles
    rng = np.random.default_rng(SEMILLA_MUESTREO)
    idx = rng.choice(pixeles.shape[0], size=tope, replace=False)
    idx.sort()
    return pixeles[idx]


def _avisos_de_calidad(pixeles: np.ndarray, stats: ColorStats) -> list[str]:
    avisos: list[str] = []
    no_finitos = int((~np.isfinite(pixeles)).any(axis=1).sum())
    if no_finitos:
        avisos.append(
            f"Hay {no_finitos} pixeles no finitos (NaN o infinito). Las medias, la "
            f"covarianza y los percentiles salen NaN a proposito: el material esta roto."
        )
    if stats.skin_locus is None:
        avisos.append(
            f"No hay piel suficiente para el locus: {stats.skin_fraction * 100:.2f}% de la "
            f"imagen (hace falta {FRACCION_PIEL_MINIMA * 100:.1f}% y {PIXELES_PIEL_MINIMOS} pixeles)."
        )
    if float(stats.saturation_hist[0]) >= 0.999:
        avisos.append("La imagen es practicamente neutra entera: no hay color que emparejar.")
    return avisos


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def estadisticas(datos: np.ndarray, *, space: ColorSpaceName = WORKING_SPACE) -> ColorStats:
    """Resumen estadistico. Acepta (alto, ancho, 3), (N, 3) o (k, alto, ancho, 3).

    `space` es el espacio en el que vienen los datos; el resultado esta SIEMPRE en
    `WORKING_SPACE` (y `skin_locus` en Oklab), como manda el contrato.
    """
    imagen, _ = _como_imagen_y_pixeles(datos)
    if space != WORKING_SPACE:
        imagen = np.asarray(convert(imagen, space, WORKING_SPACE), dtype=np.float64)
    pixeles = imagen.reshape(-1, 3)

    with np.errstate(invalid="ignore", divide="ignore"):
        media = pixeles.mean(axis=0)
        desviacion = pixeles.std(axis=0, ddof=0)
        percentiles = np.percentile(pixeles, PERCENTILE_LEVELS, axis=0)

    niveles = list(PERCENTILE_LEVELS)
    negro = percentiles[niveles.index(PERCENTIL_NEGRO)]
    blanco = percentiles[niveles.index(PERCENTIL_BLANCO)]
    locus, fraccion = _piel(imagen)

    return ColorStats(
        mean=np.asarray(media, dtype=np.float64),
        std=np.asarray(desviacion, dtype=np.float64),
        cov=_covarianza(pixeles),
        percentiles=np.asarray(percentiles, dtype=np.float64).reshape(len(niveles), 3),
        black_point=np.asarray(negro, dtype=np.float64),
        white_point=np.asarray(blanco, dtype=np.float64),
        saturation_hist=_histograma_saturacion(imagen),
        skin_locus=locus,
        skin_fraction=float(fraccion),
        n_samples=int(pixeles.shape[0]),
    )


def analizar_imagen(
    img: np.ndarray,
    *,
    clip_id: str,
    space: ColorSpaceName = WORKING_SPACE,
    guardar_pixeles: bool = False,
) -> ClipAnalysis:
    """Analiza una imagen que ya esta en memoria. `path` sale como `<memoria>`.

    Es la puerta de atras para los tests y para la GUI cuando ensena una
    referencia que no viene de un fichero.
    """
    arr = np.asarray(img, dtype=np.float64)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"analizar_imagen: esperaba (alto, ancho, 3), llego {np.shape(img)}")
    if arr.shape[0] < 1 or arr.shape[1] < 1:
        raise ValueError("analizar_imagen: la imagen no tiene ni un pixel")
    if space != WORKING_SPACE:
        arr = np.asarray(convert(arr, space, WORKING_SPACE), dtype=np.float64)

    stats = estadisticas(arr, space=WORKING_SPACE)
    huella = huella_de_contenido(arr, space=WORKING_SPACE)
    pixeles = arr.reshape(-1, 3)
    avisos = _avisos_de_calidad(pixeles, stats)

    muestra = None
    if guardar_pixeles:
        muestra = _submuestrear(pixeles, MAX_PIXELES_POR_DEFECTO).astype(np.float32)

    return ClipAnalysis(
        clip_id=str(clip_id),
        path="<memoria>",
        stats=stats,
        fingerprint=huella,
        width=int(arr.shape[1]),
        height=int(arr.shape[0]),
        frame_count=1,
        sampled_frames=1,
        source_space=space,
        pixels=muestra,
        warnings=tuple(avisos),
    )


def analizar_clip(
    ruta: str | Path,
    *,
    clip_id: str | None = None,
    n_fotogramas: int = N_FOTOGRAMAS_POR_DEFECTO,
    space: ColorSpaceName | None = None,
    guardar_pixeles: bool = False,
    max_pixeles: int = MAX_PIXELES_POR_DEFECTO,
) -> ClipAnalysis:
    """Analiza un fichero de video o una imagen suelta.

    La estadistica sale de TODOS los fotogramas que se han mirado juntos (con un
    tope de `MAX_PIXELES_ESTADISTICA` pixeles). La huella se calcula fotograma a
    fotograma y se promedia: asi un plano con un movimiento fuerte no queda
    descrito por el fotograma que toco.

    `clip_id` por defecto es el nombre del fichero sin extension.
    """
    fotogramas, avisos_fuente, info, origen = extraer_fotogramas_con_avisos(
        ruta, n_fotogramas=n_fotogramas, space=space
    )
    k, alto, ancho, _ = fotogramas.shape
    pila = np.asarray(fotogramas, dtype=np.float64)

    pixeles = pila.reshape(-1, 3)
    muestra_stats = _submuestrear(pixeles, MAX_PIXELES_ESTADISTICA)
    if muestra_stats.shape[0] < pixeles.shape[0]:
        datos_stats: np.ndarray = muestra_stats
    else:
        datos_stats = pila.reshape(k * alto, ancho, 3)
    stats = estadisticas(datos_stats, space=WORKING_SPACE)

    huellas = np.stack([huella_de_contenido(f, space=WORKING_SPACE) for f in pila])
    media = huellas.mean(axis=0)
    norma = float(np.linalg.norm(media))
    # Norma cero = fotogramas que se cancelan entre si, o sea que el clip no
    # tiene contenido comun. Se cae al mismo vector uniforme que una imagen plana.
    huella = (media / norma if norma > 0.0 else np.full(media.shape, 1.0 / np.sqrt(media.size)))
    huella = huella.astype(np.float32)

    avisos = [*avisos_fuente, *_avisos_de_calidad(pixeles, stats)]
    muestra = None
    if guardar_pixeles:
        muestra = _submuestrear(pixeles, int(max_pixeles)).astype(np.float32)

    return ClipAnalysis(
        clip_id=str(clip_id) if clip_id is not None else Path(info.ruta).stem,
        path=str(info.ruta),
        stats=stats,
        fingerprint=huella,
        width=int(ancho),
        height=int(alto),
        frame_count=int(info.n_fotogramas),
        sampled_frames=int(k),
        source_space=origen,
        pixels=muestra,
        warnings=tuple(avisos),
    )


__all__ = [
    "FRACCION_PIEL_MINIMA",
    "MAX_PIXELES_ESTADISTICA",
    "MAX_PIXELES_POR_DEFECTO",
    "PERCENTIL_BLANCO",
    "PERCENTIL_NEGRO",
    "PIXELES_PIEL_MINIMOS",
    "analizar_clip",
    "analizar_imagen",
    "estadisticas",
    "saturacion_hsv",
]
