"""Ajuste de un ASC CDL a un par de nubes de pixeles, por minimos cuadrados.

EL PROBLEMA
-----------
Un CDL es, en este orden exacto (lo dice el estandar y lo implementa
`CDL.apply`):

    x   = entrada * slope + offset
    x   = max(x, 0)
    out = x ** power
    out = luma + saturation * (out - luma)        luma con pesos Rec.709

Diez parametros: tres slope, tres offset, tres power y una saturacion. Es
**lineal en slope y offset**, pero no en `power` (esta en el exponente) ni de
forma conjunta con la saturacion. No hay solucion cerrada limpia, asi que va en
dos fases.

FASE 1 — arranque lineal (cerrado)
----------------------------------
Con `power = 1` y `saturation = 1` el modelo es `d_c = o_c * s_c + t_c` canal a
canal: tres regresiones lineales ponderadas de dos parametros, resueltas con
`lstsq`. Si un canal del origen no tiene varianza (imagen de un solo color), la
pendiente no es identificable: se deja `slope = 1` y el offset se lleva la
diferencia de medias. Despues, con esa prediccion ya hecha, la saturacion
tambien sale de una regresion lineal de un parametro (proyeccion del croma del
destino sobre el croma de la prediccion).

FASE 2 — refinado no lineal (`scipy.optimize.least_squares`, `trf`)
-------------------------------------------------------------------
Se refinan los diez a la vez partiendo de la fase 1. Metodo `trf` porque es el
unico de los tres que acepta **limites**, y aqui los limites no son un adorno:

    slope       [1e-3, 1e3]
    offset      [-10, 10]
    power       [0.05, 20]      <- lo importante
    saturation  [0, 5]

`CDL.__post_init__` lanza si algun `power` es <= 0, y un optimizador sin sujetar
se va a un power negativo en cuanto el residuo es plano (pasa con material de un
solo color: `x ** p` con x constante da lo mismo para infinitos pares de
slope/power). Sujetar el power a >= 0.05 no es maquillaje: **un power de 0.05 ya
es un grado imposible**, ningun colorista lo escribe; el limite esta ahi para
que el fallo salga como "power pegado al limite" (y baje la confianza) en vez de
como una excepcion a media noche. Lo mismo con el resto: 1e-3..1e3 de slope
cubre de sobra cualquier grado real.

ORIGEN Y DESTINO DE DISTINTA LONGITUD
-------------------------------------
Un ajuste por minimos cuadrados necesita PAREJAS. Si las dos listas no miden lo
mismo no hay parejas, asi que en ese caso se construye el destino con el
transporte MKL del origen (`transporte_mkl`), que es exactamente lo que hace
`emparejar`: la nube de destino se resume en su media y su covarianza, se
transporta el origen, y el CDL se ajusta contra esa version transportada. Queda
documentado aqui porque cambia el significado del residuo: ya no es "cuanto me
alejo del destino" sino "cuanto se aleja el CDL del transporte ideal".
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from core.contracts import CDL, LUMA_REC709
from core.matching.mkl import aplicar_mkl, pixeles_finitos, transporte_mkl

__all__ = [
    "LIMITES_CDL",
    "MAX_PUNTOS_AJUSTE",
    "SEMILLA",
    "aplicar_cdl_inverso",
    "ajustar_cdl",
    "submuestrea",
]

#: Limites del optimizador. Ver el docstring del modulo: no son cosmeticos.
LIMITES_CDL: dict[str, tuple[float, float]] = {
    "slope": (1e-3, 1e3),
    "offset": (-10.0, 10.0),
    "power": (0.05, 20.0),
    "saturation": (0.0, 5.0),
}

#: Tope de puntos que ve el optimizador. Mas de esto no mejora el ajuste (son
#: diez parametros) y multiplica el tiempo por nada.
MAX_PUNTOS_AJUSTE: int = 20000

#: Semilla del submuestreo. Fija a proposito: dos ejecuciones dan el mismo CDL.
SEMILLA: int = 20260915


def submuestrea(
    *arrays: np.ndarray, maximo: int = MAX_PUNTOS_AJUSTE, semilla: int = SEMILLA
) -> tuple[np.ndarray, ...]:
    """Recorta varios arrays a `maximo` filas con LOS MISMOS indices.

    Determinista: misma entrada, mismos indices, mismo resultado.
    """
    n = int(arrays[0].shape[0])
    if n <= maximo:
        return arrays
    idx = np.random.default_rng(semilla).choice(n, size=maximo, replace=False)
    idx.sort()
    return tuple(a[idx] for a in arrays)


def _empareja(
    origen_px: np.ndarray, destino_px: np.ndarray
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Devuelve dos listas de pixeles de la MISMA longitud, y si hubo que
    transportar (ver el docstring del modulo)."""
    o = np.asarray(origen_px, dtype=np.float64)
    d = np.asarray(destino_px, dtype=np.float64)
    if o.ndim == 0 or o.shape[-1] != 3 or d.ndim == 0 or d.shape[-1] != 3:
        raise ValueError(f"ajustar_cdl: esperaba (..., 3) en los dos, llego {o.shape} y {d.shape}")
    o = o.reshape(-1, 3)
    d = d.reshape(-1, 3)
    if o.shape[0] == d.shape[0]:
        bueno = np.isfinite(o).all(axis=1) & np.isfinite(d).all(axis=1)
        if not bueno.any():
            raise ValueError("ajustar_cdl: no queda ni una pareja de pixeles finita")
        return o[bueno], d[bueno], False
    o_f, _ = pixeles_finitos(o, "ajustar_cdl(origen)")
    d_f, _ = pixeles_finitos(d, "ajustar_cdl(destino)")
    if o_f.shape[0] == 0 or d_f.shape[0] == 0:
        raise ValueError("ajustar_cdl: alguna de las dos listas no tiene pixeles finitos")
    a, b = transporte_mkl(o_f, d_f)
    return o_f, aplicar_mkl(o_f, a, b), True


def _aplica_parametros(px: np.ndarray, p: np.ndarray) -> np.ndarray:
    """La formula de `CDL.apply`, escrita aparte para el optimizador.

    Es bit a bit el mismo calculo; no se construye un `CDL` en cada iteracion
    porque el constructor valida y eso son decenas de miles de validaciones
    inutiles. Hay un test que comprueba que las dos coinciden.
    """
    slope = p[0:3]
    offset = p[3:6]
    power = p[6:9]
    sat = p[9]
    x = px * slope + offset
    np.maximum(x, 0.0, out=x)
    out = np.power(x, power)
    if sat != 1.0:
        luma = out @ LUMA_REC709
        out = luma[..., None] + sat * (out - luma[..., None])
    return out


def _arranque_lineal(o: np.ndarray, d: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Fase 1: slope/offset por canal y saturacion, todo cerrado."""
    slope = np.ones(3)
    offset = np.zeros(3)
    raiz_w = np.sqrt(w)
    for c in range(3):
        col = o[:, c]
        # Varianza ponderada: si el canal es constante la pendiente no existe.
        media = np.average(col, weights=w)
        var = np.average((col - media) ** 2, weights=w)
        if var <= 1e-18 * max(abs(media) ** 2, 1e-12):
            offset[c] = np.average(d[:, c], weights=w) - media
            continue
        a = np.stack([col, np.ones_like(col)], axis=1) * raiz_w[:, None]
        sol, *_ = np.linalg.lstsq(a, d[:, c] * raiz_w, rcond=None)
        slope[c], offset[c] = float(sol[0]), float(sol[1])

    slope = np.clip(slope, *LIMITES_CDL["slope"])
    offset = np.clip(offset, *LIMITES_CDL["offset"])
    power = np.ones(3)

    # Saturacion: con la prediccion ya hecha es una regresion de un parametro.
    pred = _aplica_parametros(o, np.concatenate([slope, offset, power, [1.0]]))
    croma_p = pred - (pred @ LUMA_REC709)[:, None]
    croma_d = d - (d @ LUMA_REC709)[:, None]
    den = float(np.sum(w[:, None] * croma_p * croma_p))
    sat = float(np.sum(w[:, None] * croma_p * croma_d) / den) if den > 1e-18 else 1.0
    sat = float(np.clip(sat, *LIMITES_CDL["saturation"]))
    return np.concatenate([slope, offset, power, [sat]])


def ajustar_cdl(
    origen_px: np.ndarray, destino_px: np.ndarray, *, pesos: np.ndarray | None = None
) -> CDL:
    """Ajusta el CDL que mejor lleva `origen_px` a `destino_px`.

    Las dos listas son `(..., 3)`. Si miden lo mismo se emparejan pixel a pixel;
    si no, el destino se resume en su distribucion y se transporta (ver el
    docstring del modulo). `pesos` es `(N,)` sobre las filas del ORIGEN, para
    dar mas importancia a una zona (por ejemplo a la piel); se normaliza solo.

    Devuelve siempre un `CDL` valido: los limites del optimizador garantizan que
    `power > 0`, que es lo que exige el constructor.
    """
    o, d, _ = _empareja(origen_px, destino_px)
    if pesos is None:
        w = np.ones(o.shape[0], dtype=np.float64)
    else:
        w = np.asarray(pesos, dtype=np.float64).reshape(-1)
        if w.shape[0] != np.asarray(origen_px).reshape(-1, 3).shape[0]:
            raise ValueError(
                f"ajustar_cdl: 'pesos' tiene {w.shape[0]} filas y el origen "
                f"{np.asarray(origen_px).reshape(-1, 3).shape[0]}"
            )
        if w.shape[0] != o.shape[0]:
            raise ValueError(
                "ajustar_cdl: con 'pesos' no puedo descartar filas no finitas; "
                "limpia tu los pixeles antes o no pases pesos"
            )
        if np.any(w < 0) or not np.isfinite(w).all():
            raise ValueError("ajustar_cdl: los pesos tienen que ser finitos y >= 0")
    if w.sum() <= 0:
        raise ValueError("ajustar_cdl: todos los pesos son cero")
    w = w / w.mean()

    o, d, w = submuestrea(o, d, w)
    p0 = _arranque_lineal(o, d, w)

    lo = np.concatenate(
        [
            np.full(3, LIMITES_CDL["slope"][0]),
            np.full(3, LIMITES_CDL["offset"][0]),
            np.full(3, LIMITES_CDL["power"][0]),
            [LIMITES_CDL["saturation"][0]],
        ]
    )
    hi = np.concatenate(
        [
            np.full(3, LIMITES_CDL["slope"][1]),
            np.full(3, LIMITES_CDL["offset"][1]),
            np.full(3, LIMITES_CDL["power"][1]),
            [LIMITES_CDL["saturation"][1]],
        ]
    )
    p0 = np.clip(p0, lo + 1e-9, hi - 1e-9)
    raiz_w = np.sqrt(w)[:, None]

    def residuo(p: np.ndarray) -> np.ndarray:
        return ((_aplica_parametros(o, p) - d) * raiz_w).ravel()

    sol = least_squares(
        residuo,
        p0,
        bounds=(lo, hi),
        method="trf",
        x_scale="jac",
        ftol=1e-12,
        xtol=1e-12,
        gtol=1e-12,
        max_nfev=400,
    )
    p = sol.x if np.isfinite(sol.cost) else p0
    # Si el refinado empeora el arranque (pasa con nubes degeneradas), me quedo
    # con el arranque: no hay ninguna razon para devolver algo peor.
    if float(np.sum(residuo(p) ** 2)) > float(np.sum(residuo(p0) ** 2)):
        p = p0
    return CDL(
        slope=tuple(float(v) for v in p[0:3]),
        offset=tuple(float(v) for v in p[3:6]),
        power=tuple(float(v) for v in p[6:9]),
        saturation=float(p[9]),
    )


def aplicar_cdl_inverso(cdl: CDL, px: np.ndarray) -> np.ndarray:
    """Deshace un CDL. Es exacto donde el CDL no recorto, y una extrapolacion
    sujeta al borde donde si.

    El `max(x, 0)` del estandar tira informacion: todo lo que entro negativo sale
    como 0 y no hay forma de saber de donde venia. Aqui se devuelve el 0, o sea
    el borde. Se usa para construir el LUT de residuo, que se aplica DESPUES del
    CDL y por tanto necesita saber que entrada produjo cada salida.
    """
    arr = np.asarray(px, dtype=np.float64)
    if arr.ndim == 0 or arr.shape[-1] != 3:
        raise ValueError(f"aplicar_cdl_inverso: esperaba (..., 3), llego {arr.shape}")
    sat = float(cdl.saturation)
    if abs(sat) < 1e-6:
        # Saturacion 0 aplasta todo el croma: no es invertible. Se hace lo unico
        # sensato, que es tratar la salida como si fuera ya acromatica.
        out = arr
    else:
        luma = arr @ LUMA_REC709
        out = luma[..., None] + (arr - luma[..., None]) / sat
    base = np.maximum(out, 0.0)
    x = np.power(base, 1.0 / np.asarray(cdl.power))
    return (x - np.asarray(cdl.offset)) / np.asarray(cdl.slope)
