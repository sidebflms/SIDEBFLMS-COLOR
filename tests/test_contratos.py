"""Los contratos tienen que aguantar lo que les eche cualquier agente."""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import (
    CDL,
    LUMA_REC709,
    LUT3D,
    LUT_SIZE_DEFAULT,
    CoverageMap,
    confidence_level,
)


def test_cdl_identidad_no_toca_nada(rng):
    x = rng.random((16, 16, 3))
    assert np.allclose(CDL.identity().apply(x), x)


def test_cdl_recorta_negativos_antes_de_la_potencia():
    """Sin el max(x, 0) del estandar, (-0.1) ** 0.8 seria NaN."""
    c = CDL(power=(0.8, 0.8, 0.8))
    out = c.apply(np.array([[-0.1, 0.0, 0.5]]))
    assert np.isfinite(out).all()
    assert out[0, 0] == 0.0


def test_cdl_no_recorta_por_arriba():
    """Un especular a 4.0 tiene que seguir a 4.0 despues de un CDL neutro."""
    out = CDL.identity().apply(np.array([[4.0, 4.0, 4.0]]))
    assert out.max() == pytest.approx(4.0)


def test_cdl_saturacion_cero_deja_gris():
    c = CDL(saturation=0.0)
    out = c.apply(np.array([[0.8, 0.2, 0.1]]))
    assert out[0, 0] == pytest.approx(out[0, 1]) == pytest.approx(out[0, 2])
    assert out[0, 0] == pytest.approx(float(np.array([0.8, 0.2, 0.1]) @ LUMA_REC709))


def test_cdl_rechaza_power_no_positivo():
    with pytest.raises(ValueError, match="power"):
        CDL(power=(0.0, 1.0, 1.0))
    with pytest.raises(ValueError, match="power"):
        CDL(power=(-1.0, 1.0, 1.0))


def test_cdl_rechaza_no_finitos():
    with pytest.raises(ValueError):
        CDL(slope=(float("nan"), 1.0, 1.0))


def test_cdl_payload_es_lo_que_espera_resolve():
    p = CDL(slope=(1.5, 1.0, 0.5)).as_resolve_payload(2)
    assert set(p) == {"NodeIndex", "Slope", "Offset", "Power", "Saturation"}
    assert all(isinstance(v, str) for v in p.values())
    assert p["NodeIndex"] == "2"
    assert len(p["Slope"].split()) == 3


def test_cdl_payload_rechaza_indice_cero():
    with pytest.raises(ValueError, match="1-based"):
        CDL.identity().as_resolve_payload(0)


@pytest.mark.parametrize("size", [2, 17, 33, 65])
def test_lut_identidad_es_identidad(size, rng):
    x = rng.random((64, 3))
    out = LUT3D.identity(size).apply(x)
    assert np.abs(out - x).max() < 1e-5


def test_lut_sujeta_al_borde_fuera_de_dominio():
    lut = LUT3D.identity(17)
    out = lut.apply(np.array([[-0.5, 0.5, 2.0]]))
    assert out[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert out[0, 2] == pytest.approx(1.0, abs=1e-6)


def test_lut_rechaza_tabla_no_cubica():
    with pytest.raises(ValueError, match="cubica"):
        LUT3D(table=np.zeros((4, 5, 4, 3), dtype=np.float32))


def test_lut_rechaza_una_sola_muestra():
    with pytest.raises(ValueError, match="al menos 2"):
        LUT3D(table=np.zeros((1, 1, 1, 3), dtype=np.float32))


def test_lut_rechaza_dominio_invertido():
    with pytest.raises(ValueError, match="dominio"):
        LUT3D(table=LUT3D.identity(4).table, domain_min=(1.0, 0.0, 0.0), domain_max=(0.0, 1.0, 1.0))


def test_lut_indexacion_el_eje_cero_es_el_rojo():
    """Si alguien invierte los ejes, este test es el que lo caza."""
    lut = LUT3D.identity(3)
    # celda extrema en rojo, minima en verde y azul
    assert np.allclose(lut.table[2, 0, 0], [1.0, 0.0, 0.0])
    assert np.allclose(lut.table[0, 2, 0], [0.0, 1.0, 0.0])
    assert np.allclose(lut.table[0, 0, 2], [0.0, 0.0, 1.0])


def test_cobertura_vacia_es_cero():
    cm = CoverageMap(counts=np.zeros((8, 8, 8), np.int32), variance=np.zeros((8, 8, 8), np.float32))
    assert cm.coverage_fraction() == 0.0
    assert not cm.covered_mask().any()


def test_cobertura_respeta_min_samples():
    counts = np.zeros((4, 4, 4), np.int32)
    counts[0, 0, 0] = 3
    counts[1, 1, 1] = 4
    cm = CoverageMap(counts=counts, variance=np.zeros((4, 4, 4), np.float32), min_samples=4)
    assert cm.covered_mask().sum() == 1


@pytest.mark.parametrize(
    "score,esperado", [(1.0, "alta"), (0.75, "alta"), (0.74, "media"), (0.45, "media"), (0.0, "baja")]
)
def test_umbrales_de_confianza(score, esperado):
    assert confidence_level(score) == esperado


def test_tamano_de_lut_por_defecto_es_33():
    assert LUT_SIZE_DEFAULT == 33
