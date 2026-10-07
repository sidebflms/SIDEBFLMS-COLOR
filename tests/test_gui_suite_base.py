"""SIDEBFLMS COLOR en la suite, tanda 1/3: tokens, tipografía, radios y cristal.

Decisión de Mario (2026-10-06): todas las apps parecen una suite, con los colores
de sidebflms.com y su modo cristal, manteniendo la personalidad de cada una.
Prototipo y medidas: `reviews/2026-10-06-suite-color/` del repo `sidebflms-design`.

Lo que se vigila aquí:

* **Akira NO está en el repo** (licencia comercial de SIDEBFLMS, repo público) y la
  app **no se rompe sin ella**: los títulos caen a Montserrat 800.
* **Montserrat SÍ va** (licencia OFL) y se carga una sola vez.
* El relleno del cristal **bajo texto es ≥ 54 %** (con el 20 % de la web el texto no
  llega a 4,5:1).
* Contraste de los textos ≥ 4,5:1 **medido por píxel** a 1017×742, 1280×800 y
  1440×900.
"""

from __future__ import annotations

import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase, QImage
from PySide6.QtWidgets import QLabel

from gui import cristal
from gui import identidad as idn
from tests.test_gui_apoyo import ANCHURA_MINIMA, app_qt, asentar, demo, redimensionar, ventana

pytestmark = pytest.mark.gui

RAIZ = Path(__file__).resolve().parent.parent
PESOS_MONTSERRAT = ("Regular", "Medium", "SemiBold", "Bold", "ExtraBold")


# ---------------------------------------------------------------------------
# Fuentes: Montserrat va, Akira no
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("peso", PESOS_MONTSERRAT)
def test_montserrat_va_en_el_repo(peso):
    assert (RAIZ / "gui" / "fuentes" / f"Montserrat-{peso}.ttf").is_file()


def test_la_licencia_ofl_de_montserrat_va_con_las_fuentes():
    texto = (RAIZ / "gui" / "fuentes" / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL Open Font License" in texto and "Montserrat" in texto


@pytest.mark.skipif(shutil.which("git") is None, reason="sin git no se puede mirar el repo")
def test_ningun_archivo_de_akira_esta_versionado_ni_puede_estarlo():
    """Repo PUBLICO + licencia comercial de la casa: el `.otf` no se sube NUNCA."""
    versionados = subprocess.run(
        ["git", "ls-files", "gui/fuentes"], cwd=RAIZ, capture_output=True, text=True, check=False
    )
    if versionados.returncode != 0:
        pytest.skip("esto no es un checkout de git")
    nombres = [n.lower() for n in versionados.stdout.splitlines()]
    assert nombres, "no hay nada que comprobar: gui/fuentes/ tiene al menos Montserrat versionada"
    assert not [n for n in nombres if n.endswith((".otf", ".woff", ".woff2")) or "akira" in n]
    # Y el nombre del archivo de la casa esta en .gitignore: Mario puede copiarlo y `git add .` no lo sube.
    for nombre in ("SIDEBFLMS TIPOGRAFIA (c SIDEBFLMS).otf", "AkiraExpanded.otf", "akira.ttf"):
        r = subprocess.run(
            ["git", "check-ignore", "-q", f"gui/fuentes/{nombre}"], cwd=RAIZ, check=False
        )
        assert r.returncode == 0, f"gui/fuentes/{nombre} NO esta en .gitignore"


def test_cargar_fuentes_registra_montserrat_y_es_idempotente():
    app_qt()
    primera = idn.cargar_fuentes()
    familias_antes = len(QFontDatabase.families())
    segunda = idn.cargar_fuentes()
    assert "Montserrat" in primera
    assert primera == segunda
    assert len(QFontDatabase.families()) == familias_antes


def test_cargar_fuentes_no_rompe_si_falta_la_carpeta(monkeypatch):
    app_qt()
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    assert idn.cargar_fuentes() == []


def test_sin_akira_el_titulo_sale_en_montserrat_800(monkeypatch):
    monkeypatch.setattr(idn, "familia_akira", lambda **_: "")
    f = idn.fuente_display(22)
    assert f.families() == ["Montserrat"]
    assert f.weight() == QFont.Weight.ExtraBold
    assert "font-family: \"Montserrat\"" in idn.regla_display_qss() and "800" in idn.regla_display_qss()


def test_con_akira_el_titulo_sale_en_akira_con_su_unico_peso(monkeypatch):
    monkeypatch.setattr(idn, "familia_akira", lambda **_: "Akira Expanded")
    f = idn.fuente_display(22)
    assert f.families() == ["Akira Expanded"]
    assert f.weight() == QFont.Weight.Normal  # no se le pide negrita a una fuente de un solo peso
    assert "Akira Expanded" in idn.regla_display_qss()


@pytest.mark.parametrize("px", [8, 12, 17])
def test_akira_nunca_baja_de_18_px(px):
    assert idn.fuente_display(px).pixelSize() == idn.PX_DISPLAY_MIN == 18


# ---------------------------------------------------------------------------
# Cristal: relleno bajo texto >= 54 %
# ---------------------------------------------------------------------------


def test_el_relleno_del_cristal_bajo_texto_es_al_menos_el_54_por_ciento():
    minimo = int(0.54 * 255)
    assert cristal.RELLENO[3] >= minimo
    assert cristal.RELLENO_FUERTE[3] >= cristal.RELLENO[3]
    # El 20 % de la web existe como constante para que se vea POR QUE no se usa.
    assert cristal.RELLENO_DECORATIVO[3] < minimo


def test_un_panel_pinta_su_cristal_con_el_relleno_de_texto():
    from gui.widgets import Panel

    app_qt()
    v = ventana(demo())
    try:
        paneles = v.findChildren(Panel)
        assert paneles, "no hay nada que comprobar: la ventana tiene paneles de cristal"
        assert all(not p._fuerte for p in paneles if p.objectName() == "panel")
    finally:
        v.close()


# ---------------------------------------------------------------------------
# Contraste por pixel >= 4,5:1 a los tres tamanos de la auditoria
# ---------------------------------------------------------------------------


def _luminancia(c) -> float:
    def canal(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * canal(c[0]) + 0.7152 * canal(c[1]) + 0.0722 * canal(c[2])


def _contraste(a, b) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("ancho,alto", [(ANCHURA_MINIMA, 742), (1280, 800), (1440, 900)])
def test_el_texto_de_la_suite_pasa_aa_por_pixel(ancho, alto):
    app_qt()
    v = ventana(demo(), ancho=ancho, alto=alto)
    medidos, peores = 0, []
    try:
        redimensionar(v, ancho, alto)
        for indice in range(5):
            v.ir_a(indice)
            asentar()
            captura = v.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
            etiquetas = v.findChildren(QLabel)
            assert etiquetas, f"no hay nada que comprobar: la pantalla {indice} tiene etiquetas"
            for lab in etiquetas:
                if not lab.isVisible() or not lab.text().strip() or not lab.pixmap().isNull():
                    continue
                # Solo la parte que se VE: un texto fuera del visor de un QScrollArea (o
                # tapado por otro widget) tiene `isVisible()` y no esta en la captura.
                visible = lab.visibleRegion().boundingRect()
                if visible.isEmpty():
                    continue
                origen = lab.mapTo(v, visible.topLeft())
                caja = QRect(origen, visible.size()).intersected(captura.rect())
                if caja.width() < 4 or caja.height() < 4:
                    continue
                trozo = captura.copy(caja)
                pix = [
                    trozo.pixelColor(x, y).getRgb()[:3]
                    for x in range(trozo.width())
                    for y in range(trozo.height())
                ]
                fondo = Counter(pix).most_common(1)[0][0]
                mejor = max(_contraste(p, fondo) for p in pix)
                medidos += 1
                if mejor < 4.5:
                    peores.append((round(mejor, 2), indice, lab.text()[:28]))
    finally:
        v.close()
    assert medidos > 80, f"el test se ha quedado ciego: solo {medidos} textos medidos"
    assert not peores, f"textos por debajo de 4,5:1 a {ancho}x{alto}: {sorted(peores)[:6]}"


# ---------------------------------------------------------------------------
# anchos_fijos(): lo que cuesta Montserrat en la tabla de clips
# ---------------------------------------------------------------------------


def test_anchos_fijos_de_la_tabla_de_clips_con_montserrat():
    """371 px con las fuentes de antes; 387 con Montserrat (+16)."""
    app_qt()
    v = ventana(demo())
    try:
        assert sum(v.p_clips.anchos_fijos().values()) == 387
    finally:
        v.close()
