"""Casos frontera: lo que rompe un modulo de color en produccion.

Negro absoluto, saturacion absoluta, un solo pixel, negativos, un especular a
9.0, NaN, infinitos, arrays vacios, arrays de solo lectura y vistas no
contiguas. Nada de esto es rebuscado: todo sale de material real o de como
otros modulos van a llamar a este.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import (
    SPACES,
    convert,
    delta_e2000,
    delta_e2000_mean,
    from_working,
    log_decode,
    log_encode,
    oklab_to_rgb,
    rgb_to_lab,
    rgb_to_oklab,
    skin_mask_oklab,
    to_working,
)
from core.contracts import WORKING_SPACE
from tests.media import generate as gen

ESPACIOS = tuple(SPACES)


# ---------------------------------------------------------------------------
# Imagenes degeneradas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_imagen_completamente_negra(espacio):
    negra = np.zeros((16, 16, 3), dtype=np.float32)
    salida = to_working(negra, espacio)
    assert np.all(np.isfinite(salida))
    assert salida.shape == negra.shape
    # Y el negro sigue siendo neutro: los tres canales iguales.
    assert np.allclose(salida[..., 0], salida[..., 1], atol=1e-6)


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_imagen_completamente_saturada(espacio):
    """Todo a 1.0 y tambien los tres primarios puros, que es peor."""
    for valor in (np.ones((8, 8, 3), dtype=np.float32),):
        assert np.all(np.isfinite(to_working(valor, espacio)))
    primarios = np.eye(3, dtype=np.float32).reshape(1, 3, 3)
    salida = to_working(primarios, espacio)
    assert np.all(np.isfinite(salida))


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_un_solo_pixel(espacio):
    uno = np.full((1, 1, 3), 0.42, dtype=np.float32)
    assert to_working(uno, espacio).shape == (1, 1, 3)
    assert convert(uno, espacio, "rec709").shape == (1, 1, 3)
    assert rgb_to_oklab(uno, espacio).shape == (1, 1, 3)
    assert delta_e2000(uno, uno, espacio).shape == (1, 1)


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_imagen_vacia(espacio):
    """Una lista de 0 pixeles no debe lanzar: es lo que sale de una mascara vacia."""
    vacia = np.zeros((0, 3), dtype=np.float32)
    assert to_working(vacia, espacio).shape == (0, 3)
    assert rgb_to_oklab(vacia, espacio).shape == (0, 3)
    assert delta_e2000(vacia, vacia, espacio).shape == (0,)


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_valores_negativos_se_preservan(espacio):
    """Contrato 1: fuera de rango es legal. No se recorta a 0."""
    img = np.full((4, 4, 3), -0.08, dtype=np.float64)
    trabajo = to_working(img, espacio)
    vuelta = from_working(trabajo, espacio)
    assert np.allclose(vuelta, img, rtol=1e-9, atol=1e-11)


def test_el_especular_de_la_escena_de_estudio_sobrevive():
    """`studio_scene` mete un especular que pasa de 2.4 en escena-lineal."""
    escena = gen.studio_scene(skin_tone_index=2)
    assert escena.image.max() > 2.0
    trabajo = to_working(escena.image, "linear_rec709")
    assert np.all(np.isfinite(trabajo))
    vuelta = from_working(trabajo, "linear_rec709")
    assert np.allclose(vuelta, escena.image, rtol=2e-4, atol=1e-5)


def test_el_sol_del_exterior_sobrevive():
    """`exterior_scene` llega a 9.0. Es el caso que pedia el encargo."""
    exterior = gen.exterior_scene()
    assert exterior.image.max() > 8.0
    for espacio in ESPACIOS:
        trabajo = to_working(exterior.image, espacio)
        assert np.all(np.isfinite(trabajo)), espacio


# ---------------------------------------------------------------------------
# NaN e infinitos: la politica del modulo es PROPAGAR
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_nan_se_propaga_en_la_transferencia(espacio):
    x = np.array([0.1, np.nan, 0.5])
    y = log_encode(x, espacio)
    assert np.isnan(y[1])
    assert np.all(np.isfinite(y[[0, 2]]))
    z = log_decode(y, espacio)
    assert np.isnan(z[1])


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_nan_se_propaga_en_convert(espacio):
    """Un pixel NaN contamina sus tres canales al pasar por la matriz, y esta bien:
    despues de mezclar canales ya no se sabe cual estaba roto."""
    img = np.full((3, 3, 3), 0.4, dtype=np.float32)
    img[1, 1, 0] = np.nan
    salida = convert(img, "linear_rec709", WORKING_SPACE)
    assert np.all(np.isnan(salida[1, 1]))
    assert np.all(np.isfinite(salida[0, 0]))


def test_nan_se_propaga_en_oklab_y_en_lab():
    img = np.array([[0.4, np.nan, 0.2]])
    assert np.all(np.isnan(rgb_to_oklab(img, "linear_rec709")))
    assert np.all(np.isnan(rgb_to_lab(img, "linear_rec709")))


def test_nan_se_propaga_en_delta_e2000():
    a = np.full((2, 2, 3), 0.4)
    b = a.copy()
    b[0, 0, 1] = np.nan
    de = delta_e2000(a, b, "linear_rec709")
    assert np.isnan(de[0, 0])
    assert np.isfinite(de[1, 1])


def test_delta_e2000_mean_devuelve_nan_si_hay_un_nan():
    """Decision consciente: NO se usa nanmean.

    Un plano con NaN es un plano roto. Si la media los barriera, el agente C
    recibiria un numero plausible sobre un plano corrupto y nadie se enteraria.
    Que salga NaN obliga a mirar.
    """
    a = np.full((4, 4, 3), 0.4)
    b = a.copy()
    b[0, 0, 0] = np.nan
    assert np.isnan(delta_e2000_mean(a, b, "linear_rec709"))


def test_nada_lanza_por_un_nan():
    """En ningun sitio del modulo un NaN levanta una excepcion. Es la politica."""
    img = np.full((2, 2, 3), np.nan)
    for espacio in ESPACIOS:
        to_working(img, espacio)
        rgb_to_oklab(img, espacio)
        rgb_to_lab(img, espacio)
        skin_mask_oklab(img, espacio)


def test_un_pixel_nan_no_es_piel():
    escena = gen.studio_scene(skin_tone_index=2)
    img = escena.image.astype(np.float64).copy()
    img[10, 10] = np.nan
    assert not skin_mask_oklab(img, "linear_rec709")[10, 10]


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_infinito_no_lanza(espacio):
    """Un inf entra (un EXR roto lo tiene). No se pide que salga bonito, se pide
    que no reviente y que no se convierta en un numero razonable de mentira."""
    x = np.array([0.2, np.inf, -np.inf])
    with np.errstate(over="ignore", invalid="ignore"):
        y = log_encode(x, espacio)
    assert not np.isfinite(y[1]) and not np.isfinite(y[2])
    assert np.isfinite(y[0])


# ---------------------------------------------------------------------------
# Division por cero al normalizar
# ---------------------------------------------------------------------------


def test_croma_relativo_con_l_cero_no_divide_por_cero():
    """El negro puro tiene L = 0 y `skin_mask_oklab` divide croma entre L.

    Se protege con un max(L, 1e-6). Este test existe porque el bug clasico es
    que salte un RuntimeWarning y, peor, que el negro salga marcado como piel.
    """
    negra = np.zeros((4, 4, 3), dtype=np.float32)
    with np.errstate(all="raise"):
        m = skin_mask_oklab(negra, "linear_rec709")
    assert not m.any()


def test_skin_mask_con_l_negativo_no_marca():
    """Fuera de gamut se puede tener L de Oklab negativo. Eso no es piel."""
    img = np.full((2, 2, 3), -0.5, dtype=np.float64)
    assert not skin_mask_oklab(img, "linear_rec709").any()


def test_delta_e2000_entre_dos_negros_es_cero_y_no_nan():
    """Croma 0 en los dos: es la division por cero clasica del ΔE2000."""
    negro = np.zeros((3, 3, 3))
    de = delta_e2000(negro, negro, "linear_rec709")
    assert np.all(de == 0.0)


# ---------------------------------------------------------------------------
# Formas, tipos y arrays raros
# ---------------------------------------------------------------------------


def test_acepta_vistas_no_contiguas():
    """Un recorte con paso, o un array transpuesto, entran igual."""
    img = np.random.default_rng(51).uniform(0, 1, (20, 20, 3)).astype(np.float32)
    vista = img[::2, ::3]
    assert not vista.flags["C_CONTIGUOUS"]
    salida = to_working(vista, "linear_rec709")
    assert salida.shape == vista.shape
    assert np.allclose(salida, to_working(np.ascontiguousarray(vista), "linear_rec709"))


def test_acepta_arrays_de_solo_lectura():
    """Un array mapeado de disco viene con writeable=False. No se debe escribir en el."""
    img = np.full((4, 4, 3), 0.3)
    img.flags.writeable = False
    assert np.all(np.isfinite(to_working(img, "linear_rec709")))
    assert np.all(np.isfinite(rgb_to_oklab(img, "linear_rec709")))


def test_acepta_enteros_y_los_saca_en_float32():
    """Nadie deberia pasar enteros (contrato 1), pero si pasan no se rompe."""
    img = np.ones((2, 2, 3), dtype=np.uint8)
    salida = to_working(img, "linear_rec709")
    assert salida.dtype == np.float32


def test_rechaza_lo_que_no_es_numerico():
    with pytest.raises(TypeError, match="numerico"):
        log_encode(np.array([["a", "b", "c"]]), "rec709")


def test_no_toca_la_entrada():
    """Ninguna funcion del modulo modifica el array que le pasan."""
    img = np.random.default_rng(53).uniform(0, 1, (6, 6, 3)).astype(np.float32)
    copia = img.copy()
    to_working(img, "linear_rec709")
    rgb_to_oklab(img, "linear_rec709")
    rgb_to_lab(img, "linear_rec709")
    skin_mask_oklab(img, "linear_rec709")
    delta_e2000(img, img, "linear_rec709")
    assert np.array_equal(img, copia)


def test_oklab_to_rgb_rechaza_formas_malas():
    with pytest.raises(ValueError, match=r"\(\.\.\., 3\)"):
        oklab_to_rgb(np.zeros((4, 2)), "linear_rec709")


# ---------------------------------------------------------------------------
# Material sintetico completo: que todo el catalogo pase por todos los espacios
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_todo_el_catalogo_pasa_por_todos_los_espacios(espacio):
    """Carta, rampas, degradado, ruido, retrato y exterior. Sin NaN ni inf."""
    catalogo = {
        "carta": gen.colorchecker(patch_px=8, gap_px=2),
        "rampa_gris": gen.ramp_gray(width=64, height=4),
        "rampa_rgb": gen.ramp_rgb(width=64, height=16),
        "degradado": gen.gradient(width=64, height=36),
        "ruido": gen.noise_field(width=64, height=36),
        "estudio": gen.studio_scene(width=64, height=36).image,
        "exterior": gen.exterior_scene(width=64, height=36).image,
    }
    for nombre, img in catalogo.items():
        trabajo = to_working(img, "linear_rec709")
        salida = from_working(trabajo, espacio)
        assert np.all(np.isfinite(salida)), f"{nombre} -> {espacio}"
        assert salida.dtype == np.float32
