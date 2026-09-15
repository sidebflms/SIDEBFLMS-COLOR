"""LUT deliberadamente malos, para probar el QC (y para el test entregable T4).

Están **aquí y no dentro de un test** a propósito: el orquestador los necesita
para T4, el revisor los va a usar para discutir los umbrales y la GUI podría
querer un "enséñame qué detectas". Un generador escondido en un `test_*.py` es
un generador que hay que copiar y pegar.

CADA UNO ROMPE UNA COSA SOLA
----------------------------
Los seis LUT de aquí están calibrados para que `qc_lut()` saque **un único
código** (el que dice su nombre) y ninguno más. No es casualidad ni es fácil:
un hundimiento demasiado grande en la curva no sólo rompe la monotonía, también
dispara el detector de banding, y entonces el test ya no prueba lo que dice
probar. Si tocas los parámetros por defecto, vuelve a mirar
`tests/test_io_qc.py::test_cada_lut_malo_saca_su_codigo_y_solo_el_suyo`.

Todos devuelven un `LUT3D` de verdad, con la convención 4: `table[ri, gi, bi]`.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from core.contracts import LUT3D

__all__ = [
    "lut_desde_curvas",
    "lut_solo_rojo",
    "lut_no_monotono",
    "lut_con_banding",
    "lut_fuera_de_gamut",
    "lut_plano",
    "lut_con_nan",
    "lut_canales_invertidos",
    "catalogo_luts_malos",
]


def lut_desde_curvas(
    curva_r: np.ndarray,
    curva_g: np.ndarray,
    curva_b: np.ndarray,
    *,
    title: str = "SIDEB COLOR",
) -> LUT3D:
    """Tres curvas 1D (una por canal) -> el LUT 3D separable equivalente.

    `tabla[ri, gi, bi] = (curva_r[ri], curva_g[gi], curva_b[bi])`. Es la forma
    más limpia de construir un LUT que toque un canal y sólo uno, que es
    justo lo que hace falta para probar que los ejes no se han cambiado.
    """
    r = np.asarray(curva_r, dtype=np.float32)
    g = np.asarray(curva_g, dtype=np.float32)
    b = np.asarray(curva_b, dtype=np.float32)
    if not (r.shape == g.shape == b.shape) or r.ndim != 1:
        raise ValueError(f"las tres curvas tienen que ser 1D y del mismo largo: {r.shape} {g.shape} {b.shape}")
    n = int(r.shape[0])
    tabla = np.empty((n, n, n, 3), dtype=np.float32)
    tabla[..., 0] = r[:, None, None]
    tabla[..., 1] = g[None, :, None]
    tabla[..., 2] = b[None, None, :]
    return LUT3D(table=tabla, title=title)


def _rampa(size: int) -> np.ndarray:
    return np.linspace(0.0, 1.0, size, dtype=np.float32)


# ---------------------------------------------------------------------------
# El canario de los ejes (este es BUENO, no malo)
# ---------------------------------------------------------------------------


def lut_solo_rojo(size: int = 17, *, ganancia: float = 0.5) -> LUT3D:
    """LUT que **sólo** toca el rojo: `R -> R * ganancia`, verde y azul intactos.

    No está roto: está aquí porque es el canario de la convención 4. Si alguien
    se equivoca con `transpose(2,1,0,3)` al leer o escribir un `.cube`, este LUT
    vuelve tocando el azul en vez del rojo y el test lo caza al instante. Con
    `ganancia=0.5` la asimetría es evidente: el rojo llega como mucho a 0.5 y
    los otros dos a 1.0.

    Pasa el QC limpio, y así tiene que seguir.
    """
    t = _rampa(size)
    return lut_desde_curvas(t * float(ganancia), t, t, title="Solo rojo")


# ---------------------------------------------------------------------------
# Los malos
# ---------------------------------------------------------------------------


def lut_no_monotono(size: int = 17, *, eje: int = 0, caida: float = 0.01) -> LUT3D:
    """LUT donde subir la entrada de un canal BAJA su salida en un punto.

    La caída es pequeña (0.01) a propósito: con un hundimiento grande el cambio
    de pendiente dispararía también el detector de banding y el LUT dejaría de
    probar una cosa sola.
    """
    if eje not in (0, 1, 2):
        raise ValueError(f"eje tiene que ser 0, 1 o 2, y llegó {eje}")
    if size < 3:
        raise ValueError(f"hace falta size >= 3 para hundir una celda intermedia, llegó {size}")
    curvas = [_rampa(size), _rampa(size), _rampa(size)]
    rota = curvas[eje].copy()
    medio = size // 2
    rota[medio] = rota[medio - 1] - float(caida)
    curvas[eje] = rota
    return lut_desde_curvas(*curvas, title=f"No monotono en {eje}")


def lut_con_banding(size: int = 17, *, eje: int = 0, salto: float = 0.3) -> LUT3D:
    """LUT con un escalón brusco: en un degradado se ve como una banda.

    La rampa se comprime a `1 - salto` y se le suma `salto` de golpe a partir de
    la celda central, así que el LUT sigue siendo monótono y sigue cabiendo en
    0..1: lo único que está mal es el escalón.
    """
    if eje not in (0, 1, 2):
        raise ValueError(f"eje tiene que ser 0, 1 o 2, y llegó {eje}")
    if size < 3:
        raise ValueError(f"hace falta size >= 3 para meter un escalon, llegó {size}")
    if not (0.0 < salto < 1.0):
        raise ValueError(f"salto tiene que estar en (0, 1), y llegó {salto}")
    curvas = [_rampa(size), _rampa(size), _rampa(size)]
    rota = curvas[eje].astype(np.float64) * (1.0 - salto)
    rota[size // 2 :] += salto
    curvas[eje] = rota.astype(np.float32)
    return lut_desde_curvas(*curvas, title=f"Banding en {eje}")


def lut_fuera_de_gamut(size: int = 17, *, exceso: float = 0.25) -> LUT3D:
    """LUT que se sale por los dos lados: mínimo `-exceso`, máximo `1 + exceso`.

    Sigue siendo monótono y con paso constante (o sea, sin banding): lo único
    que está mal es que Resolve va a recortar por arriba y por abajo.
    """
    if exceso <= 0.0:
        raise ValueError(f"exceso tiene que ser > 0, y llegó {exceso}")
    t = _rampa(size).astype(np.float64)
    curva = (t * (1.0 + 2.0 * exceso) - exceso).astype(np.float32)
    return lut_desde_curvas(curva, curva, curva, title="Fuera de gamut")


def lut_plano(size: int = 17, *, color: tuple[float, float, float] = (0.5, 0.5, 0.5)) -> LUT3D:
    """LUT que manda la imagen entera a un solo color. Todas las celdas iguales."""
    tabla = np.empty((size, size, size, 3), dtype=np.float32)
    tabla[..., 0] = float(color[0])
    tabla[..., 1] = float(color[1])
    tabla[..., 2] = float(color[2])
    return LUT3D(table=tabla, title="Plano")


def lut_con_nan(
    size: int = 17, *, celda: tuple[int, int, int] | None = None, canal: int = 0
) -> LUT3D:
    """Identidad con un NaN metido en una celda concreta.

    `LUT3D` no valida que la tabla sea finita (a propósito: no es su trabajo),
    así que esto se construye sin protestar y revienta más tarde, que es
    exactamente el caso que el QC tiene que cazar antes.

    `celda=None` coge una celda interior cualquiera que exista seguro para el
    tamaño pedido (con `size=5` una celda fija como (3, 4, 5) se sale).
    """
    if celda is None:
        celda = (size // 3, size // 2, size - 2)
    if not all(0 <= c < size for c in celda):
        raise ValueError(f"la celda {celda} se sale de un LUT de tamaño {size}")
    if canal not in (0, 1, 2):
        raise ValueError(f"canal tiene que ser 0, 1 o 2, y llegó {canal}")
    tabla = np.array(LUT3D.identity(size).table, dtype=np.float32, copy=True)
    tabla[celda][canal] = np.nan
    return LUT3D(table=tabla, title="Con NaN")


def lut_canales_invertidos(size: int = 17) -> LUT3D:
    """El desastre de la convención 4: `table[ri, gi, bi] = (b, g, r)`.

    Es lo que sale si alguien se salta el `transpose(2, 1, 0, 3)` al leer un
    `.cube`. Aplicado a una imagen, cambia el rojo por el azul.
    """
    ident = np.asarray(LUT3D.identity(size).table)
    return LUT3D(table=np.ascontiguousarray(ident[..., ::-1]), title="Canales invertidos")


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

#: código de QC esperado -> generador. Lo usan el test T4 y `tests/test_io_qc.py`.
_GENERADORES: dict[str, Callable[[int], LUT3D]] = {
    "no_monotonia": lambda n: lut_no_monotono(n),
    "banding": lambda n: lut_con_banding(n),
    "gamut": lambda n: lut_fuera_de_gamut(n),
    "lut_plano": lambda n: lut_plano(n),
    "no_finito": lambda n: lut_con_nan(n),
    "canales_invertidos": lambda n: lut_canales_invertidos(n),
}


def catalogo_luts_malos(size: int = 17) -> dict[str, LUT3D]:
    """`{codigo_de_qc: LUT roto}`. La clave es el código que `qc_lut` tiene que
    sacar, y ningún otro."""
    return {codigo: gen(size) for codigo, gen in _GENERADORES.items()}
