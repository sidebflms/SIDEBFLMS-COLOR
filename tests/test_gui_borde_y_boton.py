"""Borde fuerte a 3:1 y «Reanalizar timeline» a 32 px de alto (auditoría de
diseño del 2026-10-06, bloque 6).

* `BORDE_FUERTE_A` 0,22 -> 0,40: el borde de botones, campos y casillas daba
  1,84-1,93:1 sobre las superficies; WCAG 1.4.11 pide 3:1 a los componentes de
  interfaz. A 0,40 da 3,55-3,63:1. Se comprueba calculado y **medido**: el píxel
  del borde de un botón real contra el del fondo que tiene al lado.
* `btn_reanalizar` medía 29 px (la letra de 11 px manda en el `sizeHint`); ahora
  tiene un mínimo de 32.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton

from gui import identidad as idn
from gui.ventana import ALTO_MINIMO_BOTON
from tests.test_gui_apoyo import app_qt, asentar, demo, ventana

pytestmark = pytest.mark.gui

MINIMO_NO_TEXTO = 3.0


def _luminancia(c) -> float:
    def canal(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * canal(c[0]) + 0.7152 * canal(c[1]) + 0.0722 * canal(c[2])


def _contraste(a, b) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("superficie", idn.SUPERFICIES)
def test_el_borde_fuerte_pasa_3_a_1_sobre_cada_superficie(superficie):
    t, f = QColor(idn.BRAND_50), QColor(superficie)
    a = idn.BORDE_FUERTE_A
    borde = tuple(
        round(a * x + (1 - a) * y)
        for x, y in ((t.red(), f.red()), (t.green(), f.green()), (t.blue(), f.blue()))
    )
    razon = _contraste(borde, (f.red(), f.green(), f.blue()))
    assert razon >= MINIMO_NO_TEXTO, f"{superficie}: {razon:.2f}:1"


@pytest.mark.parametrize("superficie", idn.SUPERFICIES)
def test_el_borde_de_control_de_la_suite_pasa_3_a_1_sobre_cada_superficie(superficie):
    """El borde que de verdad pintan botones y campos (`BORDE_CONTROL_A`, smoke): la suite
    decia 55 % = 3,0:1 y el calculo da 2,2-2,6:1; se sube para conservar el 3:1 de la auditoria."""
    t, f = QColor(idn.SMOKE), QColor(superficie)
    a = idn.BORDE_CONTROL_A
    borde = tuple(
        round(a * x + (1 - a) * y)
        for x, y in ((t.red(), f.red()), (t.green(), f.green()), (t.blue(), f.blue()))
    )
    razon = _contraste(borde, (f.red(), f.green(), f.blue()))
    assert razon >= MINIMO_NO_TEXTO, f"{superficie}: {razon:.2f}:1"


def test_el_borde_de_un_boton_real_pasa_3_a_1_por_pixel():
    app_qt()
    v = ventana(demo())
    try:
        v.ir_a(2)
        asentar()
        boton = next(b for b in v.findChildren(QPushButton) if b.isVisible() and b.text() == "Todos")
        origen = boton.mapTo(v, QPoint(0, 0))
        imagen = v.grab(QRect(origen.x() - 4, origen.y(), 8, boton.height())).toImage()
        y = boton.height() // 2
        fondo = imagen.pixelColor(0, y).getRgb()[:3]
        borde = max(
            (imagen.pixelColor(x, y).getRgb()[:3] for x in range(8)),
            key=lambda c: _contraste(c, fondo),
        )
        assert _contraste(borde, fondo) >= MINIMO_NO_TEXTO, (borde, fondo)
    finally:
        v.close()


def test_reanalizar_timeline_mide_al_menos_32_px_de_alto():
    app_qt()
    v = ventana(demo())
    try:
        assert ALTO_MINIMO_BOTON == 32
        assert v.btn_reanalizar.isVisible()
        assert v.btn_reanalizar.height() >= 32
    finally:
        v.close()
