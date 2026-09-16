"""Tests del ajuste a CDL.

El test que importa de verdad esta el primero: **fabricar un CDL conocido,
aplicarselo a una escena y comprobar que se recupera**. Todo lo demas de este
archivo sirve para acotar cuando deja de recuperarse.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.color import delta_e2000_mean
from core.contracts import CDL, LUMA_REC709
from core.matching.cdl_fit import (
    LIMITES_CDL,
    ajustar_cdl,
    aplicar_cdl_inverso,
)
from core.matching.cdl_fit import _aplica_parametros as aplica_parametros

#: Los CDL con los que se prueba la recuperacion. Cubren lo que pide el
#: encargo: suave, fuerte, con saturacion, con offsets negativos.
CDLS = {
    "identidad": CDL(),
    "suave": CDL(slope=(1.05, 1.0, 0.95), offset=(0.01, 0.0, -0.01), power=(1.0, 1.02, 0.98)),
    "fuerte": CDL(slope=(1.4, 0.9, 1.25), offset=(0.05, -0.03, 0.08), power=(0.85, 1.15, 0.92)),
    "con saturacion": CDL(slope=(1.1, 1.0, 0.92), offset=(0.02, 0.0, 0.03), saturation=1.35),
    "sin color": CDL(saturation=0.4),
    "offsets negativos": CDL(
        slope=(1.2, 1.1, 1.05), offset=(-0.08, -0.05, -0.12), power=(1.1, 1.05, 1.2), saturation=0.9
    ),
    "todo a la vez": CDL(
        slope=(1.35, 0.85, 1.18),
        offset=(-0.06, 0.04, -0.09),
        power=(0.78, 1.22, 0.95),
        saturation=1.25,
    ),
}


def _error_de_parametros(a: CDL, b: CDL) -> float:
    return max(
        float(np.abs(np.array(a.slope) - b.slope).max()),
        float(np.abs(np.array(a.offset) - b.offset).max()),
        float(np.abs(np.array(a.power) - b.power).max()),
        abs(a.saturation - b.saturation),
    )


# ---------------------------------------------------------------------------
# EL test: recuperar un CDL conocido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", list(CDLS))
def test_recupero_un_cdl_conocido_sobre_un_retrato(nombre, estudio_trabajo):
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    verdad = CDLS[nombre]
    estimado = ajustar_cdl(px, verdad.apply(px))
    assert _error_de_parametros(estimado, verdad) < 1e-9, (nombre, estimado)


@pytest.mark.parametrize("nombre", list(CDLS))
def test_recupero_un_cdl_conocido_sobre_un_exterior(nombre, exterior_trabajo):
    px = exterior_trabajo.reshape(-1, 3).astype(np.float64)
    verdad = CDLS[nombre]
    estimado = ajustar_cdl(px, verdad.apply(px))
    assert _error_de_parametros(estimado, verdad) < 1e-9, (nombre, estimado)


@pytest.mark.parametrize("nombre", list(CDLS))
def test_recupero_un_cdl_conocido_sobre_una_carta(nombre, carta):
    from tests.conftest import a_trabajo

    px = a_trabajo(carta).reshape(-1, 3).astype(np.float64)
    verdad = CDLS[nombre]
    estimado = ajustar_cdl(px, verdad.apply(px))
    assert _error_de_parametros(estimado, verdad) < 1e-9, (nombre, estimado)


def test_recupero_el_cdl_con_los_seis_tonos_de_piel(pieles_trabajo):
    """Si el ajuste solo funciona con pieles claras, aqui se ve."""
    verdad = CDLS["todo a la vez"]
    assert pieles_trabajo, "no hay nada que comprobar: el fixture `pieles_trabajo` ha salido vacio"
    for i, piel in enumerate(pieles_trabajo):
        px = piel.reshape(-1, 3).astype(np.float64)
        estimado = ajustar_cdl(px, verdad.apply(px))
        assert _error_de_parametros(estimado, verdad) < 1e-9, i


@pytest.mark.parametrize("sigma,tope", [(1e-4, 5e-4), (1e-3, 5e-3), (1e-2, 5e-2)])
def test_con_ruido_encima_el_error_crece_con_el_ruido(sigma, tope, estudio_trabajo):
    """Sin ruido sale exacto; con ruido sale proporcionado. Es lo que se espera
    de unos minimos cuadrados, y lo que descarta que este recuperando el CDL de
    casualidad."""
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    verdad = CDLS["todo a la vez"]
    destino = verdad.apply(px) + np.random.default_rng(1).normal(0.0, sigma, px.shape)
    assert _error_de_parametros(ajustar_cdl(px, destino), verdad) < tope


# ---------------------------------------------------------------------------
# Limites del optimizador: lo que garantiza que el CDL sea construible
# ---------------------------------------------------------------------------


def test_el_power_siempre_sale_mayor_que_cero(estudio_trabajo):
    """`CDL.__post_init__` lanza con power <= 0. Aqui se le tira encima el caso
    que de verdad tumba a un optimizador sin limites: un destino plano."""
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    for destino in (
        np.zeros_like(px),
        np.full_like(px, 0.5),
        np.tile([0.2, 0.2, 0.2], (px.shape[0], 1)),
        px * 1e-4,
    ):
        cdl = ajustar_cdl(px, destino)
        assert all(p > 0 for p in cdl.power), cdl
        assert all(p >= LIMITES_CDL["power"][0] for p in cdl.power), cdl


def test_todos_los_parametros_salen_dentro_de_los_limites(estudio_trabajo):
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    cdl = ajustar_cdl(px, px * 1000.0 - 500.0)
    for v in cdl.slope:
        assert LIMITES_CDL["slope"][0] <= v <= LIMITES_CDL["slope"][1]
    for v in cdl.offset:
        assert LIMITES_CDL["offset"][0] <= v <= LIMITES_CDL["offset"][1]
    for v in cdl.power:
        assert LIMITES_CDL["power"][0] <= v <= LIMITES_CDL["power"][1]
    assert LIMITES_CDL["saturation"][0] <= cdl.saturation <= LIMITES_CDL["saturation"][1]


def test_la_formula_del_optimizador_es_la_misma_que_la_de_cdl_apply(estudio_trabajo):
    """El optimizador no construye un `CDL` en cada iteracion. Si las dos
    formulas se separaran, el ajuste convergeria a otra cosa que la que se
    devuelve, y nadie se enteraria."""
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)[:5000]
    cdl = CDLS["todo a la vez"]
    p = np.array([*cdl.slope, *cdl.offset, *cdl.power, cdl.saturation])
    np.testing.assert_allclose(aplica_parametros(px, p), cdl.apply(px), rtol=0, atol=0)


# ---------------------------------------------------------------------------
# Destinos que un CDL no puede alcanzar
# ---------------------------------------------------------------------------


def test_un_destino_que_no_es_un_cdl_deja_residuo_y_no_miente(estudio_trabajo):
    """Un giro de color entre canales no lo hace un CDL (su matriz es diagonal
    mas saturacion). El ajuste tiene que quedarse corto, no fingir."""
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    m = np.array([[0.9, 0.15, -0.05], [0.1, 0.85, 0.05], [-0.05, 0.1, 0.95]])
    destino = px @ m.T + 0.02
    residuo = delta_e2000_mean(ajustar_cdl(px, destino).apply(px), destino)
    assert residuo > 0.1, "un giro de color no deberia salir gratis"
    assert residuo < 5.0, "pero tampoco es un desastre; si sube, algo se ha roto"


def test_el_ajuste_es_determinista(estudio_trabajo):
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    destino = CDLS["fuerte"].apply(px)
    a, b = ajustar_cdl(px, destino), ajustar_cdl(px, destino)
    assert a == b


# ---------------------------------------------------------------------------
# Formas, pesos y listas de distinta longitud
# ---------------------------------------------------------------------------


def test_listas_de_distinta_longitud_funcionan(estudio_trabajo):
    """No se empareja pixel a pixel: se empareja la distribucion.

    Ojo con lo que significa: los dos trozos tienen que ser muestras de la
    MISMA distribucion. Aqui se cogen uno de cada cinco pixeles y uno de cada
    tres, que recorren la imagen entera. Si en vez de eso se coge la mitad de
    arriba contra la mitad de abajo, el ajuste no recupera nada y hace bien: son
    dos distribuciones distintas de verdad, no dos muestras de la misma.
    """
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    lineal = CDL(slope=(1.4, 0.9, 1.25), offset=(0.05, -0.03, 0.08))
    estimado = ajustar_cdl(px[::5], lineal.apply(px)[::3])
    assert _error_de_parametros(estimado, lineal) < 0.01, estimado


def test_sin_parejas_un_cdl_NO_LINEAL_ya_no_se_recupera_exacto(estudio_trabajo):
    """Limite real, medido, y no es un fallo: es lo que se paga por no tener
    parejas.

    Cuando las dos listas no miden lo mismo, el destino se construye con el
    transporte MKL, que es **afin**. Un CDL con `power != 1` no es afin, asi
    que el transporte lo aplana a su mejor aproximacion lineal y lo que se
    recupera despues es esa aproximacion, no el CDL de partida.

    Numeros medidos sobre el retrato de estudio con
    `slope=(1.4, 0.9, 1.25), offset=(0.05, -0.03, 0.08), power=(0.85, 1.15, 0.92)`:

    * con parejas (mismas longitudes): error de parametros 4e-16, ΔE 0.0000
    * sin parejas (uno de cada 5 contra uno de cada 3): error de parametros
      **0.137** (todo el en `power`), ΔE **0.34**

    O sea: la imagen sale bien (0.34 de ΔE no se ve), pero los numeros del CDL
    que se le enseñan al colorista ya no son los que el habria escrito. Si eso
    importa, hay que pasar los pixeles emparejados.
    """
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    verdad = CDLS["fuerte"]
    destino = verdad.apply(px)
    estimado = ajustar_cdl(px[::5], destino[::3])
    assert _error_de_parametros(estimado, verdad) > 0.05, "si esto baja, mejor: mide y actualiza"
    assert delta_e2000_mean(estimado.apply(px), destino) < 1.0


def test_los_pesos_mandan_en_el_ajuste(estudio_trabajo, escena_estudio):
    """Ponderando solo la piel, el CDL tiene que ajustarse a la piel."""
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    piel = escena_estudio.skin_mask.reshape(-1)
    # Destino distinto para la piel que para el resto: sin pesos el ajuste
    # transige; con pesos en la piel, clava la piel.
    destino = CDLS["suave"].apply(px)
    destino[~piel] = CDLS["fuerte"].apply(px[~piel])
    w = piel.astype(np.float64)
    con_pesos = ajustar_cdl(px, destino, pesos=w)
    sin_pesos = ajustar_cdl(px, destino)
    error_piel_con = delta_e2000_mean(con_pesos.apply(px[piel]), destino[piel])
    error_piel_sin = delta_e2000_mean(sin_pesos.apply(px[piel]), destino[piel])
    assert error_piel_con < error_piel_sin


def test_pesos_de_longitud_equivocada_lanzan(estudio_trabajo):
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)[:1000]
    with pytest.raises(ValueError, match="pesos"):
        ajustar_cdl(px, px, pesos=np.ones(999))


def test_pesos_negativos_lanzan(estudio_trabajo):
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)[:1000]
    w = np.ones(1000)
    w[5] = -1.0
    with pytest.raises(ValueError, match=">= 0"):
        ajustar_cdl(px, px, pesos=w)


def test_forma_equivocada_lanza():
    with pytest.raises(ValueError, match=r"\(\.\.\., 3\)"):
        ajustar_cdl(np.zeros((10, 4)), np.zeros((10, 3)))


def test_sin_ni_una_pareja_finita_lanza():
    px = np.full((20, 3), np.nan)
    with pytest.raises(ValueError):
        ajustar_cdl(px, px)


def test_una_imagen_entera_vale_igual_que_una_lista(estudio_trabajo):
    img = estudio_trabajo.astype(np.float64)
    destino = CDLS["suave"].apply(img)
    assert ajustar_cdl(img, destino) == ajustar_cdl(img.reshape(-1, 3), destino.reshape(-1, 3))


# ---------------------------------------------------------------------------
# La inversa del CDL, que es lo que usa el LUT de residuo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", [n for n in CDLS if n != "sin color"])
def test_la_inversa_del_cdl_deshace_el_cdl(nombre, estudio_trabajo):
    px = estudio_trabajo.reshape(-1, 3).astype(np.float64)
    cdl = CDLS[nombre]
    # Solo donde el CDL no recorto: el `max(x, 0)` tira informacion y eso no se
    # puede deshacer (ver el docstring de `aplicar_cdl_inverso`).
    sin_recorte = (px * np.array(cdl.slope) + np.array(cdl.offset) > 1e-6).all(axis=1)
    vuelta = aplicar_cdl_inverso(cdl, cdl.apply(px))
    np.testing.assert_allclose(vuelta[sin_recorte], px[sin_recorte], rtol=1e-8, atol=1e-9)


def test_la_inversa_con_saturacion_cero_no_explota():
    """Saturacion 0 aplasta el croma y no hay vuelta atras. Tiene que devolver
    algo finito, no dividir por cero."""
    cdl = CDL(saturation=0.0)
    px = np.array([[0.2, 0.5, 0.7], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    salida = aplicar_cdl_inverso(cdl, cdl.apply(px))
    assert np.isfinite(salida).all()


def test_la_luma_del_cdl_es_la_de_rec709():
    """La saturacion del CDL usa pesos Rec.709 y solo para eso. Si alguien los
    cambia por los del espacio de trabajo, este test lo caza."""
    px = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    gris = CDL(saturation=0.0).apply(px)
    np.testing.assert_allclose(gris[:, 0], LUMA_REC709, rtol=1e-12)
