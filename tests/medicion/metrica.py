"""La metrica de fuera: ΔE2000 con `colour-science`, sin pasar por `core.color`.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
Verificar las cifras de ΔE del repo con el ΔE del repo es un circulo: si la
metrica estuviera mal, los dos lados fallarian igual y saldria verde. Aqui se
recorre el camino entero con otra implementacion:

    DWG / DaVinci Intermediate (codificado)
        --oetf_inverse_DaVinciIntermediate-->   DWG escena-lineal
        --colour.RGB_to_XYZ("DaVinci Wide Gamut")-->  XYZ (D65, Y=1)
        --colour.XYZ_to_Lab(D65 2 grados)-->    CIE L*a*b*
        --colour.difference.delta_E_CIE2000-->  ΔE2000

Ni una linea de `core.color` interviene. La unica funcion de este archivo que
importa `core.color` es `comparar_con_el_repo()`, que existe exactamente para
medir si los dos caminos coinciden y esta marcada como tal.

NOTA SOBRE LA ADAPTACION CROMATICA
----------------------------------
`colour.RGB_to_XYZ` se llama con `illuminant=None` a proposito: asi NO aplica
adaptacion cromatica. DaVinci Wide Gamut es D65 y el blanco de referencia del
Lab es D65, o sea que no hay nada que adaptar. Meterle un CAT aqui tintaria el
resultado y seria un error mio, no del repo.
"""

from __future__ import annotations

import colour
import numpy as np
from colour.difference import delta_E_CIE2000
from colour.models import oetf_inverse_DaVinciIntermediate

#: Blanco de referencia del L*a*b*: D65, observador 2 grados, CIE 15:2004.
#: Es el mismo valor que usa `colour.XYZ_to_Lab` por defecto y el mismo que
#: declara `core/color/spaces.py` (D65 = (0.3127, 0.3290)).
D65_XY = np.array([0.3127, 0.3290])

#: El espacio de trabajo del repo, visto desde colour-science.
DWG = colour.RGB_COLOURSPACES["DaVinci Wide Gamut"]


def wg_a_lab(img: np.ndarray) -> np.ndarray:
    """Imagen en el espacio de trabajo del repo -> CIE L*a*b* (..., 3) float64.

    `img` son valores CODIFICADOS en DaVinci Intermediate con primarios
    DaVinci Wide Gamut, que es lo que el contrato 3 llama `WORKING_SPACE`.
    """
    arr = np.asarray(img, dtype=np.float64)
    if arr.shape[-1] != 3:
        raise ValueError(f"esperaba (..., 3), llego {arr.shape}")
    lineal = np.asarray(oetf_inverse_DaVinciIntermediate(arr), dtype=np.float64)
    xyz = colour.RGB_to_XYZ(lineal, DWG, illuminant=None, apply_cctf_decoding=False)
    return np.asarray(colour.XYZ_to_Lab(xyz, D65_XY), dtype=np.float64)


def delta_e2000_wg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """ΔE2000 por pixel entre dos imagenes del espacio de trabajo. (...,) float64."""
    return np.asarray(delta_E_CIE2000(wg_a_lab(a), wg_a_lab(b)), dtype=np.float64)


def resumen_de(de: np.ndarray, mascara: np.ndarray | None = None) -> dict[str, float]:
    """Medio, p95 y maximo de un campo de ΔE, opcionalmente restringido.

    Los no finitos se DESCARTAN y se dice cuantos eran, igual que hace
    `core.reverse.invertir_grado`: asi los dos numeros son comparables.
    """
    v = np.asarray(de, dtype=np.float64).reshape(-1)
    if mascara is not None:
        v = v[np.asarray(mascara, dtype=bool).reshape(-1)]
    fin = np.isfinite(v)
    n_total = int(v.size)
    v = v[fin]
    if v.size == 0:
        return {"medio": float("nan"), "p95": float("nan"), "max": float("nan"),
                "n": 0.0, "fraccion_no_finita": 1.0}
    return {
        "medio": float(v.mean()),
        "p95": float(np.percentile(v, 95)),
        "max": float(v.max()),
        "n": float(v.size),
        "fraccion_no_finita": float(1.0 - v.size / max(n_total, 1)),
    }


# ---------------------------------------------------------------------------
# Validacion de la metrica contra Sharma, Wu y Dalal (2005)
# ---------------------------------------------------------------------------
# Los 34 pares suplementarios del articulo:
#
#   Sharma, G., Wu, W., & Dalal, E. N. (2005). "The CIEDE2000 color-difference
#   formula: Implementation notes, supplementary test data, and mathematical
#   observations". Color Research & Application, 30(1), 21-30.
#
# Transcritos de la tabla publicada. Es el conjunto estandar para verificar una
# implementacion de CIEDE2000: si una implementacion pasa estos 34 pares, los
# casos raros de tono (los que cruzan 0/360 grados) estan bien resueltos.
#
# OJO CON EL PAR 14 (indice 13, `[50, -0.001, 2.49]` vs `[50, 0.001, -2.49]`,
# ΔE publicado 4.8045): es exactamente antipodal y el resultado depende del
# ultimo bit de `arctan2`. colour-science lo excluye de su propia suite porque
# en Linux da 4.7461 y en macOS/Windows 4.8045. Aqui se mide en macOS y se
# incluye, pero se informa aparte para que nadie confunda una diferencia de
# plataforma con un fallo.

SHARMA_LAB1 = np.array([
    [50.0000, 2.6772, -79.7751],
    [50.0000, 3.1571, -77.2803],
    [50.0000, 2.8361, -74.0200],
    [50.0000, -1.3802, -84.2814],
    [50.0000, -1.1848, -84.8006],
    [50.0000, -0.9009, -85.5211],
    [50.0000, 0.0000, 0.0000],
    [50.0000, -1.0000, 2.0000],
    [50.0000, 2.4900, -0.0010],
    [50.0000, 2.4900, -0.0010],
    [50.0000, 2.4900, -0.0010],
    [50.0000, 2.4900, -0.0010],
    [50.0000, -0.0010, 2.4900],
    [50.0000, -0.0010, 2.4900],
    [50.0000, -0.0010, 2.4900],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [50.0000, 2.5000, 0.0000],
    [60.2574, -34.0099, 36.2677],
    [63.0109, -31.0961, -5.8663],
    [61.2901, 3.7196, -5.3901],
    [35.0831, -44.1164, 3.7933],
    [22.7233, 20.0904, -46.6940],
    [36.4612, 47.8580, 18.3852],
    [90.8027, -2.0831, 1.4410],
    [90.9257, -0.5406, -0.9208],
    [6.7747, -0.2908, -2.4247],
    [2.0776, 0.0795, -1.1350],
])

SHARMA_LAB2 = np.array([
    [50.0000, 0.0000, -82.7485],
    [50.0000, 0.0000, -82.7485],
    [50.0000, 0.0000, -82.7485],
    [50.0000, 0.0000, -82.7485],
    [50.0000, 0.0000, -82.7485],
    [50.0000, 0.0000, -82.7485],
    [50.0000, -1.0000, 2.0000],
    [50.0000, 0.0000, 0.0000],
    [50.0000, -2.4900, 0.0009],
    [50.0000, -2.4900, 0.0010],
    [50.0000, -2.4900, 0.0011],
    [50.0000, -2.4900, 0.0012],
    [50.0000, 0.0009, -2.4900],
    [50.0000, 0.0010, -2.4900],
    [50.0000, 0.0011, -2.4900],
    [50.0000, 0.0000, -2.5000],
    [73.0000, 25.0000, -18.0000],
    [61.0000, -5.0000, 29.0000],
    [56.0000, -27.0000, -3.0000],
    [58.0000, 24.0000, 15.0000],
    [50.0000, 3.1736, 0.5854],
    [50.0000, 3.2972, 0.0000],
    [50.0000, 1.8634, 0.5757],
    [50.0000, 3.2592, 0.3350],
    [60.4626, -34.1751, 39.4387],
    [62.8187, -29.7946, -4.0864],
    [61.4292, 2.2480, -4.9620],
    [35.0232, -40.0716, 1.5901],
    [23.0331, 14.9730, -42.5619],
    [36.2715, 50.5065, 21.2231],
    [91.1528, -1.6435, 0.0447],
    [88.6381, -0.8985, -0.7239],
    [5.8714, -0.0985, -2.2286],
    [0.9033, -0.0636, -0.5514],
])

SHARMA_DE = np.array([
    2.0425, 2.8615, 3.4412, 1.0000, 1.0000, 1.0000, 2.3669, 2.3669,
    7.1792, 7.1792, 7.2195, 7.2195, 4.8045, 4.8045, 4.7461, 4.3065,
    27.1492, 22.8977, 31.9030, 19.4535, 1.0000, 1.0000, 1.0000, 1.0000,
    1.2644, 1.2630, 1.8731, 1.8645, 2.0373, 1.4146, 1.4441, 1.5381,
    0.6377, 0.9082,
])

#: Indice (0-based) del par antipodal cuyo resultado depende de la plataforma.
SHARMA_PAR_ANTIPODAL = 13


def validar_contra_sharma(fn) -> dict[str, float]:
    """Pasa `fn(Lab1, Lab2) -> ΔE` por los 34 pares y devuelve los errores.

    `error_max` excluye el par antipodal (indice 13); `error_max_con_antipodal`
    lo incluye. Los dos van al informe.
    """
    mio = np.asarray(fn(SHARMA_LAB1, SHARMA_LAB2), dtype=np.float64).reshape(-1)
    err = np.abs(mio - SHARMA_DE)
    sin = np.delete(err, SHARMA_PAR_ANTIPODAL)
    return {
        "error_max": float(sin.max()),
        "error_medio": float(sin.mean()),
        "error_max_con_antipodal": float(err.max()),
        "error_par_antipodal": float(err[SHARMA_PAR_ANTIPODAL]),
        "n_pares": float(err.size),
    }


def comparar_con_el_repo(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """UNICO sitio de este arnes que toca `core.color`, y solo para compararlo.

    Devuelve el error entre el ΔE2000 del repo y el mio sobre las dos imagenes,
    mas el error entre los dos caminos de conversion a L*a*b*.
    """
    from core.color import delta_e2000, rgb_to_lab  # noqa: PLC0415

    de_repo = np.asarray(delta_e2000(a, b), dtype=np.float64).reshape(-1)
    de_mio = delta_e2000_wg(a, b).reshape(-1)
    fin = np.isfinite(de_repo) & np.isfinite(de_mio)
    d = np.abs(de_repo[fin] - de_mio[fin])

    lab_repo = np.asarray(rgb_to_lab(a), dtype=np.float64).reshape(-1, 3)
    lab_mio = wg_a_lab(a).reshape(-1, 3)
    finl = np.isfinite(lab_repo).all(1) & np.isfinite(lab_mio).all(1)
    dl = np.abs(lab_repo[finl] - lab_mio[finl])

    return {
        "de_error_max": float(d.max()) if d.size else float("nan"),
        "de_error_medio": float(d.mean()) if d.size else float("nan"),
        "lab_error_max": float(dl.max()) if dl.size else float("nan"),
        "lab_error_max_L": float(dl[:, 0].max()) if dl.size else float("nan"),
        "lab_error_max_a": float(dl[:, 1].max()) if dl.size else float("nan"),
        "lab_error_max_b": float(dl[:, 2].max()) if dl.size else float("nan"),
    }
