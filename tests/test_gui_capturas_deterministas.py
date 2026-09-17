"""Tarea 5 del día 6: ¿son deterministas las capturas?

El día 5 hubo que revertir 16 capturas «que cambiaron por ruido de
renderizado» al regenerar `capturas/`. Antes de tocar nada del renderizado
(fuente, antialiasing, escala), este archivo comprueba EMPÍRICAMENTE si el
problema sigue ahí: genera la carpeta de capturas completa dos veces (en
directorios separados, sin tocar la carpeta real del repo) y compara los
bytes exactos, con hash SHA-256, no con "se parecen".

RESULTADO, día 6: no hay ruido de renderizado que fijar. Ejecutado dos veces
seguidas, con carga de CPU en paralelo (tres procesos `yes` a la vez) y con
DOS invocaciones de `generar()` corriendo genuinamente en paralelo entre sí
(compitiendo de verdad por CPU, el escenario más parecido a lo que pasó el
día 5 con un agente de fondo trabajando a la vez): en las tres pruebas, cero
bytes de diferencia en las ~30 imágenes. Ver `gui/NOTAS.md` para la
investigación completa y la hipótesis de qué causó el problema del día 5 (no
era el renderizado: era un bug de estado del conmutador de modo, ya
arreglado esa misma tarde).

Este test se queda para que sea una REGRESIÓN detectable, no una comprobación
puntual: si algún día algo introduce de verdad no-determinismo (una fuente
del sistema que cambie, una animación, un timestamp), este test lo pilla.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gui import ventana as ventana_mod

pytestmark = [pytest.mark.gui, pytest.mark.lento]


class _SettingsFalso:
    """Mismo patrón que `tests/test_gui_pantalla_facil.py::_SettingsFalso`:
    un `QSettings` real (incluso apuntando a un directorio temporal) no aísla
    el test en macOS, porque `cfprefsd` cachea el valor en memoria. Ver la
    nota de ese archivo para el porqué completo."""

    _ALMACEN: dict[tuple[str, str], dict[str, object]] = {}

    def __init__(self, organizacion: str, aplicacion: str) -> None:
        self._datos = self._ALMACEN.setdefault((organizacion, aplicacion), {})

    def value(self, clave, defecto=None, type=None):  # noqa: A002
        return self._datos.get(clave, defecto)

    def setValue(self, clave, valor) -> None:
        self._datos[clave] = valor


@pytest.fixture(autouse=True)
def _settings_aislados(monkeypatch):
    _SettingsFalso._ALMACEN.clear()
    monkeypatch.setattr(ventana_mod, "QSettings", _SettingsFalso)
    yield
    _SettingsFalso._ALMACEN.clear()


def _hashes(carpeta: Path) -> dict[str, str]:
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(carpeta.glob("*.png"))}


def test_dos_ejecuciones_seguidas_dan_bytes_identicos(tmp_path: Path):
    from gui.capturas import generar

    dest1, dest2 = tmp_path / "run1", tmp_path / "run2"
    generar(dest1)
    generar(dest2)

    h1, h2 = _hashes(dest1), _hashes(dest2)
    assert h1, "generar() no ha producido ninguna captura"
    assert h1.keys() == h2.keys(), "las dos ejecuciones no produjeron los mismos archivos"
    distintos = sorted(k for k in h1 if h1[k] != h2[k])
    assert not distintos, f"capturas no deterministas entre dos ejecuciones seguidas: {distintos}"
