"""Primarios, matrices y `convert`.

El juez independiente vuelve a ser `colour-science`: sus conjuntos de datos de
cromaticidades y sus matrices RGB->XYZ salen de los mismos documentos de
fabricante, pero calculadas por otro codigo.
"""

from __future__ import annotations

import colour
import numpy as np
import pytest

from core.color import (
    SPACES,
    convert,
    from_working,
    log_decode,
    primaries_matrix,
    rgb_to_xyz_matrix,
    to_working,
)
from core.contracts import WORKING_SPACE

ESPACIOS = tuple(SPACES)

#: Como se llama cada espacio nuestro en el catalogo de colour-science.
EN_COLOUR = {
    "slog3_sgamut3cine": "S-Gamut3.Cine",
    "vlog_vgamut": "V-Gamut",
    "clog3_cinemagamut": "Cinema Gamut",
    "dlog_dgamut": "DJI D-Gamut",
    "rec709": "ITU-R BT.709",
    "davinci_wg_intermediate": "DaVinci Wide Gamut",
    "linear_davinci_wg": "DaVinci Wide Gamut",
    "linear_rec709": "ITU-R BT.709",
}


# ---------------------------------------------------------------------------
# Primarios y matrices
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_primarios_coinciden_con_colour(espacio):
    """Las cromaticidades publicadas, contra las que trae colour-science."""
    assert np.allclose(
        SPACES[espacio].primaries,
        colour.RGB_COLOURSPACES[EN_COLOUR[espacio]].primaries,
        atol=1e-12,
    )


#: Espacios donde colour-science CALCULA la matriz a partir de las
#: cromaticidades, igual que nosotros. Ahi la coincidencia tiene que ser exacta.
CALCULADAS = ("clog3_cinemagamut", "rec709", "davinci_wg_intermediate",
              "linear_davinci_wg", "linear_rec709")

#: Espacios donde colour-science usa la matriz IMPRESA por el fabricante, que
#: viene redondeada. Ahi la coincidencia solo puede llegar hasta ese redondeo.
#: Los numeros son los medidos, no estimaciones.
IMPRESAS = {
    "slog3_sgamut3cine": 1e-10,  # Sony imprime ~10 decimales
    "vlog_vgamut": 1e-6,  # Panasonic imprime 6 decimales
    "dlog_dgamut": 2e-4,  # DJI imprime 4 decimales: es el peor de los ocho
}


@pytest.mark.parametrize("espacio", CALCULADAS)
def test_matriz_rgb_a_xyz_coincide_con_colour(espacio):
    """Nuestra matriz la CALCULAMOS; la de colour tambien. Tienen que salir igual.

    1e-12 absoluto sobre numeros de orden 1: es el mismo algebra, no una
    aproximacion.
    """
    assert np.allclose(
        SPACES[espacio].matrix_rgb_to_xyz,
        colour.RGB_COLOURSPACES[EN_COLOUR[espacio]].matrix_RGB_to_XYZ,
        atol=1e-12,
    )


@pytest.mark.parametrize("espacio", sorted(IMPRESAS))
def test_matriz_impresa_por_el_fabricante_vs_la_calculada(espacio):
    """Sony, Panasonic y DJI IMPRIMEN su matriz redondeada, y no cuadra del todo.

    Esto no es un fallo de nadie: si coges las cromaticidades publicadas y
    calculas la matriz, no sale exactamente la matriz publicada, porque esa
    esta impresa con pocos decimales. DJI es el caso gordo: 1.8e-4 de
    diferencia, porque solo imprime cuatro decimales.

    NOSOTROS usamos la CALCULADA, y la razon esta en el segundo assert: la
    calculada manda el blanco RGB (1, 1, 1) exactamente a D65, y la impresa no.
    Preferimos un neutro exacto (que es lo que se ve en una imagen: un tinte)
    a cuadrar con un redondeo de un PDF. Los numeros de arriba son los medidos
    hoy; si cambian, alguien ha tocado las cromaticidades.
    """
    suya = colour.RGB_COLOURSPACES[EN_COLOUR[espacio]].matrix_RGB_to_XYZ
    mia = SPACES[espacio].matrix_rgb_to_xyz
    assert np.max(np.abs(mia - suya)) < IMPRESAS[espacio]

    x, y = SPACES[espacio].whitepoint
    d65 = np.array([x / y, 1.0, (1.0 - x - y) / y])
    error_mio = np.max(np.abs(mia @ np.ones(3) - d65))
    error_suyo = np.max(np.abs(suya @ np.ones(3) - d65))
    assert error_mio < 1e-14 < error_suyo


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_el_blanco_del_espacio_es_su_punto_blanco(espacio):
    """RGB (1, 1, 1) lineal tiene que dar exactamente el XYZ de D65 con Y = 1.

    Es la propiedad que DEFINE la matriz de primarios normalizada. Si esto
    falla, el escalado de las columnas esta mal y todo el modulo tinta.
    """
    info = SPACES[espacio]
    xyz = info.matrix_rgb_to_xyz @ np.ones(3)
    x, y = info.whitepoint
    esperado = np.array([x / y, 1.0, (1.0 - x - y) / y])
    assert np.allclose(xyz, esperado, atol=1e-14)


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_la_inversa_es_la_inversa(espacio):
    info = SPACES[espacio]
    assert np.allclose(info.matrix_rgb_to_xyz @ info.matrix_xyz_to_rgb, np.eye(3), atol=1e-12)


def test_primarios_con_y_cero_lanzan():
    """Una cromaticidad con y = 0 no tiene XYZ. Que se entere quien la meta."""
    with pytest.raises(ValueError, match="y = 0"):
        rgb_to_xyz_matrix(np.array([[0.64, 0.33], [0.3, 0.6], [0.15, 0.06]]), (0.3127, 0.0))


def test_primarios_con_forma_mala_lanzan():
    with pytest.raises(ValueError, match=r"\(3, 2\)"):
        rgb_to_xyz_matrix(np.zeros((2, 2)), (0.3127, 0.3290))


# ---------------------------------------------------------------------------
# primaries_matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_primaries_matrix_de_un_espacio_a_si_mismo_es_la_identidad(espacio):
    assert np.array_equal(primaries_matrix(espacio, espacio), np.eye(3))


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_primaries_matrix_ida_y_vuelta(espacio):
    m = primaries_matrix(espacio, WORKING_SPACE)
    n = primaries_matrix(WORKING_SPACE, espacio)
    assert np.allclose(n @ m, np.eye(3), atol=1e-12)


def test_primaries_matrix_contra_colour():
    """La matriz S-Gamut3.Cine -> DaVinci WG, contra la que calcula colour."""
    mio = primaries_matrix("slog3_sgamut3cine", "linear_davinci_wg")
    suyo = colour.matrix_RGB_to_RGB(
        colour.RGB_COLOURSPACES["S-Gamut3.Cine"],
        colour.RGB_COLOURSPACES["DaVinci Wide Gamut"],
        chromatic_adaptation_transform="Bradford",
    )
    assert np.allclose(mio, suyo, atol=1e-12)


def test_primaries_matrix_conserva_el_blanco():
    """El blanco es blanco en todos: los ocho espacios son D65, no debe tintarse."""
    for origen in ESPACIOS:
        for destino in ESPACIOS:
            blanco = primaries_matrix(origen, destino) @ np.ones(3)
            assert np.allclose(blanco, 1.0, atol=1e-12), f"{origen} -> {destino}: {blanco}"


def test_espacios_con_los_mismos_primarios_dan_identidad_exacta():
    """rec709 y linear_rec709 comparten gamut: la matriz tiene que ser I, no casi-I."""
    assert np.array_equal(primaries_matrix("rec709", "linear_rec709"), np.eye(3))
    assert np.array_equal(
        primaries_matrix("davinci_wg_intermediate", "linear_davinci_wg"), np.eye(3)
    )


# ---------------------------------------------------------------------------
# convert
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_convert_a_si_mismo_es_la_identidad_exacta(espacio):
    """Bit a bit, no "casi". Y con NaN dentro, para que no se cuele un np.nan_to_num."""
    rng = np.random.default_rng(7)
    img = rng.normal(0.35, 0.4, (9, 7, 3)).astype(np.float32)
    img[2, 3] = np.nan
    img[0, 0] = [-0.4, 0.0, 12.0]
    salida = convert(img, espacio, espacio)
    assert salida.dtype == img.dtype
    assert np.array_equal(salida, img, equal_nan=True)
    assert salida is not img


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_convert_ida_y_vuelta_por_el_espacio_de_trabajo(espacio):
    """origen -> trabajo -> origen. En float64 para medir de verdad.

    Tolerancia 1e-9 relativa: son dos logaritmos, dos exponenciales y dos
    matrices. Lo que queda es error de maquina acumulado, no sesgo.
    """
    rng = np.random.default_rng(11)
    # Rango de valores CODIFICADOS realista: de un pelin por debajo de negro a
    # un superblanco. Un 3.0 codificado en S-Log3 serian 1.9e9 de escena-lineal,
    # y eso no lo graba nadie; ver `test_valores_absurdos_pierden_precision`.
    img = rng.uniform(-0.05, 1.2, (200, 3))
    trabajo = to_working(img, espacio)
    vuelta = from_working(trabajo, espacio)
    assert np.allclose(vuelta, img, rtol=1e-9, atol=1e-11)


def test_convert_lleva_el_gris_18_donde_toca():
    """El 18% de gris en cualquier espacio de camara es el 18% en el de trabajo.

    Es la comprobacion que de verdad importa para el resto de la app: si esto
    falla, todos los emparejamientos salen con una parada de diferencia y nadie
    sabe por que.
    """
    gris_trabajo = 0.3360432724  # DaVinci Intermediate al 18%
    for espacio in ESPACIOS:
        from core.color import log_encode

        codificado = log_encode(np.full((1, 3), 0.18), espacio)
        en_trabajo = to_working(codificado.astype(np.float64), espacio)
        assert np.allclose(en_trabajo, gris_trabajo, atol=1e-6), espacio


def test_convert_conserva_el_neutro():
    """Un gris sigue siendo gris al cambiar de gamut: R = G = B a la salida."""
    rng = np.random.default_rng(3)
    for origen in ESPACIOS:
        for destino in ESPACIOS:
            grises = np.repeat(rng.uniform(0.01, 2.0, (50, 1)), 3, axis=1)
            from core.color import log_encode

            cod = log_encode(grises, origen)
            salida = convert(cod, origen, destino).astype(np.float64)
            assert np.allclose(salida[:, 0], salida[:, 1], rtol=1e-6, atol=1e-7)
            assert np.allclose(salida[:, 1], salida[:, 2], rtol=1e-6, atol=1e-7)


def test_valores_absurdos_pierden_precision_y_hay_que_saberlo():
    """LIMITE REAL: con un codificado de 3.0 en S-Log3 la vuelta pierde 5 digitos.

    3.0 codificado en S-Log3 son 1.9e9 de escena-lineal. Al pasar por la matriz
    de primarios, ese canal gigante se mezcla con los otros dos y, al volver,
    reconstruir un numero de orden 0.01 restando dos de orden 1e8 se come once
    digitos de los dieciseis del float64.

    No tiene arreglo dentro del modulo (la matriz es la matriz) y tampoco hace
    falta: 3.0 codificado no sale de ninguna camara. Se deja el test para que el
    limite este medido y para que nadie lo descubra un martes a las tres.
    """
    img = np.array([[0.0375, 0.4012, 2.781]])
    vuelta = from_working(to_working(img, "slog3_sgamut3cine"), "slog3_sgamut3cine")
    error = np.max(np.abs(vuelta - img) / np.abs(img))
    assert 1e-9 < error < 1e-3


def test_convert_entre_dos_camaras_contra_colour():
    """S-Log3/S-Gamut3.Cine -> Canon Log 3/Cinema Gamut, camino armado con colour.

    colour no tiene un `convert` que haga exactamente esto de una pieza, asi que
    el juez se arma con sus tres piezas sueltas: decodificar, matriz, codificar.
    Sigue siendo codigo independiente del nuestro.

    Se eligen estos dos y no V-Gamut a proposito: para Cinema Gamut colour
    CALCULA la matriz igual que nosotros, asi que la unica diferencia posible
    son las curvas. Con V-Gamut el juez arrastraria el redondeo de la matriz
    impresa de Panasonic y el test estaria midiendo dos cosas a la vez.
    """
    rng = np.random.default_rng(5)
    slog = rng.uniform(0.05, 0.85, (400, 3))

    lineal = colour.models.log_decoding_SLog3(slog)
    m = colour.matrix_RGB_to_RGB(
        colour.RGB_COLOURSPACES["S-Gamut3.Cine"],
        colour.RGB_COLOURSPACES["Cinema Gamut"],
        chromatic_adaptation_transform="Bradford",
    )
    with np.errstate(invalid="ignore"):
        suyo = colour.models.log_encoding_CanonLog3(np.einsum("ij,...j->...i", m, lineal))

    mio = convert(slog, "slog3_sgamut3cine", "clog3_cinemagamut")
    # 1e-8 y no 1e-12: colour usa para S-Gamut3.Cine la matriz impresa por Sony,
    # que difiere 4.5e-11 de la calculada, y eso se propaga por el logaritmo.
    assert np.allclose(mio, suyo, atol=1e-8)


def test_to_working_y_from_working_son_atajos_de_convert():
    rng = np.random.default_rng(13)
    img = rng.uniform(0.0, 1.0, (5, 4, 3)).astype(np.float32)
    assert np.array_equal(to_working(img, "vlog_vgamut"), convert(img, "vlog_vgamut", WORKING_SPACE))
    assert np.array_equal(
        from_working(img, "vlog_vgamut"), convert(img, WORKING_SPACE, "vlog_vgamut")
    )


def test_convert_conserva_la_forma():
    for forma in [(3,), (1, 3), (4, 5, 3), (2, 3, 4, 3)]:
        img = np.full(forma, 0.4, dtype=np.float32)
        assert convert(img, "rec709", WORKING_SPACE).shape == forma


def test_convert_rechaza_lo_que_no_es_rgb():
    with pytest.raises(ValueError, match=r"\(\.\.\., 3\)"):
        convert(np.zeros((4, 4)), "rec709", WORKING_SPACE)
    with pytest.raises(ValueError, match=r"\(\.\.\., 3\)"):
        convert(np.zeros((4, 4, 4)), "rec709", WORKING_SPACE)


def test_convert_espacio_desconocido_lanza():
    with pytest.raises(ValueError, match="espacio desconocido"):
        convert(np.zeros((2, 3)), "rec709", "arri_logc4")  # type: ignore[arg-type]


def test_dtype_de_convert():
    img32 = np.full((2, 2, 3), 0.4, dtype=np.float32)
    assert convert(img32, "rec709", WORKING_SPACE).dtype == np.float32
    assert convert(img32.astype(np.float64), "rec709", WORKING_SPACE).dtype == np.float64


# ---------------------------------------------------------------------------
# Metadatos
# ---------------------------------------------------------------------------


def test_spaces_cubre_exactamente_el_contrato():
    """Ni uno mas ni uno menos que los `ColorSpaceName` del contrato congelado."""
    from typing import get_args

    from core.contracts import ColorSpaceName

    assert set(SPACES) == set(get_args(ColorSpaceName))


@pytest.mark.parametrize("espacio", ESPACIOS)
def test_cada_espacio_dice_de_donde_sale(espacio):
    """Sin fuente, el numero no vale nada. El revisor tiene que poder ir a mirar."""
    info = SPACES[espacio]
    assert info.label and info.fuente
    assert info.name == espacio
    assert info.primaries.shape == (3, 2)
    assert info.whitepoint == (0.3127, 0.3290)


def test_los_lineales_estan_marcados_como_lineales():
    lineales = {n for n in SPACES if SPACES[n].is_linear}
    assert lineales == {"linear_davinci_wg", "linear_rec709"}
    for n in lineales:
        assert np.array_equal(log_decode(np.array([0.7]), n), np.array([0.7]))
