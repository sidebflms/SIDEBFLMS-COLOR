"""Averías y avisos se reconocen por una PALABRA delante, no solo por el color; la
conexión con Resolve, por la FORMA del círculo.

Auditoría de diseño del 2026-10-06 (bloque 5): las líneas de avería y de aviso de
la pantalla Aplicar iban todas en el mismo naranja que la información normal
(«Se crea la versión…»), así que un daltónico —o cualquiera con la pantalla a
poca luz— no las distinguía de lo que va bien; y «resolve desconectado» se
distinguía de «resolve conectado» solo por la palabra. Ahora:

* avería -> «AVERÍA ·» delante; aviso -> «AVISO ·» delante; ambos en `brand-400`;
* la información normal va en crema (`brand-50`);
* «● resolve conectado» / «○ resolve desconectado» (círculo lleno / vacío).

**Cero rojo**: sigue valiendo `test_no_hay_ningun_rojo_de_error_en_toda_la_gui`.
"""

from __future__ import annotations

import pytest

from gui import identidad as idn
from gui.pantalla_aplicar import LineaPlan, Plan, ResultadoClip
from tests.test_gui_apoyo import app_qt, demo, desconectado, lut_malo, ventana

pytestmark = pytest.mark.gui


def _linea(**kw) -> LineaPlan:
    base = dict(
        clip_id="c1", nombre="clip uno", version_actual="Version 1", version_ya_existe=False,
        n_nodos=3, puede=True, resumen_cdl=("slope 1.0",), look_rel="SIDEB/look.cube",
    )
    base.update(kw)
    return LineaPlan(**base)


def _pantalla(v):
    v.ir_a(2)
    return v.p_aplicar


def test_el_error_global_lleva_el_prefijo_de_averia():
    app_qt()
    v = ventana(demo())
    try:
        html = _pantalla(v)._plan_a_html(Plan(error_global="No hay conexión con DaVinci Resolve."))
        assert idn.PREFIJO_AVERIA in html
        assert "No hay conexión con DaVinci Resolve." in html
    finally:
        v.close()


def test_un_clip_que_no_se_puede_tocar_lleva_averia_y_uno_con_aviso_lleva_aviso():
    app_qt()
    v = ventana(demo())
    try:
        p = _pantalla(v)
        malo = p._plan_a_html(Plan(lineas=[_linea(puede=False, motivo="tiene 1 nodo")]))
        assert f"{idn.PREFIJO_AVERIA}</b> NO SE PUEDE" in malo
        con_aviso = p._plan_a_html(Plan(lineas=[_linea(avisos=("hay 4 nodos",))]))
        assert f"{idn.PREFIJO_AVISO}</b> hay 4 nodos" in con_aviso
        assert idn.PREFIJO_AVERIA not in con_aviso
    finally:
        v.close()


def test_el_qc_del_look_que_falla_es_averia_en_el_plan_y_aviso_en_el_panel_del_look():
    app_qt()
    v = ventana(lut_malo())
    try:
        p = _pantalla(v)
        html = p._plan_a_html(Plan(lineas=[_linea()]))
        assert f"{idn.PREFIJO_AVERIA}</b> El look que va al nodo" in html
        assert p.texto_look.text().startswith(idn.PREFIJO_AVISO)
    finally:
        v.close()


def test_la_informacion_normal_va_en_crema_y_no_en_naranja():
    app_qt()
    v = ventana(demo())
    try:
        html = _pantalla(v)._plan_a_html(Plan(lineas=[_linea()]))
        cabecera = html.split("Se crea la versión")[0]
        assert cabecera.endswith(f'<div style="color:{idn.BRAND_50};">')
        assert idn.PREFIJO_AVERIA not in html and idn.PREFIJO_AVISO not in html
    finally:
        v.close()


def test_el_resultado_de_aplicar_marca_las_averias_y_los_avisos():
    app_qt()
    v = ventana(demo())
    try:
        p = _pantalla(v)
        html = p._resultado_a_html([
            ResultadoClip(clip_id="c1", nombre="uno", ok=False, version="", mensaje="Resolve no contesta"),
            ResultadoClip(clip_id="c2", nombre="dos", ok=True, version="SIDEB COLOR",
                          mensaje="escrito", avisos=("LUT sin releer",)),
        ])
        assert f"{idn.PREFIJO_AVERIA}</b>" in html
        assert f"{idn.PREFIJO_AVISO}</b> LUT sin releer" in html
    finally:
        v.close()


def test_resolve_conectado_y_desconectado_se_distinguen_por_la_forma():
    app_qt()
    v = ventana(demo())
    try:
        assert v.estado_resolve.text().startswith(idn.MARCA_CONECTADO)
        assert v.p_aplicar.rotulo_banda.text().startswith(idn.MARCA_CONECTADO)
    finally:
        v.close()
    app_qt()
    v = ventana(desconectado())
    try:
        assert v.estado_resolve.text().startswith(idn.MARCA_DESCONECTADO)
        _pantalla(v).refrescar_plan()
        assert v.p_aplicar.rotulo_banda.text().startswith(idn.MARCA_DESCONECTADO)
    finally:
        v.close()
    assert idn.MARCA_CONECTADO != idn.MARCA_DESCONECTADO
