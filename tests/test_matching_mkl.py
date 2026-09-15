"""Tests del transporte lineal de Monge-Kantorovich.

Lo que se comprueba aqui es lo que define el metodo: que `A Sx A = Sy`, que
transportar algo a si mismo da la identidad, y que ida y vuelta vuelve. Y luego
todo lo que puede salir singular, que es lo que de verdad rompe estas cosas.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.matching.mkl import (
    GANANCIA_MAX,
    aplicar_mkl,
    covarianza_regularizada,
    ganancias,
    media_y_covarianza,
    pixeles_finitos,
    transporte_mkl,
    transporte_mkl_de_estadistica,
)


def nube(n: int, mezcla: np.ndarray, centro, semilla: int) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    return rng.normal(size=(n, 3)) @ np.asarray(mezcla) + np.asarray(centro)


MEZCLA_A = np.array([[1.0, 0.3, 0.1], [0.0, 0.8, 0.2], [0.0, 0.0, 0.5]])
MEZCLA_B = np.array([[0.7, 0.0, 0.2], [0.1, 1.2, 0.0], [0.0, 0.1, 0.9]])


# ---------------------------------------------------------------------------
# Lo que define el metodo
# ---------------------------------------------------------------------------


def test_transporte_lleva_la_covarianza_exactamente_a_la_del_destino():
    """`A Sx A = Sy` es LA propiedad del transporte. Si esto falla, no es MKL."""
    x = nube(20000, MEZCLA_A, (0.3, 0.4, 0.5), 1)
    y = nube(15000, MEZCLA_B, (0.1, 0.2, 0.9), 2)
    a, b = transporte_mkl(x, y)
    _, cov_x = media_y_covarianza(x)
    _, cov_y = media_y_covarianza(y)
    np.testing.assert_allclose(a @ cov_x @ a, cov_y, rtol=1e-10, atol=1e-12)


def test_transporte_lleva_la_media_exactamente_a_la_del_destino():
    x = nube(8000, MEZCLA_A, (0.3, 0.4, 0.5), 3)
    y = nube(5000, MEZCLA_B, (0.1, 0.2, 0.9), 4)
    a, b = transporte_mkl(x, y)
    mu_y, _ = media_y_covarianza(y)
    np.testing.assert_allclose(aplicar_mkl(x, a, b).mean(axis=0), mu_y, atol=1e-12)


def test_transportar_una_distribucion_a_si_misma_es_la_identidad():
    x = nube(9000, MEZCLA_A, (0.2, 0.3, 0.4), 5)
    a, b = transporte_mkl(x, x)
    np.testing.assert_allclose(a, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(b, np.zeros(3), atol=1e-12)


def test_ida_y_vuelta_devuelve_los_pixeles_de_partida():
    x = nube(7000, MEZCLA_A, (0.3, 0.4, 0.5), 6)
    y = nube(6000, MEZCLA_B, (0.1, 0.2, 0.9), 7)
    a1, b1 = transporte_mkl(x, y)
    a2, b2 = transporte_mkl(y, x)
    vuelta = aplicar_mkl(aplicar_mkl(x, a1, b1), a2, b2)
    np.testing.assert_allclose(vuelta, x, rtol=1e-10, atol=1e-12)


def test_la_matriz_sale_simetrica_y_semidefinida_positiva():
    """Lo es por construccion, y de ahi sale que ida y vuelta se cancelen."""
    x = nube(4000, MEZCLA_A, (0.3, 0.4, 0.5), 8)
    y = nube(4000, MEZCLA_B, (0.1, 0.2, 0.9), 9)
    a, _ = transporte_mkl(x, y)
    np.testing.assert_allclose(a, a.T, atol=1e-14)
    assert ganancias(a).min() >= 0.0


def test_da_lo_mismo_con_pixeles_que_con_media_y_covarianza():
    x = nube(5000, MEZCLA_A, (0.3, 0.4, 0.5), 10)
    y = nube(5000, MEZCLA_B, (0.1, 0.2, 0.9), 11)
    a1, b1 = transporte_mkl(x, y)
    a2, b2 = transporte_mkl_de_estadistica(*media_y_covarianza(x), *media_y_covarianza(y))
    np.testing.assert_allclose(a1, a2, atol=1e-14)
    np.testing.assert_allclose(b1, b2, atol=1e-14)


def test_el_numero_de_pixeles_de_cada_lado_no_tiene_que_coincidir():
    x = nube(50000, MEZCLA_A, (0.3, 0.4, 0.5), 12)
    y = nube(37, MEZCLA_B, (0.1, 0.2, 0.9), 13)
    a, b = transporte_mkl(x, y)
    assert np.isfinite(a).all() and np.isfinite(b).all()


# ---------------------------------------------------------------------------
# Covarianza singular: el sitio donde esto se rompe de verdad
# ---------------------------------------------------------------------------


def test_un_solo_color_de_origen_no_da_nan():
    plano = np.tile([0.2, 0.5, 0.7], (500, 1))
    y = nube(3000, MEZCLA_B, (0.1, 0.2, 0.9), 14)
    a, b = transporte_mkl(plano, y)
    assert np.isfinite(a).all() and np.isfinite(b).all()


def test_en_una_direccion_sin_varianza_la_ganancia_es_1_y_no_infinita():
    """Es LA decision del modulo: no se inventa varianza donde no hay ninguna.

    Origen en blanco y negro (R=G=B, o sea rango 1). Las dos direcciones de
    croma no tienen ninguna informacion, y en vez de amplificarlas hasta el
    infinito se dejan como estan.
    """
    gris = np.tile(np.linspace(0.05, 0.6, 4000)[:, None], (1, 3))
    color = nube(4000, MEZCLA_B, (0.3, 0.3, 0.3), 15)
    a, b = transporte_mkl(gris, color)
    assert np.isfinite(a).all()
    # Las dos ganancias pequenas (las de las direcciones muertas) rondan 1.
    g = np.sort(ganancias(a))
    assert 0.2 < g[0] < 5.0, g
    assert 0.2 < g[1] < 5.0, g
    assert g.max() < GANANCIA_MAX


def test_un_solo_pixel_de_origen_contra_una_nube_casi_no_deforma_nada():
    """Con un pixel no hay covarianza que medir: lo unico que se sabe es DONDE
    esta, asi que el transporte tiene que ser casi un desplazamiento.

    CASI, y aqui esta el limite medido: la regularizacion copia la varianza del
    destino a lo largo de las direcciones propias del ORIGEN, y con el origen
    degenerado esas direcciones son arbitrarias (los vectores propios de la
    matriz cero). Si la covarianza del destino no es diagonal en esa base, `A`
    sale cerca de la identidad pero no exactamente: aqui, elementos fuera de la
    diagonal de hasta 0.10 y ganancias entre 0.93 y 1.09. Lo importante es que
    **no se dispara**, que es de lo que protege la regularizacion.
    """
    uno = np.array([[0.3, 0.4, 0.5]])
    y = nube(3000, MEZCLA_B, (0.1, 0.2, 0.9), 16)
    a, b = transporte_mkl(uno, y)
    np.testing.assert_allclose(a, np.eye(3), atol=0.15)
    g = ganancias(a)
    assert g.min() > 0.8 and g.max() < 1.25, g
    np.testing.assert_allclose(aplicar_mkl(uno, a, b)[0], y.mean(axis=0), atol=1e-9)


def test_un_destino_sin_varianza_colapsa_y_eso_es_lo_correcto():
    """Si el destino es un color plano, el transporte optimo es una constante.

    No es un fallo, es la respuesta: llevar una distribucion a una masa puntual
    es aplastarla. Lo que protege al usuario de que eso se le cuele como un
    igualado bueno no es el transporte, es la confianza y el detector de
    contenido, y eso se prueba en `test_matching_bordes.py`.
    """
    x = nube(2000, MEZCLA_A, (0.3, 0.4, 0.5), 17)
    y = np.tile([0.1, 0.2, 0.9], (200, 1))
    a, b = transporte_mkl(x, y)
    assert np.isfinite(a).all()
    assert ganancias(a).max() < 1e-2
    np.testing.assert_allclose(aplicar_mkl(x, a, b), np.tile([0.1, 0.2, 0.9], (2000, 1)), atol=1e-3)


def test_covarianza_de_un_solo_pixel_es_cero_y_no_nan():
    mu, cov = media_y_covarianza(np.array([[0.1, 0.2, 0.3]]))
    np.testing.assert_allclose(mu, [0.1, 0.2, 0.3])
    np.testing.assert_allclose(cov, np.zeros((3, 3)))


def test_todo_negro_contra_todo_negro_es_la_identidad():
    negro = np.zeros((50, 3))
    a, b = transporte_mkl(negro, negro)
    assert np.isfinite(a).all()
    np.testing.assert_allclose(aplicar_mkl(negro, a, b), negro, atol=1e-12)


def test_la_regularizacion_marca_las_direcciones_degeneradas():
    cov_x = np.diag([1.0, 1e-20, 0.0])
    cov_y = np.diag([2.0, 3.0, 4.0])
    lam, vec, degeneradas = covarianza_regularizada(cov_x, cov_y)
    assert degeneradas == 2
    assert (lam > 0).all()
    # En las direcciones muertas se copia la varianza del destino.
    assert np.isclose(sorted(lam)[0], 3.0) or np.isclose(sorted(lam)[1], 3.0)


def test_autovalores_negativos_de_redondeo_no_meten_complejos():
    """Una covarianza con un autovalor de -1e-19 es lo normal; su raiz no."""
    cov_x = np.array([[1.0, 0.5, 0.2], [0.5, 0.25, 0.1], [0.2, 0.1, 0.04]])  # rango 1 exacto
    cov_y = np.eye(3) * 0.3
    a, b = transporte_mkl_de_estadistica(np.zeros(3), cov_x, np.ones(3) * 0.2, cov_y)
    assert a.dtype == np.float64 and not np.iscomplexobj(a)
    assert np.isfinite(a).all()


def test_el_tope_de_ganancia_existe_y_se_nota():
    """Caso patologico a mano: origen con varianza ridicula, destino enorme."""
    cov_x = np.eye(3) * 1e-30
    cov_y = np.eye(3) * 1e30
    a, _ = transporte_mkl_de_estadistica(np.zeros(3), cov_x, np.zeros(3), cov_y)
    assert ganancias(a).max() <= GANANCIA_MAX * (1 + 1e-9)


# ---------------------------------------------------------------------------
# Formas, precision y NaN
# ---------------------------------------------------------------------------


def test_aplicar_conserva_la_forma_de_la_imagen():
    img = np.random.default_rng(0).random((17, 23, 3)).astype(np.float32)
    salida = aplicar_mkl(img, np.eye(3) * 2.0, np.array([0.1, 0.0, -0.1]))
    assert salida.shape == img.shape


def test_aplicar_respeta_la_precision_que_le_entra():
    a, b = np.eye(3), np.zeros(3)
    assert aplicar_mkl(np.zeros((4, 3), dtype=np.float32), a, b).dtype == np.float32
    assert aplicar_mkl(np.zeros((4, 3), dtype=np.float64), a, b).dtype == np.float64


def test_aplicar_propaga_los_nan_como_hace_core_color():
    px = np.array([[0.1, 0.2, 0.3], [np.nan, 0.2, 0.3]])
    salida = aplicar_mkl(px, np.eye(3), np.zeros(3))
    assert np.isfinite(salida[0]).all()
    assert np.isnan(salida[1]).all()


def test_transportar_descarta_las_filas_rotas_y_lo_dice():
    px = np.zeros((100, 3))
    px[::10] = np.nan
    limpio, fraccion = pixeles_finitos(px)
    assert limpio.shape[0] == 90
    assert fraccion == pytest.approx(0.10)


def test_si_no_queda_ni_un_pixel_finito_se_lanza():
    roto = np.full((10, 3), np.nan)
    with pytest.raises(ValueError, match="finito"):
        transporte_mkl(roto, np.zeros((10, 3)))


def test_forma_equivocada_se_lanza():
    with pytest.raises(ValueError, match=r"\(\.\.\., 3\)"):
        transporte_mkl(np.zeros((10, 4)), np.zeros((10, 3)))
    with pytest.raises(ValueError, match=r"\(\.\.\., 3\)"):
        aplicar_mkl(np.zeros((10, 2)), np.eye(3), np.zeros(3))


def test_una_imagen_entera_vale_igual_que_una_lista_de_pixeles():
    img = np.random.default_rng(1).random((30, 40, 3))
    a1, b1 = transporte_mkl(img, img * 0.5 + 0.1)
    a2, b2 = transporte_mkl(img.reshape(-1, 3), (img * 0.5 + 0.1).reshape(-1, 3))
    np.testing.assert_allclose(a1, a2, atol=1e-14)
    np.testing.assert_allclose(b1, b2, atol=1e-14)


# ---------------------------------------------------------------------------
# Con material del generador, que es lo que va a ver de verdad
# ---------------------------------------------------------------------------


def test_sobre_escenas_de_verdad_el_transporte_iguala_la_estadistica(
    estudio_trabajo, exterior_trabajo
):
    o = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    r = exterior_trabajo.reshape(-1, 3).astype(np.float64)
    a, b = transporte_mkl(o, r)
    t = aplicar_mkl(o, a, b)
    np.testing.assert_allclose(t.mean(axis=0), r.mean(axis=0), atol=1e-10)
    np.testing.assert_allclose(
        np.cov(t, rowvar=False, ddof=1), np.cov(r, rowvar=False, ddof=1), rtol=1e-8, atol=1e-12
    )


def test_los_seis_tonos_de_piel_transportan_sin_romperse(pieles_trabajo):
    """Si algo solo funciona con pieles claras, aqui se ve."""
    referencia = pieles_trabajo[2].reshape(-1, 3).astype(np.float64)
    for i, piel in enumerate(pieles_trabajo):
        a, b = transporte_mkl(piel.reshape(-1, 3).astype(np.float64), referencia)
        assert np.isfinite(a).all() and np.isfinite(b).all(), i
        assert ganancias(a).max() < 4.0, i
