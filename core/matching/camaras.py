"""Igualado de varias camaras contra una referencia. Es el test T3 del encargo,
escrito como funcion reutilizable para que no viva solo dentro de un test.

QUE MIDE Y POR QUE ASI
----------------------
Aqui las imagenes **si** se corresponden pixel a pixel: es la misma escena
grabada por varias camaras. Por eso el ΔE2000 entre dos de ellas esta definido
directamente, sin transportes ni proxys, y es la medida honesta:

    delta_e_medio_antes   = media de ΔE2000 medio sobre TODOS los pares (i, j)
    delta_e_medio_despues = lo mismo, con cada camara ya corregida

Se promedia sobre todos los pares y no solo contra la referencia a proposito: lo
que Mario ve en la timeline es un plano detras de otro, y le molesta la
diferencia entre el plano 2 y el 3 igual que la diferencia de cada uno con el 1.

Las imagenes entran ya en `WORKING_SPACE`: quien las convierte desde el espacio
de cada camara es quien sabe de que camara son (el agente B), no esto.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from core.color import delta_e2000_mean
from core.contracts import LUT_SIZE_DEFAULT, WORKING_SPACE, MatchResult
from core.matching.cdl_fit import SEMILLA, submuestrea
from core.matching.empareja import emparejar

__all__ = ["ResultadoCamaras", "delta_e_medio_entre_pares", "igualar_camaras"]


@dataclass(frozen=True)
class ResultadoCamaras:
    """Lo que sale de igualar un grupo de camaras contra una de ellas."""

    delta_e_medio_antes: float
    delta_e_medio_despues: float
    delta_e_por_par_antes: dict[tuple[int, int], float]
    delta_e_por_par_despues: dict[tuple[int, int], float]
    corregidas: tuple[np.ndarray, ...]
    emparejamientos: tuple[MatchResult | None, ...]
    indice_referencia: int

    @property
    def mejora(self) -> float:
        """Cuantas veces se ha reducido la diferencia entre camaras."""
        if self.delta_e_medio_despues <= 0:
            return float("inf")
        return self.delta_e_medio_antes / self.delta_e_medio_despues


def delta_e_medio_entre_pares(
    imagenes: list[np.ndarray] | tuple[np.ndarray, ...],
    *,
    espacio: str = WORKING_SPACE,
) -> tuple[float, dict[tuple[int, int], float]]:
    """ΔE2000 medio sobre todos los pares. Necesita imagenes de la misma forma."""
    formas = {np.shape(img) for img in imagenes}
    if len(formas) != 1:
        raise ValueError(f"las imagenes tienen que tener la misma forma; llegaron {formas}")
    por_par: dict[tuple[int, int], float] = {}
    for i, j in combinations(range(len(imagenes)), 2):
        por_par[(i, j)] = float(delta_e2000_mean(imagenes[i], imagenes[j], espacio))  # type: ignore[arg-type]
    if not por_par:
        return 0.0, por_par
    return float(np.mean(list(por_par.values()))), por_par


def igualar_camaras(
    imagenes: list[np.ndarray] | tuple[np.ndarray, ...],
    *,
    indice_referencia: int = 0,
    con_lut: bool = False,
    tam_lut: int = LUT_SIZE_DEFAULT,
    max_pixeles: int = 120000,
) -> ResultadoCamaras:
    """Lleva todas las camaras al espacio de la que diga `indice_referencia`.

    `imagenes` son `(alto, ancho, 3)` en `WORKING_SPACE` y de la misma forma.
    Devuelve el ΔE2000 medio entre camaras antes y despues, par a par, mas las
    imagenes ya corregidas y el `MatchResult` de cada una (la referencia lleva
    `None`, porque a la referencia no se le hace nada).
    """
    imgs = [np.asarray(img) for img in imagenes]
    if len(imgs) < 2:
        raise ValueError("igualar_camaras: hacen falta al menos dos camaras")
    if not 0 <= indice_referencia < len(imgs):
        raise ValueError(f"igualar_camaras: indice_referencia fuera de rango: {indice_referencia}")

    antes, por_par_antes = delta_e_medio_entre_pares(imgs)

    ref_plana = imgs[indice_referencia].reshape(-1, 3)
    (ref_muestra,) = submuestrea(ref_plana, maximo=max_pixeles, semilla=SEMILLA)

    corregidas: list[np.ndarray] = []
    empar: list[MatchResult | None] = []
    for i, img in enumerate(imgs):
        if i == indice_referencia:
            corregidas.append(img)
            empar.append(None)
            continue
        (muestra,) = submuestrea(img.reshape(-1, 3), maximo=max_pixeles, semilla=SEMILLA)
        res = emparejar(muestra, ref_muestra, con_lut=con_lut, tam_lut=tam_lut)
        salida = res.cdl.apply(img)
        if res.lut is not None:
            salida = res.lut.apply(salida)
        corregidas.append(np.asarray(salida, dtype=img.dtype))
        empar.append(res)

    despues, por_par_despues = delta_e_medio_entre_pares(corregidas)
    return ResultadoCamaras(
        delta_e_medio_antes=float(antes),
        delta_e_medio_despues=float(despues),
        delta_e_por_par_antes=por_par_antes,
        delta_e_por_par_despues=por_par_despues,
        corregidas=tuple(corregidas),
        emparejamientos=tuple(empar),
        indice_referencia=int(indice_referencia),
    )
