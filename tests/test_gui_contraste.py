"""El texto secundario de la interfaz pasa WCAG AA (4,5:1) sobre las cuatro
superficies, calculado y medido en pantalla.

La auditoría de diseño del 2026-10-06 midió el texto tenue a **3,55-3,63:1**
(`TEXTO_TENUE_A = 0,40`) y lo subió a 0,56 (≥5,95:1). Dos comprobaciones, porque
una sola puede mentir:

* **calculada**: `brand-50` al alfa de cada token, compuesto sobre cada una de
  las cuatro superficies, contra esa superficie;
* **medida**: el mejor píxel de texto de cada `QLabel#tenue` de la ventana real
  (captura de la ventana, no del label: un label es transparente), contra el
  píxel de fondo más frecuente de su rectángulo.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QLabel

from gui import identidad as idn
from tests.test_gui_apoyo import app_qt, asentar, demo, ventana

pytestmark = pytest.mark.gui

AA = 4.5


def _luminancia(c: tuple[int, int, int]) -> float:
    def canal(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * canal(c[0]) + 0.7152 * canal(c[1]) + 0.0722 * canal(c[2])


def _contraste(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _componer(texto_hex: str, alfa: float, fondo_hex: str) -> tuple[int, int, int]:
    t, f = QColor(texto_hex), QColor(fondo_hex)
    return (
        round(alfa * t.red() + (1 - alfa) * f.red()),
        round(alfa * t.green() + (1 - alfa) * f.green()),
        round(alfa * t.blue() + (1 - alfa) * f.blue()),
    )


@pytest.mark.parametrize("nombre", ["TEXTO_TENUE_A", "TEXTO_APAGADO_A"])
@pytest.mark.parametrize("superficie", idn.SUPERFICIES)
def test_el_texto_secundario_pasa_aa_sobre_cada_superficie(nombre, superficie):
    alfa = getattr(idn, nombre)
    fondo = QColor(superficie)
    razon = _contraste(_componer(idn.BRAND_50, alfa, superficie), (fondo.red(), fondo.green(), fondo.blue()))
    assert razon >= AA, f"{nombre}={alfa} sobre {superficie}: {razon:.2f}:1 (< {AA}:1)"


def test_el_texto_tenue_de_la_ventana_real_pasa_aa_por_pixel():
    from collections import Counter

    app_qt()
    v = ventana(demo())
    medidos = 0
    try:
        for indice in range(5):
            v.ir_a(indice)
            asentar()
            for lab in v.findChildren(QLabel):
                if not lab.isVisible() or lab.objectName() != "tenue" or not lab.text().strip():
                    continue
                img = v.grab(QRect(lab.mapTo(v, QPoint(0, 0)), lab.size())).toImage()
                img = img.convertToFormat(QImage.Format.Format_RGB32)
                pix = [img.pixelColor(x, y).getRgb()[:3] for x in range(img.width()) for y in range(img.height())]
                fondo = Counter(pix).most_common(1)[0][0]
                mejor = max(_contraste(p, fondo) for p in pix)
                assert mejor >= AA, f"«{lab.text()[:30]}» ({indice}): {mejor:.2f}:1"
                medidos += 1
    finally:
        v.close()
    assert medidos >= 5, "el test se ha quedado ciego: casi no hay textos tenues que medir"
