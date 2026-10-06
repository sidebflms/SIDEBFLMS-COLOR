"""Suelo de tamaño de letra: ningún texto informativo por debajo de 12 px, y el
cuerpo (tablas y párrafos) a 14.

Auditoría de diseño del 2026-10-06 (veredicto «Mejorable»): 44 textos a 10 px y
44 a 11 px. Tres comprobaciones, cada una cubre un hueco de las otras:

* **estática** (AST): ningún `idn.fuente_*()`, `Rotulo()` ni `Cifra()` de `gui/`
  recibe un literal por debajo del suelo, salvo los dos glifos «!» de los
  rombos (no son texto informativo, y el rombo no se toca);
* **dinámica**: ningún `QLabel`/`QPushButton`/`QCheckBox` visible con texto, en
  las cinco pantallas, tiene una letra por debajo del suelo;
* **lo que no se ve en un widget**: la cabecera de las tablas (que la pinta la
  hoja de estilo) y la fuente base de la aplicación.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton

from gui import identidad as idn
from tests.test_gui_apoyo import app_qt, asentar, demo, ventana

GUI = Path(__file__).resolve().parents[1] / "gui"
FUNCIONES = {"fuente_texto", "fuente_cifra", "fuente_rotulo"}
CLASES = {"Rotulo", "Cifra"}
#: (fichero, tamaño): los glifos «!» de los dos rombos (`MarcaDesajuste` y el
#: delegado de aviso de la tabla). Son iconografía, no texto, y el rombo no se toca.
GLIFOS_PERMITIDOS = {("widgets.py", 10), ("pantalla_clips.py", 9)}


def _literales_pequenos(ruta: Path) -> list[tuple[int, int]]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    fuera: list[tuple[int, int]] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if nombre in FUNCIONES and nodo.args and isinstance(nodo.args[0], ast.Constant):
            px = nodo.args[0].value
        elif nombre in CLASES:
            px = next(
                (k.value.value for k in nodo.keywords if k.arg == "px" and isinstance(k.value, ast.Constant)),
                None,
            )
        else:
            continue
        if isinstance(px, int) and px < idn.PX_MIN_INFORMATIVO:
            fuera.append((nodo.lineno, px))
    return fuera


def test_el_suelo_y_el_cuerpo_son_los_de_la_auditoria():
    assert idn.PX_MIN_INFORMATIVO == 12
    assert idn.PX_CUERPO == 14


@pytest.mark.parametrize("fichero", sorted(p.name for p in GUI.glob("*.py")))
def test_ningun_literal_de_tamano_baja_del_suelo_en_gui(fichero):
    malos = [
        (linea, px)
        for linea, px in _literales_pequenos(GUI / fichero)
        if (fichero, px) not in GLIFOS_PERMITIDOS
    ]
    assert not malos, f"{fichero}: tamaños por debajo de {idn.PX_MIN_INFORMATIVO}px (línea, px): {malos}"


def test_el_detector_estatico_ve_un_literal_pequeno(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("import gui.identidad as idn\nidn.fuente_texto(11)\nRotulo('a', px=10)\nidn.fuente_texto(12)\n")
    assert _literales_pequenos(f) == [(2, 11), (3, 10)]


def test_ningun_texto_visible_baja_del_suelo_en_ninguna_pantalla():
    app_qt()
    v = ventana(demo())
    revisados = 0
    try:
        for indice in range(5):
            v.ir_a(indice)
            asentar()
            for clase in (QLabel, QPushButton, QCheckBox):
                for w in v.findChildren(clase):
                    if not w.isVisible() or not w.text().strip():
                        continue
                    px = w.font().pixelSize()
                    assert px >= idn.PX_MIN_INFORMATIVO, f"«{w.text()[:30]}» ({indice}): {px}px"
                    revisados += 1
    finally:
        v.close()
    assert revisados > 50, "el test se ha quedado ciego: casi no hay textos que revisar"


def test_la_cabecera_de_las_tablas_y_la_fuente_base_respetan_el_suelo():
    app_qt()
    assert idn.fuente_cabecera_tabla().pixelSize() == idn.PX_MIN_INFORMATIVO
    assert f"font-size: {idn.PX_MIN_INFORMATIVO}px" in idn.hoja_de_estilo()
    assert QApplication.instance().font().pixelSize() == idn.PX_CUERPO
