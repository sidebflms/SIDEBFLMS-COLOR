"""Primarios, punto blanco y conversion entre espacios de color.

Las cromaticidades estan copiadas de la documentacion del fabricante (ver
`SPACES`, cada entrada dice de donde sale). La matriz RGB->XYZ no se copia de
ningun sitio: se CALCULA con el metodo estandar de la matriz de primarios
normalizada (SMPTE RP 177), que es una linea de algebra y se puede comprobar.

Los ocho espacios son D65, asi que la adaptacion cromatica sale identidad. Aun
asi el camino de Bradford esta implementado: cuesta diez lineas y el dia que
entre un espacio DCI-P3 o un ACES con punto blanco distinto esto ya funciona en
vez de dar un error silencioso de tinte.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.color.transfer import decode_raw, dtype_salida, encode_raw
from core.contracts import WORKING_SPACE, ColorSpaceName

__all__ = [
    "ColorSpaceInfo",
    "SPACES",
    "primaries_matrix",
    "convert",
    "to_working",
    "from_working",
    "rgb_to_xyz_matrix",
    "xyz_from_xy",
]

#: CIE 1931 2 grados. Es el punto blanco de los ocho espacios que manejamos.
D65: tuple[float, float] = (0.3127, 0.3290)

#: Matriz de Bradford (von Kries modificada), la que usan ACES y Resolve.
_BRADFORD = np.array(
    [
        [0.8951, 0.2664, -0.1614],
        [-0.7502, 1.7135, 0.0367],
        [0.0389, -0.0685, 1.0296],
    ],
    dtype=np.float64,
)


def xyz_from_xy(xy: tuple[float, float]) -> np.ndarray:
    """Cromaticidad (x, y) -> XYZ con Y = 1."""
    x, y = float(xy[0]), float(xy[1])
    if y == 0.0:
        raise ValueError(f"cromaticidad con y = 0, no tiene XYZ: {xy}")
    return np.array([x / y, 1.0, (1.0 - x - y) / y], dtype=np.float64)


def rgb_to_xyz_matrix(primaries: np.ndarray, whitepoint: tuple[float, float]) -> np.ndarray:
    """Matriz de primarios normalizada (3, 3): lineal RGB -> XYZ.

    `primaries` es (3, 2): las cromaticidades xy de R, G y B, en ese orden.
    El metodo es el clasico: se monta la matriz de cromaticidades por columnas,
    se resuelve que componente de cada primario hace falta para que (1, 1, 1)
    de exactamente el XYZ del blanco, y se escalan las columnas con eso.
    """
    xy = np.asarray(primaries, dtype=np.float64)
    if xy.shape != (3, 2):
        raise ValueError(f"primarios tienen que ser (3, 2), llego {xy.shape}")
    z = 1.0 - xy[:, 0] - xy[:, 1]
    P = np.vstack([xy[:, 0], xy[:, 1], z])  # columnas = R, G, B
    escala = np.linalg.solve(P, xyz_from_xy(whitepoint))
    return P * escala  # difunde por columnas


@dataclass(frozen=True)
class ColorSpaceInfo:
    """Metadatos de un espacio. Lo que hay en `SPACES[nombre]`."""

    name: str
    label: str  # nombre legible, el que ve Mario en la GUI
    primaries: np.ndarray  # (3, 2) cromaticidades xy de R, G, B
    whitepoint: tuple[float, float]
    transfer: str  # nombre de la curva, "lineal" si no tiene
    is_linear: bool
    fuente: str  # de donde salen las cromaticidades

    @property
    def matrix_rgb_to_xyz(self) -> np.ndarray:
        return rgb_to_xyz_matrix(self.primaries, self.whitepoint)

    @property
    def matrix_xyz_to_rgb(self) -> np.ndarray:
        return np.linalg.inv(self.matrix_rgb_to_xyz)


def _info(
    name: str,
    label: str,
    primaries: tuple[tuple[float, float], ...],
    transfer: str,
    fuente: str,
    *,
    is_linear: bool = False,
) -> ColorSpaceInfo:
    return ColorSpaceInfo(
        name=name,
        label=label,
        primaries=np.array(primaries, dtype=np.float64),
        whitepoint=D65,
        transfer=transfer,
        is_linear=is_linear,
        fuente=fuente,
    )


_SGAMUT3_CINE = ((0.766, 0.275), (0.225, 0.800), (0.089, -0.087))
_VGAMUT = ((0.730, 0.280), (0.165, 0.840), (0.100, -0.030))
_CINEMA_GAMUT = ((0.740, 0.270), (0.170, 1.140), (0.080, -0.100))
_DGAMUT = ((0.710, 0.310), (0.210, 0.880), (0.090, -0.080))
_DWG = ((0.8000, 0.3130), (0.1682, 0.9877), (0.0790, -0.1155))
_REC709 = ((0.640, 0.330), (0.300, 0.600), (0.150, 0.060))


#: Metadatos por espacio. La clave es el `ColorSpaceName` del contrato.
SPACES: dict[str, ColorSpaceInfo] = {
    "slog3_sgamut3cine": _info(
        "slog3_sgamut3cine",
        "Sony S-Log3 / S-Gamut3.Cine",
        _SGAMUT3_CINE,
        "S-Log3",
        "Sony, Technical Summary for S-Gamut3.Cine/S-Log3",
    ),
    "vlog_vgamut": _info(
        "vlog_vgamut",
        "Panasonic V-Log / V-Gamut",
        _VGAMUT,
        "V-Log",
        "Panasonic, V-Log/V-Gamut Reference Manual",
    ),
    "clog3_cinemagamut": _info(
        "clog3_cinemagamut",
        "Canon Log 3 / Cinema Gamut",
        _CINEMA_GAMUT,
        "Canon Log 3",
        "Canon, White Paper on Canon Log Gamma Curves",
    ),
    "dlog_dgamut": _info(
        "dlog_dgamut",
        "DJI D-Log / D-Gamut",
        _DGAMUT,
        "D-Log",
        "DJI, D-Log/D-Gamut White Paper",
    ),
    "rec709": _info(
        "rec709",
        "Rec.709 (OETF de camara)",
        _REC709,
        "BT.709 OETF",
        "ITU-R BT.709-6",
    ),
    # sRGB comparte primarios EXACTOS con Rec.709 pero NO comparte curva: el
    # tramo lineal de sRGB tiene pendiente 12.92 y corta en 0.0031308, el de
    # Rec.709 pendiente 4.5 y corta en 0.018. Confundirlas cuesta un 57% de
    # error en las sombras. `tests/media/generate.py` codifica en sRGB, asi que
    # el material sintetico se nombra `srgb`. Lo pidio el agente B en la
    # ronda 1 de revision; no esta en `ColorSpaceName` porque `core/contracts.py`
    # es del orquestador (ver NOTAS.md seccion 9).
    "srgb": _info(
        "srgb",
        "sRGB (IEC 61966-2-1)",
        _REC709,
        "sRGB",
        "IEC 61966-2-1:1999",
    ),
    "davinci_wg_intermediate": _info(
        "davinci_wg_intermediate",
        "DaVinci Wide Gamut / DaVinci Intermediate",
        _DWG,
        "DaVinci Intermediate",
        "Blackmagic Design, DaVinci Wide Gamut white paper",
    ),
    "linear_davinci_wg": _info(
        "linear_davinci_wg",
        "DaVinci Wide Gamut escena-lineal",
        _DWG,
        "lineal",
        "Blackmagic Design, DaVinci Wide Gamut white paper",
        is_linear=True,
    ),
    "linear_rec709": _info(
        "linear_rec709",
        "Rec.709 escena-lineal",
        _REC709,
        "lineal",
        "ITU-R BT.709-6",
        is_linear=True,
    ),
}


def _space(name: ColorSpaceName) -> ColorSpaceInfo:
    try:
        return SPACES[str(name)]
    except KeyError:
        raise ValueError(f"espacio desconocido: {name!r}. Conocidos: {sorted(SPACES)}") from None


def _cat_bradford(origen: tuple[float, float], destino: tuple[float, float]) -> np.ndarray:
    """Adaptacion cromatica de Bradford entre dos puntos blancos (3, 3).

    Con origen == destino sale la identidad hasta el error de maquina, que es
    justo lo que queremos: los ocho espacios son D65 y esto no debe tintar nada.
    """
    if origen == destino:
        return np.eye(3, dtype=np.float64)
    lms_o = _BRADFORD @ xyz_from_xy(origen)
    lms_d = _BRADFORD @ xyz_from_xy(destino)
    return np.linalg.inv(_BRADFORD) @ np.diag(lms_d / lms_o) @ _BRADFORD


def primaries_matrix(src: ColorSpaceName, dst: ColorSpaceName) -> np.ndarray:
    """Matriz (3, 3) que lleva RGB **lineal** de `src` a RGB **lineal** de `dst`.

    Solo primarios: la transferencia no se toca. Se aplica como
    `lineal_dst = lineal_src @ M.T` (o `M @ pixel` para un pixel suelto).

    Si los dos espacios comparten primarios devuelve exactamente la identidad,
    sin pasar por XYZ: asi `rec709 -> linear_rec709` no mete ruido de 1e-16 en
    un sitio donde el resultado tiene que ser limpio.
    """
    a, b = _space(src), _space(dst)
    if np.array_equal(a.primaries, b.primaries) and a.whitepoint == b.whitepoint:
        return np.eye(3, dtype=np.float64)
    cat = _cat_bradford(a.whitepoint, b.whitepoint)
    return b.matrix_xyz_to_rgb @ cat @ a.matrix_rgb_to_xyz


def _aplicar_matriz(rgb: np.ndarray, m: np.ndarray) -> np.ndarray:
    """(..., 3) @ M.T conservando la forma. Sin reshape si no hace falta."""
    return rgb @ np.asarray(m, dtype=np.float64).T


def _validar_forma(arr: np.ndarray, quien: str) -> None:
    if arr.ndim < 1 or arr.shape[-1] != 3:
        raise ValueError(f"{quien}: esperaba (..., 3), llego {arr.shape}")


def _identidad_exacta(arr: np.ndarray) -> np.ndarray:
    """Copia de `arr` con el dtype que promete el modulo.

    Para float32 y float64 el cambio de dtype es un no-op, o sea que la copia
    sigue siendo bit a bit: NaN, infinitos y el signo del cero se conservan.
    Para enteros SI convierte, y tiene que hacerlo: un uint8 cruzando una
    frontera entre modulos es justo lo que prohibe el contrato 1, y el dtype
    que devuelve `convert` no puede depender de si los dos espacios coinciden
    o no (lo cazo el revisor en la ronda 1).

    Los dtypes que el modulo no sabe procesar (booleanos, complejos) lanzan
    `TypeError`, igual que por la rama que si convierte. En la ronda 1 esto era
    un pico: pasaban tal cual por aqui y lanzaban por la otra. El orquestador
    arbitro a favor de que lance por las dos (ronda 2), que es lo coherente:
    `convert` no puede comportarse distinto segun si los dos espacios coinciden.
    """
    if arr.dtype.kind not in "fiu":
        raise TypeError(f"convert: esperaba un array numerico, llego dtype={arr.dtype}")
    return arr.astype(dtype_salida(arr), copy=True)


def convert(img: np.ndarray, src: ColorSpaceName, dst: ColorSpaceName) -> np.ndarray:
    """Valores CODIFICADOS de `src` -> valores CODIFICADOS de `dst`.

    Tres pasos: decodificar la curva de `src`, pasar los primarios por la
    matriz, codificar la curva de `dst`. Los `linear_*` se saltan el primer o el
    ultimo paso porque su curva es la identidad.

    `convert(x, X, X)` devuelve una COPIA EXACTA de `x` (mismos bits, NaN
    incluidos): no se pasa por la curva ni por la matriz, porque ida y vuelta
    por un logaritmo en coma flotante no da exactamente lo que entro.
    """
    arr = np.asarray(img)
    _validar_forma(arr, "convert")
    src_s, dst_s = _space(src), _space(dst)
    if src_s.name == dst_s.name:
        return _identidad_exacta(arr)

    # Todo el camino en float64 y se baja SOLO al final: decodificar un valor
    # alto de un espacio log da numeros que no caben en float32 (ver
    # `encode_raw`), y bajar a mitad de camino convertiria en infinito un
    # intermedio cuyo resultado final si cabe de sobra.
    lineal = decode_raw(arr, src)
    m = primaries_matrix(src, dst)
    if not np.array_equal(m, np.eye(3)):
        lineal = _aplicar_matriz(lineal, m)
    return np.asarray(encode_raw(lineal, dst), dtype=dtype_salida(arr))


def to_working(img: np.ndarray, src: ColorSpaceName) -> np.ndarray:
    """Atajo de `convert(img, src, WORKING_SPACE)`."""
    return convert(img, src, WORKING_SPACE)  # type: ignore[arg-type]


def from_working(img: np.ndarray, dst: ColorSpaceName) -> np.ndarray:
    """Atajo de `convert(img, WORKING_SPACE, dst)`."""
    return convert(img, WORKING_SPACE, dst)  # type: ignore[arg-type]
