"""Casos frontera del emparejamiento.

La regla de este archivo: **nada puede lanzar una excepcion que no sea un
`ValueError` explicado, nada puede devolver NaN, y todo lo que es una barbaridad
tiene que salir con la confianza por los suelos.** Un plano absurdo no puede
salir con un "alta" al lado.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import CDL
from core.matching import ajustar_cdl, emparejar, transporte_mkl

GRADO = CDL(slope=(1.2, 0.9, 1.1), offset=(0.02, -0.01, 0.03), power=(0.9, 1.1, 1.0))


def pix(img) -> np.ndarray:
    return np.asarray(img, dtype=np.float64).reshape(-1, 3)


@pytest.fixture
def escena(estudio_trabajo) -> np.ndarray:
    return pix(estudio_trabajo)


# ---------------------------------------------------------------------------
# Material imposible: nada de NaN, nada de excepciones raras
# ---------------------------------------------------------------------------


def casos(escena: np.ndarray) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    negro = np.zeros((100, 3))
    saturado = np.ones((100, 3))
    un_pixel = np.array([[0.3, 0.4, 0.5]])
    un_color = np.tile([0.2, 0.5, 0.7], (500, 1))
    gris = np.tile(np.linspace(0.0, 1.0, 500)[:, None], (1, 3))
    return {
        "negro -> escena": (negro, escena),
        "escena -> negro": (escena, negro),
        "saturado -> escena": (saturado, escena),
        "escena -> saturado": (escena, saturado),
        "un pixel -> escena": (un_pixel, escena),
        "escena -> un pixel": (escena, un_pixel),
        "un color -> escena": (un_color, escena),
        "escena -> un color": (escena, un_color),
        "gris -> escena": (gris, escena),
        "escena -> gris": (escena, gris),
        "un pixel -> un pixel": (un_pixel, np.array([[0.1, 0.2, 0.3]])),
        "fuera de rango": (escena * 3.0 - 1.0, escena),
        "longitudes distintas": (escena[::7], escena[::3]),
    }


@pytest.mark.parametrize("nombre", list(casos(np.zeros((10, 3)))))
def test_ningun_caso_frontera_devuelve_nan_ni_revienta(nombre, escena):
    origen, destino = casos(escena)[nombre]
    m = emparejar(origen, destino)
    assert np.isfinite(m.delta_e_before), nombre
    assert np.isfinite(m.delta_e_after), nombre
    assert np.isfinite(m.confidence.score), nombre
    assert 0.0 <= m.confidence.score <= 1.0, nombre
    assert all(np.isfinite(v) for v in (*m.cdl.slope, *m.cdl.offset, *m.cdl.power)), nombre
    assert all(p > 0 for p in m.cdl.power), nombre
    assert m.confidence.reasons, nombre


@pytest.mark.parametrize(
    "nombre",
    [
        "negro -> escena",
        "escena -> negro",
        "saturado -> escena",
        "escena -> saturado",
        "un pixel -> escena",
        "escena -> un pixel",
        "un color -> escena",
        "escena -> un color",
        "gris -> escena",
        "escena -> gris",
    ],
)
def test_el_material_imposible_sale_con_la_confianza_por_los_suelos(nombre, escena):
    """Es lo que de verdad protege a Mario: que ninguno de estos salga en verde."""
    origen, destino = casos(escena)[nombre]
    m = emparejar(origen, destino)
    assert m.confidence.level == "baja", (nombre, m.confidence.score)


def test_un_plano_plano_contra_una_escena_se_marca_como_otro_contenido(escena):
    un_color = np.tile([0.2, 0.5, 0.7], (500, 1))
    assert emparejar(un_color, escena).content_mismatch is True


def test_blanco_y_negro_contra_color_no_inventa_croma(escena):
    """Con un origen sin croma, el transporte no puede sacarse el color de la
    manga: lo que no se puede medir se deja como esta (ver `mkl.py`)."""
    gris = np.tile(np.linspace(0.05, 0.6, 5000)[:, None], (1, 3))
    a, _ = transporte_mkl(gris, escena)
    from core.matching import ganancias

    assert ganancias(a).max() < 5.0


# ---------------------------------------------------------------------------
# Valores fuera de 0..1
# ---------------------------------------------------------------------------


def test_los_valores_fuera_de_rango_son_legales_y_se_igualan_bien(escena):
    """El contrato 1 dice que fuera de 0..1 es legal y hay que preservarlo."""
    estirado = escena * 3.0 - 1.0
    assert estirado.min() < 0.0
    m = emparejar(estirado, escena)
    assert m.delta_e_after < 0.5
    assert m.confidence.level == "alta"


def test_valores_enormes_no_desbordan(escena):
    m = emparejar(escena * 1e4, escena)
    assert np.isfinite(m.delta_e_after)
    assert np.isfinite(m.confidence.score)


def test_valores_negativos_en_el_destino_tambien(escena):
    m = emparejar(escena, escena - 0.5)
    assert np.isfinite(m.delta_e_after)
    assert all(p > 0 for p in m.cdl.power)


# ---------------------------------------------------------------------------
# NaN: la desviacion deliberada respecto a core.color
# ---------------------------------------------------------------------------


def test_los_nan_se_descartan_se_cuentan_y_se_dicen(escena):
    """`core.color` propaga los NaN; aqui NO, porque un CDL con un NaN dentro no
    se puede ni construir. A cambio se cuenta y se dice. Ver `empareja.py`."""
    roto = escena.copy()
    roto[::100] = np.nan
    m = emparejar(roto, escena)
    assert np.isfinite(m.delta_e_after)
    assert m.confidence.metrics["fraccion_no_finita"] == pytest.approx(0.01, abs=2e-3)
    assert any("no finitos" in n for n in m.notes)


def test_muchos_nan_bajan_la_confianza(escena):
    poco, mucho = escena.copy(), escena.copy()
    poco[::200] = np.nan
    mucho[::4] = np.nan
    assert emparejar(mucho, escena).confidence.score < emparejar(poco, escena).confidence.score


def test_un_infinito_cuenta_igual_que_un_nan(escena):
    roto = escena.copy()
    roto[::100] = np.inf
    m = emparejar(roto, escena)
    assert np.isfinite(m.delta_e_after)
    assert m.confidence.metrics["fraccion_no_finita"] > 0.0


def test_todo_nan_lanza_un_valueerror_claro(escena):
    roto = np.full_like(escena, np.nan)
    with pytest.raises(ValueError, match="ni un pixel valido"):
        emparejar(roto, escena)
    with pytest.raises(ValueError, match="ni un pixel valido"):
        emparejar(escena, roto)


# ---------------------------------------------------------------------------
# Formas mal
# ---------------------------------------------------------------------------


def test_formas_invalidas_lanzan_valueerror(escena):
    with pytest.raises(ValueError):
        emparejar(np.zeros((10, 4)), escena)
    with pytest.raises(ValueError):
        emparejar(escena, np.zeros((10, 2)))
    with pytest.raises(ValueError):
        emparejar(np.zeros((0, 3)), escena)


def test_una_lista_vacia_lanza(escena):
    with pytest.raises(ValueError):
        ajustar_cdl(np.zeros((0, 3)), escena)


# ---------------------------------------------------------------------------
# Origen y destino identicos
# ---------------------------------------------------------------------------


def test_identicos_dan_cdl_identidad_y_delta_e_cero(escena):
    m = emparejar(escena, escena)
    assert m.cdl.is_identity(tol=1e-8), m.cdl
    assert m.delta_e_before == pytest.approx(0.0, abs=1e-9)
    assert m.delta_e_after == pytest.approx(0.0, abs=1e-9)


def test_identicos_con_lut_dan_lut_identidad(escena):
    m = emparejar(escena, escena, con_lut=True)
    assert m.delta_e_after == pytest.approx(0.0, abs=1e-6)


def test_identicos_aunque_sean_de_un_solo_color():
    plano = np.tile([0.37, 0.37, 0.37], (400, 1))
    m = emparejar(plano, plano)
    assert np.isfinite(m.delta_e_after)
    assert m.delta_e_after == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# El negro absoluto: era un salto de core.color, ya arreglado. Queda de guardia.
# ---------------------------------------------------------------------------


def test_el_negro_absoluto_ya_no_da_un_salto_en_lab(escena):
    """Historia, por si alguien vuelve a tropezar: esto ESTUVO roto.

    `core.color.rgb_to_lab` de un negro EXACTO devolvia L* = -16 en vez de 0,
    porque la extension impar de la f() de CIE L*a*b* usaba `np.sign(t)` y
    `sign(0) = 0`, mientras que la rama lineal de la CIE vale 16/116. Habia un
    salto de 16 unidades de L* justo en el cero y el ΔE2000 entre un negro
    exacto y un "casi negro" de 1e-30 salia **8.57**.

    Se veia en un sitio de este modulo: emparejar una escena contra un plano
    negro puro dejaba un `delta_e_after` de **7.65** que no era del ajuste. El
    agente A lo arreglo (era de `core/color/**`, no mio) y ahora el mismo caso
    sale **0.0**.

    Este test se queda de guardia: es barato y caza la regresion al instante.
    """
    from core.color import delta_e2000, rgb_to_lab

    np.testing.assert_allclose(rgb_to_lab(np.zeros(3)), np.zeros(3), atol=1e-12)
    assert float(delta_e2000(np.zeros(3), np.full(3, 1e-30))) < 1e-6
    assert emparejar(escena, np.zeros((100, 3))).delta_e_after < 1e-6
