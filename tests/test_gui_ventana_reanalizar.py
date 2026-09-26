"""`VentanaPrincipal.btn_reanalizar` (día 9, continuación 13): el punto 3 de
la lista de Mario — hasta hoy, analizar el timeline actual sólo pasaba una
vez, al arrancar `lanzar.py`; no había forma de repetirlo con la app ya
abierta si Mario cambiaba de timeline o añadía clips.

Nada de ffmpeg real: mismo patrón que `test_gui_estado_real.py`
(`analizar_clip`/`extraer_fotogramas` sustituidos, deterministas por ruta).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from core.analysis import analizar_imagen  # noqa: E402
from core.contracts import ClipRef  # noqa: E402
from core.resolve import FakeResolve  # noqa: E402
from gui import datos_demo as dd  # noqa: E402
from gui.ventana import VentanaPrincipal, crear_app  # noqa: E402

pytestmark = pytest.mark.gui


def _imagen(semilla: int) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    return rng.random((8, 8, 3)).astype(np.float32)


def _puente_con_rutas(n: int, *, conectado: bool = True) -> FakeResolve:
    refs = [
        ClipRef(
            clip_id=f"clip{i:03d}", name=f"Clip {i}", track=1, index=i,
            start_frame=0, end_frame=99, file_path=f"/material/clip{i:03d}.mov",
        )
        for i in range(1, n + 1)
    ]
    return FakeResolve(clips=refs, nodos_por_clip=3, conectado=conectado)


class _SettingsFalso:
    """`QSettings` en memoria: `boton_modo_facil.setChecked(True)` escribe el
    modo en el `QSettings` REAL del usuario, y un test que lo deja en «fácil»
    rompe los demás tests de GUI y cambia el modo con el que Mario abre la
    app (pasó de verdad). Mismo doble que `test_gui_pantalla_facil.py`."""

    _ALMACEN: dict = {}

    def __init__(self, organizacion, aplicacion):
        self._datos = self._ALMACEN.setdefault((organizacion, aplicacion), {})

    def value(self, clave, defecto=None, type=None):  # noqa: A002
        return self._datos.get(clave, defecto)

    def setValue(self, clave, valor):
        self._datos[clave] = valor


@pytest.fixture(autouse=True)
def _settings_aislados(monkeypatch):
    import gui.ventana as ventana_mod

    _SettingsFalso._ALMACEN.clear()
    monkeypatch.setattr(ventana_mod, "QSettings", _SettingsFalso)
    yield
    _SettingsFalso._ALMACEN.clear()


@pytest.fixture(autouse=True)
def _dobles(monkeypatch):
    """Sustituye ffmpeg por análisis/lectura en memoria, determinista por ruta."""
    import core.analysis.lote as lote_mod
    import gui.estado_real as estado_real_mod

    def analizar_clip_falso(ruta, *, clip_id=None, **kwargs):
        semilla = abs(hash(ruta)) % (2**32)
        return analizar_imagen(_imagen(semilla), clip_id=clip_id)

    def extraer_fotogramas_falso(ruta, *, n_fotogramas=1, **kwargs):
        semilla = abs(hash(ruta)) % (2**32)
        return _imagen(semilla)[None, ...]

    monkeypatch.setattr(lote_mod, "analizar_clip", analizar_clip_falso)
    monkeypatch.setattr(estado_real_mod, "extraer_fotogramas", extraer_fotogramas_falso)


def _app():
    return crear_app([])


def test_boton_deshabilitado_si_resolve_esta_desconectado():
    _app()
    puente = _puente_con_rutas(2, conectado=False)
    estado = dd.EstadoDemo(clips=[], puente=puente)
    v = VentanaPrincipal(estado)
    try:
        assert not v.btn_reanalizar.isEnabled()
    finally:
        v.close()


def test_boton_habilitado_si_resolve_esta_conectado():
    _app()
    puente = _puente_con_rutas(2)
    estado = dd.EstadoDemo(clips=[], puente=puente)
    v = VentanaPrincipal(estado)
    try:
        assert v.btn_reanalizar.isEnabled()
    finally:
        v.close()


def test_reanalizar_sustituye_los_clips_y_conserva_el_mismo_estado():
    _app()
    puente = _puente_con_rutas(3)
    estado = dd.EstadoDemo(clips=[], puente=puente)  # arranca sin clips
    v = VentanaPrincipal(estado)
    try:
        v.btn_reanalizar.click()
        assert v._estado is estado  # mismo objeto, mutado en el sitio
        assert len(estado.clips) == 3
        assert {c.clip_id for c in estado.clips} == {"clip001", "clip002", "clip003"}
    finally:
        v.close()


def test_reanalizar_reconstruye_las_pantallas_con_los_clips_nuevos():
    _app()
    puente = _puente_con_rutas(2)
    estado = dd.EstadoDemo(clips=[], puente=puente)
    v = VentanaPrincipal(estado)
    try:
        p_clips_viejo = v.p_clips
        v.btn_reanalizar.click()
        assert v.p_clips is not p_clips_viejo  # pantalla reconstruida de verdad
        assert v.p_clips.modelo.rowCount() == 2
    finally:
        v.close()


def test_reanalizar_sin_clips_reales_avisa_y_no_rompe(monkeypatch):
    _app()
    puente = FakeResolve(
        clips=[ClipRef(clip_id="c1", name="c1", track=1, index=1, start_frame=0, end_frame=9)],
        nodos_por_clip=3,
    )  # sin file_path: nada que analizar
    estado = dd.EstadoDemo(clips=[], puente=puente)
    v = VentanaPrincipal(estado)
    try:
        import gui.ventana as ventana_mod

        avisos = []
        monkeypatch.setattr(ventana_mod.QMessageBox, "warning", lambda *a, **k: avisos.append(a))
        v.btn_reanalizar.click()
        assert avisos
        assert estado.clips == []  # no se ha tocado nada
    finally:
        v.close()


def test_reanalizar_conserva_el_modo_facil_si_estaba_activo():
    _app()
    puente = _puente_con_rutas(2)
    estado = dd.EstadoDemo(clips=[], puente=puente)
    v = VentanaPrincipal(estado)
    try:
        v.boton_modo_facil.setChecked(True)
        assert v.pila.currentWidget() is v.p_facil
        v.btn_reanalizar.click()
        assert v.pila.currentWidget() is v.p_facil  # sigue en modo facil, con la pantalla nueva
    finally:
        v.close()
