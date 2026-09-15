"""Casos frontera. Aqui no se busca que salgan numeros bonitos: se busca que
salga algo definido, documentado y coherente, o un error legible.

La lista es la del encargo: imagen negra, blanca, saturada del todo, un solo
pixel, un solo color, valores fuera de 0..1, NaN de entrada, division por cero en
la covarianza y en la normalizacion de la huella.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.analysis import (
    analizar_imagen,
    estadisticas,
    huella_de_contenido,
    saturacion_hsv,
)
from core.contracts import FINGERPRINT_LEN, PERCENTILE_LEVELS, SAT_BINS

NEGRA = np.zeros((16, 16, 3), dtype=np.float32)
BLANCA = np.ones((16, 16, 3), dtype=np.float32)
UN_COLOR = np.full((16, 16, 3), 0.37, dtype=np.float32)
UN_PIXEL = np.full((1, 1, 3), 0.37, dtype=np.float32)

SATURADA = np.zeros((16, 16, 3), dtype=np.float32)
SATURADA[:, :8, 0] = 1.0
SATURADA[:, 8:, 2] = 1.0

TODOS = {
    "negra": NEGRA,
    "blanca": BLANCA,
    "saturada": SATURADA,
    "un color": UN_COLOR,
    "un pixel": UN_PIXEL,
}


# ---------------------------------------------------------------------------
# Lo que tiene que cumplirse SIEMPRE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", list(TODOS))
def test_ningun_borde_deja_nan_por_sorpresa(nombre):
    """Sin NaN de entrada no puede haber NaN de salida. Nunca."""
    s = estadisticas(TODOS[nombre])
    for campo in ("mean", "std", "cov", "percentiles", "black_point", "white_point"):
        valor = np.asarray(getattr(s, campo))
        assert np.isfinite(valor).all(), f"{nombre}: {campo} trae NaN o infinito"
    assert np.isfinite(s.saturation_hist).all()


@pytest.mark.parametrize("nombre", list(TODOS))
def test_el_histograma_sigue_sumando_uno(nombre):
    s = estadisticas(TODOS[nombre])
    assert s.saturation_hist.shape == (SAT_BINS,)
    assert s.saturation_hist.sum() == pytest.approx(1.0)


@pytest.mark.parametrize("nombre", list(TODOS))
def test_la_huella_sigue_teniendo_norma_uno(nombre):
    h = huella_de_contenido(TODOS[nombre])
    assert h.shape == (FINGERPRINT_LEN,)
    assert float(np.linalg.norm(h)) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("nombre", list(TODOS))
def test_analizar_imagen_no_se_cae_con_ninguno(nombre):
    a = analizar_imagen(TODOS[nombre], clip_id=nombre)
    assert a.stats.n_samples == TODOS[nombre][..., 0].size
    assert a.stats.skin_locus is None


# ---------------------------------------------------------------------------
# Caso a caso
# ---------------------------------------------------------------------------


def test_imagen_totalmente_negra():
    s = estadisticas(NEGRA)
    assert np.allclose(s.mean, 0.0)
    assert np.allclose(s.std, 0.0)
    assert np.allclose(s.cov, 0.0)
    assert np.allclose(s.black_point, 0.0) and np.allclose(s.white_point, 0.0)
    # Sin luz no hay saturacion que medir: todo al primer bin.
    assert s.saturation_hist[0] == pytest.approx(1.0)


def test_imagen_totalmente_blanca():
    s = estadisticas(BLANCA)
    assert np.allclose(s.mean, 1.0)
    assert np.allclose(s.cov, 0.0)
    assert s.saturation_hist[0] == pytest.approx(1.0), "el blanco es neutro, no saturado"


def test_imagen_totalmente_saturada():
    s = estadisticas(SATURADA)
    assert s.saturation_hist[-1] == pytest.approx(1.0)
    assert float(saturacion_hsv(SATURADA).min()) == 1.0


def test_un_solo_pixel():
    s = estadisticas(UN_PIXEL)
    assert s.n_samples == 1
    assert np.allclose(s.mean, 0.37)
    assert np.allclose(s.std, 0.0)
    # La covarianza NO esta definida con un solo pixel: se decide ceros.
    assert np.array_equal(s.cov, np.zeros((3, 3)))
    # Y todos los percentiles son el mismo valor.
    assert np.allclose(s.percentiles, 0.37)


def test_imagen_de_un_solo_color():
    s = estadisticas(UN_COLOR)
    assert np.allclose(s.cov, 0.0)
    assert np.allclose(s.black_point, s.white_point)
    assert np.allclose(s.std, 0.0)


def test_una_lista_de_un_solo_pixel():
    s = estadisticas(np.array([[0.2, 0.4, 0.6]], dtype=np.float32))
    assert s.n_samples == 1
    assert np.array_equal(s.cov, np.zeros((3, 3)))


# ---------------------------------------------------------------------------
# Fuera de 0..1
# ---------------------------------------------------------------------------


def test_valores_muy_por_encima_de_uno(escena_exterior):
    """El sol de `exterior_scene` esta a 9.0 en escena-lineal. No se recorta."""
    assert escena_exterior.image.max() > 8.0
    s = estadisticas(escena_exterior.image, space="linear_rec709")
    assert np.isfinite(s.mean).all()
    assert s.saturation_hist.sum() == pytest.approx(1.0)
    # Y el percentil alto se entera de que hay un sol ahi.
    mediana = s.percentiles[list(PERCENTILE_LEVELS).index(50.0)]
    assert s.white_point.max() > mediana.max()


def test_valores_negativos_se_conservan_y_no_rompen_la_saturacion():
    """Fuera de gamut se producen negativos, y el contrato manda preservarlos."""
    img = np.full((8, 8, 3), 0.4, dtype=np.float32)
    img[..., 2] = -0.2
    s = estadisticas(img)
    assert s.mean[2] < 0.0, "el negativo se ha recortado por el camino"
    assert np.isfinite(s.saturation_hist).all()
    assert s.saturation_hist.sum() == pytest.approx(1.0)
    # (max - min) / max con max = 0.4 y min = -0.2 daria 1.5: se sujeta a 1.
    assert float(saturacion_hsv(img).max()) <= 1.0


def test_un_pixel_con_maximo_negativo_da_saturacion_cero():
    img = np.full((4, 4, 3), -0.3, dtype=np.float32)
    img[..., 0] = -0.1
    assert float(saturacion_hsv(img).max()) == 0.0


def test_infinitos_de_entrada():
    img = np.full((8, 8, 3), 0.3, dtype=np.float32)
    img[0, 0] = np.inf
    s = estadisticas(img)
    assert not np.isfinite(s.mean).all(), "un infinito tiene que verse en la media"
    # El histograma descarta el pixel roto y sigue sumando 1.
    assert s.saturation_hist.sum() == pytest.approx(1.0)
    assert any("no finitos" in w for w in analizar_imagen(img, clip_id="inf").warnings)


# ---------------------------------------------------------------------------
# NaN: se propaga, como en core.color
# ---------------------------------------------------------------------------


def test_un_nan_se_propaga_a_la_estadistica(estudio_trabajo):
    """Misma politica que `core.color`: un plano roto tiene que SALIR roto.

    Si la media usara `nanmean`, el agente C recibiria un numero plausible sobre
    material corrupto y nadie se enteraria.
    """
    sucia = np.array(estudio_trabajo, copy=True)
    sucia[5, 5] = np.nan
    s = estadisticas(sucia)
    assert np.isnan(s.mean).all()
    assert np.isnan(s.std).all()
    assert np.isnan(s.cov).all()
    assert np.isnan(s.percentiles).all()
    assert np.isnan(s.black_point).all() and np.isnan(s.white_point).all()


def test_el_histograma_es_la_excepcion_documentada(estudio_trabajo):
    """El histograma cuenta SOLO pixeles finitos, para poder seguir sumando 1."""
    sucia = np.array(estudio_trabajo, copy=True)
    sucia[5, 5] = np.nan
    s = estadisticas(sucia)
    assert s.saturation_hist.sum() == pytest.approx(1.0)
    limpio = estadisticas(estudio_trabajo).saturation_hist
    assert 0.5 * np.abs(s.saturation_hist - limpio).sum() < 1e-4


def test_con_todo_nan_el_histograma_se_queda_a_cero():
    """Unico caso en el que NO suma 1, y esta escrito en el codigo y en NOTAS."""
    s = estadisticas(np.full((8, 8, 3), np.nan, dtype=np.float32))
    assert s.saturation_hist.sum() == 0.0
    assert np.isnan(s.mean).all()


def test_el_nan_deja_aviso_en_el_clipanalysis(estudio_trabajo):
    sucia = np.array(estudio_trabajo, copy=True)
    sucia[5:8, 5:8] = np.nan
    a = analizar_imagen(sucia, clip_id="rota")
    assert any("no finitos" in w for w in a.warnings)
    assert any("9 pixeles" in w for w in a.warnings)


def test_el_nan_no_cuenta_como_piel(estudio_trabajo):
    """`skin_mask_oklab` devuelve False para un NaN, y aqui se comprueba que el
    locus no se envenena por ello."""
    sucia = np.array(estudio_trabajo, copy=True)
    sucia[100:150, 250:350] = np.nan  # justo encima de la cara
    s = estadisticas(sucia)
    assert s.skin_locus is None or np.isfinite(s.skin_locus).all()
