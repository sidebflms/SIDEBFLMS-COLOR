"""`core.reverse.confianza_destino`: solo se prueba que CALCULA bien, no que
PREDICE bien. Que prediga o no el error real es una pregunta de calibracion,
y esta puntualmente fuera de este archivo (ver NOTAS.md del paquete y
CIFRAS.md); estos tests fijan aritmetica sobre un `CoverageMap` sintetico
donde el resultado se puede calcular a mano.
"""

from __future__ import annotations

import numpy as np

from core.contracts import CoverageMap
from core.reverse.confianza_destino import calcular_features_destino


def _coverage_3(counts: np.ndarray, variance: np.ndarray | None = None) -> CoverageMap:
    """Cubo 3x3x3: nodos exactos en 0.0, 0.5 y 1.0 por eje."""
    if variance is None:
        variance = np.zeros((3, 3, 3), dtype=np.float32)
    return CoverageMap(counts=counts.astype(np.int32), variance=variance.astype(np.float32), min_samples=4)


def test_pixel_exacto_en_celda_cubierta_da_cobertura_uno():
    counts = np.zeros((3, 3, 3))
    counts[0, 0, 0] = 10  # >= min_samples (4): cubierta
    cov = _coverage_3(counts)
    f = calcular_features_destino(cov, np.array([[0.0, 0.0, 0.0]]))
    assert f.cobertura_destino == 1.0
    assert f.muestras_mediana_zona == 10.0


def test_pixel_exacto_en_celda_no_cubierta_da_cobertura_cero():
    counts = np.zeros((3, 3, 3))
    counts[0, 0, 0] = 1  # < min_samples (4): no cubierta
    cov = _coverage_3(counts)
    f = calcular_features_destino(cov, np.array([[0.0, 0.0, 0.0]]))
    assert f.cobertura_destino == 0.0
    assert f.muestras_mediana_zona == 1.0


def test_pixel_a_medias_entre_dos_celdas_pondera():
    """Pixel en (0.25, 0, 0): a mitad de camino entre el nodo 0 (0.0) y el 1
    (0.5) del eje R. Peso 0.5 en cada uno."""
    counts = np.zeros((3, 3, 3))
    counts[0, 0, 0] = 100  # cubierta
    counts[1, 0, 0] = 0  # no cubierta
    cov = _coverage_3(counts)
    f = calcular_features_destino(cov, np.array([[0.25, 0.0, 0.0]]))
    assert abs(f.cobertura_destino - 0.5) < 1e-9


def test_variance_se_pondera_igual_que_cobertura():
    counts = np.full((3, 3, 3), 10)  # todo cubierto, para aislar la varianza
    variance = np.zeros((3, 3, 3))
    variance[0, 0, 0] = 2.0
    cov = _coverage_3(counts, variance)
    f = calcular_features_destino(cov, np.array([[0.0, 0.0, 0.0]]))
    assert abs(f.variance_zona - 2.0) < 1e-9


def test_nan_e_inf_se_descartan_antes_de_calcular():
    counts = np.full((3, 3, 3), 10)
    cov = _coverage_3(counts)
    con_basura = np.array([[0.0, 0.0, 0.0], [np.nan, 0.0, 0.0], [np.inf, 0.0, 0.0]])
    f = calcular_features_destino(cov, con_basura)
    assert f.n_pixeles_destino == 1


def test_todo_no_finito_da_features_vacias_sin_lanzar():
    counts = np.full((3, 3, 3), 10)
    cov = _coverage_3(counts)
    f = calcular_features_destino(cov, np.array([[np.nan, np.nan, np.nan]]))
    assert f.n_pixeles_destino == 0
    assert f.cobertura_destino == 0.0


def test_planos_acumulados_se_pasa_tal_cual():
    counts = np.full((3, 3, 3), 10)
    cov = _coverage_3(counts)
    f = calcular_features_destino(cov, np.array([[0.0, 0.0, 0.0]]), planos_acumulados=40)
    assert f.planos_acumulados == 40


def test_muchos_pixeles_en_celdas_mixtas_da_cobertura_intermedia():
    """La mitad de los pixeles del destino en una celda cubierta, la mitad en
    una vacia (los dos exactos en su nodo, sin interpolar entre ellos)."""
    counts = np.zeros((3, 3, 3))
    counts[0, 0, 0] = 50  # cubierta
    counts[2, 2, 2] = 0  # no cubierta
    cov = _coverage_3(counts)
    px = np.array([[0.0, 0.0, 0.0]] * 30 + [[1.0, 1.0, 1.0]] * 70)
    f = calcular_features_destino(cov, px)
    assert abs(f.cobertura_destino - 0.30) < 1e-9


def test_percentil_10_es_sensible_a_la_cola_baja():
    """90 pixeles en una celda con 100 muestras, 10 en una con 1: el p10
    ponderado tiene que caer en la cola baja, no en la mediana de 100."""
    counts = np.zeros((3, 3, 3))
    counts[0, 0, 0] = 100
    counts[1, 0, 0] = 1
    cov = _coverage_3(counts)
    px = np.array([[0.0, 0.0, 0.0]] * 90 + [[0.5, 0.0, 0.0]] * 10)
    f = calcular_features_destino(cov, px)
    assert f.muestras_p10_zona == 1.0
    assert f.muestras_mediana_zona == 100.0
