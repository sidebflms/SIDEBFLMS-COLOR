"""Las fuentes que van en el repo (`gui/fuentes/`): Montserrat completa, con su licencia.

La primera versión de la suite llevaba un subconjunto latino de ~44 KB sin flechas ni
signos matemáticos, así que «←», «→», «≥», «≤» y sobre todo «Δ» (que aparece ~300 veces en
la interfaz) caían a la fuente del sistema. Ahora van las cinco instancias estáticas
(400-800) generadas del Montserrat 9.000 completo (1312 glifos).

**Σ (U+03A3, sigma griega mayúscula) NO existe en Montserrat** ni la interfaz la usa (solo
aparece en `core/reverse/NOTAS.md`, que no se dibuja). Se deja dicho aquí para que nadie la
añada a un texto de la GUI creyendo que sale en Montserrat.
"""

from __future__ import annotations

import glob
import os
import tokenize
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

pytestmark = pytest.mark.gui

CARPETA = Path(__file__).resolve().parent.parent / "gui" / "fuentes"
PESOS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800}
#: Lo que la interfaz dibuja de verdad y el subconjunto de 44 KB no tenia.
GLIFOS_QUE_USA_LA_GUI = "←→≥≤Δ≈√±°×·«»…"


def _fuentes() -> dict[str, Path]:
    return {peso: CARPETA / f"Montserrat-{peso}.ttf" for peso in PESOS}


def test_estan_los_cinco_pesos_y_no_son_el_subconjunto_de_44_kb():
    for peso, ruta in _fuentes().items():
        assert ruta.is_file(), f"falta {ruta.name}"
        assert ruta.stat().st_size > 250_000, f"{ruta.name} parece el subconjunto de 44 KB, no la fuente completa"
        assert TTFont(ruta)["OS/2"].usWeightClass == PESOS[peso]


@pytest.mark.parametrize("peso", list(PESOS))
def test_cada_peso_tiene_las_flechas_los_signos_y_la_delta(peso):
    cmap = TTFont(_fuentes()[peso]).getBestCmap()
    assert len(cmap) > 1000, "se esperaba la fuente completa (1312 glifos)"
    faltan = [c for c in GLIFOS_QUE_USA_LA_GUI if ord(c) not in cmap]
    assert not faltan, f"Montserrat-{peso} no trae {faltan}"


def test_las_cifras_tabulares_estan_en_la_fuente():
    fuente = TTFont(_fuentes()["Regular"])
    etiquetas = {fr.FeatureTag for fr in fuente["GSUB"].table.FeatureList.FeatureRecord}
    assert "tnum" in etiquetas, "sin la caracteristica tnum no hay cifras tabulares"


def test_sigma_griega_no_esta_en_montserrat_ni_la_usa_la_interfaz():
    """Hecho documentado: si esto cambia (Montserrat la añade), se puede quitar la nota."""
    assert ord("Σ") not in TTFont(_fuentes()["Regular"]).getBestCmap()
    usada = []
    for ruta in glob.glob(str(CARPETA.parent / "*.py")):
        with open(ruta, "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type == tokenize.STRING and "Σ" in tok.string:
                    usada.append(os.path.basename(ruta))
    assert not usada, f"la GUI dibuja una Σ que Montserrat no tiene: {usada}"


def test_todo_glifo_no_ascii_de_los_textos_de_la_gui_esta_en_montserrat():
    """Barrido mecanico de los literales de `gui/*.py`: ningun texto cae a otra fuente."""
    cmap = TTFont(_fuentes()["Regular"]).getBestCmap()
    sin_glifo: dict[str, set[str]] = {}
    for ruta in glob.glob(str(CARPETA.parent / "*.py")):
        with open(ruta, "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type in (tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", -1)):
                    for c in tok.string:
                        if ord(c) > 0x7F and ord(c) not in cmap:
                            sin_glifo.setdefault(c, set()).add(os.path.basename(ruta))
    assert not sin_glifo, f"glifos de la GUI que Montserrat no tiene: {sin_glifo}"


def test_la_licencia_ofl_corresponde_a_la_fuente_incluida():
    """El `OFL.txt` lleva el mismo copyright que la propia fuente (nombre ID 0)."""
    copyright_fuente = TTFont(_fuentes()["Regular"])["name"].getDebugName(0)
    texto = (CARPETA / "OFL.txt").read_text(encoding="utf-8")
    primera = texto.splitlines()[0].strip()
    assert primera == copyright_fuente, f"OFL.txt dice {primera!r} y la fuente {copyright_fuente!r}"
    assert "SIL OPEN FONT LICENSE Version 1.1" in texto
    assert "Copyright 2011 The Montserrat Project Authors" in primera
    assert "Akira" not in texto


def test_el_qt_resuelve_la_delta_y_las_flechas_en_montserrat():
    from PySide6.QtGui import QFontInfo, QFontMetrics

    from gui import identidad as idn
    from tests.test_gui_apoyo import app_qt

    app_qt()
    for fuente in (idn.fuente_cifra(14), idn.fuente_texto(14)):
        assert QFontInfo(fuente).family() == "Montserrat"
        m = QFontMetrics(fuente)
        for c in GLIFOS_QUE_USA_LA_GUI:
            assert m.inFontUcs4(ord(c)), f"Qt no encuentra {c!r} en Montserrat"
