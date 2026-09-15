"""`ColorStats`: que el contrato se rellena entero, bien, y con criterio.

Lo que se comprueba aqui no es que los numeros "salgan": es que signifiquen lo
que dicen que significan. El punto negro tiene que aguantar pixeles muertos, el
histograma de saturacion tiene que sumar 1 siempre que haya algo que sumar, y el
locus de piel tiene que caer donde cae la piel.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.analysis import (
    FRACCION_PIEL_MINIMA,
    PERCENTIL_BLANCO,
    PERCENTIL_NEGRO,
    analizar_imagen,
    estadisticas,
    saturacion_hsv,
)
from core.color import rgb_to_oklab
from core.contracts import PERCENTILE_LEVELS, SAT_BINS, WORKING_SPACE, ColorStats
from tests.conftest import a_trabajo

# ---------------------------------------------------------------------------
# Forma, tipo y contrato
# ---------------------------------------------------------------------------


def test_rellena_el_contrato_entero(estudio_trabajo):
    s = estadisticas(estudio_trabajo)
    assert s.mean.shape == (3,) and s.mean.dtype == np.float64
    assert s.std.shape == (3,) and s.std.dtype == np.float64
    assert s.cov.shape == (3, 3) and s.cov.dtype == np.float64
    assert s.percentiles.shape == (len(PERCENTILE_LEVELS), 3)
    assert s.black_point.shape == (3,) and s.white_point.shape == (3,)
    assert s.saturation_hist.shape == (SAT_BINS,)
    assert s.skin_locus is not None and s.skin_locus.shape == (3,)
    assert 0.0 <= s.skin_fraction <= 1.0
    assert s.n_samples == 640 * 360


def test_acepta_imagen_y_lista_de_pixeles(estudio_trabajo):
    """(alto, ancho, 3) y (N, 3) tienen que dar exactamente lo mismo."""
    a = estadisticas(estudio_trabajo)
    b = estadisticas(estudio_trabajo.reshape(-1, 3))
    assert np.allclose(a.mean, b.mean)
    assert np.allclose(a.cov, b.cov)
    assert np.allclose(a.percentiles, b.percentiles)
    assert np.allclose(a.saturation_hist, b.saturation_hist)
    assert a.skin_fraction == pytest.approx(b.skin_fraction)
    assert np.allclose(a.skin_locus, b.skin_locus)


def test_acepta_una_pila_de_fotogramas(estudio_trabajo):
    pila = np.stack([estudio_trabajo, estudio_trabajo])
    s = estadisticas(pila)
    uno = estadisticas(estudio_trabajo)
    assert s.n_samples == 2 * uno.n_samples
    assert np.allclose(s.mean, uno.mean)


def test_formas_imposibles_dan_un_error_legible():
    with pytest.raises(ValueError, match="esperaba"):
        estadisticas(np.zeros((10, 10)))
    with pytest.raises(ValueError, match="esperaba"):
        estadisticas(np.zeros((10, 10, 4)))
    with pytest.raises(ValueError, match="ni un pixel"):
        estadisticas(np.zeros((0, 3)))


def test_se_serializa_y_vuelve(estudio_trabajo):
    s = estadisticas(estudio_trabajo)
    vuelta = ColorStats.from_dict(s.to_dict())
    assert np.allclose(vuelta.mean, s.mean)
    assert np.allclose(vuelta.saturation_hist, s.saturation_hist)
    assert np.allclose(vuelta.skin_locus, s.skin_locus)
    assert vuelta.n_samples == s.n_samples


# ---------------------------------------------------------------------------
# Percentiles, punto negro y punto blanco
# ---------------------------------------------------------------------------


def test_los_percentiles_van_en_el_orden_del_contrato(estudio_trabajo):
    s = estadisticas(estudio_trabajo)
    for canal in range(3):
        columna = s.percentiles[:, canal]
        assert np.all(np.diff(columna) >= 0), "los percentiles no son crecientes"
    assert np.allclose(s.percentiles[list(PERCENTILE_LEVELS).index(50.0)],
                       np.median(estudio_trabajo.reshape(-1, 3), axis=0))


def test_punto_negro_y_blanco_son_los_percentiles_1_y_99(estudio_trabajo):
    s = estadisticas(estudio_trabajo)
    niveles = list(PERCENTILE_LEVELS)
    assert np.array_equal(s.black_point, s.percentiles[niveles.index(PERCENTIL_NEGRO)])
    assert np.array_equal(s.white_point, s.percentiles[niveles.index(PERCENTIL_BLANCO)])


def test_un_pixel_muerto_no_decide_el_punto_negro(estudio_trabajo):
    """La razon de ser del percentil 1, con los numeros de por que no es el 0.1.

    Se matan 144 pixeles (0,06% de la imagen) y se mira cuanto se mueve cada
    candidato a punto negro. Medido sobre el retrato de estudio:

    | candidato | desplazamiento relativo maximo |
    |---|---|
    | minimo    | colapsa a 0 |
    | p0.1      | 13,8% |
    | **p1 (el elegido)** | **2,4%** |
    | p5        | 0,1% |

    El p5 aguantaria aun mas, pero el 5% de los pixeles de un plano oscuro ya no
    es "el negro": es media imagen. El p1 es el punto donde deja de mandarlo un
    accidente sin dejar de ser el negro.
    """
    niveles = list(PERCENTILE_LEVELS)
    sucia = np.array(estudio_trabajo, dtype=np.float32, copy=True)
    sucia[:12, :12] = 0.0  # 144 pixeles muertos de 230.400
    limpia = estadisticas(estudio_trabajo)
    rota = estadisticas(sucia)

    rel_p1 = np.abs(rota.black_point - limpia.black_point) / limpia.black_point
    i = niveles.index(0.1)
    rel_p01 = np.abs(rota.percentiles[i] - limpia.percentiles[i]) / limpia.percentiles[i]
    assert rel_p1.max() < 0.03, f"el p1 se ha movido un {rel_p1.max():.1%}"
    assert (rel_p01 > 3 * rel_p1).all(), "el p0.1 tendria que ser claramente mas fragil"
    # Y el minimo se entera del todo, que es justo por lo que no se usa.
    assert sucia.min() == 0.0
    assert estudio_trabajo.min() > 0.0


def test_un_especular_no_decide_el_punto_blanco(estudio_trabajo):
    sucia = np.array(estudio_trabajo, dtype=np.float32, copy=True)
    sucia[:12, :12] = 20.0
    assert np.allclose(
        estadisticas(sucia).white_point, estadisticas(estudio_trabajo).white_point, atol=2e-3
    )
    assert sucia.max() == 20.0


def test_los_valores_fuera_de_rango_se_conservan():
    """El contrato 1 manda: nada se recorta. El sol del exterior esta a 9.0."""
    img = np.full((8, 8, 3), 3.5, dtype=np.float32)
    img[0, 0] = -0.25
    s = estadisticas(img)
    assert s.white_point.max() > 1.0
    assert s.percentiles[0].min() < 0.0 or s.mean.max() > 1.0


# ---------------------------------------------------------------------------
# Covarianza
# ---------------------------------------------------------------------------


def test_la_covarianza_es_simetrica_y_semidefinida(estudio_trabajo):
    s = estadisticas(estudio_trabajo)
    assert np.allclose(s.cov, s.cov.T)
    autovalores = np.linalg.eigvalsh(s.cov)
    assert autovalores.min() > -1e-12
    # La diagonal es la varianza: tiene que cuadrar con std**2.
    assert np.allclose(np.diag(s.cov), s.std**2, rtol=1e-5)


def test_covarianza_de_una_imagen_de_un_solo_color_es_cero():
    s = estadisticas(np.full((32, 32, 3), 0.42, dtype=np.float32))
    assert np.allclose(s.cov, 0.0)
    assert np.isfinite(s.cov).all(), "una imagen plana no puede dar NaN en la covarianza"


def test_covarianza_de_un_solo_pixel_es_ceros_y_no_nan():
    """No esta definida (N-1 = 0). Se decide ceros, y esta documentado."""
    s = estadisticas(np.full((1, 1, 3), 0.3, dtype=np.float32))
    assert s.cov.shape == (3, 3)
    assert np.array_equal(s.cov, np.zeros((3, 3)))
    assert s.n_samples == 1


def test_dos_pixeles_ya_tienen_covarianza_de_verdad():
    datos = np.array([[0.1, 0.2, 0.3], [0.5, 0.4, 0.3]], dtype=np.float32)
    s = estadisticas(datos)
    assert not np.allclose(s.cov, 0.0)
    assert np.allclose(s.cov, np.cov(datos.astype(np.float64), rowvar=False, ddof=1))


# ---------------------------------------------------------------------------
# Histograma de saturacion
# ---------------------------------------------------------------------------


def test_el_histograma_suma_uno_y_tiene_64_bins(estudio_trabajo, exterior_trabajo, carta):
    for img in (estudio_trabajo, exterior_trabajo, a_trabajo(carta)):
        s = estadisticas(img)
        assert s.saturation_hist.shape == (SAT_BINS,)
        assert s.saturation_hist.sum() == pytest.approx(1.0)
        assert (s.saturation_hist >= 0).all()


def test_un_neutro_cae_entero_en_el_primer_bin(rampa):
    s = estadisticas(a_trabajo(rampa))
    assert s.saturation_hist[0] > 0.99


def test_un_primario_puro_cae_en_el_ultimo_bin():
    rojo = np.zeros((16, 16, 3), dtype=np.float32)
    rojo[..., 0] = 0.8
    s = estadisticas(rojo)
    assert s.saturation_hist[-1] > 0.99


def test_mas_saturacion_desplaza_el_histograma_a_la_derecha(estudio_trabajo):
    from core.contracts import CDL

    centro = np.arange(SAT_BINS) + 0.5
    flojo = estadisticas(CDL(saturation=0.4).apply(estudio_trabajo)).saturation_hist
    fuerte = estadisticas(CDL(saturation=2.2).apply(estudio_trabajo)).saturation_hist
    assert float(fuerte @ centro) > float(flojo @ centro)


def test_la_saturacion_de_un_negro_es_cero():
    assert float(saturacion_hsv(np.zeros((4, 4, 3), np.float32)).max()) == 0.0


def test_la_saturacion_nunca_se_sale_de_0_1(exterior_trabajo):
    s = saturacion_hsv(exterior_trabajo)
    assert float(s.min()) >= 0.0 and float(s.max()) <= 1.0


# ---------------------------------------------------------------------------
# Piel
# ---------------------------------------------------------------------------


def test_hay_locus_en_los_seis_tonos_de_piel(pieles_trabajo):
    """Si solo funcionara con pieles claras, no funcionaria."""
    for i, img in enumerate(pieles_trabajo):
        s = estadisticas(img)
        assert s.skin_locus is not None, f"tono {i} sin locus"
        assert s.skin_fraction > FRACCION_PIEL_MINIMA, f"tono {i}: {s.skin_fraction}"


def test_el_locus_va_en_oklab_y_cae_donde_cae_la_piel(pieles_trabajo):
    for img in pieles_trabajo:
        s = estadisticas(img)
        ll, a, b = s.skin_locus
        tono = np.degrees(np.arctan2(b, a)) % 360.0
        assert 10.0 <= tono <= 85.0, f"tono de piel fuera del locus: {tono}"
        assert 0.0 < ll < 1.3
        # Y no es un RGB disfrazado: el Oklab del mismo color no coincide con el RGB.
        assert not np.allclose(s.skin_locus, s.mean, atol=1e-3)


def test_el_locus_es_el_oklab_medio_de_los_pixeles_marcados(estudio_trabajo):
    from core.color import skin_mask_oklab

    mascara = skin_mask_oklab(estudio_trabajo, WORKING_SPACE)
    esperado = rgb_to_oklab(estudio_trabajo[mascara], WORKING_SPACE).mean(axis=0)
    assert np.allclose(estadisticas(estudio_trabajo).skin_locus, esperado)


def test_sin_piel_el_locus_es_none(rampa):
    s = estadisticas(a_trabajo(rampa))
    assert s.skin_locus is None
    assert s.skin_fraction == pytest.approx(0.0, abs=1e-6)


def test_poca_piel_tampoco_cuenta(estudio_trabajo):
    """Una cara de 40 pixeles en un plano general no puede decidir el color."""
    plano_general = np.full((400, 400, 3), 0.25, dtype=np.float32)
    trozo = estudio_trabajo[150:156, 300:306]  # 36 pixeles de cara
    plano_general[:6, :6] = trozo
    s = estadisticas(plano_general)
    assert s.skin_locus is None
    assert s.skin_fraction < FRACCION_PIEL_MINIMA


# ---------------------------------------------------------------------------
# Espacio de origen
# ---------------------------------------------------------------------------


def test_el_space_de_entrada_se_convierte_al_de_trabajo(escena_estudio):
    desde_lineal = estadisticas(escena_estudio.image, space="linear_rec709")
    ya_convertido = estadisticas(a_trabajo(escena_estudio.image))
    assert np.allclose(desde_lineal.mean, ya_convertido.mean, atol=1e-6)
    # El histograma no sale bit a bit igual porque `a_trabajo` convierte en
    # float32 y `estadisticas` en float64: unos pocos pixeles cambian de bin.
    # La distancia de variacion total medida es 4,3e-6.
    assert 0.5 * np.abs(desde_lineal.saturation_hist - ya_convertido.saturation_hist).sum() < 1e-4


def test_las_estadisticas_no_son_las_del_espacio_de_origen(escena_estudio):
    """Si alguien se saltara la conversion, este test lo caza."""
    en_trabajo = estadisticas(escena_estudio.image, space="linear_rec709")
    sin_convertir = estadisticas(escena_estudio.image, space=WORKING_SPACE)
    assert not np.allclose(en_trabajo.mean, sin_convertir.mean, atol=1e-3)


# ---------------------------------------------------------------------------
# analizar_imagen
# ---------------------------------------------------------------------------


def test_analizar_imagen_devuelve_un_clipanalysis(estudio_trabajo):
    a = analizar_imagen(estudio_trabajo, clip_id="ref")
    assert a.clip_id == "ref"
    assert a.path == "<memoria>"
    assert (a.width, a.height) == (640, 360)
    assert a.frame_count == 1 and a.sampled_frames == 1
    assert a.fingerprint.shape == (96,) and a.fingerprint.dtype == np.float32
    assert a.pixels is None
    assert a.source_space == WORKING_SPACE


def test_analizar_imagen_guarda_pixeles_si_se_pide(estudio_trabajo):
    a = analizar_imagen(estudio_trabajo, clip_id="ref", guardar_pixeles=True)
    assert a.pixels is not None
    assert a.pixels.shape[1] == 3 and a.pixels.dtype == np.float32
    assert a.pixels.shape[0] <= 200_000
    # La muestra tiene que parecerse al original, no ser un trozo del principio.
    assert np.allclose(a.pixels.mean(axis=0), a.stats.mean, atol=5e-3)


def test_analizar_imagen_convierte_desde_el_espacio_de_origen(escena_estudio):
    a = analizar_imagen(escena_estudio.image, clip_id="x", space="linear_rec709")
    assert a.source_space == "linear_rec709"
    assert np.allclose(a.stats.mean, estadisticas(a_trabajo(escena_estudio.image)).mean)


def test_analizar_imagen_avisa_cuando_no_hay_piel(rampa):
    a = analizar_imagen(a_trabajo(rampa), clip_id="rampa")
    assert any("piel" in w for w in a.warnings)
    assert any("neutra" in w for w in a.warnings)


def test_analizar_imagen_rechaza_formas_raras():
    with pytest.raises(ValueError, match="esperaba"):
        analizar_imagen(np.zeros((10, 10)), clip_id="x")
    with pytest.raises(ValueError, match="ni un pixel"):
        analizar_imagen(np.zeros((0, 10, 3)), clip_id="x")
