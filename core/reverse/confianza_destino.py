"""Señales para una confianza que SÍ mira el plano de destino.

POR QUÉ EXISTE (día 5, tarea 2)
--------------------------------
`ReverseResult.confidence` (en `invertir.py`) se calcula **sólo con el par de
extracción**: no sabe nada del plano al que se va a aplicar el LUT después. El
día 4 lo diagnosticó (`CALIBRACION-CONFIANZA.md` §1): la nota da 1.0 en el
100% de las extracciones sin comprimir mientras el ΔE2000 máximo fuera de
plano va de 0.50 a 39.26. No predice nada porque no puede: pregunta «¿este LUT
reproduce el plano del que salió?», que es casi siempre que sí por
construcción, y no «¿este LUT le sirve a OTRO plano?».

Este módulo calcula las señales que SÍ dependen del plano de destino, tal y
como pide el encargo del día 5: cobertura de las celdas que el destino
REALMENTE usa (no del cubo entero), y cuántas muestras reales sostienen esas
celdas. Lo que NO hace este módulo es decidir la fórmula de confianza: eso
necesita calibrarse contra error real, igual que se hizo (y falló) con la
nota actual, y esa calibración la tiene que hacer alguien que no haya escrito
esta fórmula (ver `CIFRAS.md` §12 y `NOTAS.md` de este paquete).

OJO CON "MÁS MUESTRAS = MEJOR": no está claro que lo sea. El día 4 encontró
que los peores errores fuera de plano NO salían de celdas vacías, sino de
celdas con 7 o 14 muestras (`CALIBRACION-CONFIANZA.md`, hallazgo aparte, sin
número de sección propia). Por eso `FeaturesDestino` expone el conteo crudo
(`muestras_p10_zona`, `muestras_mediana_zona`) en vez de una "cobertura de
muestras" ya convertida a 0..1: convertirla a una rampa monótona sin medir
sería repetir el error que causó que la nota actual no sirva.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.contracts import Array, CoverageMap
from core.reverse.acumulacion import pesos_trilineales

__all__ = ["FeaturesDestino", "calcular_features_destino"]


@dataclass(frozen=True)
class FeaturesDestino:
    """Señales crudas de cuánto se fía un LUT de `coverage` a un plano nuevo.

    Todo ponderado por el peso trilineal de cada píxel del destino en sus 8
    celdas vecinas, no por el vecino más cercano: un píxel que cae justo en el
    borde de una celda cubierta y una vacía está, literalmente, mitad en cada
    una, y promediar sin peso lo trataría como si estuviera entero en una.
    """

    #: Fracción 0..1 del PESO del destino que cae en celdas cubiertas
    #: (`CoverageMap.covered_mask()`). 1.0 = el destino sólo pide colores que
    #: el LUT ha visto de verdad; 0.0 = todo extrapolado/relleno.
    cobertura_destino: float
    #: Percentil 10 del conteo de muestras (`CoverageMap.counts`) en las
    #: celdas que el destino pesa, ponderado por ese mismo peso. Percentil y
    #: no mínimo: un solo vértice mal cubierto de una celda que por lo demás
    #: está bien apoyada no debería hundir la señal entera.
    muestras_p10_zona: float
    #: Mediana del mismo conteo, ponderada igual.
    muestras_mediana_zona: float
    #: Varianza media (ponderada) del residuo (`CoverageMap.variance`) en las
    #: celdas que el destino pesa. Alta = ahí el grado no se comporta como un
    #: LUT limpio (ver el contrato de `CoverageMap.variance`).
    variance_zona: float
    #: Cuántos planos entraron en la extracción del LUT (1 = un solo
    #: fotograma; `core.reverse.acumulacion` permite acumular varios). Se pasa
    #: tal cual, no se deriva de `coverage`: `CoverageMap` no sabe cuántos
    #: planos hay detrás de sus conteos, sólo el total.
    planos_acumulados: int
    #: Cuántos píxeles del destino se pudieron evaluar (tras filtrar NaN/inf).
    n_pixeles_destino: int


def _percentil_ponderado(valores: np.ndarray, pesos: np.ndarray, q: float) -> float:
    """Percentil `q` (0..100) de `valores`, ponderado por `pesos`. `pesos >= 0`."""
    orden = np.argsort(valores)
    v = valores[orden]
    w = pesos[orden]
    acumulado = np.cumsum(w)
    total = acumulado[-1] if acumulado.size else 0.0
    if total <= 0.0:
        return 0.0
    objetivo = (q / 100.0) * total
    idx = int(np.searchsorted(acumulado, objetivo))
    idx = min(idx, v.size - 1)
    return float(v[idx])


def calcular_features_destino(
    coverage: CoverageMap,
    plano_destino: Array,
    *,
    planos_acumulados: int = 1,
) -> FeaturesDestino:
    """Calcula `FeaturesDestino` para `plano_destino` contra `coverage`.

    `plano_destino` son valores en el mismo dominio que `coverage` (el cubo
    del LUT: `WORKING_SPACE`, 0..1 nominal), forma `(..., 3)`. Los píxeles no
    finitos se descartan antes de nada, igual que hace el resto de `core`.
    """
    px = np.asarray(plano_destino, dtype=np.float64).reshape(-1, 3)
    finitos = np.isfinite(px).all(axis=1)
    px = px[finitos]

    if px.shape[0] == 0:
        return FeaturesDestino(
            cobertura_destino=0.0,
            muestras_p10_zona=0.0,
            muestras_mediana_zona=0.0,
            variance_zona=0.0,
            planos_acumulados=int(planos_acumulados),
            n_pixeles_destino=0,
        )

    n = coverage.size
    idx, w = pesos_trilineales(px, n)  # (8, M) cada uno

    covered = coverage.covered_mask().reshape(-1).astype(np.float64)
    counts = coverage.counts.reshape(-1).astype(np.float64)
    variance = coverage.variance.reshape(-1).astype(np.float64)

    idx_flat = idx.reshape(-1)
    w_flat = w.reshape(-1)

    cobertura_destino = float(np.sum(w_flat * covered[idx_flat]) / max(np.sum(w_flat), 1e-12))
    counts_por_celda = counts[idx_flat]
    variance_por_celda = variance[idx_flat]

    return FeaturesDestino(
        cobertura_destino=cobertura_destino,
        muestras_p10_zona=_percentil_ponderado(counts_por_celda, w_flat, 10.0),
        muestras_mediana_zona=_percentil_ponderado(counts_por_celda, w_flat, 50.0),
        variance_zona=float(np.sum(w_flat * variance_por_celda) / max(np.sum(w_flat), 1e-12)),
        planos_acumulados=int(planos_acumulados),
        n_pixeles_destino=int(px.shape[0]),
    )
