"""De numpy en espacio de trabajo a `QImage`, que es lo unico que Qt sabe pintar.

**La conversion pasa siempre por `core.color.from_working`.** No se hace un
`clip(0,1) * 255` sobre el espacio de trabajo y a correr: el material de trabajo
esta en DaVinci Intermediate (logaritmico) y pintarlo tal cual daria una imagen
lavada que no se parece a lo que Mario veria en Resolve. Se lleva a Rec.709 —con
su curva— y ahi si se recorta a 0..1 para la pantalla.

Los valores fuera de rango son legales en el nucleo (contrato 1) y se preservan
hasta aqui; **el recorte ocurre solo en el ultimo paso, el de pintar**.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

from core.color import from_working
from core.contracts import ColorSpaceName

#: Espacio en el que se pinta. Rec.709 con su curva, que es lo que ensena un
#: monitor normal y lo que Resolve manda a la ventana de previsualizacion.
ESPACIO_PANTALLA: ColorSpaceName = "rec709"


def a_uint8(img: np.ndarray, *, espacio_origen: ColorSpaceName | None = None) -> np.ndarray:
    """(alto, ancho, 3) float en espacio de trabajo -> (alto, ancho, 3) uint8 Rec.709.

    `espacio_origen=None` significa «ya viene en el espacio de trabajo», que es
    lo normal. Si se pasa `"rec709"` se entiende que ya esta listo y solo se
    recorta.
    """
    arr = np.asarray(img)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"esperaba (alto, ancho, 3), llego {arr.shape}")
    if espacio_origen == ESPACIO_PANTALLA:
        pantalla = arr.astype(np.float64, copy=False)
    else:
        pantalla = from_working(arr.astype(np.float32, copy=False), ESPACIO_PANTALLA)
    pantalla = np.nan_to_num(np.asarray(pantalla, dtype=np.float64), nan=0.0,
                             posinf=1.0, neginf=0.0)
    return (np.clip(pantalla, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def a_qimage(img: np.ndarray, *, espacio_origen: ColorSpaceName | None = None) -> QImage:
    """`QImage` RGB888 con su propia copia de los bytes.

    La copia no es un descuido: `QImage` no toma posesion del buffer de numpy y
    si el array se libera, Qt pinta basura. Es un fallo que solo se ve en la
    captura, o sea tarde.
    """
    datos = np.ascontiguousarray(a_uint8(img, espacio_origen=espacio_origen))
    alto, ancho, _ = datos.shape
    qimg = QImage(datos.data, ancho, alto, 3 * ancho, QImage.Format.Format_RGB888)
    return qimg.copy()


def tira_de_color(colores: np.ndarray, *, ancho: int = 240, alto: int = 26) -> QImage:
    """Una tira horizontal de parches a partir de (N, 3) en espacio de trabajo.

    Se usa para ensenar «asi queda el CDL» sin necesidad de una imagen entera.
    """
    px = np.asarray(colores, dtype=np.float32).reshape(-1, 3)
    n = max(1, px.shape[0])
    repeticiones = max(1, ancho // n)
    fila = np.repeat(px, repeticiones, axis=0)[:ancho]
    if fila.shape[0] < ancho:
        fila = np.pad(fila, ((0, ancho - fila.shape[0]), (0, 0)), mode="edge")
    return a_qimage(np.tile(fila[None, :, :], (alto, 1, 1)))


__all__ = ["ESPACIO_PANTALLA", "a_qimage", "a_uint8", "tira_de_color"]
