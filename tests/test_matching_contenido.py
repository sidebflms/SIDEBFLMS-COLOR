"""Tests del detector de desajuste de contenido.

Los dos que mandan son los que pide el encargo:

* `studio_scene()` contra `exterior_scene()` **tiene** que dar desajuste;
* `studio_scene(2)` contra `studio_scene(2, key_ev=-1.0)` **no** tiene que
  darlo, porque es la misma escena con otra exposicion, que es exactamente lo
  que si queremos igualar.

El resto sirve para medir el hueco entre los dos y dejarlo escrito.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import PERCENTILE_LEVELS, SAT_BINS, ColorStats
from core.matching.contenido import (
    UMBRAL_DESAJUSTE,
    desajuste_de_contenido,
    distancia_hellinger,
    rasgos_de_contenido,
)
from tests.conftest import a_trabajo
from tests.media import generate as gen


def pix(img) -> np.ndarray:
    return np.asarray(img, dtype=np.float64).reshape(-1, 3)


# ---------------------------------------------------------------------------
# Los dos casos del encargo
# ---------------------------------------------------------------------------


def test_estudio_contra_exterior_da_desajuste(estudio_trabajo, exterior_trabajo):
    hay, distancia, razones = desajuste_de_contenido(pix(estudio_trabajo), pix(exterior_trabajo))
    assert hay is True
    assert distancia > UMBRAL_DESAJUSTE
    assert razones and "no parecen comparables" in razones[0]


def test_la_misma_escena_con_otra_exposicion_no_da_desajuste():
    a = a_trabajo(gen.studio_scene(skin_tone_index=2).image)
    b = a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=-1.0).image)
    hay, distancia, _ = desajuste_de_contenido(pix(a), pix(b))
    assert hay is False
    assert distancia < UMBRAL_DESAJUSTE


@pytest.mark.parametrize("ev", [-2.0, -1.0, -0.5, 0.5, 1.5, 2.5])
def test_no_da_desajuste_en_todo_el_rango_de_exposiciones_que_probamos(ev):
    a = a_trabajo(gen.studio_scene(skin_tone_index=2).image)
    b = a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=ev).image)
    hay, distancia, _ = desajuste_de_contenido(pix(a), pix(b))
    assert hay is False, (ev, distancia)


def test_el_hueco_entre_los_dos_casos_es_de_verdad(estudio_trabajo, exterior_trabajo):
    """El umbral tiene que estar en un hueco, no rozando un dato.

    Medido: la misma escena a otra exposicion ronda 0.27-0.31 y estudio contra
    exterior 1.07. El umbral esta en 0.70. Si alguien mueve una cosa o la otra,
    esto se pone rojo antes de que se note en la GUI.
    """
    otra_exposicion = a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=-1.0).image)
    _, d_igual, _ = desajuste_de_contenido(pix(estudio_trabajo), pix(otra_exposicion))
    _, d_distinto, _ = desajuste_de_contenido(pix(estudio_trabajo), pix(exterior_trabajo))
    assert d_igual < 0.45
    assert d_distinto > 0.95
    assert d_igual < UMBRAL_DESAJUSTE < d_distinto


# ---------------------------------------------------------------------------
# Invariantes
# ---------------------------------------------------------------------------


def test_un_plano_contra_si_mismo_da_distancia_cero(estudio_trabajo):
    hay, distancia, razones = desajuste_de_contenido(pix(estudio_trabajo), pix(estudio_trabajo))
    assert hay is False
    assert distancia == pytest.approx(0.0, abs=1e-12)
    assert "contenido parecido" in razones[0]


def test_es_simetrico(estudio_trabajo, exterior_trabajo):
    a, b = pix(estudio_trabajo), pix(exterior_trabajo)
    assert desajuste_de_contenido(a, b)[1] == pytest.approx(desajuste_de_contenido(b, a)[1])


def test_un_balance_de_blancos_distinto_no_cuenta_como_otra_escena(estudio_trabajo):
    """Cambiar el balance es lo que el programa tiene que poder corregir; si el
    detector lo marcara, no se podria igualar nada."""
    a = pix(estudio_trabajo)
    b = a + np.array([0.04, 0.0, -0.05])  # desplazamiento por canal = balance
    hay, distancia, _ = desajuste_de_contenido(a, b)
    assert hay is False, distancia


def test_los_seis_tonos_de_piel_siguen_siendo_la_misma_escena(pieles_trabajo):
    """Cambiar de modelo no es cambiar de escena. Es el caso mas dificil del
    detector y el que menos margen tiene: medido, el peor par (el mas claro
    contra el mas oscuro) llega a 0.59 con el umbral en 0.70."""
    peor = 0.0
    assert len(pieles_trabajo) >= 2, (
        f"no hay nada que comprobar: con {len(pieles_trabajo)} tono(s) no hay ni un par que comparar"
    )
    for i in range(len(pieles_trabajo)):
        for j in range(i + 1, len(pieles_trabajo)):
            hay, d, _ = desajuste_de_contenido(pix(pieles_trabajo[i]), pix(pieles_trabajo[j]))
            peor = max(peor, d)
            assert hay is False, (i, j, d)
    assert peor < UMBRAL_DESAJUSTE
    assert peor > 0.3, "si el peor par baja mucho, el margen ha cambiado: mide y actualiza"


def test_una_rampa_de_gris_contra_una_escena_da_desajuste(estudio_trabajo, rampa):
    hay, _, _ = desajuste_de_contenido(pix(estudio_trabajo), pix(a_trabajo(rampa)))
    assert hay is True


def test_una_carta_de_color_no_es_un_retrato(estudio_trabajo, carta):
    hay, _, _ = desajuste_de_contenido(pix(estudio_trabajo), pix(a_trabajo(carta)))
    assert hay is True


# ---------------------------------------------------------------------------
# Que acepta y que no
# ---------------------------------------------------------------------------


def _stats_de(px: np.ndarray) -> ColorStats:
    """Un `ColorStats` construido a mano, sin pasar por `core.analysis`.

    El agente B esta escribiendo ese modulo a la vez que yo, asi que aqui se
    rellenan los campos del contrato con numpy y punto.
    """
    px = np.asarray(px, dtype=np.float64).reshape(-1, 3)
    croma = px.max(axis=1) - px.min(axis=1)
    hist, _ = np.histogram(croma, bins=SAT_BINS, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    hist = hist / max(hist.sum(), 1.0)
    perc = np.percentile(px, PERCENTILE_LEVELS, axis=0)
    return ColorStats(
        mean=px.mean(axis=0),
        std=px.std(axis=0),
        cov=np.cov(px, rowvar=False, ddof=1),
        percentiles=perc,
        black_point=perc[1],
        white_point=perc[-2],
        saturation_hist=hist,
        skin_locus=None,
        skin_fraction=0.0,
        n_samples=px.shape[0],
    )


class AnalisisFalso:
    """Lo minimo que `desajuste_de_contenido` lee de un `ClipAnalysis`."""

    def __init__(self, px, huella=None, con_pixeles=True):
        self.stats = _stats_de(px)
        self.pixels = np.asarray(px, dtype=np.float64).reshape(-1, 3) if con_pixeles else None
        self.fingerprint = huella


def test_acepta_una_imagen_entera_igual_que_una_lista(estudio_trabajo, exterior_trabajo):
    d1 = desajuste_de_contenido(estudio_trabajo, exterior_trabajo)
    d2 = desajuste_de_contenido(pix(estudio_trabajo), pix(exterior_trabajo))
    assert d1[0] == d2[0]
    assert d1[1] == pytest.approx(d2[1])


def test_acepta_colorstats_sueltos(estudio_trabajo, exterior_trabajo):
    """La via de solo `ColorStats` usa `saturation_hist` en vez del histograma
    2D de croma. Da un numero del mismo orden, NO el mismo: esta advertido en el
    docstring del modulo y por eso aqui solo se le exige que ordene bien."""
    a, b = pix(estudio_trabajo), pix(exterior_trabajo)
    otra = pix(a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=-1.0).image))
    _, d_distinto, _ = desajuste_de_contenido(_stats_de(a), _stats_de(b))
    _, d_igual, _ = desajuste_de_contenido(_stats_de(a), _stats_de(otra))
    assert d_igual < d_distinto


def test_acepta_algo_con_pinta_de_clipanalysis(estudio_trabajo, exterior_trabajo):
    a = AnalisisFalso(pix(estudio_trabajo))
    b = AnalisisFalso(pix(exterior_trabajo))
    hay, _, _ = desajuste_de_contenido(a, b)
    assert hay is True


def test_usa_la_huella_cuando_las_dos_la_traen(estudio_trabajo):
    """Dos huellas casi opuestas marcan desajuste aunque los pixeles sean el
    mismo plano. El umbral de la huella esta SIN CALIBRAR (el agente B la estaba
    escribiendo a la vez); esta puesto flojo a proposito."""
    px = pix(estudio_trabajo)
    h1 = np.zeros(96, dtype=np.float32)
    h1[0] = 1.0
    h2 = np.zeros(96, dtype=np.float32)
    h2[1] = 1.0
    sin_huella = desajuste_de_contenido(AnalisisFalso(px), AnalisisFalso(px))
    con_huella = desajuste_de_contenido(AnalisisFalso(px, h1), AnalisisFalso(px, h2))
    assert sin_huella[0] is False
    assert con_huella[0] is True


def test_una_huella_parecida_no_estropea_nada(estudio_trabajo):
    px = pix(estudio_trabajo)
    h = np.full(96, 1.0 / np.sqrt(96), dtype=np.float32)
    hay, _, _ = desajuste_de_contenido(AnalisisFalso(px, h), AnalisisFalso(px, h * 1.0))
    assert hay is False


def test_mezclar_pixeles_con_solo_stats_se_resuelve_por_la_via_comun(estudio_trabajo):
    """Si uno trae pixeles y el otro no, se baja a `ColorStats` en los dos."""
    px = pix(estudio_trabajo)
    hay, distancia, _ = desajuste_de_contenido(
        AnalisisFalso(px, con_pixeles=True), AnalisisFalso(px, con_pixeles=False)
    )
    assert hay is False
    assert distancia == pytest.approx(0.0, abs=1e-12)


def test_mezclar_pixeles_sueltos_con_stats_sueltos_lanza(estudio_trabajo):
    px = pix(estudio_trabajo)
    with pytest.raises(ValueError, match="forma comun"):
        desajuste_de_contenido(px, _stats_de(px))


def test_algo_que_no_es_nada_de_esto_lanza():
    with pytest.raises(TypeError):
        desajuste_de_contenido("un retrato", "un exterior")


# ---------------------------------------------------------------------------
# Piezas sueltas
# ---------------------------------------------------------------------------


def test_hellinger_de_un_histograma_consigo_mismo_es_cero():
    h = np.array([0.1, 0.2, 0.3, 0.4])
    assert distancia_hellinger(h, h) == pytest.approx(0.0, abs=1e-12)


def test_hellinger_de_dos_histogramas_ajenos_es_uno():
    a = np.array([1.0, 0.0, 0.0, 0.0])
    b = np.array([0.0, 0.0, 0.0, 1.0])
    assert distancia_hellinger(a, b) == pytest.approx(1.0)


def test_hellinger_con_formas_distintas_lanza():
    with pytest.raises(ValueError):
        distancia_hellinger(np.ones(4), np.ones(5))


def test_los_rasgos_no_se_mueven_con_la_exposicion(estudio_trabajo):
    """El perfil normalizado y el histograma de croma centrado son invariantes a
    la exposicion POR CONSTRUCCION. Aqui se comprueba con la exposicion
    simulada tal cual la hace el generador, que no es un desplazamiento exacto
    en el espacio de trabajo (la curva tiene un pie lineal)."""
    a = rasgos_de_contenido(pix(estudio_trabajo))
    otra = a_trabajo(gen.studio_scene(skin_tone_index=2, key_ev=1.0).image)
    b = rasgos_de_contenido(pix(otra))
    assert float(np.mean(np.abs(a["perfil"] - b["perfil"]))) < 0.05


def test_un_solo_pixel_no_rompe_los_rasgos():
    r = rasgos_de_contenido(np.array([[0.3, 0.4, 0.5]]))
    assert np.isfinite(r["perfil"]).all()
    assert np.isfinite(r["croma"]).all()


def test_pedir_una_via_que_no_existe_lanza(estudio_trabajo):
    with pytest.raises(TypeError, match="pixeles"):
        rasgos_de_contenido(_stats_de(pix(estudio_trabajo)), preferir="pixeles")
    with pytest.raises(ValueError, match="preferir"):
        rasgos_de_contenido(pix(estudio_trabajo), preferir="inventado")
