"""Averías y avisos: UN SOLO vocabulario, por palabra y por forma (nunca por color).

Auditoría de diseño del 2026-10-06 (bloque 5) y suite SIDEBFLMS (3/3): las líneas de
avería y de aviso de «Aplicar» iban en el mismo naranja que la información normal. Ahora
el estado lo dicen el **rombo** (relleno = avería, de contorno = aviso) y la **palabra**
(«AVERÍA ·» / «AVISO ·»), y la información normal va en crema:

* **AVERÍA**: falta de conexión, QC del look fallido, «No se puede…» y una escritura
  fallida en Resolve (algo que impide o estropea);
* **AVISO**: lo leve (un aviso de la línea o del resultado: se puede seguir);
* conexión con Resolve: por la forma del `PuntoEstado` (disco / contorno discontinuo).

**Cero rojo**: sigue valiendo `test_no_hay_ningun_rojo_de_error_en_toda_la_gui`.

Rojo declarado respecto a #11 solo en la forma: antes el prefijo era un texto en negrita
(«AVERÍA ·») y la conexión llevaba «●» / «○» delante; ahora el prefijo es rombo + palabra
(`marca_html`) y la conexión es el `PuntoEstado`. El **reparto** averia/aviso es el de #11
salvo que el QC fallido del panel del look pasa de aviso a avería (un solo criterio).
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
        assert idn.PALABRA_AVERIA in html and "data:image/png" in html
        assert "No hay conexión con DaVinci Resolve." in html
    finally:
        v.close()


def test_un_clip_que_no_se_puede_tocar_lleva_averia_y_uno_con_aviso_lleva_aviso():
    app_qt()
    v = ventana(demo())
    try:
        p = _pantalla(v)
        malo = p._plan_a_html(Plan(lineas=[_linea(puede=False, motivo="tiene 1 nodo")]))
        assert idn.PALABRA_AVERIA in malo and "No se puede" in malo
        con_aviso = p._plan_a_html(Plan(lineas=[_linea(avisos=("hay 4 nodos",))]))
        assert idn.PALABRA_AVISO in con_aviso and "hay 4 nodos" in con_aviso
        assert idn.PALABRA_AVERIA not in con_aviso
    finally:
        v.close()


def test_el_qc_del_look_que_falla_es_averia_en_el_plan_y_en_el_panel_del_look():
    app_qt()
    v = ventana(lut_malo())
    try:
        p = _pantalla(v)
        html = p._plan_a_html(Plan(lineas=[_linea()]))
        assert idn.PALABRA_AVERIA in html and "El look que va al nodo" in html
        assert idn.PALABRA_AVERIA in p.texto_look.text()
        assert idn.PALABRA_AVISO not in p.texto_look.text()
    finally:
        v.close()


def test_la_informacion_normal_va_en_crema_y_no_en_naranja():
    app_qt()
    v = ventana(demo())
    try:
        html = _pantalla(v)._plan_a_html(Plan(lineas=[_linea()]))
        cabecera = html.split("Se crea la versión")[0]
        assert idn.BRAND_400 not in cabecera, "la informacion normal ya no va en naranja"
        assert idn.PALABRA_AVERIA not in html and idn.PALABRA_AVISO not in html
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
        assert idn.PALABRA_AVERIA in html and "Resolve no contesta" in html
        assert idn.PALABRA_AVISO in html and "LUT sin releer" in html
    finally:
        v.close()


def test_resolve_conectado_y_desconectado_se_distinguen_por_la_forma():
    app_qt()
    v = ventana(demo())
    try:
        assert v.punto_resolve._ok is True
        assert v.estado_resolve.text().endswith("resolve conectado")
        assert v.p_aplicar.punto_banda._ok is True
    finally:
        v.close()
    app_qt()
    v = ventana(desconectado())
    try:
        assert v.punto_resolve._ok is False
        assert v.estado_resolve.text().endswith("resolve desconectado")
        _pantalla(v).refrescar_plan()
        assert v.p_aplicar.punto_banda._ok is False
    finally:
        v.close()
