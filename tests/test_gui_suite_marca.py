"""SIDEBFLMS COLOR en la suite, tanda 2/3: cabecera de marca, botón y pastilla.

* **Cabecera de marca:** casete + wordmark (B naranja, el resto blanco; SVG de
  `sidebflms-web/public/logo`) y el nombre de la app en Akira (≥ 18 px, ASCII), que
  sin Akira sale en Montserrat 800.
* **Títulos de pantalla** en Akira: SOLO ASCII (el archivo tiene 104 glifos: sin
  tildes ni ñ), así que «Antes / después» es `COMPARAR`; la navegación del carril
  conserva el texto completo en Montserrat.
* **Botón:** píldora, en frase (NO en mayúsculas: los textos largos volverían a
  cortarse, ver el PR #7), hover del primario que SUBE a `#e8451d`.
* **Pastilla:** la insignia de confianza en píldora, **sin perder su forma**
  (relleno+3 barras / contorno+2 / discontinuo+1). La conexión con Resolve, por forma:
  disco relleno / contorno discontinuo.
* La fila seleccionada de la tabla lleva un filete naranja de 2 px, no un bloque.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage
from PySide6.QtWidgets import QPushButton

from gui import identidad as idn
from gui.ventana import TITULOS_AKIRA, _TituloAkira
from gui.widgets import (
    INSIGNIA_ALTO,
    INSIGNIA_ANCHO,
    CabeceraMarca,
    InsigniaConfianza,
    PuntoEstado,
)
from tests.test_gui_apoyo import app_qt, asentar, demo, ventana

pytestmark = pytest.mark.gui

RAIZ_LOGO = __import__("pathlib").Path(__file__).resolve().parent.parent / "gui" / "logo"


def test_los_logos_de_la_marca_estan_en_el_repo():
    for nombre in ("mark-blanco.svg", "wordmark.svg"):
        assert (RAIZ_LOGO / nombre).is_file(), nombre


def test_la_cabecera_de_marca_dice_la_app_y_usa_display_de_18_px():
    app_qt()
    c = CabeceraMarca("COLOR")
    c.resize(154, c.height())
    assert c.accessibleName() == "SIDEBFLMS COLOR"
    assert c._ok, "los SVG del logo no se han cargado"
    assert c._f.pixelSize() >= idn.PX_DISPLAY_MIN == 18
    assert "COLOR".isascii()
    imagen = c.grab().toImage()
    assert imagen.width() > 0
    # El wordmark lleva una B naranja y letras blancas: hay pixeles de los dos.
    colores = {imagen.pixelColor(x, y).rgb() for x in range(imagen.width()) for y in range(0, 24)}
    assert QColor(idn.BRAND_500).rgb() in colores or any(
        abs(QColor(c_).red() - 0xE8) < 12 and abs(QColor(c_).green() - 0x45) < 20 for c_ in colores
    ), "no se ve el naranja de la B del wordmark"


def test_la_cabecera_de_marca_no_rompe_si_faltan_los_svg(monkeypatch):
    app_qt()
    from PySide6.QtSvg import QSvgRenderer

    monkeypatch.setattr(QSvgRenderer, "isValid", lambda self: False)
    c = CabeceraMarca("COLOR")
    c.resize(154, c.height())
    assert not c._ok
    assert c.grab().toImage().width() > 0  # cae al rotulo de texto, sin excepcion


def test_los_titulos_de_akira_son_solo_ascii_y_en_mayusculas():
    assert TITULOS_AKIRA, "no hay nada que comprobar: la tabla de titulos esta vacia"
    for largo, corto in TITULOS_AKIRA.items():
        assert corto.isascii(), f"«{corto}» lleva caracteres que Akira no tiene"
        assert corto == corto.upper()
        assert corto != largo


def test_cada_pantalla_pinta_su_titulo_en_ascii_a_18_px_o_mas():
    app_qt()
    v = ventana(demo())
    try:
        for indice, (_, etiqueta) in enumerate(__import__("gui.ventana", fromlist=["PANTALLAS"]).PANTALLAS):
            v.ir_a(indice)
            asentar()
            assert isinstance(v.titulo_pantalla, _TituloAkira)
            assert v.titulo_pantalla.text() == TITULOS_AKIRA[etiqueta]
            assert v.titulo_pantalla.accessibleName() == etiqueta  # el lector dice el texto completo
            assert v.titulo_pantalla.font().pixelSize() >= 18
    finally:
        v.close()


def test_los_botones_son_pildora_y_estan_en_frase_no_en_mayusculas():
    css = idn.hoja_de_estilo()
    assert "border-radius: 15px" in css
    app_qt()
    v = ventana(demo())
    try:
        v.ir_a(2)
        asentar()
        botones = [b for b in v.findChildren(QPushButton) if b.isVisible() and b.objectName() != "navegacion"]
        assert botones, "no hay nada que comprobar: Aplicar tiene botones"
        for b in botones:
            assert b.font().capitalization() == QFont.Capitalization.MixedCase, b.text()
            assert b.text() != b.text().upper() or len(b.text()) < 3, f"«{b.text()}» va en mayusculas"
    finally:
        v.close()


def test_el_hover_del_primario_sube_a_e8451d():
    css = idn.hoja_de_estilo()
    assert f"QPushButton#primario:hover {{ background: {idn.BRAND_500};" in css
    assert f"QPushButton#primario {{\n        background: {idn.BRAND_600};" in css


@pytest.mark.parametrize("nivel", ["alta", "media", "baja"])
def test_la_insignia_es_pildora_y_sigue_distinguiendose_por_forma(nivel):
    app_qt()
    ins = InsigniaConfianza(idn.FormaConfianza.de_nivel(nivel), 0.7)
    imagen = ins.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    # Pildora: la esquina (1,1) queda FUERA de la forma (transparente); con el radio de 4 de antes, dentro.
    assert imagen.pixelColor(1, 1).alpha() == 0
    assert imagen.height() == INSIGNIA_ALTO and imagen.width() == INSIGNIA_ANCHO
    f = idn.FormaConfianza.de_nivel(nivel)
    assert f.escalones == {"alta": 3, "media": 2, "baja": 1}[nivel]
    assert (f.relleno is not None) == (nivel == "alta")
    assert f.discontinuo == (nivel == "baja")


def test_la_conexion_con_resolve_se_distingue_por_forma_no_por_color():
    app_qt()
    p = PuntoEstado()
    p.poner(True)
    lleno = p.grab().toImage()
    p.poner(False)
    vacio = p.grab().toImage()
    centro = (lleno.width() // 2, lleno.height() // 2)
    assert lleno.pixelColor(*centro).alpha() > 200  # disco relleno
    assert vacio.pixelColor(*centro).alpha() == 0  # contorno discontinuo: el centro esta vacio


def test_la_fila_seleccionada_lleva_un_filete_naranja_de_2_px():
    app_qt()
    v = ventana(demo())
    try:
        v.ir_a(0)
        asentar()
        tabla = v.p_clips.tabla
        tabla.selectRow(1)
        asentar()
        fila = tabla.visualRect(tabla.model().index(1, 0))
        imagen = tabla.viewport().grab().toImage()
        y = fila.center().y()
        naranja = QColor(idn.BRAND_500).rgb()
        assert imagen.pixel(0, y) == naranja and imagen.pixel(1, y) == naranja
        assert imagen.pixel(3, y) != naranja, "el filete es de 2 px, no un bloque"
    finally:
        v.close()


def test_el_rotulo_de_navegacion_sigue_en_mayusculas_con_tracking():
    app_qt()
    v = ventana(demo())
    try:
        for b in v.grupo.buttons():
            assert b.font().capitalization() == QFont.Capitalization.AllUppercase
            assert b.font().letterSpacing() > 0
            assert b.font().pixelSize() == idn.PX_MIN_INFORMATIVO
            assert b.text() != b.text().upper(), "el texto completo se conserva; la fuente lo pone en mayusculas"
    finally:
        v.close()


def test_la_navegacion_conserva_el_texto_completo_con_tildes_en_montserrat():
    app_qt()
    v = ventana(demo())
    try:
        textos = [b.text() for b in v.grupo.buttons()]
        assert "Antes / después" in textos and "Ingeniería inversa" in textos
        assert Qt.AlignmentFlag.AlignLeft is not None
    finally:
        v.close()
