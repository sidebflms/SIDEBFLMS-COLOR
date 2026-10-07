"""SIDEBFLMS COLOR en la suite, tanda 3/3: avería/aviso por forma y rótulo, y la barra
de progreso de marca.

La suite no lleva pastillas de color de estado y **aquí no hay rojo**: un aviso es un
**rombo de contorno + «AVISO ·»** y una avería un **rombo relleno + «AVERÍA ·»**; el
mensaje que sigue va en crema. El rombo es el mismo dibujo que `MarcaDesajuste`.
Lo que no hay: esqueletos de carga. El prototipo tampoco los hizo: ninguna pantalla de
esta app carga datos (solo existe el diálogo de «Reanalizar timeline»).
"""

from __future__ import annotations

import base64
import colorsys
import re

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QProgressBar

from gui import identidad as idn
from gui.pantalla_aplicar import LineaPlan, Plan, ResultadoClip
from gui.widgets import MarcaDesajuste, marca_html
from tests.test_gui_apoyo import app_qt, demo, desconectado, lut_malo, vacio, ventana

pytestmark = pytest.mark.gui


def _rombo(html: str) -> QImage:
    uri = re.search(r'src="data:image/png;base64,([^"]+)"', html).group(1)
    imagen = QImage.fromData(base64.b64decode(uri), "PNG")
    assert not imagen.isNull()
    return imagen.convertToFormat(QImage.Format.Format_ARGB32)


def test_un_aviso_es_un_rombo_de_contorno_y_una_averia_un_rombo_relleno():
    app_qt()
    aviso, averia = _rombo(marca_html("aviso")), _rombo(marca_html("averia"))
    c = aviso.width() // 2
    assert aviso.pixelColor(c, c).alpha() == 0, "el rombo de aviso es de contorno: el centro esta vacio"
    assert averia.pixelColor(c, c).alpha() > 200, "el rombo de averia esta relleno"
    assert QColor(idn.BRAND_400).rgb() == averia.pixelColor(c, c).rgb() | 0xFF000000 & QColor(idn.BRAND_400).rgb()


def test_la_marca_lleva_el_rotulo_con_la_palabra_y_el_punto_medio():
    assert "AVISO" in marca_html("aviso") and "AVERÍA" in marca_html("averia")
    assert " · " in marca_html("aviso")
    assert "AVERÍA" not in marca_html("aviso")


def test_el_rombo_no_es_rojo_es_el_naranja_de_marca():
    """Cero rojo: matiz del naranja de marca (~12-16°), no el rojo de alarma (~0°)."""
    app_qt()
    for tipo in ("aviso", "averia"):
        imagen = _rombo(marca_html(tipo))
        visibles = [
            imagen.pixelColor(x, y)
            for x in range(imagen.width())
            for y in range(imagen.height())
            if imagen.pixelColor(x, y).alpha() > 200
        ]
        assert visibles, f"el rombo de {tipo} esta vacio"
        for color in visibles:
            h, s, _v = colorsys.rgb_to_hsv(color.redF(), color.greenF(), color.blueF())
            assert 0.025 < h < 0.09 and s > 0.5, f"{tipo}: matiz {h * 360:.0f}° no es el naranja de marca"


def test_el_rombo_de_la_marca_tiene_los_mismos_vertices_que_marca_desajuste():
    """Mismo dibujo: el vertice de arriba, el de la izquierda, el de abajo y el de la
    derecha estan pintados en los dos."""
    app_qt()
    m = MarcaDesajuste(lado=12)
    propio = m.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    suite = _rombo(marca_html("aviso"))
    for imagen in (propio, suite):
        w, h = imagen.width(), imagen.height()
        for x, y in ((w // 2, 2), (2, h // 2), (w // 2, h - 3), (w - 3, h // 2)):
            zona = [imagen.pixelColor(x + dx, y + dy).alpha() for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
            assert max(zona) > 100, f"falta un vertice del rombo cerca de {(x, y)}"


def test_el_plan_de_aplicar_marca_avisos_y_averias_por_forma_y_pone_lo_normal_en_crema():
    app_qt()
    v = ventana(demo())
    try:
        v.ir_a(2)
        p = v.p_aplicar
        normal = p._plan_a_html(Plan(lineas=[LineaPlan(
            clip_id="c1", nombre="uno", version_actual="Version 1", version_ya_existe=False,
            n_nodos=3, puede=True, resumen_cdl=("slope 1.0",), look_rel="SIDEB/look.cube",
        )]))
        assert "data:image/png" not in normal, "sin avisos no hay rombo"
        cabecera = normal.split("Se crea la versión")[0]
        assert idn.BRAND_400 not in cabecera, "la informacion normal ya no va en naranja"
        con_aviso = p._plan_a_html(Plan(lineas=[LineaPlan(
            clip_id="c1", nombre="uno", version_actual="Version 1", version_ya_existe=False,
            n_nodos=3, puede=True, avisos=("hay 4 nodos",), look_rel="x.cube",
        )]))
        assert con_aviso.count("data:image/png") == 1 and "AVISO" in con_aviso and "hay 4 nodos" in con_aviso
        bloqueado = p._plan_a_html(Plan(lineas=[LineaPlan(
            clip_id="c1", nombre="uno", version_actual="?", version_ya_existe=False,
            n_nodos=0, puede=False, motivo="tiene 1 nodo",
        )]))
        assert "No se puede" in bloqueado and "AVISO" in bloqueado
        sin_conexion = p._plan_a_html(Plan(error_global="No hay conexión con DaVinci Resolve."))
        assert "AVISO" in sin_conexion and "No hay conexión" in sin_conexion
    finally:
        v.close()


def test_el_resultado_de_una_escritura_fallida_es_una_averia_con_rombo_relleno():
    app_qt()
    v = ventana(demo())
    try:
        v.ir_a(2)
        html = v.p_aplicar._resultado_a_html([
            ResultadoClip(clip_id="c1", nombre="uno", ok=False, version="", mensaje="Resolve no contesta"),
        ])
        assert "AVERÍA" in html and html.count("data:image/png") == 1
        assert "Resolve no contesta" in html
    finally:
        v.close()


def test_el_qc_del_look_que_falla_sale_con_rombo_y_aviso_en_aplicar_y_en_reverse():
    app_qt()
    v = ventana(lut_malo())
    try:
        v.ir_a(2)
        t = v.p_aplicar.texto_look
        assert "data:image/png" in t.text() and "AVISO" in t.text()
        assert v.p_aplicar.texto_look.styleSheet() == "", "ya no se pinta en naranja el bloque entero"
    finally:
        v.close()


def test_el_estado_desconectado_se_ve_por_forma_y_por_rotulo_no_por_color():
    app_qt()
    v = ventana(desconectado())
    try:
        v.ir_a(2)
        v.p_aplicar.refrescar_plan()
        assert v.p_aplicar.punto_banda._ok is False
        assert v.punto_resolve._ok is False
        assert "desconectado" in v.p_aplicar.rotulo_banda.text()
        assert "AVISO" in v.p_aplicar.texto_plan.toHtml().upper()
    finally:
        v.close()


def test_la_barra_de_progreso_es_de_marca_y_no_el_azul_del_sistema():
    app_qt()
    css = idn.hoja_de_estilo()
    assert "QProgressBar::chunk" in css and idn.BRAND_600 in css.split("QProgressBar::chunk")[1][:80]
    barra = QProgressBar()
    barra.resize(220, 18)
    barra.setRange(0, 100)
    barra.setValue(60)
    barra.show()
    imagen = barra.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    relleno = QColor(idn.BRAND_600).rgb()
    assert any(imagen.pixel(x, 9) == relleno for x in range(imagen.width())), "no se ve el relleno brand-600"
    for x in range(imagen.width()):
        c = imagen.pixelColor(x, 9)
        h, s, _v = colorsys.rgb_to_hsv(c.redF(), c.greenF(), c.blueF())
        assert not (0.5 < h < 0.72 and s > 0.4), f"hay azul en la barra: {c.name()}"


def test_con_cero_clips_nada_se_rompe_y_la_app_lo_dice_con_palabras():
    """Estado vacio de la suite: frase llana, y ningun «0» donde deberia haber un texto."""
    app_qt()
    v = ventana(vacio())
    try:
        v.ir_a(1)
        assert v.p_comparar.visor._mensaje == "No hay clips que comparar."
        v.ir_a(0)
        assert v.p_clips.tabla.model().rowCount() == 0
    finally:
        v.close()
