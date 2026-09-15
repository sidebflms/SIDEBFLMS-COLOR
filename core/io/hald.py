"""Imagen HALD CLUT: un LUT 3D metido en una imagen cuadrada.

Sirve para lo de siempre: metes la imagen HALD por un grado (de Resolve, de
Photoshop, de lo que sea), exportas el resultado, y la imagen de salida ES el
LUT de ese grado. Es la forma más barata de sacar un grado de una herramienta
que no tiene exportación de LUT.

ORDEN DE LOS PÍXELES
--------------------
Aquí NO se usa el orden del fichero `.cube`. El orden de una imagen HALD es
exactamente el de `LUT3D.table.reshape(-1, 3)`: el **azul** es el que varía más
rápido y el **rojo** el que varía más lento, que es lo que hace
`tests/media/generate.py::hald()` con `np.meshgrid(..., indexing="ij")`.

Consecuencia práctica, y hay un test que lo comprueba:
`hald_image(LUT3D.identity(17))` es idéntico píxel a píxel a `generate.hald(17)`.

El lado de la imagen es `ceil(sqrt(N**3))`, y las celdas que sobran al final se
rellenan con negro (igual que el generador). Para N = 17 salen 4913 entradas en
una imagen de 71x71 = 5041 píxeles: sobran 128 píxeles negros que se ignoran al
volver.
"""

from __future__ import annotations

import numpy as np

from core.contracts import LUT3D

from .errores import ErrorFormatoHald

__all__ = ["lado_hald", "hald_image", "lut_from_hald"]


def lado_hald(size: int) -> int:
    """Lado en píxeles de la imagen HALD de un LUT de tamaño `size`."""
    if size < 2:
        raise ErrorFormatoHald(f"un LUT necesita al menos 2 muestras por eje, y llegó {size}")
    return int(np.ceil(np.sqrt(float(size) ** 3)))


def hald_image(lut: LUT3D) -> np.ndarray:
    """`LUT3D` -> imagen HALD `(lado, lado, 3)` float32.

    No recorta: si el LUT saca valores fuera de 0..1 la imagen los lleva tal
    cual, que es lo que manda la convención 1 de CONTRATOS. Quien quiera un PNG
    ya se ocupará de recortar al guardar.
    """
    n = lut.size
    lado = lado_hald(n)
    entradas = np.asarray(lut.table, dtype=np.float32).reshape(-1, 3)
    img = np.zeros((lado * lado, 3), dtype=np.float32)
    img[: entradas.shape[0]] = entradas
    return img.reshape(lado, lado, 3)


def lut_from_hald(img: np.ndarray, size: int) -> LUT3D:
    """Imagen HALD + tamaño de rejilla -> `LUT3D`. Ida y vuelta exacta.

    El tamaño hay que pasarlo porque una imagen de 71x71 podría ser el HALD de
    un LUT de 17 con relleno, y adivinarlo a partir del lado es un sitio
    estupendo para equivocarse en silencio.
    """
    arr = np.asarray(img)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ErrorFormatoHald(
            f"una imagen HALD tiene que ser (alto, ancho, 3) y llegó {arr.shape}"
        )
    if size < 2:
        raise ErrorFormatoHald(f"un LUT necesita al menos 2 muestras por eje, y llegó {size}")

    necesarios = size**3
    disponibles = arr.shape[0] * arr.shape[1]
    if disponibles < necesarios:
        lado = lado_hald(size)
        raise ErrorFormatoHald(
            f"para un LUT de {size} hacen falta {necesarios} píxeles "
            f"(una imagen de {lado}x{lado}) y esta tiene {arr.shape[1]}x{arr.shape[0]} "
            f"= {disponibles}"
        )

    plano = arr.reshape(-1, 3)[:necesarios].astype(np.float32)
    table = plano.reshape(size, size, size, 3)
    return LUT3D(table=np.ascontiguousarray(table), title="Desde HALD")
