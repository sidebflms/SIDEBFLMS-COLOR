"""`gui.__main__::_biblioteca_de_desarrollo`: el cableado de `core.looks` (día 9,
continuación 3) al arranque real de la app.

El punto entero de esta prueba: que el selector del paso 4 (look) del modo
fácil tenga presets DE VERDAD sin depender de `tests/luts_reales/` (material
privado de Mario, gitignored, ausente en un checkout limpio o en CI) — los
looks de `core.looks` no necesitan ningún fichero externo.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import gui.__main__ as main_mod  # noqa: E402
from core.looks import PRESETS  # noqa: E402


def _sin_externos(tmp_path, monkeypatch) -> None:
    """La mayoría de estos tests no quieren saber nada de `luts_externos/`
    (día 9, continuación 4) -- lo apartan a una carpeta vacía para no
    depender de lo que haya de verdad en el repo en cada momento."""
    monkeypatch.setattr(main_mod, "_CARPETA_LUTS_EXTERNOS", tmp_path / "no-hay-externos")


def test_biblioteca_no_depende_de_luts_reales(tmp_path, monkeypatch):
    """Sin `tests/luts_reales/` (carpeta inexistente), la biblioteca del
    modo fácil no debería quedar vacía: `core.looks` no necesita material
    externo."""
    monkeypatch.setattr(main_mod, "_CARPETA_LUTS_DESARROLLO", tmp_path / "no-existe")
    monkeypatch.setattr(main_mod, "_CARPETA_LOOKS_GENERADOS", tmp_path / "looks")
    _sin_externos(tmp_path, monkeypatch)

    biblioteca = main_mod._biblioteca_de_desarrollo()

    assert {p.nombre for p in biblioteca} == {parametros.nombre for parametros in PRESETS.values()}
    assert all(p.clasificacion == "look" for p in biblioteca)


def test_biblioteca_reales_van_antes_que_generados(tmp_path, monkeypatch):
    """Cuando SÍ hay material real de Mario, va primero (índice 0, el
    preset por defecto del selector) — los generados se añaden detrás, no
    desplazan el que ya se enseñaba antes de que existiera `core.looks`."""
    from core.io.cube import escribir_cube
    from core.looks.generador import ParametrosLook, generar_look

    carpeta_reales = tmp_path / "reales"
    carpeta_reales.mkdir()
    # Una rejilla identidad clasificaría como "conversion" (sin croma que
    # teñir el gris neutro) y el filtro de `_biblioteca_de_desarrollo` la
    # descartaría -- se necesita un tinte de verdad para que cuente como look.
    lut_real = generar_look(ParametrosLook(tinte_sombras=(0.05, 0.0, -0.05)), n=9)
    escribir_cube(lut_real, carpeta_reales / "Look de Mario.cube")

    monkeypatch.setattr(main_mod, "_CARPETA_LUTS_DESARROLLO", carpeta_reales)
    monkeypatch.setattr(main_mod, "_CARPETA_LOOKS_GENERADOS", tmp_path / "looks")
    _sin_externos(tmp_path, monkeypatch)

    biblioteca = main_mod._biblioteca_de_desarrollo()

    assert biblioteca[0].nombre == "Look de Mario"
    assert {p.nombre for p in biblioteca[1:]} == {parametros.nombre for parametros in PRESETS.values()}


def test_regenerar_es_idempotente(tmp_path, monkeypatch):
    """Arrancar la app dos veces seguidas (misma carpeta de generados) no
    debería fallar por reescribir ficheros que ya existen."""
    monkeypatch.setattr(main_mod, "_CARPETA_LUTS_DESARROLLO", tmp_path / "no-existe")
    monkeypatch.setattr(main_mod, "_CARPETA_LOOKS_GENERADOS", tmp_path / "looks")
    _sin_externos(tmp_path, monkeypatch)

    primera = main_mod._biblioteca_de_desarrollo()
    segunda = main_mod._biblioteca_de_desarrollo()

    assert {p.nombre for p in primera} == {p.nombre for p in segunda}


def test_biblioteca_incluye_los_externos_al_final(tmp_path, monkeypatch):
    """Día 9 (continuación 4): los packs de `luts_externos/` (descargados,
    metidos en el repo por decisión explícita de Mario) también entran en el
    selector — detrás de los reales y de los generados, en ese orden."""
    from core.io.cube import escribir_cube
    from core.looks.generador import ParametrosLook, generar_look

    carpeta_externos = tmp_path / "externos"
    carpeta_externos.mkdir()
    lut_externo = generar_look(ParametrosLook(tinte_luces=(0.03, 0.0, -0.02)), n=9)
    escribir_cube(lut_externo, carpeta_externos / "Pack Externo.cube")

    monkeypatch.setattr(main_mod, "_CARPETA_LUTS_DESARROLLO", tmp_path / "no-existe")
    monkeypatch.setattr(main_mod, "_CARPETA_LOOKS_GENERADOS", tmp_path / "looks")
    monkeypatch.setattr(main_mod, "_CARPETA_LUTS_EXTERNOS", carpeta_externos)

    biblioteca = main_mod._biblioteca_de_desarrollo()

    nombres_generados = {parametros.nombre for parametros in PRESETS.values()}
    assert biblioteca[-1].nombre == "Pack Externo"
    assert {p.nombre for p in biblioteca[:-1]} == nombres_generados
