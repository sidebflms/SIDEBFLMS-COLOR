"""QC de LUT.

EL TEST QUE MANDA es `test_la_identidad_pasa_limpia`. Un QC que se inventa
avisos sobre un LUT identidad no sirve para nada: la GUI se llenaría de ruido y
Mario dejaría de mirarlos en dos días. Si tocas un umbral en `core/io/qc.py` y
este test se pone rojo, el umbral está mal, no el test.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.contracts import CDL, LUT3D
from core.io import (
    CODIGO_BANDING,
    CODIGO_CANALES_INVERTIDOS,
    CODIGO_GAMUT,
    CODIGO_LUT_PLANO,
    CODIGO_NO_FINITO,
    CODIGO_NO_MONOTONIA,
    MAX_PROBLEMAS_POR_CODIGO,
    catalogo_luts_malos,
    lut_con_banding,
    lut_con_nan,
    lut_desde_curvas,
    lut_fuera_de_gamut,
    lut_no_monotono,
    lut_plano,
    lut_solo_rojo,
    qc_lut,
)


def _lut_de_funcion(n: int, fn) -> LUT3D:
    """Aplica `fn` a la rejilla identidad y recorta a 0..1. Es la forma en que
    el agente F va a fabricar LUT de verdad, así que es lo que hay que probar."""
    ident = np.asarray(LUT3D.identity(n).table, dtype=np.float64)
    return LUT3D(table=np.clip(fn(ident), 0.0, 1.0).astype(np.float32))


# ---------------------------------------------------------------------------
# Falsos positivos: lo que NO puede avisar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [2, 17, 33, 65])
def test_la_identidad_pasa_limpia(size):
    """EL test del módulo. Ni un aviso, de ningún tipo, en ningún tamaño."""
    informe = qc_lut(LUT3D.identity(size))
    assert informe.problemas == (), informe.resumen()
    assert informe.ok
    assert not informe.hay_errores
    assert informe.resumen().endswith("limpio.")


def test_un_lut_que_solo_toca_el_rojo_pasa_limpio():
    assert qc_lut(lut_solo_rojo(33, ganancia=0.5)).ok


@pytest.mark.parametrize("size", [17, 33, 65])
def test_una_curva_en_s_de_contraste_pasa_limpia(size):
    """Lo que hace un colorista todos los días: subir contraste con una S."""
    assert qc_lut(_lut_de_funcion(size, lambda x: x * x * (3 - 2 * x))).ok


@pytest.mark.parametrize("size", [17, 33, 65])
def test_un_cdl_realista_convertido_a_lut_pasa_limpio(size):
    cdl = CDL(
        slope=(1.05, 0.98, 0.93),
        offset=(0.01, 0.0, -0.005),
        power=(0.95, 1.0, 1.08),
        saturation=1.15,
    )
    assert qc_lut(_lut_de_funcion(size, cdl.apply)).ok


def test_un_lut_que_desatura_no_cuenta_como_ejes_cambiados():
    """Un LUT monocromo mueve los tres canales de salida con los tres de
    entrada por igual. El detector de ejes invertidos NO puede confundirlo con
    un rojo y un azul cambiados de sitio."""
    luma = np.array([0.2126, 0.7152, 0.0722])
    lut = _lut_de_funcion(33, lambda x: np.repeat((x @ luma)[..., None], 3, axis=-1))
    assert CODIGO_CANALES_INVERTIDOS not in qc_lut(lut).codigos()


# ---------------------------------------------------------------------------
# Verdaderos positivos: cada LUT roto saca SU código y sólo el suyo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", sorted(catalogo_luts_malos(5)))
def test_cada_lut_malo_saca_su_codigo_y_solo_el_suyo(codigo):
    """Los generadores de `core/io/lut_malos.py` están calibrados para romper
    UNA cosa. Si este test empieza a fallar es que alguien ha cambiado un
    parámetro por defecto y el LUT ya no prueba lo que dice probar."""
    lut = catalogo_luts_malos(17)[codigo]
    informe = qc_lut(lut)
    assert informe.codigos() == (codigo,), informe.resumen()
    assert not informe.ok


def test_la_no_monotonia_dice_que_celda_y_que_eje():
    p = qc_lut(lut_no_monotono(17, eje=1)).por_codigo(CODIGO_NO_MONOTONIA)[0]
    assert p.gravedad == "error"
    assert p.eje == 1 and p.canal == 1
    assert p.celda is not None and p.celda[1] == 7  # la celda de antes del hundimiento
    assert p.valor < 0
    assert "verde" in p.mensaje and "BAJA" in p.mensaje


def test_la_no_monotonia_se_caza_en_los_tres_ejes():
    for eje in (0, 1, 2):
        problemas = qc_lut(lut_no_monotono(17, eje=eje)).por_codigo(CODIGO_NO_MONOTONIA)
        assert problemas and all(p.eje == eje for p in problemas)


def test_el_banding_dice_donde_esta_el_escalon():
    p = qc_lut(lut_con_banding(17, eje=2, salto=0.3)).por_codigo(CODIGO_BANDING)[0]
    assert p.gravedad == "aviso"
    assert p.eje == 2 and p.canal == 2
    # El escalón está entre la celda 7 y la 8 (`lut_con_banding` suma el salto
    # a partir de `size // 2`), así que las dos son culpables y se avisa de las
    # dos; la primera que sale es la 7.
    assert p.celda is not None and p.celda[2] == 7
    celdas = {q.celda[2] for q in qc_lut(lut_con_banding(17, eje=2)).por_codigo(CODIGO_BANDING)}
    assert celdas == {7, 8}
    assert "banda" in p.mensaje


def test_un_escalon_pequeno_no_se_marca_como_banding():
    """El umbral tiene dos patas y la absoluta es la que evita el ruido: un
    escalón de 0.005 (algo más de 1/255) no se ve y no se avisa."""
    assert CODIGO_BANDING not in qc_lut(lut_con_banding(17, salto=0.005)).codigos()


def test_el_gamut_dice_por_que_lado_se_sale():
    informe = qc_lut(lut_fuera_de_gamut(17, exceso=0.25))
    problemas = informe.por_codigo(CODIGO_GAMUT)
    assert problemas
    assert all(p.gravedad == "aviso" for p in problemas)
    assert informe.metricas["minimo"] == pytest.approx(-0.25, abs=1e-5)
    assert informe.metricas["maximo"] == pytest.approx(1.25, abs=1e-5)
    assert any("por debajo de 0" in p.mensaje for p in problemas)
    assert not informe.hay_errores, "salirse de gamut es un aviso, no un error"


def test_el_nan_es_un_error_y_dice_la_celda():
    p = qc_lut(lut_con_nan(17, celda=(3, 4, 5), canal=1)).por_codigo(CODIGO_NO_FINITO)[0]
    assert p.gravedad == "error"
    assert p.celda == (3, 4, 5) and p.canal == 1
    assert np.isnan(p.valor)


def test_el_lut_plano_es_un_error():
    informe = qc_lut(lut_plano(17, color=(0.2, 0.4, 0.6)))
    assert informe.hay_errores
    p = informe.por_codigo(CODIGO_LUT_PLANO)[0]
    assert "0.2" in p.mensaje and "aplasta" in p.mensaje


def test_los_ejes_cambiados_se_detectan():
    """El desastre que este módulo entero existe para evitar."""
    from core.io import lut_canales_invertidos

    problemas = qc_lut(lut_canales_invertidos(17)).por_codigo(CODIGO_CANALES_INVERTIDOS)
    ejes = {p.eje for p in problemas}
    assert ejes == {0, 2}, "el rojo apunta al azul y el azul al rojo"
    assert all("ejes cambiados" in p.mensaje for p in problemas)


# ---------------------------------------------------------------------------
# Límites conocidos, escritos a propósito
# ---------------------------------------------------------------------------


def test_una_gamma_fuerte_cerca_del_negro_se_marca_como_banding():
    """LÍMITE REAL, no bug. Este test documenta una decisión discutible.

    Una curva t**0.45 en una rejilla uniforme no se puede representar bien cerca
    del negro: medido sobre una rampa, un LUT de 65 puntos se desvía 11/255 de
    la curva real en los primeros pasos, y deja un quiebro de pendiente. El QC lo
    marca, y lo marca también con 65 puntos, así que "sube la resolución" no es
    el remedio: el remedio es no meter esa curva en un LUT 3D.

    Es un detector del lado sensible. Mario puede querer subir
    `UMBRAL_BANDING` o `SALTO_MINIMO_BANDING` si esto le molesta; está en
    `core/io/NOTAS.md`.
    """
    for size in (17, 33, 65):
        informe = qc_lut(_lut_de_funcion(size, lambda x: x**0.45))
        assert CODIGO_BANDING in informe.codigos(), f"tamaño {size}"
    # La gamma contraria (2.2) es suave donde importa y NO se marca.
    assert qc_lut(_lut_de_funcion(33, lambda x: x**2.2)).ok


def test_con_tamano_2_no_hay_segunda_derivada_y_no_se_busca_banding():
    """Caso frontera: el LUT legal más pequeño. No puede reventar ni avisar."""
    informe = qc_lut(LUT3D.identity(2))
    assert informe.ok
    assert informe.metricas["celdas_con_banding"] == 0.0


def test_no_se_listan_mas_problemas_de_la_cuenta_pero_si_se_cuentan():
    """Un LUT entero de NaN no puede devolver 14.739 problemas a la GUI."""
    tabla = np.full((17, 17, 17, 3), np.nan, dtype=np.float32)
    informe = qc_lut(LUT3D(table=tabla))
    listados = informe.por_codigo(CODIGO_NO_FINITO)
    assert len(listados) == MAX_PROBLEMAS_POR_CODIGO
    assert informe.metricas["no_finitos"] == 17**3 * 3


def test_el_resumen_es_una_linea_en_castellano():
    resumen = qc_lut(lut_no_monotono(17)).resumen()
    assert resumen.startswith("LUT de 17:")
    assert CODIGO_NO_MONOTONIA in resumen


def test_un_lut_con_mezcla_de_canales_fuerte_pero_sano_pasa_limpio():
    """Un tinte de verdad mezcla canales. Eso NO es un defecto."""
    n = 33
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    lut = lut_desde_curvas(t * 0.9 + 0.05, t, t * 0.8 + 0.1)
    assert qc_lut(lut).ok
