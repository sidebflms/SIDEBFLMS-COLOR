"""Espacios de color y funciones de transferencia de SIDEBFLMS COLOR.

Es el cimiento del proyecto: si esto esta mal, todo lo demas esta mal y no se
entera nadie hasta que Mario mira una imagen y le parece que "esta rara".

LO QUE HAY QUE SABER PARA USARLO
--------------------------------
- Un valor **codificado** es lo que lleva un fichero: S-Log3, V-Log, DaVinci
  Intermediate... El valor codificado del 18% de gris no es 0.18.
- Un valor **lineal** es escena-lineal con **0.18 = 18% de gris**. Es lo que
  produce `tests/media/generate.py` y lo que entra y sale de `log_encode` /
  `log_decode`.
- `convert(img, src, dst)` va de codificado a codificado y hace los tres pasos
  (decodificar curva, matriz de primarios, codificar curva).
- `primaries_matrix(src, dst)` es solo la matriz, sobre valores LINEALES.
- Los espacios `linear_*` son escena-lineales: tienen primarios pero su curva
  es la identidad.

POLITICA DE NaN (la misma en todo el modulo)
--------------------------------------------
Se **propaga**. Nada lanza por un NaN. Un pixel roto sale NaN en la imagen, en
el ΔE y en la media del ΔE; no se barre bajo la alfombra con `nanmean`, porque
entonces un plano corrupto daria un numero plausible y nadie lo miraria.

PRECISION
---------
`convert`, `log_encode`, `log_decode`, `to_working` y `from_working` devuelven
float32 (contrato 1) salvo que les entre float64, en cuyo caso respetan la
precision que les han dado. Las funciones perceptuales (`rgb_to_oklab`,
`rgb_to_lab`, `delta_e2000`...) devuelven siempre float64.
"""

from __future__ import annotations

from core.color.perceptual import (
    SKIN_OKLAB_LIMITES,
    XYZ_D65,
    delta_e2000,
    delta_e2000_lab,
    delta_e2000_mean,
    lab_to_xyz,
    oklab_to_rgb,
    rgb_to_lab,
    rgb_to_oklab,
    skin_mask_oklab,
    xyz_to_lab,
)
from core.color.spaces import (
    D65,
    SPACES,
    ColorSpaceInfo,
    convert,
    from_working,
    primaries_matrix,
    rgb_to_xyz_matrix,
    to_working,
    xyz_from_xy,
)
from core.color.transfer import TRANSFERENCIAS, log_decode, log_encode

__all__ = [
    # conversion entre espacios
    "convert",
    "to_working",
    "from_working",
    # transferencia sola
    "log_encode",
    "log_decode",
    # primarios solos
    "primaries_matrix",
    # perceptual
    "rgb_to_oklab",
    "oklab_to_rgb",
    "rgb_to_lab",
    "xyz_to_lab",
    "lab_to_xyz",
    "delta_e2000",
    "delta_e2000_lab",
    "delta_e2000_mean",
    "skin_mask_oklab",
    # metadatos y utilidades
    "SPACES",
    "ColorSpaceInfo",
    "SKIN_OKLAB_LIMITES",
    "TRANSFERENCIAS",
    "D65",
    "XYZ_D65",
    "rgb_to_xyz_matrix",
    "xyz_from_xy",
]
