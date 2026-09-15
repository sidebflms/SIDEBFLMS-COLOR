"""Imagen HALD CLUT: ida y vuelta exacta, y el mismo orden que el generador."""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import LUT3D
from core.io import ErrorFormatoHald, hald_image, lado_hald, lut_from_hald, lut_solo_rojo
from tests.media import generate as gen


def test_el_hald_de_la_identidad_es_el_del_generador():
    """`tests/media/generate.py` ya sabe fabricar la imagen de entradas. Si mi
    `hald_image` usara otro orden de píxeles, todo el camino HALD sería
    incompatible con el material de prueba del proyecto y nadie lo notaría
    hasta muy tarde."""
    mio = hald_image(LUT3D.identity(17))
    suyo = gen.hald(17)
    assert mio.shape == suyo.shape == (71, 71, 3)
    assert mio.dtype == np.float32
    assert np.array_equal(mio, suyo)


@pytest.mark.parametrize("size", [2, 5, 17, 33])
def test_ida_y_vuelta_exacta(size, rng):
    tabla = rng.random((size, size, size, 3)).astype(np.float32)
    lut = LUT3D(table=tabla)
    vuelto = lut_from_hald(hald_image(lut), size)
    assert np.array_equal(vuelto.table, tabla)


def test_en_el_hald_el_azul_es_el_que_varia_mas_rapido():
    """Al revés que en el fichero .cube, donde manda el rojo. Es la otra mitad
    de la convención 4 y conviene tenerla escrita en un test."""
    img = hald_image(LUT3D.identity(4)).reshape(-1, 3)
    assert img[0] == pytest.approx([0.0, 0.0, 0.0])
    assert img[1] == pytest.approx([0.0, 0.0, 1 / 3], abs=1e-6)
    assert img[4] == pytest.approx([0.0, 1 / 3, 0.0], abs=1e-6)
    assert img[16] == pytest.approx([1 / 3, 0.0, 0.0], abs=1e-6)


def test_el_hald_conserva_un_lut_que_solo_toca_el_rojo():
    lut = lut_solo_rojo(17, ganancia=0.5)
    vuelto = lut_from_hald(hald_image(lut), 17)
    salida = vuelto.apply(np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]))
    assert salida[0] == pytest.approx([0.5, 0.0, 0.0], abs=1e-6)
    assert salida[1] == pytest.approx([0.0, 0.0, 1.0], abs=1e-6)


def test_los_valores_fuera_de_rango_se_preservan():
    """Convención 1 de CONTRATOS: fuera de 0..1 es legal y no se recorta."""
    tabla = np.full((2, 2, 2, 3), -0.25, dtype=np.float32)
    tabla[1, 1, 1] = 4.0
    img = hald_image(LUT3D(table=tabla))
    assert img.min() == pytest.approx(-0.25)
    assert img.max() == pytest.approx(4.0)


def test_el_relleno_sobrante_es_negro_y_no_estorba():
    """17**3 = 4913 entradas en una imagen de 71x71 = 5041 píxeles."""
    img = hald_image(LUT3D.identity(17))
    assert lado_hald(17) == 71
    assert np.array_equal(img.reshape(-1, 3)[4913:], np.zeros((5041 - 4913, 3), np.float32))


def test_imagen_con_forma_equivocada():
    with pytest.raises(ErrorFormatoHald) as e:
        lut_from_hald(np.zeros((71, 71), dtype=np.float32), 17)
    assert "(alto, ancho, 3)" in str(e.value)


def test_imagen_demasiado_pequena():
    with pytest.raises(ErrorFormatoHald) as e:
        lut_from_hald(np.zeros((10, 10, 3), dtype=np.float32), 17)
    assert "4913" in str(e.value) and "71x71" in str(e.value)


def test_tamano_invalido():
    with pytest.raises(ErrorFormatoHald):
        lut_from_hald(np.zeros((71, 71, 3), dtype=np.float32), 1)
    with pytest.raises(ErrorFormatoHald):
        lado_hald(0)
