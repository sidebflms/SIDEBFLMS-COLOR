"""Espacios perceptuales: Oklab, CIE L*a*b* y CIEDE2000.

Todo lo que hay aqui devuelve **float64** y no float32, a proposito: son
magnitudes de analisis, no imagenes. `ColorStats` las guarda en float64 y un
ΔE2000 calculado en float32 pierde digitos justo donde se decide si dos planos
casan o no.

FUENTES
-------
- Oklab: Bjorn Ottosson, "A perceptual color space for image processing"
  (2020). Las dos matrices y la raiz cubica intermedia son las suyas.
- CIE L*a*b*: CIE 15:2004, con blanco de referencia D65 2 grados.
- CIEDE2000: Sharma, Wu y Dalal, "The CIEDE2000 Color-Difference Formula:
  Implementation Notes, Supplementary Test Data, and Mathematical
  Observations" (Color Research & Application, 2005). Se siguen sus notas de
  implementacion, que son las que resuelven bien los casos raros de tono.

NaN: se propaga, como en todo el modulo.
"""

from __future__ import annotations

import numpy as np

from core.color.spaces import SPACES, xyz_from_xy
from core.color.transfer import decode_raw, encode_raw
from core.contracts import WORKING_SPACE, ColorSpaceName

__all__ = [
    "rgb_to_oklab",
    "oklab_to_rgb",
    "rgb_to_lab",
    "lab_to_xyz",
    "delta_e2000",
    "delta_e2000_lab",
    "delta_e2000_mean",
    "skin_mask_oklab",
    "SKIN_OKLAB_LIMITES",
]

# --- Oklab (Ottosson) -------------------------------------------------------

_M1_XYZ_LMS = np.array(
    [
        [0.8189330101, 0.3618667424, -0.1288597137],
        [0.0329845436, 0.9293118715, 0.0361456387],
        [0.0482003018, 0.2643662691, 0.6338517070],
    ],
    dtype=np.float64,
)
_M2_LMS_LAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ],
    dtype=np.float64,
)
_M1_INV = np.linalg.inv(_M1_XYZ_LMS)
_M2_INV = np.linalg.inv(_M2_LMS_LAB)

#: Blanco de referencia de CIE L*a*b*: D65 2 grados con Y = 1.
XYZ_D65 = xyz_from_xy((0.3127, 0.3290))

_LAB_EPSILON = 216.0 / 24389.0  # (6/29)^3
_LAB_KAPPA = 24389.0 / 27.0  # (29/3)^3


def _pixeles(img: np.ndarray, quien: str) -> np.ndarray:
    arr = np.asarray(img, dtype=np.float64)
    if arr.ndim < 1 or arr.shape[-1] != 3:
        raise ValueError(f"{quien}: esperaba (..., 3), llego {arr.shape}")
    return arr


def _a_xyz(img: np.ndarray, space: ColorSpaceName) -> np.ndarray:
    """Valores codificados de `space` -> XYZ (D65, Y = 1 para el blanco)."""
    lineal = decode_raw(_pixeles(img, "espacio->XYZ"), space)
    return lineal @ SPACES[str(space)].matrix_rgb_to_xyz.T


def _de_xyz(xyz: np.ndarray, space: ColorSpaceName) -> np.ndarray:
    """XYZ -> valores codificados de `space`."""
    lineal = np.asarray(xyz, dtype=np.float64) @ SPACES[str(space)].matrix_xyz_to_rgb.T
    return np.asarray(encode_raw(lineal, space), dtype=np.float64)


# ---------------------------------------------------------------------------
# Oklab
# ---------------------------------------------------------------------------


def rgb_to_oklab(img: np.ndarray, space: ColorSpaceName = WORKING_SPACE) -> np.ndarray:
    """Valores codificados de `space` -> Oklab (..., 3) float64.

    La raiz cubica es `np.cbrt`, que conserva el signo. Es importante: los
    valores fuera de gamut dan LMS negativos y con `x ** (1/3)` saldrian NaN.
    Un color imposible tiene que seguir siendo un numero con el que operar, no
    un agujero en la imagen.
    """
    lms = _a_xyz(img, space) @ _M1_XYZ_LMS.T
    return np.cbrt(lms) @ _M2_LMS_LAB.T


def oklab_to_rgb(lab: np.ndarray, space: ColorSpaceName = WORKING_SPACE) -> np.ndarray:
    """Oklab -> valores codificados de `space` (..., 3) float64."""
    lms_ = _pixeles(lab, "oklab_to_rgb") @ _M2_INV.T
    xyz = (lms_**3) @ _M1_INV.T
    return _de_xyz(xyz, space)


# ---------------------------------------------------------------------------
# CIE L*a*b*
# ---------------------------------------------------------------------------


def _f_lab(t: np.ndarray) -> np.ndarray:
    """La f() de CIE L*a*b*, extendida a negativos por simetria impar.

    La CIE solo la define para t >= 0. Como aqui entran colores fuera de gamut
    con XYZ negativo, se extiende con f(-t) = -f(t): es continua, monotona e
    invertible, que es lo que necesita ΔE2000 para no romperse.
    """
    s = np.sign(t)
    a = np.abs(t)
    return s * np.where(a > _LAB_EPSILON, np.cbrt(a), (_LAB_KAPPA * a + 16.0) / 116.0)


def _f_lab_inv(t: np.ndarray) -> np.ndarray:
    s = np.sign(t)
    a = np.abs(t)
    return s * np.where(a**3 > _LAB_EPSILON, a**3, (116.0 * a - 16.0) / _LAB_KAPPA)


def xyz_to_lab(xyz: np.ndarray) -> np.ndarray:
    """XYZ (D65) -> CIE L*a*b* con L* en 0..100."""
    f = _f_lab(_pixeles(xyz, "xyz_to_lab") / XYZ_D65)
    return np.stack(
        [
            116.0 * f[..., 1] - 16.0,
            500.0 * (f[..., 0] - f[..., 1]),
            200.0 * (f[..., 1] - f[..., 2]),
        ],
        axis=-1,
    )


def lab_to_xyz(lab: np.ndarray) -> np.ndarray:
    """CIE L*a*b* -> XYZ (D65)."""
    arr = _pixeles(lab, "lab_to_xyz")
    fy = (arr[..., 0] + 16.0) / 116.0
    fx = fy + arr[..., 1] / 500.0
    fz = fy - arr[..., 2] / 200.0
    return _f_lab_inv(np.stack([fx, fy, fz], axis=-1)) * XYZ_D65


def rgb_to_lab(img: np.ndarray, space: ColorSpaceName = WORKING_SPACE) -> np.ndarray:
    """Valores codificados de `space` -> CIE L*a*b* (D65), L* en 0..100."""
    return xyz_to_lab(_a_xyz(img, space))


# ---------------------------------------------------------------------------
# CIEDE2000
# ---------------------------------------------------------------------------


def delta_e2000_lab(
    lab1: np.ndarray, lab2: np.ndarray, *, k_l: float = 1.0, k_c: float = 1.0, k_h: float = 1.0
) -> np.ndarray:
    """ΔE2000 entre dos conjuntos de L*a*b*. Devuelve (...) sin eje de canal.

    Implementacion segun las notas de Sharma, Wu y Dalal (2005). Los tres sitios
    donde una implementacion ingenua falla, y que aqui estan tratados:

    1. `C' = 0` en uno de los dos colores (un gris): el tono no esta definido y
       hay que forzar Δh' = 0 y h̄' = h1' + h2', no promediarlos.
    2. La media de tonos cuando los dos estan a caballo de 0/360.
    3. `C^7` se calcula como `1 / (1 + (25/C)^7)` para que un color muy saturado
       (que aqui pasa, venimos de log y de especulares) no desborde el float64.
    """
    a = _pixeles(lab1, "delta_e2000_lab")
    b = _pixeles(lab2, "delta_e2000_lab")
    if a.shape != b.shape:
        try:
            a, b = np.broadcast_arrays(a, b)
        except ValueError:
            raise ValueError(f"formas incompatibles: {a.shape} y {b.shape}") from None

    l1, a1, b1 = a[..., 0], a[..., 1], a[..., 2]
    l2, a2, b2 = b[..., 0], b[..., 1], b[..., 2]

    c1 = np.hypot(a1, b1)
    c2 = np.hypot(a2, b2)
    c_barra = 0.5 * (c1 + c2)
    g = 0.5 * (1.0 - np.sqrt(_frac_c7(c_barra)))

    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = np.hypot(a1p, b1)
    c2p = np.hypot(a2p, b2)

    h1p = _tono(b1, a1p, c1p)
    h2p = _tono(b2, a2p, c2p)

    dlp = l2 - l1
    dcp = c2p - c1p

    cero = (c1p * c2p) == 0.0
    dif = h2p - h1p
    dhp = np.where(dif > 180.0, dif - 360.0, np.where(dif < -180.0, dif + 360.0, dif))
    dhp = np.where(cero, 0.0, dhp)
    dHp = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(dhp) / 2.0)

    lbp = 0.5 * (l1 + l2)
    cbp = 0.5 * (c1p + c2p)

    suma = h1p + h2p
    absdif = np.abs(h1p - h2p)
    hbp = np.where(
        cero,
        suma,
        np.where(
            absdif <= 180.0,
            0.5 * suma,
            np.where(suma < 360.0, 0.5 * (suma + 360.0), 0.5 * (suma - 360.0)),
        ),
    )

    t = (
        1.0
        - 0.17 * np.cos(np.radians(hbp - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * hbp))
        + 0.32 * np.cos(np.radians(3.0 * hbp + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * hbp - 63.0))
    )
    # El famoso pico en 275 grados: ahi el termino de rotacion es maximo y es
    # donde mas de una implementacion se desvia. Ver el test de tonos dificiles.
    d_theta = 30.0 * np.exp(-(((hbp - 275.0) / 25.0) ** 2))
    r_c = 2.0 * np.sqrt(_frac_c7(cbp))
    s_l = 1.0 + (0.015 * (lbp - 50.0) ** 2) / np.sqrt(20.0 + (lbp - 50.0) ** 2)
    s_c = 1.0 + 0.045 * cbp
    s_h = 1.0 + 0.015 * cbp * t
    r_t = -np.sin(np.radians(2.0 * d_theta)) * r_c

    term_l = dlp / (k_l * s_l)
    term_c = dcp / (k_c * s_c)
    term_h = dHp / (k_h * s_h)
    return np.sqrt(term_l**2 + term_c**2 + term_h**2 + r_t * term_c * term_h)


def _frac_c7(c: np.ndarray) -> np.ndarray:
    """C^7 / (C^7 + 25^7), escrito para que no desborde con C grande."""
    c = np.asarray(c, dtype=np.float64)
    out = np.zeros(np.shape(c), dtype=np.float64)
    positivo = c > 0.0
    with np.errstate(over="ignore"):
        razon = np.where(positivo, 25.0 / np.where(positivo, c, 1.0), 0.0) ** 7
    np.divide(1.0, 1.0 + razon, out=out, where=positivo)
    # Un NaN de entrada tiene que salir NaN, no 0.
    return np.where(np.isnan(c), np.nan, out)


def _tono(b: np.ndarray, ap: np.ndarray, cp: np.ndarray) -> np.ndarray:
    """h' en grados 0..360. Con C' = 0 el tono es 0 por convenio de Sharma."""
    h = np.degrees(np.arctan2(b, ap))
    h = np.where(h < 0.0, h + 360.0, h)
    return np.where(cp == 0.0, 0.0, h)


def delta_e2000(
    a: np.ndarray, b: np.ndarray, space: ColorSpaceName = WORKING_SPACE
) -> np.ndarray:
    """ΔE2000 por pixel entre dos imagenes en `space`. Forma (...) sin canal."""
    return delta_e2000_lab(rgb_to_lab(a, space), rgb_to_lab(b, space))


def delta_e2000_mean(
    a: np.ndarray, b: np.ndarray, space: ColorSpaceName = WORKING_SPACE
) -> float:
    """ΔE2000 medio. Si hay un NaN, el resultado es NaN: no se barre nada.

    Es deliberado y es coherente con el resto del modulo. Un plano con NaN es un
    plano roto y quien lo esta midiendo tiene que enterarse, no recibir una
    media plausible calculada sobre los pixeles que sobrevivieron.
    """
    return float(np.mean(delta_e2000(a, b, space)))


# ---------------------------------------------------------------------------
# Locus de piel en Oklab
# ---------------------------------------------------------------------------

#: Limites del locus de piel en Oklab. Salen de medir los SEIS tonos de
#: `SKIN_TONES_SRGB` sobre `studio_scene`, no de un paper: ver NOTAS.md, que
#: trae la precision y la exhaustividad tono a tono.
#:
#: La clave para que funcione con pieles oscuras es usar **croma relativo a L**
#: (C/L) y no croma absoluto: la piel oscura tiene la misma tonalidad pero
#: mucho menos croma absoluto, asi que un umbral fijo de croma la pierde entera.
SKIN_OKLAB_LIMITES: dict[str, float] = {
    "tono_min": 10.0,  # grados
    "tono_max": 85.0,
    "croma_rel_min": 0.040,  # C / L
    "croma_rel_max": 0.300,
    "croma_abs_min": 0.015,  # corta el gris con ruido, que no tiene tono fiable
    "l_min": 0.25,
    "l_max": 1.30,
}


def skin_mask_oklab(img: np.ndarray, space: ColorSpaceName = WORKING_SPACE) -> np.ndarray:
    """(h, w) bool: que pixeles estan dentro del locus de piel en Oklab.

    Es un detector de COLOR, no de caras: marca todo lo que tiene tono y croma
    de piel, incluida la madera o un fondo terroso. Para la app vale porque se
    usa sobre planos donde hay alguien, y porque lo que interesa es el color
    medio del locus, no recortar a nadie.

    El criterio es el de `SKIN_OKLAB_LIMITES` y esta calibrado con los seis
    tonos de `tests/media/generate.py`, oscuros incluidos. En NOTAS.md estan los
    numeros reales de precision y exhaustividad de cada uno.
    """
    lab = rgb_to_oklab(img, space)
    if lab.ndim != 3:
        raise ValueError(f"skin_mask_oklab: esperaba (alto, ancho, 3), llego {np.shape(img)}")
    lim = SKIN_OKLAB_LIMITES
    ll = lab[..., 0]
    croma = np.hypot(lab[..., 1], lab[..., 2])
    with np.errstate(invalid="ignore", divide="ignore"):
        tono = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0
        croma_rel = croma / np.maximum(ll, 1e-6)
    mascara = (
        (tono >= lim["tono_min"])
        & (tono <= lim["tono_max"])
        & (croma_rel >= lim["croma_rel_min"])
        & (croma_rel <= lim["croma_rel_max"])
        & (croma >= lim["croma_abs_min"])
        & (ll >= lim["l_min"])
        & (ll <= lim["l_max"])
    )
    # Un pixel NaN no es piel: todas las comparaciones de arriba son falsas, o
    # sea que esto ya sale solo. Se deja explicito para que se lea.
    return np.asarray(mascara & ~np.isnan(ll), dtype=bool)
