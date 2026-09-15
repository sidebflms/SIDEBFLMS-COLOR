"""Funciones de transferencia (curvas log) de las camaras que nos importan.

Todas las formulas estan implementadas AQUI a partir de la documentacion
publicada del fabricante. No se envuelve `colour-science`: colour se usa solo
en los tests, como juez independiente.

CONVENCION DE ENTRADA (lo lineal)
---------------------------------
`log_encode(x, espacio)` recibe **escena-lineal con 0.18 = 18% de gris**, tal y
como lo produce `tests/media/generate.py`. Los valores negativos y los mayores
que 1 son legales y se preservan hasta donde la formula publicada lo permita.

CONVENCION DE SALIDA (lo codificado)
------------------------------------
El valor codificado es el **code value normalizado** del fabricante: lo que
sale de dividir el codigo de 10 bits entre 1023. Es la convencion en la que
estan publicados los numeros que todo el mundo cita (S-Log3 al 18% = 0.4106,
V-Log al 18% = 0.4233, DaVinci Intermediate al 18% = 0.3360). Canon publica su
curva en dos formas equivalentes; aqui se usa la de code value (la que Canon
llama v1.2), que es la misma curva escalada a rango legal, para que los seis
espacios compartan convencion.

CANON Y EL 0.9
--------------
La formula de Canon Log 3 esta definida sobre una entrada donde el 18% de gris
vale 0.2, no 0.18 (es decir, reflectancia dividida entre 0.9). Sony, Panasonic,
DJI y Blackmagic definen la suya sobre la reflectancia directamente. Por eso
`_clog3_*` divide y multiplica por 0.9 y las demas no. No es un apano: esta en
los documentos.

NaN
---
Politica del modulo entero: **se propaga**. Un NaN de entrada sale como NaN, no
lanza excepcion. Un pixel roto no debe tumbar un render de 40 minutos; que se
vea en la imagen y en las estadisticas.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from core.contracts import ColorSpaceName

__all__ = [
    "log_encode",
    "log_decode",
    "encode_raw",
    "decode_raw",
    "dtype_salida",
    "TRANSFERENCIAS",
]


# ---------------------------------------------------------------------------
# Utilidad: evaluar una curva a trozos sin evaluar ramas fuera de su dominio
# ---------------------------------------------------------------------------


def _piecewise(
    x: np.ndarray,
    condiciones: list[np.ndarray],
    funciones: list[Callable[[np.ndarray], np.ndarray]],
) -> np.ndarray:
    """Evalua cada rama SOLO donde toca (con mascara, no con `np.where`).

    Con `np.where` las tres ramas se calculan enteras y las que estan fuera de
    su dominio sueltan warnings o NaN que luego hay que barrer. Con mascara no
    se calculan siquiera.

    Lo que no cae en ninguna condicion sale NaN. Como las comparaciones con NaN
    son falsas, un NaN de entrada acaba ahi solo: la propagacion es gratis.
    """
    out = np.full(x.shape, np.nan, dtype=np.float64)
    pendiente = np.ones(x.shape, dtype=bool)
    for cond, fn in zip(condiciones, funciones, strict=True):
        m = cond & pendiente
        if m.any():
            out[m] = fn(x[m])
        pendiente &= ~cond
    return out


# ---------------------------------------------------------------------------
# Sony S-Log3
# ---------------------------------------------------------------------------
# Fuente: Sony, "Technical Summary for S-Gamut3.Cine/S-Log3 and S-Gamut3/S-Log3".
# Anclas publicadas: 18% de gris -> 420/1023; punto de corte en 0.01125.

_SLOG3_CUT = 0.01125
_SLOG3_A = 171.2102946929  # code value (10 bits) del punto de corte, rama lineal
_SLOG3_PIVOTE = 0.01  # el "+0.01" del logaritmo
_SLOG3_GRIS = 0.18


def _slog3_encode(x: np.ndarray) -> np.ndarray:
    log = lambda v: (  # noqa: E731
        420.0 + np.log10((v + _SLOG3_PIVOTE) / (_SLOG3_GRIS + _SLOG3_PIVOTE)) * 261.5
    ) / 1023.0
    lin = lambda v: (v * (_SLOG3_A - 95.0) / _SLOG3_CUT + 95.0) / 1023.0  # noqa: E731
    return _piecewise(x, [x >= _SLOG3_CUT, x < _SLOG3_CUT], [log, lin])


#: Valor codificado exacto en el punto de corte, por la rama que usa el codificador.
#: Ojo: NO es _SLOG3_A/1023. La curva de Sony tiene un salto de ~3e-6 ahi, y el
#: umbral del decodificador tiene que ser el del codificador o la ida y vuelta
#: deja de ser exacta justo en el corte.
_SLOG3_UMBRAL = float(_slog3_encode(np.array([_SLOG3_CUT]))[0])


def _slog3_decode(y: np.ndarray) -> np.ndarray:
    log = lambda v: (  # noqa: E731
        10.0 ** ((v * 1023.0 - 420.0) / 261.5) * (_SLOG3_GRIS + _SLOG3_PIVOTE) - _SLOG3_PIVOTE
    )
    lin = lambda v: (v * 1023.0 - 95.0) * _SLOG3_CUT / (_SLOG3_A - 95.0)  # noqa: E731
    return _piecewise(y, [y >= _SLOG3_UMBRAL, y < _SLOG3_UMBRAL], [log, lin])


# ---------------------------------------------------------------------------
# Panasonic V-Log
# ---------------------------------------------------------------------------
# Fuente: Panasonic, "V-Log/V-Gamut Reference Manual".
# Anclas publicadas: reflectancia 0% -> 0.125 (7.3 IRE), 18% -> ~42 IRE,
# 90% -> ~61 IRE. cut1 = 0.01 mapea exactamente a cut2 = 0.181.

_VLOG_CUT1 = 0.01
_VLOG_CUT2 = 0.181
_VLOG_B = 0.00873
_VLOG_C = 0.241514
_VLOG_D = 0.598206


def _vlog_encode(x: np.ndarray) -> np.ndarray:
    lin = lambda v: 5.6 * v + 0.125  # noqa: E731
    log = lambda v: _VLOG_C * np.log10(v + _VLOG_B) + _VLOG_D  # noqa: E731
    return _piecewise(x, [x < _VLOG_CUT1, x >= _VLOG_CUT1], [lin, log])


_VLOG_UMBRAL = float(_vlog_encode(np.array([_VLOG_CUT1]))[0])


def _vlog_decode(y: np.ndarray) -> np.ndarray:
    lin = lambda v: (v - 0.125) / 5.6  # noqa: E731
    log = lambda v: 10.0 ** ((v - _VLOG_D) / _VLOG_C) - _VLOG_B  # noqa: E731
    return _piecewise(y, [y < _VLOG_UMBRAL, y >= _VLOG_UMBRAL], [lin, log])


# ---------------------------------------------------------------------------
# Canon Log 3
# ---------------------------------------------------------------------------
# Fuente: Canon, "White Paper on Canon Log Gamma Curves" (revision 1.2, la que
# publica la curva ya en code value normalizado de rango legal).
# La entrada de la formula es reflectancia/0.9: el 18% de gris entra como 0.2.
# Anclas publicadas: 18% de gris -> 32.8 IRE en rango completo, que es
# exactamente el 0.343389 de code value que devuelve esta implementacion; los
# injertos entre ramas estan en +/-0.014 de la entrada de la formula.

_CLOG3_ESCALA_ENTRADA = 0.9
_CLOG3_INJERTO = 0.014
_CLOG3_K = 14.98325
_CLOG3_PEND_LOG = 0.36726845
_CLOG3_OFF_NEG = 0.12783901
_CLOG3_PEND_LIN = 1.9754798
_CLOG3_OFF_LIN = 0.12512219
_CLOG3_OFF_POS = 0.12240537


def _clog3_encode(x: np.ndarray) -> np.ndarray:
    t = x / _CLOG3_ESCALA_ENTRADA
    neg = lambda v: -_CLOG3_PEND_LOG * np.log10(-v * _CLOG3_K + 1.0) + _CLOG3_OFF_NEG  # noqa: E731
    lin = lambda v: _CLOG3_PEND_LIN * v + _CLOG3_OFF_LIN  # noqa: E731
    pos = lambda v: _CLOG3_PEND_LOG * np.log10(v * _CLOG3_K + 1.0) + _CLOG3_OFF_POS  # noqa: E731
    return _piecewise(
        t,
        [t < -_CLOG3_INJERTO, t <= _CLOG3_INJERTO, t > _CLOG3_INJERTO],
        [neg, lin, pos],
    )


#: Umbrales del decodificador: los valores codificados de los dos injertos POR LA
#: RAMA LINEAL, que es la que usa el codificador en +/-0.014 (el `<=`).
_CLOG3_UMBRAL_BAJO = _CLOG3_PEND_LIN * (-_CLOG3_INJERTO) + _CLOG3_OFF_LIN
_CLOG3_UMBRAL_ALTO = _CLOG3_PEND_LIN * _CLOG3_INJERTO + _CLOG3_OFF_LIN


def _clog3_decode(y: np.ndarray) -> np.ndarray:
    neg = lambda v: -(  # noqa: E731
        10.0 ** ((_CLOG3_OFF_NEG - v) / _CLOG3_PEND_LOG) - 1.0
    ) / _CLOG3_K
    lin = lambda v: (v - _CLOG3_OFF_LIN) / _CLOG3_PEND_LIN  # noqa: E731
    pos = lambda v: (10.0 ** ((v - _CLOG3_OFF_POS) / _CLOG3_PEND_LOG) - 1.0) / _CLOG3_K  # noqa: E731
    t = _piecewise(
        y,
        [y < _CLOG3_UMBRAL_BAJO, y <= _CLOG3_UMBRAL_ALTO, y > _CLOG3_UMBRAL_ALTO],
        [neg, lin, pos],
    )
    return t * _CLOG3_ESCALA_ENTRADA


# ---------------------------------------------------------------------------
# DJI D-Log
# ---------------------------------------------------------------------------
# Fuente: DJI, "D-Log / D-Gamut White Paper".
# Es la unica de las cinco cuyo salto en el punto de corte va en el sentido malo
# (la rama log queda POR DEBAJO de la lineal). Ver `_DLOG_HUECO` mas abajo y la
# nota en NOTAS.md: hay una ventana de ~6e-6 en x donde la ida y vuelta no puede
# ser exacta. No es un bug mio, es la curva publicada.

_DLOG_CUT = 0.0078
_DLOG_PEND_LIN = 6.025
_DLOG_OFF_LIN = 0.0929
_DLOG_A = 0.9892
_DLOG_B = 0.0108
_DLOG_C = 0.256663
_DLOG_D = 0.584555


def _dlog_encode(x: np.ndarray) -> np.ndarray:
    lin = lambda v: _DLOG_PEND_LIN * v + _DLOG_OFF_LIN  # noqa: E731
    log = lambda v: np.log10(v * _DLOG_A + _DLOG_B) * _DLOG_C + _DLOG_D  # noqa: E731
    return _piecewise(x, [x <= _DLOG_CUT, x > _DLOG_CUT], [lin, log])


_DLOG_UMBRAL = _DLOG_PEND_LIN * _DLOG_CUT + _DLOG_OFF_LIN


def _dlog_decode(y: np.ndarray) -> np.ndarray:
    lin = lambda v: (v - _DLOG_OFF_LIN) / _DLOG_PEND_LIN  # noqa: E731
    log = lambda v: (10.0 ** ((v - _DLOG_D) / _DLOG_C) - _DLOG_B) / _DLOG_A  # noqa: E731
    return _piecewise(y, [y <= _DLOG_UMBRAL, y > _DLOG_UMBRAL], [lin, log])


# ---------------------------------------------------------------------------
# DaVinci Intermediate
# ---------------------------------------------------------------------------
# Fuente: Blackmagic Design, "DaVinci Wide Gamut / DaVinci Intermediate"
# (white paper que acompana a Resolve 17+).
# Anclas publicadas: 18% de gris -> 0.336; LIN_CUT * M == LOG_CUT.

_DI_A = 0.0075
_DI_B = 7.0
_DI_C = 0.07329248
_DI_M = 10.44426855
_DI_LIN_CUT = 0.00262409
_DI_LOG_CUT = 0.02740668


def _di_encode(x: np.ndarray) -> np.ndarray:
    lin = lambda v: v * _DI_M  # noqa: E731
    log = lambda v: _DI_C * (np.log2(v + _DI_A) + _DI_B)  # noqa: E731
    return _piecewise(x, [x <= _DI_LIN_CUT, x > _DI_LIN_CUT], [lin, log])


_DI_UMBRAL = _DI_LIN_CUT * _DI_M


def _di_decode(y: np.ndarray) -> np.ndarray:
    lin = lambda v: v / _DI_M  # noqa: E731
    log = lambda v: 2.0 ** (v / _DI_C - _DI_B) - _DI_A  # noqa: E731
    return _piecewise(y, [y <= _DI_UMBRAL, y > _DI_UMBRAL], [lin, log])


# ---------------------------------------------------------------------------
# Rec.709 (OETF de camara de la BT.709) y sRGB
# ---------------------------------------------------------------------------
# Fuentes: ITU-R BT.709-6 apartado 1.2, e IEC 61966-2-1:1999 para sRGB.
#
# Ojo con Rec.709: esto es la OETF de CAMARA (4.5x / 1.099 x^0.45 - 0.099), NO
# la EOTF de pantalla de la BT.1886. Es lo que hace falta para pasar de
# escena-lineal a un Rec.709 "de video", que es el uso que le damos.
#
# Y OJO con no confundir Rec.709 y sRGB: son curvas DISTINTAS. El tramo lineal
# de sRGB tiene pendiente 12.92 y corta en 0.0031308; el de Rec.709 tiene
# pendiente 4.5 y corta en 0.018. Confundirlas cuesta un 57% de error en las
# sombras: un 0.045 lineal vuelve como 0.0705. `tests/media/generate.py` codifica
# en sRGB, asi que el material sintetico se nombra `srgb`, nunca `rec709`.
#
# NEGATIVOS (decidido en la ronda 1 de revision, ver NOTAS.md seccion 9):
# las dos normas definen su curva solo en 0..1. Aqui se extiende **prolongando
# el tramo lineal** (4.5x y 12.92x respectivamente), que es lo que hace
# colour-science. Antes se extendia por simetria impar; se cambio para que la
# afirmacion "nuestras curvas son la misma funcion que las de colour-science"
# valga en TODO el dominio y no solo en x >= 0. Las dos extensiones son
# monotonas e invertibles, asi que el contrato 1 se cumple con cualquiera de
# las dos; lo que decide es poder verificarlo.

_BT709_CUT = 0.018
_BT709_ALFA = 1.099
_BT709_BETA = 0.099
_BT709_PEND = 4.5


def _bt709_encode(x: np.ndarray) -> np.ndarray:
    lin = lambda v: _BT709_PEND * v  # noqa: E731
    pot = lambda v: _BT709_ALFA * v**0.45 - _BT709_BETA  # noqa: E731
    return _piecewise(x, [x < _BT709_CUT, x >= _BT709_CUT], [lin, pot])


#: Valor codificado del corte por la rama que usa el codificador (la potencia).
_BT709_UMBRAL = _BT709_ALFA * _BT709_CUT**0.45 - _BT709_BETA


def _bt709_decode(y: np.ndarray) -> np.ndarray:
    lin = lambda v: v / _BT709_PEND  # noqa: E731
    pot = lambda v: ((v + _BT709_BETA) / _BT709_ALFA) ** (1.0 / 0.45)  # noqa: E731
    return _piecewise(y, [y < _BT709_UMBRAL, y >= _BT709_UMBRAL], [lin, pot])


_SRGB_CUT = 0.0031308
_SRGB_ALFA = 1.055
_SRGB_BETA = 0.055
_SRGB_PEND = 12.92
_SRGB_GAMMA = 2.4


def _srgb_encode(x: np.ndarray) -> np.ndarray:
    lin = lambda v: _SRGB_PEND * v  # noqa: E731
    pot = lambda v: _SRGB_ALFA * v ** (1.0 / _SRGB_GAMMA) - _SRGB_BETA  # noqa: E731
    return _piecewise(x, [x <= _SRGB_CUT, x > _SRGB_CUT], [lin, pot])


#: El codificador usa la rama LINEAL en el corte (el `<=`), asi que el umbral del
#: decodificador es 12.92 * 0.0031308 = 0.040449936, y no el 0.04045 redondeado
#: que imprime la norma. Con el 0.04045 la ida y vuelta dejaria de ser exacta en
#: una franja de 5e-9 en x.
_SRGB_UMBRAL = _SRGB_PEND * _SRGB_CUT


def _srgb_decode(y: np.ndarray) -> np.ndarray:
    lin = lambda v: v / _SRGB_PEND  # noqa: E731
    pot = lambda v: ((v + _SRGB_BETA) / _SRGB_ALFA) ** _SRGB_GAMMA  # noqa: E731
    return _piecewise(y, [y <= _SRGB_UMBRAL, y > _SRGB_UMBRAL], [lin, pot])


# ---------------------------------------------------------------------------
# Identidad (los espacios escena-lineales)
# ---------------------------------------------------------------------------


def _identidad(v: np.ndarray) -> np.ndarray:
    # Copia deliberada: si devolvieramos `v` tal cual, `log_encode(x, "linear_*")`
    # con x en float64 devolveria el MISMO array que entro y quien tocara el
    # resultado estaria tocando la entrada de otro.
    return v.copy()


#: espacio -> (codificar, decodificar). Es la tabla que consulta `log_encode`.
TRANSFERENCIAS: dict[str, tuple[Callable[[np.ndarray], np.ndarray], ...]] = {
    "slog3_sgamut3cine": (_slog3_encode, _slog3_decode),
    "vlog_vgamut": (_vlog_encode, _vlog_decode),
    "clog3_cinemagamut": (_clog3_encode, _clog3_decode),
    "dlog_dgamut": (_dlog_encode, _dlog_decode),
    "rec709": (_bt709_encode, _bt709_decode),
    "srgb": (_srgb_encode, _srgb_decode),
    "davinci_wg_intermediate": (_di_encode, _di_decode),
    "linear_davinci_wg": (_identidad, _identidad),
    "linear_rec709": (_identidad, _identidad),
}


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def _dtype_salida(arr: np.ndarray) -> np.dtype:
    """float64 entra, float64 sale. Cualquier otra cosa sale float32.

    El contrato 1 pide float32 en las fronteras entre modulos, y eso es lo que
    devuelve por defecto. Pero si alguien entra en float64 a proposito (los
    tests de ida y vuelta, `core.analysis`) se le respeta la precision: bajarlo
    a float32 seria tirar 16 bits de mantisa sin que lo haya pedido nadie.
    """
    return np.dtype(np.float64) if arr.dtype == np.float64 else np.dtype(np.float32)


def _preparar(img: np.ndarray) -> tuple[np.ndarray, np.dtype]:
    arr = np.asarray(img)
    if arr.dtype.kind not in "fiu":
        raise TypeError(f"esperaba un array numerico, llego dtype={arr.dtype}")
    return np.asarray(arr, dtype=np.float64), _dtype_salida(arr)


def _curva(space: ColorSpaceName, indice: int) -> Callable[[np.ndarray], np.ndarray]:
    try:
        return TRANSFERENCIAS[str(space)][indice]
    except KeyError:
        raise ValueError(
            f"espacio desconocido: {space!r}. Conocidos: {sorted(TRANSFERENCIAS)}"
        ) from None


def encode_raw(linear: np.ndarray, space: ColorSpaceName) -> np.ndarray:
    """Como `log_encode` pero SIEMPRE en float64. Uso interno del paquete.

    Existe por un desbordamiento real: decodificar un valor alto de un espacio
    log da numeros enormes (un 9.5 codificado en S-Log3 son 8.4e39 de
    escena-lineal), y eso NO cabe en float32 (que se queda en 3.4e38). Si
    `convert` bajara a float32 entre paso y paso, ese valor intermedio seria
    infinito y el resultado final, un NaN, aunque el resultado final si cupiera
    de sobra. Los pasos intermedios van en float64 y solo se baja al final.
    """
    arr, _ = _preparar(linear)
    return _curva(space, 0)(arr)


def decode_raw(encoded: np.ndarray, space: ColorSpaceName) -> np.ndarray:
    """Como `log_decode` pero SIEMPRE en float64. Ver `encode_raw`."""
    arr, _ = _preparar(encoded)
    return _curva(space, 1)(arr)


def dtype_salida(img: np.ndarray) -> np.dtype:
    """float64 si entro float64, float32 en cualquier otro caso."""
    return _dtype_salida(np.asarray(img))


def log_encode(linear: np.ndarray, space: ColorSpaceName) -> np.ndarray:
    """Escena-lineal (0.18 = 18% de gris) -> valores codificados de `space`.

    NO toca los primarios: es solo la curva. Para cambiar de gamut usa
    `primaries_matrix` o `convert`.

    Los espacios `linear_*` devuelven la entrada tal cual (su transferencia es
    la identidad), pero convertida al dtype de salida.
    """
    arr, dtype = _preparar(linear)
    return np.asarray(_curva(space, 0)(arr), dtype=dtype)


def log_decode(encoded: np.ndarray, space: ColorSpaceName) -> np.ndarray:
    """Valores codificados de `space` -> escena-lineal (0.18 = 18% de gris)."""
    arr, dtype = _preparar(encoded)
    return np.asarray(_curva(space, 1)(arr), dtype=dtype)
