"""La GUI con Resolve abierto pero SIN proyecto (o con el proyecto cerrado a
mitad de sesión): `is_connected()` sigue diciendo `True` —Resolve contesta a
`GetProductName()`— pero `project_info()` lanza `ResolveNoConectado` ("no hay
ningún proyecto abierto"). Es lo que pasa cuando Mario vuelve al gestor de
proyectos de Resolve con la app ya conectada.

Hasta ahora tres sitios llamaban a `project_info()`/`list_nodes()` justo
después de comprobar `is_connected()`, sin capturar `ResolveError` (que es lo
único que la GUI sabe tratar): el pie de la ventana, la banda de Aplicar y el
paso "ordenar" del modo fácil. Una excepción en un slot de Qt no tumba el
proceso, pero deja la pantalla a medio pintar. Aquí se simula con
`FakeResolve.fallar_en("project_info")`, que lanza `ResolveError` sin tocar
`is_connected()` -- exactamente la combinación real.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from gui import datos_demo as dd  # noqa: E402
from gui.asistente_facil import ejecutar_ordenar  # noqa: E402
from gui.datos_demo import estado_demo  # noqa: E402
from gui.ventana import VentanaPrincipal, crear_app  # noqa: E402


@pytest.fixture(autouse=True)
def _settings_aislados(monkeypatch):
    """Mismo motivo que `test_gui_ventana_reanalizar.py`: que ningún test
    deje el modo "fácil" escrito en el `QSettings` real del usuario."""
    import gui.ventana as ventana_mod

    almacen: dict = {}

    class _SettingsFalso:
        def __init__(self, organizacion, aplicacion):
            self._datos = almacen.setdefault((organizacion, aplicacion), {})

        def value(self, clave, defecto=None, type=None):  # noqa: A002
            return self._datos.get(clave, defecto)

        def setValue(self, clave, valor):
            self._datos[clave] = valor

    monkeypatch.setattr(ventana_mod, "QSettings", _SettingsFalso)


def _estado_sin_proyecto() -> dd.EstadoDemo:
    estado = estado_demo()
    estado.puente.fallar_en("project_info", "no hay ningun proyecto abierto en Resolve")
    assert estado.puente.is_connected() is True  # la combinacion real
    return estado


@pytest.mark.gui
def test_el_pie_de_la_ventana_no_revienta_sin_proyecto_abierto():
    crear_app([])
    v = VentanaPrincipal(_estado_sin_proyecto())
    try:
        assert v.estado_resolve.text().endswith("resolve desconectado")
        assert "no hay conexión" in v.detalle_resolve.text()
    finally:
        v.close()


@pytest.mark.gui
def test_la_banda_de_aplicar_no_revienta_si_el_proyecto_se_cierra_tras_el_plan():
    """`refrescar_plan` calcula el plan (que ve a Resolve conectado) y LUEGO
    pinta la banda: si el proyecto se cierra entre medias, `project_info()`
    falla en la banda aunque el plan saliera bien."""
    crear_app([])
    estado = estado_demo()
    v = VentanaPrincipal(estado)
    try:
        estado.puente.fallar_en("project_info", "no hay ningun proyecto abierto en Resolve")
        v.p_aplicar.refrescar_plan()
        assert v.p_aplicar.rotulo_banda.text().endswith("resolve desconectado")
        assert "no hay ningun proyecto abierto" in v.p_aplicar.texto_banda.text()
    finally:
        v.close()


def test_ordenar_no_revienta_si_project_info_falla_con_resolve_conectado():
    estado = _estado_sin_proyecto()
    paso = ejecutar_ordenar(estado)
    # Sin el aviso del proyecto sigue habiendo diagnostico de los clips.
    assert paso.avisos == ()
    assert sum(len(g.clip_ids) for g in paso.grupos_pendientes) == len(estado.clips)


def test_ordenar_no_revienta_si_list_nodes_falla_con_resolve_conectado():
    estado = estado_demo()
    estado.puente.fallar_en("list_nodes", "Resolve ya no encuentra ese clip")
    paso = ejecutar_ordenar(estado)
    assert sum(len(g.clip_ids) for g in paso.grupos_pendientes) == len(estado.clips)
